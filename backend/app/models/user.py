"""
Asaas (اثاثہ) — User Model

Schema: TECH.md §7.2 `users` table.
id must equal the Supabase auth.users.id — set explicitly on creation, no local default.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        # No default — ID is provided by Supabase Auth (auth.users.id)
    )
    email: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, index=True
    )
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    # --- Relationships ---
    risk_profile = relationship(
        "RiskProfile", back_populates="user", uselist=False, lazy="selectin"
    )
    portfolios = relationship(
        "Portfolio", back_populates="user", lazy="selectin"
    )
    chat_messages = relationship(
        "ChatMessage", back_populates="user", lazy="noload"
    )
