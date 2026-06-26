"""
Tool: fetch_relevant_news

Reads news items matched to portfolio holdings via NewsHoldingLink.
Returns abstracted news list sorted by materiality_score. No writes.
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.news import NewsHoldingLink, NewsItem


async def fetch_relevant_news(
    db: AsyncSession,
    portfolio_id: UUID,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Fetch news items relevant to the holdings in a given portfolio.
    Joins news_holding_link → news_items, ordered by materiality_score DESC.
    """
    # 1. Get instrument IDs held in this portfolio
    holdings_res = await db.execute(
        select(Holding.instrument_id).where(Holding.portfolio_id == portfolio_id)
    )
    instrument_ids = [row[0] for row in holdings_res.fetchall()]

    if not instrument_ids:
        return []

    # 2. Join NewsHoldingLink → NewsItem + Instrument for symbol
    rows = await db.execute(
        select(NewsItem, NewsHoldingLink.relevance, Instrument.symbol)
        .join(NewsHoldingLink, NewsItem.id == NewsHoldingLink.news_id)
        .join(Instrument, NewsHoldingLink.instrument_id == Instrument.id)
        .where(NewsHoldingLink.instrument_id.in_(instrument_ids))
        .order_by(
            NewsItem.materiality_score.desc().nullslast(),
            NewsItem.published_at.desc().nullslast(),
        )
        .limit(limit)
    )

    results: List[Dict[str, Any]] = []
    for news_item, relevance, symbol in rows.all():
        results.append({
            "news_id": str(news_item.id),
            "headline": news_item.headline,
            "source": news_item.source,
            "level": news_item.level,
            "sentiment": news_item.sentiment,
            "materiality_score": (
                str(news_item.materiality_score) if news_item.materiality_score else None
            ),
            "matched_symbol": symbol,
            "relevance": str(relevance) if relevance else None,
            "published_at": (
                news_item.published_at.isoformat() if news_item.published_at else None
            ),
            "url": news_item.url,
        })

    return results
