"""
Asaas (اثاثہ) — Cash Account Model

Schema: `cash_accounts` table. One virtual PKR cash balance per user (paper
money — no payment gateway). The balance is mutated only through the wallet
service's atomic conditional UPDATEs; `cash_transactions` is the audit ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CashAccount(Base):
    __tablename__ = "cash_accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_cash_accounts_balance_non_negative"),
    )

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
        unique=True,
        index=True,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    currency: Mapped[str] = mapped_column(
        Text, nullable=False, default="PKR", server_default="PKR"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # --- Relationships ---
    user = relationship("User")
