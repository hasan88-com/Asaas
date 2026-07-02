"""
Asaas (اثاثہ) — Watchlist API Router

Per-user instrument watchlist across all asset classes (stocks / commodities /
debt / crypto). Rows are pure pointers to `instruments`; prices come from the
shared price cache at read time. Adding a symbol reuses resolve_instrument, so
any valid PSX ticker works even if it was never seeded.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.watchlist_item import WatchlistItem
from app.schemas.watchlist import (
    WatchlistAddRequest,
    WatchlistItemResponse,
    WatchlistResponse,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _to_response(item: WatchlistItem, price: Optional[object], inst=None) -> WatchlistItemResponse:
    # `inst` is passed explicitly on the POST path — a freshly inserted item's
    # selectin relationship isn't loaded, and lazy-loading it would raise in
    # async context.
    inst = inst if inst is not None else item.instrument
    return WatchlistItemResponse(
        id=item.id,
        symbol=inst.symbol,
        name=inst.name,
        asset_class=inst.asset_class,
        sector=inst.sector,
        currency=inst.currency,
        price=price,
        created_at=item.created_at,
    )


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.data.cache import get_prices

    res = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.created_at.desc())
    )
    items = res.scalars().all()

    price_by_symbol: dict = {}
    if items:
        try:
            price_by_symbol = await get_prices([i.instrument.symbol for i in items], db)
        except Exception:
            price_by_symbol = {}  # prices are decoration — never fail the list

    return {
        "items": [
            _to_response(i, price_by_symbol.get(i.instrument.symbol.upper()))
            for i in items
        ]
    }


@router.post("", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    payload: WatchlistAddRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.instrument_resolver import resolve_instrument

    symbol = payload.symbol.upper().strip()
    inst = await resolve_instrument(symbol, db, asset_class=payload.asset_class, name=payload.name)
    if not inst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument '{symbol}' not found.",
        )

    res = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.instrument_id == inst.id,
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        return _to_response(existing, None, inst=inst)

    item = WatchlistItem(user_id=user.id, instrument_id=inst.id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _to_response(item, None, inst=inst)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == user.id,
        )
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Watchlist item not found.")
    await db.delete(item)
    await db.commit()
