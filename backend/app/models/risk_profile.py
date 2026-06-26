"""
Asaas (اثاثہ) — Risk Profile Model

Schema: TECH.md §7.2 `risk_profiles` table.
1:1 with users. Stores normalized 8-question answers + derived IPS fields.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class RiskProfile(Base):
    __tablename__ = "risk_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # ── Core questionnaire answers (normalized) ───────────────────────────────
    goal: Mapped[str] = mapped_column(Text, nullable=False)  # preservation/income/growth
    horizon: Mapped[str] = mapped_column(Text, nullable=False)  # short/medium/long
    risk_willingness: Mapped[str | None] = mapped_column(Text, nullable=True)  # sell_all/sell_some/hold/buy_more
    loss_tolerance: Mapped[str | None] = mapped_column(Text, nullable=True)  # 5pct/10pct/15pct/25pct_plus
    experience: Mapped[str | None] = mapped_column(Text, nullable=True)  # none/limited/moderate/extensive/advanced

    # ── Capital fields ────────────────────────────────────────────────────────
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    monthly_contribution: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    investment_frequency: Mapped[str | None] = mapped_column(Text, nullable=True)  # one_time/monthly/quarterly/annually

    # ── Asset preferences (replaces 4 legacy JSONB columns) ──────────────────
    investment_preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Derived fields (kept for optimizer + agent compatibility) ─────────────
    risk_tolerance: Mapped[str] = mapped_column(Text, nullable=False)  # conservative/moderate/aggressive
    investor_mode: Mapped[str] = mapped_column(Text, nullable=False)   # long_term/balanced/maximum_growth
    constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    # ── Computed profile ──────────────────────────────────────────────────────
    risk_score: Mapped[int | None] = mapped_column(nullable=True)
    investor_persona: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Raw questionnaire answers (for agent personalisation) ─────────────────
    questionnaire_answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── AI insights ───────────────────────────────────────────────────────────
    agent_remarks: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    recommendations: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user = relationship("User", back_populates="risk_profile")
    ips = relationship("InvestmentPolicyStatement", back_populates="risk_profile", uselist=False)
    portfolio_recommendation = relationship("PortfolioRecommendation", back_populates="risk_profile", uselist=False)
