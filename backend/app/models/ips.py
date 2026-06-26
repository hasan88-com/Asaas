"""
Asaas (اثاثہ) — Investment Policy Statement Model

1:1 with risk_profiles. Auto-generated after questionnaire submission.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class InvestmentPolicyStatement(Base):
    __tablename__ = "investment_policy_statements"

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
    risk_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    investment_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_horizon: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_tolerance: Mapped[str | None] = mapped_column(Text, nullable=True)
    liquidity_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    investment_frequency: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_capital: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    monthly_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    eligible_asset_classes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    investment_restrictions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    recommended_allocation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    risk_profile = relationship("RiskProfile", back_populates="ips")
