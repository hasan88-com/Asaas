"""
Asaas (اثاثہ) — Holding Model

Schema: TECH.md §7.2 `holdings` table.
Positions within a portfolio.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_weight: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )  # optimizer's suggested weight (0.0–1.0)
    actual_weight: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )  # confirmed weight (may differ)
    quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )  # units held
    entry_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )  # cost basis
    entry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )

    # --- Relationships ---
    portfolio = relationship("Portfolio", back_populates="holdings")
    # Eager-loaded so PortfolioResponse serialization can read symbol/name/
    # asset_class below without triggering an async lazy-load.
    instrument = relationship("Instrument", back_populates="holdings", lazy="selectin")

    # --- Instrument passthroughs (populate HoldingResponse for confirmed
    # portfolios, which serialize the ORM directly rather than being built
    # manually like the suggest/guest paths). ---
    # Read only the *already-loaded* instrument (via __dict__) so serialization
    # never triggers a sync lazy-load in an async context (MissingGreenlet) for
    # freshly-created holdings whose relationship isn't loaded yet. When loaded
    # (e.g. selectin on a query), the real value is returned.
    @property
    def symbol(self) -> str | None:
        inst = self.__dict__.get("instrument")
        return inst.symbol if inst is not None else None

    @property
    def name(self) -> str | None:
        inst = self.__dict__.get("instrument")
        return inst.name if inst is not None else None

    @property
    def asset_class(self) -> str | None:
        inst = self.__dict__.get("instrument")
        return inst.asset_class if inst is not None else None

    # --- Indexes ---
    __table_args__ = (
        Index(
            "uq_portfolio_instrument",
            "portfolio_id",
            "instrument_id",
            unique=True,
        ),
    )
