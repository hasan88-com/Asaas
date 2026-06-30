"""
Asaas (اثاثہ) — Strategies API Router

No-code strategies. Both kinds reuse existing engines — no new quant code:
  • allocation → app.agent.tools.suggest_portfolio (MPT optimizer, draft only)
  • screener   → filter active instruments by AND-ed conditions, prices via cache

Endpoints: create / list / delete / run. All scoped to the current user.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.models.instrument import Instrument
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.strategy import (
    ScreenerMatch,
    StrategyCreate,
    StrategyResponse,
    StrategyRunResult,
)

logger = logging.getLogger("asaas.api.strategy")

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: StrategyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Strategy:
    """Create a strategy (config shape validated per kind in the schema)."""
    strategy = Strategy(
        user_id=current_user.id,
        name=payload.name,
        kind=payload.kind,
        config=payload.config,
    )
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return strategy


@router.get("", response_model=List[StrategyResponse])
async def list_strategies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[Strategy]:
    """List the current user's strategies (newest first)."""
    res = await db.execute(
        select(Strategy)
        .where(Strategy.user_id == current_user.id)
        .order_by(Strategy.created_at.desc())
    )
    return list(res.scalars().all())


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete one of the current user's strategies."""
    strategy = await _load_owned_strategy(strategy_id, current_user, db)
    await db.delete(strategy)
    await db.commit()


@router.post("/{strategy_id}/run", response_model=StrategyRunResult)
async def run_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyRunResult:
    """Run a strategy on demand.

    allocation → produce a draft portfolio via the optimizer (no mutation beyond
    the existing draft semantics). screener → return matching instruments.
    """
    strategy = await _load_owned_strategy(strategy_id, current_user, db)

    if strategy.kind == "allocation":
        from app.agent.tools.suggest_portfolio import suggest_portfolio

        result = await suggest_portfolio(db, current_user.id, overrides=strategy.config)
        if result.get("error"):
            return StrategyRunResult(kind="allocation", error=result["error"])
        return StrategyRunResult(kind="allocation", allocation=result)

    # screener
    matches = await _run_screener(strategy.config, db)
    return StrategyRunResult(kind="screener", matches=matches, count=len(matches))


# --- helpers ---------------------------------------------------------------

async def _load_owned_strategy(
    strategy_id: UUID, current_user: User, db: AsyncSession
) -> Strategy:
    res = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id, Strategy.user_id == current_user.id
        )
    )
    strategy = res.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found."
        )
    return strategy


def _matches_condition(inst: Instrument, price, cond: dict) -> bool:
    """Evaluate one screener condition against an instrument (+ its price)."""
    field = cond.get("field")
    op = cond.get("op")
    value = cond.get("value")

    if field == "sector":
        actual = (inst.sector or "").lower()
    elif field == "asset_class":
        actual = (inst.asset_class or "").lower()
    elif field == "price":
        if price is None:
            return False
        try:
            target = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return False
        if op == "gt":
            return price > target
        if op == "gte":
            return price >= target
        if op == "lt":
            return price < target
        if op == "lte":
            return price <= target
        if op == "eq":
            return price == target
        if op == "neq":
            return price != target
        return False
    else:
        return False

    # string comparisons for sector / asset_class
    if op == "eq":
        return actual == str(value).lower()
    if op == "neq":
        return actual != str(value).lower()
    if op == "in":
        if isinstance(value, list):
            return actual in {str(x).lower() for x in value}
        return actual == str(value).lower()
    return False


async def _run_screener(config: dict, db: AsyncSession) -> List[ScreenerMatch]:
    """Filter active instruments by AND-ed conditions. Prices via the cache."""
    conditions = config.get("conditions") or []
    res = await db.execute(select(Instrument).where(Instrument.is_active == True))  # noqa: E712
    instruments = list(res.scalars().all())

    # Fetch prices only when a price condition exists (avoids needless network).
    needs_price = any(c.get("field") == "price" for c in conditions)
    prices: dict = {}
    if needs_price and instruments:
        from app.data.cache import get_prices

        try:
            prices = await get_prices([i.symbol for i in instruments], db)
        except Exception as exc:
            logger.warning("Screener price fetch failed: %s", exc)

    out: List[ScreenerMatch] = []
    for inst in instruments:
        px = prices.get((inst.symbol or "").upper())
        if all(_matches_condition(inst, px, c) for c in conditions):
            out.append(
                ScreenerMatch(
                    symbol=inst.symbol,
                    name=inst.name,
                    sector=inst.sector,
                    asset_class=inst.asset_class,
                    current_price=str(px) if px is not None else None,
                )
            )
    return out
