"""
Asaas (اثاثہ) — Flag Model

Schema: TECH.md §7.2 `flags` table.
Pending material events awaiting user decision.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Flag(Base):
    __tablename__ = "flags"

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
        index=True,
    )
    news_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_items.id", ondelete="SET NULL"),
        nullable=True,
    )  # nullable for drift/rate flags (TECH.md §7.3)
    type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # news / rate_impact / drift
    severity: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # high / medium
    message: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # impact rationale shown to user
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )  # pending / acknowledged / actioned
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ---
    portfolio = relationship("Portfolio", back_populates="flags", lazy="noload")
    news_item = relationship("NewsItem", back_populates="flags", lazy="noload")
