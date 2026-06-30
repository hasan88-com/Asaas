"""
Asaas (اثاثہ) — Valuation Service

DCF, Monte Carlo, and multiples analysis using yfinance fundamentals.
PSX data via .KA tickers; WACC risk-free leg = SBP policy rate (AGENT_RULES.md §6b, §8.3b).
All functions are read-only — no DB writes.
Degrades gracefully when PSX fundamentals are thin or absent (never fabricates).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("asaas.services.valuation")

# In-process TTL cache for yfinance ticker data (info, cashflow, balance_sheet).
# Avoids repeated Yahoo Finance hits within a single deployment process.
# TTL = 1 hour; keyed by upper-case symbol.
_YF_CACHE: Dict[str, Any] = {}
_YF_CACHE_TTL = 3600.0


def _yf_cache_get(key: str) -> Optional[Any]:
    import time
    entry = _YF_CACHE.get(key)
    if entry and time.monotonic() - entry["ts"] < _YF_CACHE_TTL:
        return entry["data"]
    return None


def _yf_cache_set(key: str, data: Any) -> None:
    import time
    _YF_CACHE[key] = {"ts": time.monotonic(), "data": data}


async def _yf_get_info(symbol: str) -> Dict[str, Any]:
    """Fetch yfinance .info with in-process caching."""
    import yfinance as yf
    key = f"info:{symbol.upper()}"
    cached = _yf_cache_get(key)
    if cached is not None:
        return cached
    data = await asyncio.to_thread(lambda: yf.Ticker(symbol).info)
    _yf_cache_set(key, data)
    return data


async def _yf_get_fundamentals(symbol: str):
    """Fetch yfinance cashflow + balance_sheet + info with in-process caching."""
    import yfinance as yf
    key = f"fundamentals:{symbol.upper()}"
    cached = _yf_cache_get(key)
    if cached is not None:
        return cached

    def _fetch():
        t = yf.Ticker(symbol)
        # cashflow: annual; income_stmt: for net income fallback
        return t.cashflow, t.balance_sheet, t.info, t.income_stmt

    data = await asyncio.to_thread(_fetch)
    _yf_cache_set(key, data)
    return data

_EQUITY_RISK_PREMIUM = Decimal("0.1635")  # Pakistan total ERP — Damodaran (Caa2):
# 12.02% country risk premium + 4.33% mature-market premium. Among the world's
# highest, so WACC lands in the high-teens/low-20s% and DCF outputs are a
# conservative floor, very sensitive to inputs (field guide §1.A).
_DEFAULT_BETA = Decimal("1.0")
_TERMINAL_GROWTH = Decimal("0.03")  # 3% terminal growth default
_SHARES_FALLBACK = Decimal("1000000000")  # 1B shares if not available


# Absolute last-resort risk-free rate. Used ONLY when there is no live rate, no
# 1h cache, AND no last-known-good value in Redis (e.g. a cold start with an
# empty cache while the SBP site is unreachable). It is always surfaced via the
# `risk_free_is_placeholder` flag so a fabricated number is never trusted
# silently. NOT a routine fallback — get_sbp_rate's last-known-good handles that.
_RISK_FREE_PLACEHOLDER = Decimal("0.115")


async def _get_sbp_rate() -> tuple[Decimal, bool]:
    """Return ``(risk_free_rate, is_placeholder)``.

    Delegates to ``app.core.market.get_sbp_rate`` (cache → live → last-known-good).
    Only if that raises — meaning there has never been a successful fetch on this
    deployment — do we fall back to a clearly-flagged placeholder, logged loudly.
    """
    try:
        from app.core.market import get_sbp_rate
        return await get_sbp_rate(), False
    except Exception:
        logger.error(
            "SBP rate UNAVAILABLE (no live, no cache, no last-known-good) — using "
            "PLACEHOLDER %s. WACC/DCF outputs are UNRELIABLE and are flagged as such.",
            _RISK_FREE_PLACEHOLDER,
        )
        return _RISK_FREE_PLACEHOLDER, True


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Convert any numeric value to Decimal; returns None on failure."""
    if value is None:
        return None
    try:
        return Decimal(str(round(float(value), 6)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _safe_info(info: Dict[str, Any], key: str) -> Optional[Decimal]:
    return _to_decimal(info.get(key))


async def compute_beta(symbol: str, db=None) -> Optional[Decimal]:
    """Beta of a PSX stock vs the market, from DB price history when available.

    Yahoo's `^KSE` index is delisted and PSX serves no index feed, so the market
    is an equal-weight PSX-stock composite proxy (services/risk.compute_asset_beta)
    computed from the backfilled `prices` table. Falls back to a yfinance `^KSE`
    regression only when no DB session is provided. None when too thin / fails.
    """
    # DB-first: composite-proxy beta from backfilled history.
    if db is not None:
        try:
            from sqlalchemy import select
            from app.models.instrument import Instrument
            from app.services.risk import compute_asset_beta

            inst = (await db.execute(
                select(Instrument).where(Instrument.symbol == symbol.upper())
            )).scalar_one_or_none()
            if inst is not None:
                b = await compute_asset_beta(db, inst.id)
                if b is not None:
                    return _to_decimal(b)
        except Exception as exc:
            logger.warning("DB proxy beta failed for %s: %s", symbol, exc)

    # Legacy fallback: yfinance ^KSE regression (usually empty — index delisted).
    try:
        import yfinance as yf

        def _hist():
            return yf.download([symbol, "^KSE"], period="1y", progress=False, auto_adjust=True)["Close"]

        df = await asyncio.to_thread(_hist)
        if df is None or df.empty or symbol not in df.columns or "^KSE" not in df.columns:
            return None
        rets = df[[symbol, "^KSE"]].pct_change().dropna()
        if len(rets) < 30:
            return None
        cov = np.cov(rets[symbol].to_numpy(), rets["^KSE"].to_numpy())
        var_m = float(cov[1][1])
        if var_m == 0:
            return None
        return _to_decimal(float(cov[0][1]) / var_m)
    except Exception as exc:
        logger.warning("Beta regression failed for %s: %s", symbol, exc)
        return None


async def extract_company_info(symbol: str, db=None) -> Dict[str, Any]:
    """
    Fetch company profile, financial ratios, and metadata from yfinance.
    Returns a dict with a 'missing_fields' list for any absent data.
    Never raises — returns {'error': '...'} on total failure.
    """
    try:
        info = await _yf_get_info(symbol)
    except Exception as exc:
        logger.error("yfinance info fetch failed for %s: %s", symbol, exc)
        return {"symbol": symbol, "error": f"Could not fetch data: {exc}", "missing_fields": []}

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        return {"symbol": symbol, "error": "No data returned by yfinance", "missing_fields": []}

    fields = {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "currency": info.get("currency"),
        "current_price": _to_decimal(info.get("currentPrice") or info.get("regularMarketPrice")),
        "market_cap": _to_decimal(info.get("marketCap")),
        "shares_outstanding": _to_decimal(info.get("sharesOutstanding")),
        "trailing_pe": _to_decimal(info.get("trailingPE")),
        "forward_pe": _to_decimal(info.get("forwardPE")),
        "price_to_book": _to_decimal(info.get("priceToBook")),
        "ev_to_ebitda": _to_decimal(info.get("enterpriseToEbitda")),
        "beta": _to_decimal(info.get("beta")),
        "dividend_yield": _to_decimal(info.get("dividendYield")),
        "return_on_equity": _to_decimal(info.get("returnOnEquity")),
        "return_on_assets": _to_decimal(info.get("returnOnAssets")),
        "debt_to_equity": _to_decimal(info.get("debtToEquity")),
        "current_ratio": _to_decimal(info.get("currentRatio")),
        "revenue_growth": _to_decimal(info.get("revenueGrowth")),
        "earnings_growth": _to_decimal(info.get("earningsGrowth")),
    }

    # yfinance omits beta for PSX (.KA) tickers — compute it vs the PSX composite
    # proxy from DB history (db passed by the valuation API), else legacy fallback.
    if fields["beta"] is None and symbol.upper().endswith(".KA"):
        fields["beta"] = await compute_beta(symbol, db=db)

    missing_fields = [k for k, v in fields.items() if v is None and k not in ("sector", "industry", "country", "currency")]
    result = {"symbol": symbol, "missing_fields": missing_fields}
    # Convert Decimal values to str for JSON safety; leave None as None
    for k, v in fields.items():
        result[k] = str(v) if isinstance(v, Decimal) else v

    return result


async def run_dcf(
    symbol: str,
    assumptions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Discounted Cash Flow valuation.
    WACC risk-free leg = SBP policy rate (AGENT_RULES.md §6b).
    Returns {'insufficient_data': True, 'reason': '...'} if FCF data is absent.
    Never fabricates cash flows or growth rates.
    """
    assumptions = assumptions or {}

    try:
        cashflow, balance_sheet, info, income_stmt = await _yf_get_fundamentals(symbol)
    except Exception as exc:
        logger.error("yfinance fundamentals fetch failed for %s: %s", symbol, exc)
        return {"insufficient_data": True, "reason": f"Could not fetch fundamentals: {exc}"}

    # Extract Free Cash Flow = Operating CF - CapEx.
    # Use fuzzy keyword matching on the index so we're not sensitive to
    # exact yfinance label strings (which change across versions/markets).
    def _find_row(df, *keywords):
        """Return first row value whose index label contains ALL keywords (case-insensitive)."""
        if df is None or df.empty:
            return None
        for idx in df.index:
            low = str(idx).lower().replace("_", " ")
            if all(kw.lower() in low for kw in keywords):
                vals = df.loc[idx].dropna()
                if not vals.empty:
                    v = _to_decimal(vals.iloc[0])
                    if v is not None:
                        logger.debug("DCF %s: matched '%s' → %s", symbol, idx, v)
                        return v
        return None

    try:
        if cashflow is not None and not cashflow.empty:
            logger.info("DCF %s cashflow rows: %s", symbol, list(cashflow.index))
        if income_stmt is not None and not income_stmt.empty:
            logger.info("DCF %s income rows: %s", symbol, list(income_stmt.index))
        if balance_sheet is not None and not balance_sheet.empty:
            logger.info("DCF %s balance rows: %s", symbol, list(balance_sheet.index))

        op_cf = (
            _find_row(cashflow, "operating") or
            _find_row(cashflow, "operating", "cash")
        )
        capex = (
            _find_row(cashflow, "capital", "expenditure") or
            _find_row(cashflow, "capital", "expenditures") or
            _find_row(cashflow, "purchase", "property")
        )

        # Fallback: use free cash flow row if present
        if op_cf is None:
            op_cf = _find_row(cashflow, "free", "cash")

        # Fallback: net income from income_stmt as proxy FCF
        if op_cf is None and income_stmt is not None and not income_stmt.empty:
            op_cf = (
                _find_row(income_stmt, "net", "income") or
                _find_row(income_stmt, "net income")
            )
            if op_cf is not None:
                logger.info("DCF for %s: using net income as FCF proxy", symbol)

    except Exception as exc:
        logger.warning("Cash flow parsing error for %s: %s", symbol, exc)
        op_cf = None
        capex = None

    if op_cf is None:
        return {
            "insufficient_data": True,
            "reason": (
                "yfinance does not publish cash flow or income data for this ticker. "
                "PSX fundamentals are sometimes unavailable — try again later."
            ),
        }

    fcf = op_cf + (capex or Decimal("0"))  # capex is typically negative

    # Shares outstanding
    shares = _to_decimal(info.get("sharesOutstanding")) or _SHARES_FALLBACK

    # WACC: risk-free = SBP rate; beta from yfinance or default 1.0
    risk_free, rf_placeholder = await _get_sbp_rate()
    beta = _to_decimal(info.get("beta")) or _DEFAULT_BETA
    equity_premium = _EQUITY_RISK_PREMIUM
    wacc = risk_free + beta * equity_premium

    # Override from assumptions if provided
    growth_rate = _to_decimal(assumptions.get("growth_rate")) or (
        _to_decimal(info.get("earningsGrowth")) or Decimal("0.05")
    )
    terminal_growth = _to_decimal(assumptions.get("terminal_growth")) or _TERMINAL_GROWTH
    wacc = _to_decimal(assumptions.get("wacc")) or wacc

    # Clamp growth to sane range [-0.20, 0.30]
    growth_rate = max(Decimal("-0.20"), min(Decimal("0.30"), growth_rate))
    # Ensure WACC > terminal_growth to avoid division by zero
    if wacc <= terminal_growth:
        wacc = terminal_growth + Decimal("0.02")

    # Project 5-year FCF
    pv_total = Decimal("0")
    for t in range(1, 6):
        projected_fcf = fcf * ((1 + growth_rate) ** t)
        pv = projected_fcf / ((1 + wacc) ** t)
        pv_total += pv

    # Terminal value (Gordon Growth Model)
    terminal_fcf = fcf * ((1 + growth_rate) ** 5) * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1 + wacc) ** 5)

    enterprise_value = pv_total + pv_terminal

    # Subtract net debt if available
    net_debt = Decimal("0")
    try:
        if balance_sheet is not None and not balance_sheet.empty:
            total_debt = (
                _find_row(balance_sheet, "total", "debt") or
                _find_row(balance_sheet, "long", "term", "debt")
            )
            cash = (
                _find_row(balance_sheet, "cash", "equivalents") or
                _find_row(balance_sheet, "cash", "short", "term") or
                _find_row(balance_sheet, "cash")
            )
            if total_debt is not None and cash is not None:
                net_debt = total_debt - cash
    except Exception:
        pass

    equity_value = enterprise_value - net_debt
    intrinsic_value_per_share = equity_value / shares if shares > 0 else Decimal("0")

    return {
        "intrinsic_value_per_share": str(intrinsic_value_per_share.quantize(Decimal("0.01"))),
        "enterprise_value": str(enterprise_value.quantize(Decimal("1"))),
        "equity_value": str(equity_value.quantize(Decimal("1"))),
        "wacc": str(wacc.quantize(Decimal("0.0001"))),
        "risk_free_rate": str(risk_free.quantize(Decimal("0.0001"))),
        "risk_free_is_placeholder": rf_placeholder,
        "growth_rate": str(growth_rate.quantize(Decimal("0.0001"))),
        "terminal_growth": str(terminal_growth.quantize(Decimal("0.0001"))),
        "fcf_base": str(fcf.quantize(Decimal("1"))),
        "shares_outstanding": str(shares.quantize(Decimal("1"))),
        "assumptions": {
            "beta": str(beta),
            "equity_risk_premium": str(equity_premium),
            "projection_years": 5,
        },
    }


async def run_monte_carlo(
    symbol: str,
    ranges: Optional[Dict[str, Any]] = None,
    n: int = 1000,
) -> Dict[str, Any]:
    """
    Monte Carlo DCF: samples growth/WACC/terminal ranges n times.
    Returns p10/p50/p90 fair-value distribution (AGENT_RULES.md §8.3b).
    Returns {'insufficient_data': True} if base DCF cannot run.
    """
    ranges = ranges or {}

    # Get base DCF to check data availability and get FCF
    base = await run_dcf(symbol)
    if base.get("insufficient_data"):
        return base  # propagate the insufficient_data flag

    try:
        info = await _yf_get_info(symbol)
    except Exception:
        info = {}

    try:
        fcf = Decimal(base["fcf_base"])
        shares = Decimal(base["shares_outstanding"])
        risk_free = Decimal(base["risk_free_rate"])
        beta = Decimal(base["assumptions"]["beta"])
        equity_premium = _EQUITY_RISK_PREMIUM

        base_wacc = risk_free + beta * equity_premium

        # Sampling ranges
        g_lo = float(ranges.get("growth_lo", -0.05))
        g_hi = float(ranges.get("growth_hi", 0.15))
        w_lo = float(ranges.get("wacc_lo", float(base_wacc) - 0.03))
        w_hi = float(ranges.get("wacc_hi", float(base_wacc) + 0.05))
        t_lo = float(ranges.get("terminal_lo", 0.00))
        t_hi = float(ranges.get("terminal_hi", 0.05))

        rng = np.random.default_rng(seed=42)
        growths = rng.uniform(g_lo, g_hi, n)
        waccs = rng.uniform(max(w_lo, 0.01), max(w_hi, 0.02), n)
        terminals = rng.uniform(t_lo, t_hi, n)

        results = []
        for g, w, tg in zip(growths, waccs, terminals):
            g_d = Decimal(str(round(g, 6)))
            w_d = Decimal(str(round(w, 6)))
            tg_d = Decimal(str(round(tg, 6)))
            if w_d <= tg_d:
                w_d = tg_d + Decimal("0.02")
            pv = Decimal("0")
            for t in range(1, 6):
                pv += fcf * ((1 + g_d) ** t) / ((1 + w_d) ** t)
            tv_fcf = fcf * ((1 + g_d) ** 5) * (1 + tg_d)
            tv = tv_fcf / (w_d - tg_d)
            pv += tv / ((1 + w_d) ** 5)
            iv = pv / shares if shares > 0 else Decimal("0")
            results.append(float(iv))

        results_arr = np.array(results)
        p10 = Decimal(str(round(float(np.percentile(results_arr, 10)), 2)))
        p50 = Decimal(str(round(float(np.percentile(results_arr, 50)), 2)))
        p90 = Decimal(str(round(float(np.percentile(results_arr, 90)), 2)))
        mean = Decimal(str(round(float(np.mean(results_arr)), 2)))
        std = Decimal(str(round(float(np.std(results_arr)), 2)))

        return {
            "p10": str(p10),
            "p50": str(p50),
            "p90": str(p90),
            "mean": str(mean),
            "std": str(std),
            "n_simulations": n,
            "ranges": {
                "growth": [g_lo, g_hi],
                "wacc": [round(w_lo, 4), round(w_hi, 4)],
                "terminal_growth": [t_lo, t_hi],
            },
        }

    except Exception as exc:
        logger.error("Monte Carlo failed for %s: %s", symbol, exc)
        return {"insufficient_data": True, "reason": f"Monte Carlo simulation failed: {exc}"}


async def run_multiples(
    symbol: str,
    peers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Relative valuation: P/E, EV/EBITDA, P/B for subject vs peers.
    Missing ratios are set to None — never fabricated.
    """
    peers = peers or []

    async def _fetch_ratios(sym: str) -> Dict[str, Any]:
        try:
            info = await _yf_get_info(sym)
            pe = _to_decimal(info.get("trailingPE"))
            # Compute P/E from price / trailingEps when yfinance omits trailingPE
            if pe is None:
                price = _to_decimal(info.get("currentPrice") or info.get("regularMarketPrice"))
                eps = _to_decimal(info.get("trailingEps"))
                if price and eps and eps != 0:
                    pe = (price / eps).quantize(Decimal("0.01"))
            return {
                "symbol": sym,
                "pe": pe,
                "forward_pe": _to_decimal(info.get("forwardPE")),
                "ev_ebitda": _to_decimal(info.get("enterpriseToEbitda")),
                "pb": _to_decimal(info.get("priceToBook")),
                "ps": _to_decimal(info.get("priceToSalesTrailing12Months")),
            }
        except Exception as exc:
            logger.warning("Multiples fetch failed for %s: %s", sym, exc)
            return {"symbol": sym, "pe": None, "forward_pe": None, "ev_ebitda": None, "pb": None, "ps": None}

    subject_ratios = await _fetch_ratios(symbol)
    peer_results = await asyncio.gather(*[_fetch_ratios(p) for p in peers])

    def _fmt(d: Dict[str, Any]) -> Dict[str, Any]:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}

    return {
        "subject": _fmt(subject_ratios),
        "peers": [_fmt(p) for p in peer_results],
        "missing_note": (
            "Some ratios may be unavailable for PSX stocks via yfinance."
            if symbol.endswith(".KA") else None
        ),
    }


# --- Asset-class-specific valuation methods --------------------------------

# yfinance needs explicit quote tickers for crypto (e.g. BTC -> BTC-USD).
_CRYPTO_YF_TICKER = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
    "BNB": "BNB-USD", "XRP": "XRP-USD", "ADA": "ADA-USD", "DOGE": "DOGE-USD",
}


async def run_market_comparison(symbol: str) -> Dict[str, Any]:
    """
    Market-price comparison for crypto & commodity: current price relative to
    30/90-day moving averages and the 52-week range. Real values only — returns
    insufficient_data when price history is unavailable (never fabricates).
    """
    yf_symbol = _CRYPTO_YF_TICKER.get(symbol.upper(), symbol)
    try:
        import yfinance as yf

        def _hist():
            return yf.Ticker(yf_symbol).history(period="1y")

        df = await asyncio.to_thread(_hist)
    except Exception as exc:
        logger.warning("Market-comparison history fetch failed for %s: %s", symbol, exc)
        return {"method": "market_comparison", "insufficient_data": True,
                "reason": f"Could not load price history for {symbol}."}

    if df is None or df.empty or "Close" not in df:
        return {"method": "market_comparison", "insufficient_data": True,
                "reason": f"No price history available for {symbol}."}

    close = df["Close"].dropna()
    if len(close) < 30:
        return {"method": "market_comparison", "insufficient_data": True,
                "reason": "Fewer than 30 price bars available."}

    current = _to_decimal(close.iloc[-1])
    sma_30 = _to_decimal(close.tail(30).mean())
    sma_90 = _to_decimal(close.tail(90).mean()) if len(close) >= 90 else None
    high_52w = _to_decimal(close.max())
    low_52w = _to_decimal(close.min())

    # Position within the 52-week range (0% = low, 100% = high).
    range_pos: Optional[Decimal] = None
    if current is not None and high_52w is not None and low_52w is not None and high_52w > low_52w:
        range_pos = ((current - low_52w) / (high_52w - low_52w) * Decimal("100")).quantize(Decimal("0.1"))

    def _s(v: Optional[Decimal]) -> Optional[str]:
        return str(v) if isinstance(v, Decimal) else None

    return {
        "method": "market_comparison",
        "insufficient_data": False,
        "current_price": _s(current),
        "sma_30": _s(sma_30),
        "sma_90": _s(sma_90),
        "high_52w": _s(high_52w),
        "low_52w": _s(low_52w),
        "range_position_pct": _s(range_pos),
    }


# Approximate tenor length (calendar days) inferred from the friendly symbol.
_TENOR_DAYS = {
    "MTB-1M": 30, "MTB-3M": 91, "MTB-6M": 182, "MTB-12M": 364,
    "PIB-2Y": 730, "PIB-3Y": 1095, "PIB-5Y": 1825, "PIB-7Y": 2555,
    "PIB-10Y": 3650, "PIB-20Y": 7300, "GIS-3Y": 1095,
}


def _q2(v: Decimal) -> str:
    return str(v.quantize(Decimal("0.01")))


def _compute_duration(
    coupon_pct: Decimal,
    ytm_pct: Decimal,
    years: Decimal,
    face: Decimal,
    freq: int = 2,
) -> Optional[Dict[str, Any]]:
    """Interest-rate-risk metrics for a coupon bond / PIB.

    Macaulay & modified duration, DV01, and convexity, computed by discounting
    the contractual cash-flow schedule at the YTM. Assumes ``freq`` coupons/year
    (Pakistani PIBs/TFCs/Sukuk are typically semi-annual) and prices off ``face``
    (par-equivalent when YTM == coupon). For a zero-coupon instrument
    (``coupon_pct <= 0``) Macaulay duration == years to maturity.

    Returns None when inputs are unusable. Durations are in years; DV01 and
    price are Decimal rupees per the codebase's no-float-money rule.
    """
    if face is None or face <= 0 or years is None or years <= 0:
        return None

    y_ann = ytm_pct / Decimal("100")
    if y_ann <= Decimal("-1"):
        return None

    if coupon_pct is None or coupon_pct <= 0 or freq <= 0:
        # Zero-coupon (T-bill): single cash flow at maturity → Macaulay = years.
        # Fractional exponent needs float; convert back to Decimal immediately.
        price = face / Decimal(str((1.0 + float(y_ann)) ** float(years)))
        mac_years = years
        mod_years = mac_years / (Decimal("1") + y_ann)
        convexity = (years * (years + Decimal("1"))) / ((Decimal("1") + y_ann) ** 2)
    else:
        n = max(1, int(years * Decimal(freq) + Decimal("0.5")))  # whole coupon periods
        c = face * (coupon_pct / Decimal("100")) / Decimal(freq)  # periodic coupon
        y = y_ann / Decimal(freq)                                 # periodic yield
        one_plus_y = Decimal("1") + y

        price = Decimal("0")
        mac_period_sum = Decimal("0")   # Σ t · PV  (t in periods)
        conv_sum = Decimal("0")         # Σ t(t+1) · PV
        for t in range(1, n + 1):
            cf = c + (face if t == n else Decimal("0"))
            pv = cf / (one_plus_y ** t)
            price += pv
            mac_period_sum += Decimal(t) * pv
            conv_sum += Decimal(t) * Decimal(t + 1) * pv

        if price <= 0:
            return None
        mac_years = (mac_period_sum / price) / Decimal(freq)
        mod_years = mac_years / one_plus_y
        convexity = (conv_sum / (price * (one_plus_y ** 2))) / (Decimal(freq) ** 2)

    dv01 = mod_years * price * Decimal("0.0001")
    price_change_100bps = mod_years * price * Decimal("0.01")  # |Δprice| for a ±100bps move

    return {
        "macaulay_years": _q2(mac_years),
        "modified_years": _q2(mod_years),
        "dv01": _q2(dv01),
        "convexity": _q2(convexity),
        "price": _q2(price),
        "price_change_per_100bps": _q2(price_change_100bps),
        "frequency": freq,
    }


def _years_to_maturity(maturity_date: Optional[str], symbol: str) -> Optional[Decimal]:
    """Years to maturity from the PSX maturity-date string, falling back to the
    friendly-tenor calendar length (e.g. MTB-3M → 91 days)."""
    yrs: Optional[Decimal] = None
    if maturity_date:
        try:
            from dateutil import parser as _dateparser
            mat = _dateparser.parse(str(maturity_date)).date()
            yrs = Decimal(max((mat - date.today()).days, 0)) / Decimal("365")
        except Exception:
            yrs = None
    if yrs is None or yrs <= 0:
        td = _TENOR_DAYS.get(symbol.strip().upper())
        if td is not None:
            yrs = Decimal(td) / Decimal("365")
    return yrs


async def run_fixed_income_valuation(
    symbol: str,
    face_value: Optional[Decimal] = None,
    coupon_rate: Optional[Decimal] = None,
    buy_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Yield-to-maturity valuation for T-bills / bonds.

    Resolution priority for the instrument terms: explicit caller params →
    live PSX Debt Market data (``PSXDebtAdapter.get_instrument``) → SBP-benchmark
    fallback. ``coupon_rate`` is a percentage (e.g. 22.4); SBP rate is returned
    by ``get_sbp_rate()`` as a fraction. Never fabricates: when no real coupon
    is available the result carries ``insufficient_data: True``.
    """
    sbp_rate, rf_placeholder = await _get_sbp_rate()   # fraction, e.g. Decimal("0.115")
    sbp_pct = sbp_rate * Decimal("100")

    # --- Pull live PSX terms (best-effort) ---
    psx_coupon_pct: Optional[Decimal] = None
    psx_face: Optional[Decimal] = None
    maturity_date: Optional[str] = None
    source = "User input"
    try:
        from app.data.adapters.psx_debt_adapter import PSXDebtAdapter
        inst = await PSXDebtAdapter().get_instrument(symbol)
        if inst:
            if inst.get("coupon_rate") is not None:
                psx_coupon_pct = _to_decimal(inst["coupon_rate"])
                if psx_coupon_pct is not None:
                    psx_coupon_pct *= Decimal("100")  # adapter stores a fraction
            psx_face = _to_decimal(inst.get("face_value"))
            maturity_date = inst.get("maturity_date") or None
    except Exception as exc:
        logger.warning("PSX debt lookup failed for %s: %s", symbol, exc)

    # --- Resolve effective inputs ---
    coupon_pct = coupon_rate if coupon_rate is not None else psx_coupon_pct
    face = face_value if face_value is not None else psx_face
    if coupon_rate is None and psx_coupon_pct is not None:
        source = "PSX Debt Market"

    # No usable coupon anywhere → honest benchmark fallback. T-bills are
    # zero-coupon, so PSX reports a 0 coupon; without the rate the user locked in
    # at purchase we cannot compute a real YTM and must not fabricate one.
    if coupon_pct is None or coupon_pct <= 0:
        # Zero-coupon T-bill: no precise YTM without the user's purchase yield,
        # but interest-rate risk still applies — Macaulay duration ≈ time to
        # maturity, discounted at the SBP benchmark. Show it so the holding
        # isn't left without any risk metric.
        _yrs = _years_to_maturity(maturity_date, symbol)
        _duration = (
            _compute_duration(Decimal("0"), sbp_pct, _yrs,
                              face if face is not None else Decimal("100"))
            if _yrs else None
        )
        return {
            "method": "yield_to_maturity",
            "insufficient_data": True,
            "sbp_rate": _q2(sbp_pct),
            "benchmark_yield": _q2(sbp_pct),
            "risk_free_is_placeholder": rf_placeholder,
            "maturity_date": maturity_date,
            "duration": _duration,
            "reason": (
                "No coupon/yield available for this instrument from your holding "
                "or PSX (T-bills are zero-coupon). Showing the SBP policy rate as "
                "a benchmark reference — enter your purchase yield for a precise YTM. "
                "Duration below is discounted at the SBP rate."
            ),
        }

    ytm = coupon_pct
    spread_bps = int((ytm - sbp_pct) * Decimal("100"))
    verdict = "above_market" if ytm > sbp_pct else "below_market" if ytm < sbp_pct else "at_market"

    tenor_days = _TENOR_DAYS.get(symbol.strip().upper())

    accrued_value: Optional[str] = None
    remaining_return: Optional[str] = None
    days_held: Optional[int] = None
    days_remaining: Optional[int] = None

    if buy_date is not None:
        days_held = max((date.today() - buy_date).days, 0)
        if face is not None:
            accrued_value = _q2(face * (Decimal("1") + (coupon_pct / Decimal("100")) * Decimal(days_held) / Decimal("365")))
        if tenor_days is not None:
            days_remaining = max(tenor_days - days_held, 0)
            if face is not None:
                remaining_return = _q2(face * (coupon_pct / Decimal("100")) * Decimal(days_remaining) / Decimal("365"))

    # Interest-rate-risk metrics (duration / DV01 / convexity).
    years_to_maturity = _years_to_maturity(maturity_date, symbol)
    duration = (
        _compute_duration(coupon_pct, ytm, years_to_maturity, face)
        if (face is not None and years_to_maturity is not None)
        else None
    )

    return {
        "method": "yield_to_maturity",
        "insufficient_data": False,
        "source": source,
        "symbol": symbol,
        "face_value": _q2(face) if face is not None else None,
        "accrued_value": accrued_value,
        "remaining_return": remaining_return,
        "ytm": _q2(ytm),
        "sbp_rate": _q2(sbp_pct),
        "spread_bps": spread_bps,
        "days_held": days_held,
        "days_remaining": days_remaining,
        "maturity_date": maturity_date,
        "verdict": verdict,
        "duration": duration,
        "risk_free_is_placeholder": rf_placeholder,
    }
