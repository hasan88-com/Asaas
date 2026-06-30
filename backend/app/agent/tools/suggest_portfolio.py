"""
Tool: suggest_portfolio

Runs PyPortfolioOpt with the SBP risk-free rate and persists a DRAFT portfolio.
Status is always "draft" — user must explicitly confirm (RULES.md A1.1).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.price import Price
from app.models.risk_profile import RiskProfile
from app.services.optimizer import PortfolioOptimizer, is_valid_candidate

logger = logging.getLogger("asaas.agent.tools.suggest_portfolio")


# Absolute last-resort risk-free rate for the optimizer, used ONLY when there is
# no live rate, no cache, and no last-known-good value in Redis. Logged loudly —
# get_sbp_rate's last-known-good fallback handles the normal "scrape is down" case.
_RISK_FREE_PLACEHOLDER = Decimal("0.115")


async def _get_sbp_rate() -> Decimal:
    """Risk-free rate via app.core.market.get_sbp_rate (cache → live →
    last-known-good). Falls back to a loudly-logged placeholder only if that
    raises (no successful fetch ever on this deployment)."""
    try:
        from app.core.market import get_sbp_rate
        return await get_sbp_rate()
    except Exception:
        logger.error(
            "SBP rate UNAVAILABLE (no live, cache, or last-known-good) — optimizer "
            "using PLACEHOLDER %s; Sharpe/expected-return are unreliable.",
            _RISK_FREE_PLACEHOLDER,
        )
        return _RISK_FREE_PLACEHOLDER


async def suggest_portfolio(
    db: AsyncSession,
    user_id: UUID,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a diversified draft portfolio using MPT + SBP risk-free rate.

    overrides (optional): risk_tolerance, horizon, investor_mode, goal, constraints
    Returns abstracted allocation (no absolute PKR).
    Status is always "draft".
    """
    overrides = overrides or {}

    # 1. Load risk profile
    prof_res = await db.execute(
        select(RiskProfile).where(RiskProfile.user_id == user_id)
    )
    profile = prof_res.scalar_one_or_none()
    if not profile:
        return {"error": "No risk profile found. Please complete your investor profile first."}

    risk_tolerance = overrides.get("risk_tolerance", profile.risk_tolerance)
    constraints = overrides.get("constraints") or profile.constraints or {}
    method = overrides.get("method")  # optimizer method; None → profile default

    # 2. SBP policy rate (risk-free rate)
    risk_free_rate = await _get_sbp_rate()

    # 3. Load active instruments (respecting excluded sectors / asset classes)
    excluded_sectors = constraints.get("excluded_sectors", [])
    excluded_classes = constraints.get("excluded_asset_classes", [])
    inst_res = await db.execute(
        select(Instrument).where(Instrument.is_active == True)
    )
    all_instruments: List[Instrument] = inst_res.scalars().all()
    instruments = [
        i for i in all_instruments
        if (i.sector or "") not in excluded_sectors
        and i.asset_class not in excluded_classes
        and is_valid_candidate(i)
    ]

    if not instruments:
        return {"error": "No instruments available after applying sector constraints."}

    # 4. Fetch historical prices from DB (last 90 days per instrument)
    historical_prices: Dict[str, List[Decimal]] = {}
    asset_classes: Dict[str, str] = {}
    sectors: Dict[str, str] = {}

    for inst in instruments:
        prices_res = await db.execute(
            select(Price.price)
            .where(Price.instrument_id == inst.id)
            .order_by(Price.price_date.desc())
            .limit(90)
        )
        rows = prices_res.fetchall()
        if len(rows) >= 2:
            historical_prices[inst.symbol] = [Decimal(str(row[0])) for row in rows]
            asset_classes[inst.symbol] = inst.asset_class
            sectors[inst.symbol] = inst.sector or ""

    if not historical_prices:
        return {"error": "Insufficient price history. Run the daily data fetch first."}

    # 5. Run optimizer
    optimizer = PortfolioOptimizer(risk_free_rate=risk_free_rate)
    weights: Dict[str, Decimal] = optimizer.optimize(
        historical_prices=historical_prices,
        asset_classes=asset_classes,
        sectors=sectors,
        risk_tolerance=risk_tolerance,
        constraints=constraints,
        method=method,
    )

    if not weights or all(w == 0 for w in weights.values()):
        return {"error": "Optimizer returned empty allocation. Check instrument universe."}

    # 6. Compute expected return (weighted historical mean, annualised)
    total_return = Decimal("0")
    for sym, w in weights.items():
        prices_list = historical_prices.get(sym, [])
        if len(prices_list) >= 2 and prices_list[-1] > 0:
            period_return = (prices_list[0] - prices_list[-1]) / prices_list[-1]
            ann_factor = Decimal("365") / Decimal(len(prices_list))
            total_return += w * period_return * ann_factor

    # Simple Sharpe approximation (vol estimated at 15% for heuristic path)
    vol_estimate = Decimal("0.15")
    excess = total_return - risk_free_rate
    sharpe = excess / vol_estimate if vol_estimate > 0 else Decimal("0")

    # 7. Persist draft portfolio
    name = f"Suggested Portfolio {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    rationale = (
        f"Mean-variance optimised for {risk_tolerance} risk tolerance. "
        f"SBP risk-free rate: {risk_free_rate:.2%}. "
        f"Expected return: {total_return:.2%}. Sharpe: {sharpe:.2f}."
    )
    portfolio = Portfolio(
        user_id=user_id,
        name=name,
        status="draft",
        expected_return=total_return,
        expected_risk=vol_estimate,
        sharpe=sharpe,
        risk_free_rate=risk_free_rate,
        rationale=rationale,
    )
    db.add(portfolio)
    await db.flush()

    # 8. Persist holdings (target_weight only; quantity/entry not set at draft)
    sym_to_inst = {i.symbol: i for i in instruments}
    for sym, weight in weights.items():
        if weight <= 0:
            continue
        inst = sym_to_inst.get(sym)
        if not inst:
            continue
        holding = Holding(
            portfolio_id=portfolio.id,
            instrument_id=inst.id,
            target_weight=weight,
        )
        db.add(holding)

    await db.commit()
    await db.refresh(portfolio)

    # 9. Sector breakdown (abstracted — no absolute values)
    sector_breakdown: Dict[str, Decimal] = defaultdict(Decimal)
    for sym, w in weights.items():
        if w > 0:
            sector_breakdown[sectors.get(sym, "Unknown")] += w

    return {
        "portfolio_id": str(portfolio.id),
        "status": "draft",
        "target_weights": {s: str(w) for s, w in weights.items() if w > 0},
        "expected_return": str(total_return),
        "expected_risk": str(vol_estimate),
        "sharpe": str(sharpe),
        "risk_free_rate": str(risk_free_rate),
        "sector_breakdown": {k: str(v) for k, v in sector_breakdown.items()},
        "rationale": rationale,
    }
