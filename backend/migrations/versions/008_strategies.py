"""Add strategies table (no-code allocation / screener strategies).

Revision ID: 008
Revises: 007
Create Date: 2026-06-26

User-defined strategies: `kind` is 'allocation' or 'screener', `config` holds
the per-kind structured rules (JSONB). Nothing here is read by the optimizer /
money pipeline automatically — strategies run only on demand.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "config",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_strategies_user_id", "strategies", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_strategies_user_id", table_name="strategies")
    op.drop_table("strategies")
