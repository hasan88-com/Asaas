"""
Asaas (اثاثہ) — Market Sentiment Aggregator (Stage 4: AGGREGATE)

Rolls the per-item sentiment signals (Stage 2) up into market sentiment along
three axes — overall market, per sector, per asset class — with exponential
time-decay weighting (recent items count more). Writes one snapshot row per
scope/label per day into market_sentiment_snapshot.

Pure signal aggregation (weighted averages of existing tags). Never reads or
writes the optimizer, weights, prices, or the Decimal money pipeline.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import async_session_factory
from app.models.instrument import Instrument
from app.models.market_sentiment import MarketSentimentSnapshot
from app.models.news import NewsHoldingLink, NewsItem

logger = logging.getLogger("asaas.workers.aggregate_sentiment")

_WINDOW_DAYS = 7      # how far back items are considered
_DECAY_TAU = 3.0      # exponential decay constant (days); ~7d item weighs ~0.1
_DIRECTION = {"positive": 1, "negative": -1, "neutral": 0}


class _Bucket:
    """Running weighted aggregate for one scope/label."""
    __slots__ = ("num", "den", "count", "bull", "bear")

    def __init__(self):
        self.num = 0.0   # Σ signed_magnitude · weight
        self.den = 0.0   # Σ weight
        self.count = 0
        self.bull = 0
        self.bear = 0

    def add(self, sentiment: str, magnitude: float, weight: float) -> None:
        direction = _DIRECTION.get(sentiment or "neutral", 0)
        self.num += direction * magnitude * weight
        self.den += weight
        self.count += 1
        if direction > 0:
            self.bull += 1
        elif direction < 0:
            self.bear += 1

    def score(self) -> float:
        return (self.num / self.den) if self.den > 0 else 0.0


def _weight(published_at: datetime, now: datetime) -> float:
    age_days = max((now - published_at).total_seconds() / 86400.0, 0.0)
    return math.exp(-age_days / _DECAY_TAU)


async def run_aggregate_sentiment() -> None:
    """Recompute today's market/sector/asset-class sentiment snapshots."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=_WINDOW_DAYS)
    today = date.today()

    market = _Bucket()
    sectors: Dict[str, _Bucket] = {}
    classes: Dict[str, _Bucket] = {}

    async with async_session_factory() as session:
        # MARKET scope: every recent item (incl. unlinked macro news).
        rows = await session.execute(
            select(NewsItem.sentiment, NewsItem.magnitude, NewsItem.published_at)
            .where(NewsItem.published_at >= cutoff)
        )
        for sentiment, magnitude, published_at in rows.all():
            if published_at is None:
                continue
            market.add(sentiment, float(magnitude or 0), _weight(published_at, now))

        # SECTOR / ASSET_CLASS scopes: items linked to a held/known instrument.
        linked = await session.execute(
            select(
                NewsItem.sentiment, NewsItem.magnitude, NewsItem.published_at,
                Instrument.sector, Instrument.asset_class,
            )
            .join(NewsHoldingLink, NewsHoldingLink.news_id == NewsItem.id)
            .join(Instrument, NewsHoldingLink.instrument_id == Instrument.id)
            .where(NewsItem.published_at >= cutoff)
        )
        for sentiment, magnitude, published_at, sector, asset_class in linked.all():
            if published_at is None:
                continue
            w = _weight(published_at, now)
            mag = float(magnitude or 0)
            if sector:
                sectors.setdefault(sector, _Bucket()).add(sentiment, mag, w)
            if asset_class:
                classes.setdefault(asset_class, _Bucket()).add(sentiment, mag, w)

        # Upsert one row per scope/label for today.
        def _rows():
            yield ("market", "PSX_overall", market)
            for label, b in sectors.items():
                yield ("sector", label, b)
            for label, b in classes.items():
                yield ("asset_class", label, b)

        n = 0
        for scope, label, b in _rows():
            if b.count == 0:
                continue
            score = Decimal(str(round(b.score(), 4)))
            stmt = pg_insert(MarketSentimentSnapshot).values(
                snapshot_date=today, scope=scope, label=label,
                score=score, item_count=b.count, bullish_count=b.bull, bearish_count=b.bear,
            ).on_conflict_do_update(
                index_elements=["snapshot_date", "scope", "label"],
                set_={
                    "score": score, "item_count": b.count,
                    "bullish_count": b.bull, "bearish_count": b.bear,
                },
            )
            await session.execute(stmt)
            n += 1

        await session.commit()

    logger.info("Sentiment aggregation complete — %d snapshot rows for %s", n, today)
