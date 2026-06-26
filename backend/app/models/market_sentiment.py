"""
Asaas (اثاثہ) — Market Sentiment Snapshot Model (Stage 4: AGGREGATE)

Per-day rollup of news sentiment along three axes (sector / asset_class /
overall market), written by the aggregate_sentiment worker. The dashboard reads
a precomputed row in <10ms instead of recomputing over dozens of items per load.

Additive signal only — never read by the optimizer, weights, or money pipeline.
Pattern mirrors PortfolioSnapshot (immutable-ish daily rows, upserted per cycle).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MarketSentimentSnapshot(Base):
    __tablename__ = "market_sentiment_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date: Mapped["datetime.date"] = mapped_column(Date, nullable=False)  # type: ignore[name-defined]
    scope: Mapped[str] = mapped_column(Text, nullable=False)   # sector | asset_class | market
    label: Mapped[str] = mapped_column(Text, nullable=False)   # e.g. banking / crypto / PSX_overall
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)  # -1.0000 … 1.0000
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bullish_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bearish_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_market_sentiment_scope_label_date",
            "snapshot_date",
            "scope",
            "label",
            unique=True,
        ),
    )
