"""Add cash_accounts + cash_transactions (virtual PKR wallet, Cash & Transfers PR 1).

Revision ID: 011
Revises: 010
Create Date: 2026-07-02

Per-user virtual cash balance plus an append-only ledger. `counterparty_user_id`,
`status` and `settles_at` on the ledger are reserved hooks for P2P transfers and
T+2 settlement in later PRs; unused in PR 1.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cash_accounts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.Text(), nullable=False, server_default="PKR"),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint("balance >= 0", name="ck_cash_accounts_balance_non_negative"),
    )
    op.create_index("ix_cash_accounts_user_id", "cash_accounts", ["user_id"], unique=True)

    op.create_table(
        "cash_transactions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cash_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "holding_id",
            UUID(as_uuid=True),
            sa.ForeignKey("holdings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("price", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "counterparty_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="settled"),
        sa.Column("settles_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_cash_transactions_user_id", "cash_transactions", ["user_id"])
    op.create_index(
        "ix_cash_transactions_account_created", "cash_transactions", ["account_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_cash_transactions_account_created", table_name="cash_transactions")
    op.drop_index("ix_cash_transactions_user_id", table_name="cash_transactions")
    op.drop_table("cash_transactions")
    op.drop_index("ix_cash_accounts_user_id", table_name="cash_accounts")
    op.drop_table("cash_accounts")
