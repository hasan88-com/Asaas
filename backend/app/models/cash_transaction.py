"""
Asaas (اثاثہ) — Cash Transaction Model

Schema: `cash_transactions` table. Append-only ledger of every cash movement
on a `cash_accounts` row: deposit / withdrawal / buy / sell today; the
`counterparty_user_id`, `status` and `settles_at` columns are reserved hooks
for P2P transfers and T+2 settlement in later PRs. `amount` is always
positive — the sign is implied by `type`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CashTransaction(Base):
    __tablename__ = "cash_transactions"
    __table_args__ = (
        Index("ix_cash_transactions_account_created", "account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cash_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)  # deposit / withdrawal / buy / sell
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    holding_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("holdings.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    counterparty_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="settled", server_default="settled"
    )
    settles_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # --- Relationships ---
    account = relationship("CashAccount")
