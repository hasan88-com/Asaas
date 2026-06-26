"""Add index on news_items.published_at.

Revision ID: 006
Revises: 005
Create Date: 2026-06-24

The /news/feed query filters published_at >= cutoff and orders by published_at
DESC; without an index that's a full scan + sort. The snapshot composite
(portfolio_id, snapshot_date) and holdings (portfolio_id, instrument_id) indexes
already exist, so this is the only missing one. Idempotent (IF NOT EXISTS).
"""

from __future__ import annotations

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_news_items_published_at "
        "ON news_items (published_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_news_items_published_at")
