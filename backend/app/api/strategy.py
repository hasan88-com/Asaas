"""
Asaas (اثاثہ) — Strategy API Router

No-code strategy builder: `kind="allocation"` thinly wraps the existing
suggest_portfolio tool (PortfolioOptimizer); `kind="screener"` filters
active instruments by simple field/operator/value conditions (AND logic).
No new quant logic — this just parameterizes engines that already exist.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.suggest_portfolio import suggest_portfolio
from app.core.db import get_db
from app.core.security import get_current_user
from app.data.cache import get_prices
from app.models.instrument import Instrument
from app.models.strategy import Strategy
from app.models.user import User
from app.schemas.strategy import StrategyCreate, StrategyResponse, StrategyRunResult

router = APIRouter(prefix="/strategies", tags=["strategies"])

_OPS = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gte": lambda a, b: a is not None and a >= b,
    "lte": lambda a, b: a is not None and a <= b,
    "gt": lambda a, b: a is not None and a > b,
    "lt": lambda a, b: a is not None and a < b,
}


async def _get_owned_strategy(strategy_id: uuid.UUID, user: User, db: AsyncSession) -> Strategy:
    res = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
    )
    strategy = res.scalar_one_or_none()
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Strategy not found.")
    return strategy


@router.post("", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: StrategyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Strategy:
    strategy = Strategy(
        user_id=user.id,
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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[Strategy]:
    res = await db.execute(
        select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.created_at.desc())
    )
    return res.scalars().all()


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    strategy = await _get_owned_strategy(strategy_id, user, db)
    await db.delete(strategy)
    await db.commit()


async def _run_screener(config: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
    conditions = config.get("conditions", [])
    res = await db.execute(select(Instrument).where(Instrument.is_active == True))
    instruments: List[Instrument] = res.scalars().all()

    price_by_symbol = {}
    if any(c.get("field") == "price" for c in conditions):
        price_by_symbol = await get_prices([i.symbol for i in instruments], db)

    matches = []
    for inst in instruments:
        ok = True
        for c in conditions:
            field, op, value = c.get("field"), c.get("op"), c.get("value")
            cmp_fn = _OPS.get(op)
            if cmp_fn is None:
                continue
            if field == "sector":
                actual = inst.sector
            elif field == "asset_class":
                actual = inst.asset_class
            elif field == "price":
                actual = price_by_symbol.get(inst.symbol.upper())
                value = float(value) if value is not None else None
                actual = float(actual) if actual is not None else None
            else:
                continue
            if not cmp_fn(actual, value):
                ok = False
                break
        if ok:
            matches.append({"symbol": inst.symbol, "name": inst.name, "sector": inst.sector, "asset_class": inst.asset_class})

    return {"matches": matches, "count": len(matches)}


@router.post("/{strategy_id}/run", response_model=StrategyRunResult)
async def run_strategy(
    strategy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    strategy = await _get_owned_strategy(strategy_id, user, db)

    if strategy.kind == "allocation":
        result = await suggest_portfolio(db, user.id, overrides=strategy.config)
        if "error" in result:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])
    elif strategy.kind == "screener":
        result = await _run_screener(strategy.config, db)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown strategy kind: {strategy.kind}")

    return {"kind": strategy.kind, "result": result}
