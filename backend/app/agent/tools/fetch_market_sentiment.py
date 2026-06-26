"""
Tool: fetch_market_sentiment (read-only)

Reads the latest market_sentiment_snapshot rows scoped to the user's held
sectors / asset classes, plus the overall PSX market. No writes. Sentiment is
additive signal — this never reaches the optimizer or money pipeline.
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.market_sentiment import MarketSentimentSnapshot


async def fetch_market_sentiment(db: AsyncSession, portfolio_id: UUID) -> Dict[str, Any]:
    """Latest sentiment for the portfolio's sectors/asset-classes + overall market."""
    latest_date = await db.scalar(select(func.max(MarketSentimentSnapshot.snapshot_date)))
    if latest_date is None:
        return {"as_of": None, "market": None, "sectors": [], "asset_classes": []}

    # Held sectors + asset classes.
    held = await db.execute(
        select(Instrument.sector, Instrument.asset_class)
        .join(Holding, Holding.instrument_id == Instrument.id)
        .where(Holding.portfolio_id == portfolio_id)
    )
    sectors, classes = set(), set()
    for sector, asset_class in held.all():
        if sector:
            sectors.add(sector)
        if asset_class:
            classes.add(asset_class)

    rows = (await db.execute(
        select(MarketSentimentSnapshot).where(MarketSentimentSnapshot.snapshot_date == latest_date)
    )).scalars().all()

    def _row(r: MarketSentimentSnapshot) -> Dict[str, Any]:
        return {
            "label": r.label, "score": float(r.score), "item_count": r.item_count,
            "bullish_count": r.bullish_count, "bearish_count": r.bearish_count,
        }

    return {
        "as_of": str(latest_date),
        "market": next((_row(r) for r in rows if r.scope == "market"), None),
        "sectors": [_row(r) for r in rows if r.scope == "sector" and r.label in sectors],
        "asset_classes": [_row(r) for r in rows if r.scope == "asset_class" and r.label in classes],
    }
