"""
Asaas (اثاثہ) — News Models

Schema: TECH.md §7.2 `news_items` + `news_holding_link` tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # psx / sbp / business_recorder / dawn
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )  # indexed: /news/feed filters >= cutoff and orders by this
    level: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # direct / sector / macro
    sentiment: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # positive / negative / neutral
    magnitude: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )  # 0–1 directional strength (lexicon); feeds materiality + aggregation
    sentiment_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # one-line reason (reserved for a future LLM tagging tier; NULL for lexicon)
    materiality_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )  # 0–1 = relevance × magnitude × directional factor
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # agent's short impact note
    raw: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # original scraped payload
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # --- Relationships ---
    instrument_links = relationship(
        "NewsHoldingLink", back_populates="news_item", lazy="selectin", cascade="all, delete-orphan"
    )
    flags = relationship("Flag", back_populates="news_item", lazy="noload")


class NewsHoldingLink(Base):
    """N:M link between news_items and instruments."""
    __tablename__ = "news_holding_link"

    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relevance: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )  # match strength

    # --- Relationships ---
    news_item = relationship("NewsItem", back_populates="instrument_links")
    instrument = relationship("Instrument", back_populates="news_links")
