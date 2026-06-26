"""
Asaas (اثاثہ) — Price Model

Schema: TECH.md §7.2 `prices` table.
Single wide time-series table for all asset classes.
Money is NUMERIC, never float (RULES.md A2.6).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )  # close / current — stored as NUMERIC
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # --- Relationships ---
    instrument = relationship("Instrument", back_populates="prices")

    # --- Indexes ---
    __table_args__ = (
        Index(
            "uq_instrument_price_date",
            "instrument_id",
            "price_date",
            unique=True,
        ),
        Index(
            "ix_instrument_price_date_desc",
            "instrument_id",
            price_date.desc(),
        ),
    )
