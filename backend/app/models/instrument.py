"""
Asaas (اثاثہ) — Instrument Model

Schema: TECH.md §7.2 `instruments` table.
The asset universe: PSX stocks, global stocks, crypto, T-bills, commodities, mutual funds.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    symbol: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, index=True
    )  # e.g. HBL.KA, BTC, GC=F, TBILL-3M
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_class: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # psx_stock / global_stock / crypto / tbill / commodity / mutual_fund
    sector: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # for diversification limits (PSX sectors)
    currency: Mapped[str] = mapped_column(
        Text, default="PKR", server_default="PKR"
    )
    data_source: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # yfinance / coingecko / sbp / fred
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )  # coupon, exchange, etc.

    # Debt-instrument lifecycle columns. First-class so the optimizer / daily
    # jobs can filter matured instruments without parsing JSONB. Stocks/crypto
    # leave these NULL (never mature). face_value is in RUPEES (PSX reports in
    # thousands; the debt adapter normalizes on scrape).
    maturity_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, index=True
    )
    face_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    # --- Relationships ---
    prices = relationship("Price", back_populates="instrument", lazy="noload")
    holdings = relationship("Holding", back_populates="instrument", lazy="noload")
    news_links = relationship(
        "NewsHoldingLink", back_populates="instrument", lazy="noload"
    )
