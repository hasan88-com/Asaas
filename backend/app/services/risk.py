"""
Asaas (اثاثہ) — Portfolio Risk Analytics (Phase C)

Reads the backfilled `prices` table (DB-first) and computes VaR, CVaR, max
drawdown (+duration), rolling volatility/Sharpe, Sortino, and beta vs an
equal-weight PSX-stock **composite proxy** (Yahoo `^KSE` is delisted and PSX DPS
serves no index, so we proxy the market). SBP policy rate = risk-free.

Pure-numpy metric helpers are unit-testable; the DB orchestration builds a
date-aligned portfolio return series from held instruments. Every result carries
`value` / `as_of` / `source` / `stale` (the number+date rule). Read-only.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.price import Price
from app.services.optimizer import MAX_DAILY_RETURN

logger = logging.getLogger("asaas.services.risk")

_TRADING_DAYS = 252
_Z = {95: 1.645, 99: 2.326}        # standard-normal quantiles
_MIN_POINTS = 30                    # minimum aligned return observations


# ---------------------------------------------------------------------------
# Pure metric helpers (numpy) — fractions of value unless noted
# ---------------------------------------------------------------------------

def var_historical(returns: np.ndarray, c: int = 95) -> float:
    """Historical VaR as a positive loss fraction at confidence c."""
    return float(-np.percentile(returns, 100 - c))


def var_parametric(returns: np.ndarray, c: int = 95) -> float:
    """Gaussian VaR: z_c·σ − μ (positive loss fraction)."""
    return float(_Z[c] * returns.std(ddof=1) - returns.mean())


def cvar(returns: np.ndarray, c: int = 95) -> float:
    """Conditional VaR (expected shortfall): mean loss beyond historical VaR."""
    threshold = np.percentile(returns, 100 - c)
    tail = returns[returns <= threshold]
    return float(-tail.mean()) if tail.size else var_historical(returns, c)


def max_drawdown(returns: np.ndarray) -> Tuple[float, int]:
    """Max drawdown (negative fraction) + its longest peak-to-peak duration (days)."""
    equity = np.cumprod(1.0 + returns)
    running_max = np.maximum.accumulate(equity)
    dd = (equity - running_max) / running_max
    mdd = float(dd.min()) if dd.size else 0.0
    # Longest gap between successive equity peaks (drawdown duration).
    longest = cur = 0
    peak = -np.inf
    for v in equity:
        if v >= peak:
            peak = v
            cur = 0
        else:
            cur += 1
            longest = max(longest, cur)
    return mdd, int(longest)


def rolling_vol(returns: np.ndarray, window: int = 30) -> float:
    """Annualized volatility over the trailing window."""
    w = returns[-window:] if returns.size >= window else returns
    return float(w.std(ddof=1) * np.sqrt(_TRADING_DAYS))


def rolling_sharpe(returns: np.ndarray, rf_daily: float, window: int = 30) -> float:
    """Annualized Sharpe over the trailing window (r_f = SBP daily)."""
    w = returns[-window:] if returns.size >= window else returns
    sd = w.std(ddof=1)
    if sd == 0:
        return 0.0
    return float((w.mean() - rf_daily) / sd * np.sqrt(_TRADING_DAYS))


def sortino(returns: np.ndarray, rf_daily: float) -> float:
    """Annualized Sortino: excess return / downside deviation."""
    downside = returns[returns < 0]
    dd = downside.std(ddof=1) if downside.size > 1 else 0.0
    if dd == 0:
        return 0.0
    return float((returns.mean() - rf_daily) / dd * np.sqrt(_TRADING_DAYS))


def beta(asset_returns: np.ndarray, market_returns: np.ndarray) -> Optional[float]:
    """Beta = Cov(asset, market) / Var(market) over aligned returns."""
    n = min(len(asset_returns), len(market_returns))
    if n < _MIN_POINTS:
        return None
    a, m = asset_returns[-n:], market_returns[-n:]
    var_m = float(np.var(m, ddof=1))
    if var_m == 0:
        return None
    return float(np.cov(a, m, ddof=1)[0][1] / var_m)


# ---------------------------------------------------------------------------
# DB orchestration
# ---------------------------------------------------------------------------

async def _price_series(db: AsyncSession, instrument_ids: List[UUID]) -> Dict[UUID, Dict[date, float]]:
    """{instrument_id: {date: close}} from the prices table."""
    if not instrument_ids:
        return {}
    rows = await db.execute(
        select(Price.instrument_id, Price.price_date, Price.price)
        .where(Price.instrument_id.in_(instrument_ids))
        .order_by(Price.price_date.asc())
    )
    out: Dict[UUID, Dict[date, float]] = {}
    for iid, d, px in rows.all():
        out.setdefault(iid, {})[d] = float(px)
    return out


def _returns_on_common_dates(series: Dict[Any, Dict[date, float]]) -> Tuple[List[date], Dict[Any, np.ndarray]]:
    """Date-intersect the close series and return (dates, {key: daily returns})."""
    keys = [k for k, v in series.items() if len(v) >= _MIN_POINTS + 1]
    if not keys:
        return [], {}
    common = set.intersection(*(set(series[k]) for k in keys))
    dates = sorted(common)
    if len(dates) < _MIN_POINTS + 1:
        return [], {}
    rets: Dict[Any, np.ndarray] = {}
    for k in keys:
        px = np.array([series[k][d] for d in dates])
        rets[k] = np.diff(px) / px[:-1]
    # Drop corrupt time steps (non-finite or >100% daily move, e.g. a USD↔PKR
    # price splice) across ALL keys, keeping the per-asset arrays date-aligned.
    R = np.column_stack([rets[k] for k in keys])
    good = np.isfinite(R).all(axis=1) & (np.abs(R) <= MAX_DAILY_RETURN).all(axis=1)
    if not good.all():
        rets = {k: rets[k][good] for k in keys}
        ret_dates = [d for d, g in zip(dates[1:], good) if g]
        return ret_dates, rets
    return dates[1:], rets


async def _market_proxy_returns(db: AsyncSession) -> Tuple[Optional[np.ndarray], List[date]]:
    """Equal-weight PSX-stock composite as the market benchmark for beta."""
    insts = (await db.execute(
        select(Instrument).where(Instrument.asset_class == "psx_stock", Instrument.is_active == True)  # noqa: E712
    )).scalars().all()
    series = await _price_series(db, [i.id for i in insts])
    dates, rets = _returns_on_common_dates(series)
    if not rets:
        return None, []
    proxy = np.mean(np.column_stack(list(rets.values())), axis=1)  # equal-weight
    return proxy, dates


async def compute_asset_beta(db: AsyncSession, instrument_id: UUID) -> Optional[float]:
    """Beta of one instrument vs the equal-weight PSX-stock composite proxy
    (excluding the instrument itself), aligned on common dates. None if thin."""
    insts = (await db.execute(
        select(Instrument).where(Instrument.asset_class == "psx_stock", Instrument.is_active == True)  # noqa: E712
    )).scalars().all()
    proxy_ids = [i.id for i in insts if i.id != instrument_id]
    if len(proxy_ids) < 2:
        return None
    series = await _price_series(db, proxy_ids + [instrument_id])
    _dates, rets = _returns_on_common_dates(series)
    if instrument_id not in rets:
        return None
    proxy_cols = [rets[i] for i in proxy_ids if i in rets]
    if len(proxy_cols) < 2:
        return None
    proxy = np.mean(np.column_stack(proxy_cols), axis=1)
    return beta(rets[instrument_id], proxy)


async def compute_portfolio_risk(db: AsyncSession, portfolio_id: UUID, sbp_rate: Decimal) -> Dict[str, Any]:
    """Full risk snapshot for a portfolio. Returns metrics + as_of/source/stale.

    Builds a date-aligned portfolio daily return series from held instruments
    (weighted by current value), then computes the metric suite. Beta is vs the
    equal-weight PSX-stock composite proxy.
    """
    holdings = (await db.execute(
        select(Holding).where(Holding.portfolio_id == portfolio_id)
    )).scalars().all()
    held = [h for h in holdings if h.quantity]
    if not held:
        return {"insufficient_data": True, "reason": "No holdings with quantity."}

    inst_ids = [h.instrument_id for h in held]
    series = await _price_series(db, inst_ids)
    dates, rets = _returns_on_common_dates(series)
    if not rets:
        return {"insufficient_data": True,
                "reason": "Not enough overlapping price history yet — risk builds as data accumulates."}

    as_of = dates[-1]

    # Current-value weights over the instruments that have aligned history.
    weights: Dict[UUID, float] = {}
    total = 0.0
    for h in held:
        s = series.get(h.instrument_id)
        if h.instrument_id not in rets or not s:
            continue
        last_close = s[max(s)]
        val = float(h.quantity) * last_close
        weights[h.instrument_id] = val
        total += val
    if total <= 0:
        return {"insufficient_data": True, "reason": "Could not value holdings from price history."}
    for k in weights:
        weights[k] /= total

    # Weighted portfolio daily returns (constant-weight approximation).
    port = np.zeros(len(next(iter(rets.values()))))
    for iid, w in weights.items():
        port = port + w * rets[iid]

    rf_daily = float(sbp_rate) / _TRADING_DAYS
    mdd, dd_days = max_drawdown(port)
    proxy, _ = await _market_proxy_returns(db)
    port_beta = beta(port, proxy) if proxy is not None else None

    def _m(value: Any) -> Dict[str, Any]:
        return {"value": value, "as_of": str(as_of), "source": "prices_db", "stale": False}

    return {
        "insufficient_data": False,
        "observations": int(port.size),
        "as_of": str(as_of),
        "var_95": _m(round(var_historical(port, 95), 4)),
        "var_99": _m(round(var_historical(port, 99), 4)),
        "var_95_parametric": _m(round(var_parametric(port, 95), 4)),
        "cvar_95": _m(round(cvar(port, 95), 4)),
        "max_drawdown": _m(round(mdd, 4)),
        "max_drawdown_days": _m(dd_days),
        "rolling_vol_30": _m(round(rolling_vol(port, 30), 4)),
        "rolling_sharpe_30": _m(round(rolling_sharpe(port, rf_daily, 30), 4)),
        "sortino": _m(round(sortino(port, rf_daily), 4)),
        "beta_vs_kse_proxy": _m(round(port_beta, 4) if port_beta is not None else None),
    }
