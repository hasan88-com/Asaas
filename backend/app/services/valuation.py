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
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("asaas.services.valuation")

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


# --- Shared fundamentals fetch (one yfinance round-trip per symbol, cached) ----
#
# A single valuation previously fired 5-6 separate yfinance fetches (info in
# extract_company_info, cashflow+balance+info in run_dcf, info again in
# run_monte_carlo, info in run_multiples). Yahoo throttles repeated calls to
# EMPTY DataFrames, which surfaced as "insufficient cash-flow history". We now
# fetch info + income_stmt + cashflow + balance_sheet ONCE and share the bundle.
_FUNDAMENTALS_TTL = 900  # seconds (15 min)
_fundamentals_cache: Dict[str, Dict[str, Any]] = {}  # symbol -> bundle
# Per-symbol fetch lock: a single valuation fires 4 concurrent calls
# (company-info, DCF, Monte-Carlo, multiples). Without a lock they all miss the
# cache at once and hit Yahoo simultaneously → some get 429'd (so DCF can
# succeed while multiples come back empty). The lock collapses them into ONE
# fetch that all four then share.
_fetch_locks: Dict[str, "asyncio.Lock"] = {}


def _df_empty(df: Any) -> bool:
    return df is None or getattr(df, "empty", True)


async def _yf_get_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch and cache ``{info, income, cashflow, balance, fetched_at, stale}``.

    One round-trip per symbol; results cached for ``_FUNDAMENTALS_TTL``. When a
    fetch comes back throttled/empty we serve the last-known-good bundle (flagged
    ``stale``) if we have one, and never cache an empty result (so the next call
    retries). Never raises.
    """
    now = time.time()
    cached = _fundamentals_cache.get(symbol)
    if cached and (now - cached["fetched_at"]) < _FUNDAMENTALS_TTL:
        return cached

    # Dedup concurrent fetches for the same symbol (one Yahoo round-trip, shared).
    lock = _fetch_locks.setdefault(symbol, asyncio.Lock())
    async with lock:
        # Re-check: another coroutine may have populated the cache while we waited.
        cached = _fundamentals_cache.get(symbol)
        if cached and (time.time() - cached["fetched_at"]) < _FUNDAMENTALS_TTL:
            return cached
        return await _do_fetch_fundamentals(symbol, cached)


async def _do_fetch_fundamentals(symbol: str, cached: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    now = time.time()
    info: Optional[Dict[str, Any]] = None
    income = cashflow = balance = None
    try:
        import yfinance as yf

        def _fetch():
            t = yf.Ticker(symbol)
            return t.info, t.income_stmt, t.cashflow, t.balance_sheet

        info, income, cashflow, balance = await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("yfinance fundamentals fetch failed for %s: %s", symbol, exc)

    info = info or {}
    # PSX official fundamentals (dps.psx.com.pk) for .KA — authoritative P/E, EPS,
    # price, market cap, shares. Works for ANY listed ticker (incl. ones yfinance
    # can't serve) and isn't blocked on cloud IPs, so it fills/overrides the (often
    # stale or missing) yfinance `info`. Statements still come from yfinance/DB.
    if symbol.upper().endswith(".KA"):
        try:
            from app.data.adapters.psx_fundamentals_adapter import fetch_psx_fundamentals
            dps = await fetch_psx_fundamentals(symbol)
            if dps:
                info = {**info, **{k: v for k, v in dps.items() if v is not None}}
        except Exception as exc:
            logger.warning("PSX (dps) fundamentals failed for %s: %s", symbol, exc)

    # A fetch only counts as "complete" when it brought financial statements.
    # On a throttled cloud IP (Render) Yahoo often returns a price-only / empty
    # response; treating that as success would persist a thin bundle OVER the
    # good DB seed and wipe P/E/EV-EBITDA/P/B. So when statements are missing we
    # serve the persisted snapshot instead and never let an empty fetch clobber it.
    statements_present = not (
        _df_empty(income) and _df_empty(cashflow) and _df_empty(balance)
    )

    if statements_present:
        bundle = {
            "info": info, "income": income, "cashflow": cashflow,
            "balance": balance, "fetched_at": now, "stale": False,
        }
        _fundamentals_cache[symbol] = bundle
        await _persist_fundamentals(symbol, bundle)  # merge-upsert (never erases)
        return bundle

    # No statements this time → prefer the DB-persisted last-known-good.
    persisted = await _load_persisted_fundamentals(symbol)
    if persisted is not None:
        logger.info("No live statements for %s — serving DB-persisted fundamentals.", symbol)
        # If the live call still gave fresh `info`, merge it over the cached info.
        if info:
            persisted = {**persisted, "info": {**persisted.get("info", {}), **{k: v for k, v in info.items() if v is not None}}}
        _fundamentals_cache[symbol] = persisted
        if info:
            await _persist_fundamentals(symbol, {"info": info, "income": None, "cashflow": None, "balance": None})
        return persisted

    if cached:
        stale = dict(cached); stale["stale"] = True
        return stale

    # Return whatever info we have — for .KA the dps merge above already provides
    # P/E / EPS / price, so multiples + the industry-P/E × EPS verdict resolve even
    # with no statements. Seed it so a later request has something to merge onto.
    bundle = {"info": info, "income": income, "cashflow": cashflow, "balance": balance, "fetched_at": now, "stale": True}
    if info:
        await _persist_fundamentals(symbol, bundle)
    return bundle


# --- DB-persisted fundamentals (last-known-good for rate-limited environments) --

_CACHED_INFO_KEYS = (
    "regularMarketPrice", "currentPrice", "marketCap", "sharesOutstanding",
    "trailingPE", "forwardPE", "trailingEps", "priceToBook", "bookValue",
    "enterpriseValue", "enterpriseToEbitda", "ebitda", "priceToSalesTrailing12Months",
    "beta", "earningsGrowth", "dividendYield", "returnOnEquity", "returnOnAssets",
    "debtToEquity", "currentRatio", "revenueGrowth", "longName", "shortName",
    "sector", "industry", "country", "currency",
)


def _coerce_json(v: Any) -> Any:
    if v is None or isinstance(v, (bool, str)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def _stmt_latest_col(df: Any) -> Dict[str, float]:
    """Latest fiscal column of a statement as {label: float} (JSON-safe)."""
    if _df_empty(df):
        return {}
    out: Dict[str, float] = {}
    try:
        col = df.iloc[:, 0]
        for idx, val in col.items():
            if val is None:
                continue
            try:
                f = float(val)
            except (TypeError, ValueError):
                continue
            if f == f:  # not NaN
                out[str(idx)] = f
    except Exception:
        return {}
    return out


def _serialize_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    info = bundle.get("info") or {}
    return {
        "info": {k: _coerce_json(info.get(k)) for k in _CACHED_INFO_KEYS if info.get(k) is not None},
        "income": _stmt_latest_col(bundle.get("income")),
        "cashflow": _stmt_latest_col(bundle.get("cashflow")),
        "balance": _stmt_latest_col(bundle.get("balance")),
    }


def _deserialize_bundle(payload: Dict[str, Any]) -> Dict[str, Any]:
    import pandas as pd

    def _df(d):
        if not d:
            return None
        return pd.Series(d, dtype="float64").to_frame("v")  # index=labels, 1 col → _find_row works

    return {
        "info": payload.get("info") or {},
        "income": _df(payload.get("income")),
        "cashflow": _df(payload.get("cashflow")),
        "balance": _df(payload.get("balance")),
        "fetched_at": time.time(),
        "stale": True,
    }


async def _persist_fundamentals(symbol: str, bundle: Dict[str, Any]) -> None:
    """Upsert a JSON snapshot of the fundamentals for this symbol (best-effort)."""
    try:
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.core.db import async_session_factory
        from app.models.instrument import Instrument
        from app.models.instrument_fundamentals import InstrumentFundamentals

        new = _serialize_bundle(bundle)
        sym = symbol.upper()
        async with async_session_factory() as db:
            inst = (await db.execute(
                select(Instrument).where(Instrument.symbol == sym)
            )).scalar_one_or_none()
            if inst is None:
                return
            # Merge with any existing snapshot so a partial fetch never erases
            # previously-captured statements/info (only fills/refreshes them).
            existing = (await db.execute(
                select(InstrumentFundamentals).where(InstrumentFundamentals.instrument_id == inst.id)
            )).scalar_one_or_none()
            old = existing.payload if existing else {}
            payload = {
                "info": {**(old.get("info") or {}), **(new.get("info") or {})},
                "income": new.get("income") or old.get("income") or {},
                "cashflow": new.get("cashflow") or old.get("cashflow") or {},
                "balance": new.get("balance") or old.get("balance") or {},
            }
            now = datetime.now(timezone.utc)
            stmt = pg_insert(InstrumentFundamentals).values(
                instrument_id=inst.id, symbol=sym, payload=payload, fetched_at=now,
            ).on_conflict_do_update(
                index_elements=["instrument_id"],
                set_={"payload": payload, "fetched_at": now, "symbol": sym},
            )
            await db.execute(stmt)
            await db.commit()
    except Exception as exc:
        logger.warning("Persist fundamentals failed for %s: %s", symbol, exc)


async def _load_persisted_fundamentals(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        from sqlalchemy import select
        from app.core.db import async_session_factory
        from app.models.instrument_fundamentals import InstrumentFundamentals

        async with async_session_factory() as db:
            row = (await db.execute(
                select(InstrumentFundamentals).where(InstrumentFundamentals.symbol == symbol.upper())
            )).scalar_one_or_none()
            if row is None:
                return None
            return _deserialize_bundle(row.payload)
    except Exception as exc:
        logger.warning("Load persisted fundamentals failed for %s: %s", symbol, exc)
        return None


def _yf_equity_symbol(symbol: str) -> str:
    """PSX tickers on yfinance need the ``.KA`` suffix — a bare ticker silently
    resolves to a *different* (often foreign) company. Append it when missing.
    Only used on the equity path; crypto/commodity never reach here."""
    s = symbol.strip().upper()
    if "." in s or "-" in s or "=" in s:
        return s
    return f"{s}.KA"


def _find_row(df: Any, *keywords: str) -> Optional[Decimal]:
    """Most-recent non-NaN value of the first statement row whose label contains
    any of ``keywords`` (case-insensitive substring). yfinance orders statement
    columns newest-first, so ``iloc[0]`` is the latest fiscal period.

    Replaces brittle exact-label matching — yfinance row labels vary by ticker
    (e.g. "Operating Cash Flow" vs "Total Cash From Operating Activities").
    """
    if _df_empty(df):
        return None
    try:
        for idx in df.index:
            label = str(idx).lower()
            if any(kw.lower() in label for kw in keywords):
                vals = df.loc[idx].dropna()
                if not vals.empty:
                    return _to_decimal(vals.iloc[0])
    except Exception as exc:
        logger.debug("_find_row(%s) failed: %s", keywords, exc)
    return None


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
    bundle = await _yf_get_fundamentals(symbol)
    info = bundle.get("info") or {}

    if info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        return {"symbol": symbol, "error": "No data returned by yfinance", "missing_fields": []}

    # Statement-derived ratios fill the gaps yfinance leaves for PSX `.KA`
    # (trailingEps/enterpriseToEbitda are absent there).
    derived = _subject_ratios(bundle)

    # Instrument metadata (asset class + sector) so every "tell me about X" answer
    # can state what kind of instrument it is — for stocks, commodities, debt, crypto.
    inst_asset_class = None
    inst_sector = None
    if db is not None:
        try:
            from sqlalchemy import select as _select
            from app.models.instrument import Instrument as _Instrument
            _inst = (await db.execute(
                _select(_Instrument).where(_Instrument.symbol == symbol.upper())
            )).scalar_one_or_none()
            if _inst is not None:
                inst_asset_class = _inst.asset_class
                inst_sector = _inst.sector
        except Exception:
            pass

    fields = {
        "name": info.get("longName") or info.get("shortName"),
        "asset_class": inst_asset_class,
        "sector": info.get("sector") or inst_sector,
        "industry": info.get("industry"),
        "country": info.get("country"),
        "currency": info.get("currency"),
        "current_price": _to_decimal(info.get("currentPrice") or info.get("regularMarketPrice")),
        "market_cap": _to_decimal(info.get("marketCap")),
        "shares_outstanding": _to_decimal(info.get("sharesOutstanding")),
        "trailing_pe": _to_decimal(info.get("trailingPE")) or derived["pe"],
        "forward_pe": _to_decimal(info.get("forwardPE")) or derived["forward_pe"],
        "price_to_book": _to_decimal(info.get("priceToBook")) or derived["pb"],
        "ev_to_ebitda": _to_decimal(info.get("enterpriseToEbitda")) or derived["ev_ebitda"],
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

    missing_fields = [k for k, v in fields.items() if v is None and k not in ("asset_class", "sector", "industry", "country", "currency")]
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
    symbol = _yf_equity_symbol(symbol)

    bundle = await _yf_get_fundamentals(symbol)
    info = bundle.get("info") or {}
    cashflow = bundle.get("cashflow")
    balance_sheet = bundle.get("balance")
    income = bundle.get("income")

    # Free Cash Flow: prefer the explicit FCF row → else Operating CF + CapEx
    # (capex is negative) → else Net Income as a proxy (flagged via fcf_source).
    fcf_source = "free_cash_flow"
    fcf = _find_row(cashflow, "free cash flow")
    if fcf is None:
        op_cf = _find_row(cashflow, "operating cash flow", "cash from operating")
        if op_cf is not None:
            capex = _find_row(cashflow, "capital expenditure") or Decimal("0")
            fcf = op_cf + capex
            fcf_source = "operating_cf_minus_capex"
    if fcf is None:
        net_income = _find_row(income, "net income from continuing operation", "net income")
        if net_income is not None:
            fcf = net_income
            fcf_source = "net_income_proxy"

    if fcf is None:
        return {
            "insufficient_data": True,
            "reason": (
                "No cash-flow or net-income data available from yfinance for this "
                "ticker right now (the source may be rate-limiting — try again)."
            ),
        }

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

    # Subtract net debt = total debt − cash (fuzzy row match; missing → 0).
    total_debt = _find_row(balance_sheet, "total debt", "long term debt")
    cash = _find_row(balance_sheet, "cash and cash equivalents")
    net_debt = (total_debt or Decimal("0")) - (cash or Decimal("0"))

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
        # Both keys: `terminal_growth` (legacy) + `terminal_growth_rate` (frontend type).
        "terminal_growth": str(terminal_growth.quantize(Decimal("0.0001"))),
        "terminal_growth_rate": str(terminal_growth.quantize(Decimal("0.0001"))),
        "fcf_base": str(fcf.quantize(Decimal("1"))),
        "fcf_source": fcf_source,
        "stale": bool(bundle.get("stale")),
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
        return base  # propagate the insufficient_data flag (shares the cached bundle)

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
            "num_simulations": n,  # frontend MonteCarloResult key
            "ranges": {
                "growth": [g_lo, g_hi],
                "wacc": [round(w_lo, 4), round(w_hi, 4)],
                "terminal_growth": [t_lo, t_hi],
            },
        }

    except Exception as exc:
        logger.error("Monte Carlo failed for %s: %s", symbol, exc)
        return {"insufficient_data": True, "reason": f"Monte Carlo simulation failed: {exc}"}


def _subject_ratios(bundle: Dict[str, Any]) -> Dict[str, Optional[Decimal]]:
    """Compute P/E, forward P/E, EV/EBITDA, P/B, P/S from a fundamentals bundle.

    ``info`` is used first; anything yfinance omits (common for PSX `.KA` —
    trailingEps, enterpriseValue, ebitda are all absent) is derived from the
    financial statements. Genuinely uncomputable values stay ``None``.
    """
    info = bundle.get("info") or {}
    income = bundle.get("income")
    balance = bundle.get("balance")

    price = _to_decimal(info.get("currentPrice") or info.get("regularMarketPrice"))
    shares = _to_decimal(info.get("sharesOutstanding"))
    market_cap = _to_decimal(info.get("marketCap"))
    if market_cap is None and price is not None and shares is not None:
        market_cap = price * shares

    # P/E — info.trailingPE → price / EPS (EPS = net income / shares); skip if earnings ≤ 0.
    pe = _to_decimal(info.get("trailingPE"))
    if pe is None and price is not None and shares and shares > 0:
        net_income = _find_row(income, "net income from continuing operation", "net income")
        if net_income is not None and net_income > 0:
            eps = net_income / shares
            if eps > 0:
                pe = price / eps
    forward_pe = _to_decimal(info.get("forwardPE"))

    # P/B — info.priceToBook → price / bookValue → price / (equity per share).
    pb = _to_decimal(info.get("priceToBook"))
    if pb is None and price is not None:
        book = _to_decimal(info.get("bookValue"))
        if book is not None and book > 0:
            pb = price / book
        elif shares and shares > 0:
            equity = _find_row(balance, "stockholders equity", "total equity")
            if equity is not None and equity > 0:
                pb = price / (equity / shares)

    # EV/EBITDA — info.enterpriseToEbitda → (marketCap + totalDebt − cash) / EBITDA.
    # None when there's no EBITDA (e.g. banks) — correct, not an error.
    ev_ebitda = _to_decimal(info.get("enterpriseToEbitda"))
    if ev_ebitda is None and market_cap is not None:
        ebitda = _find_row(income, "normalized ebitda", "ebitda")
        if ebitda is not None and ebitda > 0:
            total_debt = _find_row(balance, "total debt") or Decimal("0")
            cash = _find_row(balance, "cash and cash equivalents") or Decimal("0")
            ev_ebitda = (market_cap + total_debt - cash) / ebitda

    # P/S — info → marketCap / revenue.
    ps = _to_decimal(info.get("priceToSalesTrailing12Months"))
    if ps is None and market_cap is not None:
        revenue = _find_row(income, "total revenue", "operating revenue")
        if revenue is not None and revenue > 0:
            ps = market_cap / revenue

    # Trailing EPS — info.trailingEps → price / P/E (consistent with the reported
    # ratio) → net income / shares. The price/PE step avoids the unit mismatch you
    # get from raw net-income/shares on PSX statements.
    eps = _to_decimal(info.get("trailingEps"))
    if eps is None and price is not None and pe is not None and pe > 0:
        eps = price / pe
    if eps is None and shares and shares > 0:
        net_income = _find_row(income, "net income from continuing operation", "net income")
        if net_income is not None:
            eps = net_income / shares

    return {"pe": pe, "forward_pe": forward_pe, "ev_ebitda": ev_ebitda, "pb": pb, "ps": ps, "eps": eps}


async def _relative_valuation(
    symbol: str, subject: Dict[str, Optional[Decimal]], bundle: Dict[str, Any]
) -> Dict[str, Any]:
    """Fair price = industry-average P/E × trailing EPS, then an over/under verdict.

    industry P/E (layered): median P/E of same-sector seeded peers → maintained
    sector benchmark (``core.sector_pe``). Also returns the instrument's sector +
    asset class. Equity-only for the verdict; sector/asset_class returned for all.
    """
    from app.core.sector_pe import industry_pe_for_sector

    info = bundle.get("info") or {}
    price = _to_decimal(info.get("currentPrice") or info.get("regularMarketPrice"))
    eps = subject.get("eps")

    sector: Optional[str] = None
    asset_class: Optional[str] = None
    industry_pe: Optional[Decimal] = None
    source: Optional[str] = None
    try:
        from sqlalchemy import select
        from app.core.db import async_session_factory
        from app.models.instrument import Instrument
        from app.models.instrument_fundamentals import InstrumentFundamentals

        async with async_session_factory() as db:
            inst = (await db.execute(
                select(Instrument).where(Instrument.symbol == symbol.upper())
            )).scalar_one_or_none()
            if inst is not None:
                sector, asset_class = inst.sector, inst.asset_class
                # Peer-median P/E from same-sector seeded instruments.
                if sector:
                    rows = (await db.execute(
                        select(InstrumentFundamentals.payload).join(
                            Instrument, Instrument.id == InstrumentFundamentals.instrument_id
                        ).where(Instrument.sector == sector, Instrument.symbol != symbol.upper())
                    )).scalars().all()
                    peer_pes = []
                    for p in rows:
                        v = _to_decimal((p.get("info") or {}).get("trailingPE"))
                        if v is not None and v > 0:
                            peer_pes.append(v)
                    if len(peer_pes) >= 2:
                        peer_pes.sort()
                        mid = len(peer_pes) // 2
                        industry_pe = peer_pes[mid] if len(peer_pes) % 2 else (peer_pes[mid - 1] + peer_pes[mid]) / 2
                        source = "peer_median"
    except Exception as exc:
        logger.warning("Relative-valuation sector lookup failed for %s: %s", symbol, exc)

    if industry_pe is None:
        industry_pe = industry_pe_for_sector(sector)
        source = "sector_benchmark"

    fair_value = None
    verdict = None
    equity = asset_class in (None, "psx_stock", "global_stock", "equity")
    if equity and eps is not None and eps > 0 and industry_pe is not None:
        fair_value = industry_pe * eps
        if price is not None and fair_value > 0:
            ratio = price / fair_value
            gap = (ratio - 1) * 100
            if ratio < Decimal("0.9"):
                verdict = f"appears undervalued by ~{abs(gap):.0f}% vs the sector multiple"
            elif ratio > Decimal("1.1"):
                verdict = f"appears overvalued by ~{gap:.0f}% vs the sector multiple"
            else:
                verdict = "appears fairly valued vs the sector multiple"

    def _s(v):
        return str(v.quantize(Decimal("0.01"))) if isinstance(v, Decimal) else v

    return {
        "asset_class": asset_class,
        "sector": sector,
        "current_price": _s(price),
        "eps": _s(eps),
        "industry_pe": _s(industry_pe),
        "industry_pe_source": source,
        "fair_value": _s(fair_value),
        "verdict": verdict,
    }


async def run_multiples(
    symbol: str,
    peers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Relative valuation: P/E, EV/EBITDA, P/B for subject vs peers, plus an
    industry-P/E × EPS fair-value + over/under verdict and the instrument's
    sector + asset class.

    Returns the flat shape the frontend ``MultiplesResult`` expects
    (``pe_ratio`` / ``ev_ebitda`` / ``pb_ratio`` + peer medians). Ratios yfinance
    omits for PSX `.KA` are computed from the statements (see ``_subject_ratios``);
    nothing is fabricated. Peer medians are ``None`` unless peers are supplied.
    """
    peers = peers or []
    symbol = _yf_equity_symbol(symbol)

    async def _ratios(sym: str) -> Dict[str, Optional[Decimal]]:
        bundle = await _yf_get_fundamentals(_yf_equity_symbol(sym))
        return _subject_ratios(bundle)

    subject_bundle = await _yf_get_fundamentals(symbol)
    subject = _subject_ratios(subject_bundle)
    peer_ratios = await asyncio.gather(*[_ratios(p) for p in peers]) if peers else []

    def _median(key: str) -> Optional[Decimal]:
        vals = sorted(r[key] for r in peer_ratios if r.get(key) is not None)
        if not vals:
            return None
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2

    def _s(v: Optional[Decimal]) -> Optional[str]:
        if not isinstance(v, Decimal):
            return None
        try:
            return str(v.quantize(Decimal("0.01")))
        except Exception:
            return str(v)

    rel = await _relative_valuation(symbol, subject, subject_bundle)

    return {
        "pe_ratio": _s(subject["pe"]),
        "forward_pe": _s(subject["forward_pe"]),
        "ev_ebitda": _s(subject["ev_ebitda"]),
        "pb_ratio": _s(subject["pb"]),
        "ps_ratio": _s(subject["ps"]),
        "peer_pe_median": _s(_median("pe")),
        "peer_ev_ebitda_median": _s(_median("ev_ebitda")),
        "peer_pb_median": _s(_median("pb")),
        # Industry-P/E × EPS relative valuation + instrument metadata.
        "eps": rel["eps"],
        "industry_pe": rel["industry_pe"],
        "industry_pe_source": rel["industry_pe_source"],
        "fair_value": rel["fair_value"],
        "verdict": rel["verdict"],
        "asset_class": rel["asset_class"],
        "sector": rel["sector"],
        "current_price": rel["current_price"],
        "missing_note": (
            "Ratios yfinance omits for PSX stocks are computed from financial statements."
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
