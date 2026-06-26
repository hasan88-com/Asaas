"""
Asaas (اثاثہ) — Portfolio Snapshot Model

Schema: TECH.md §7.2 `portfolio_snapshots` table.
Immutable daily value history — powers the performance chart.
Never updated, only inserted (TECH.md §7.3).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value_pkr: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    pnl_absolute: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    pnl_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    breakdown: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # per-asset-class value split

    # --- Relationships ---
    portfolio = relationship("Portfolio", back_populates="snapshots")

    # --- Indexes ---
    __table_args__ = (
        Index(
            "uq_portfolio_snapshot_date",
            "portfolio_id",
            "snapshot_date",
            unique=True,
        ),
    )
