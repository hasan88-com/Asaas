"""Add instrument_fundamentals cache (DB-first valuation fundamentals).

Revision ID: 010
Revises: 009
Create Date: 2026-06-30

Persisted yfinance fundamentals snapshot per instrument so the valuation service
serves P/E / EV-EBITDA / P/B / DCF from the DB when live yfinance is rate-limited
(Render 429s). One row per instrument; refreshed on every successful live fetch.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_fundamentals",
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column(
            "fetched_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_instrument_fundamentals_symbol", "instrument_fundamentals", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_instrument_fundamentals_symbol", table_name="instrument_fundamentals")
    op.drop_table("instrument_fundamentals")
