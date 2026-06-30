"""Add strategies table — no-code allocation/screener builder.

Revision ID: 008
Revises: 007
Create Date: 2026-06-30

User-authored strategy rows. `kind` is 'allocation' (params fed into the
existing PortfolioOptimizer via suggest_portfolio/reoptimize) or 'screener'
(structured conditions evaluated against active instruments). No new quant
logic lives here — `config` JSONB just parameterizes the engines that
already exist.
"""

from __future__ import annotations

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS strategies (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT         NOT NULL,
            kind        TEXT         NOT NULL,
            config      JSONB        NOT NULL DEFAULT '{}'::jsonb,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_strategies_user_id ON strategies (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS strategies")
