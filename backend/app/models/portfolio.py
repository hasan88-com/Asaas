"""
Asaas (اثاثہ) — Portfolio Model

Schema: TECH.md §7.2 `portfolios` table.
Status: draft → confirmed → tracked.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft"
    )  # draft / confirmed / tracked
    expected_return: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    expected_risk: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )  # volatility
    sharpe: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    risk_free_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 4), nullable=True
    )  # SBP policy rate snapshot at optimization
    rationale: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # agent's plain-language explanation
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ---
    user = relationship("User", back_populates="portfolios")
    holdings = relationship(
        "Holding", back_populates="portfolio", lazy="selectin", cascade="all, delete-orphan"
    )
    snapshots = relationship(
        "PortfolioSnapshot", back_populates="portfolio", lazy="noload", cascade="all, delete-orphan"
    )
    flags = relationship(
        "Flag", back_populates="portfolio", lazy="selectin", cascade="all, delete-orphan"
    )
