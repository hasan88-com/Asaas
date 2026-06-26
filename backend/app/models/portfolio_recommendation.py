"""
Asaas (اثاثہ) — Portfolio Recommendation Model

1:1 with risk_profiles. Auto-generated after IPS creation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class PortfolioRecommendation(Base):
    __tablename__ = "portfolio_recommendations"

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

    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    investor_persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_allocation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expected_return_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_volatility: Mapped[str | None] = mapped_column(Text, nullable=True)
    rebalance_frequency: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    risk_profile = relationship("RiskProfile", back_populates="portfolio_recommendation")
