"""Add per-item sentiment fields + market_sentiment_snapshot table.

Revision ID: 007
Revises: 006
Create Date: 2026-06-25

Stage 2 (ENRICH): news_items gains `magnitude` (0–1 directional strength) and
`sentiment_reason` (reserved for a future LLM tagging tier; NULL for the lexicon
tier). `sentiment` and `materiality_score` already exist.

Stage 4 (AGGREGATE): a new `market_sentiment_snapshot` table holds per-day
rollups of news sentiment along sector / asset_class / overall-market axes,
written once per news ingest cycle so the dashboard reads a precomputed row.

All additive signal — nothing here is read by the optimizer / weights / money
pipeline. Idempotent (IF NOT EXISTS) so it is safe to re-run.
"""

from __future__ import annotations

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Stage 2: per-item sentiment fields ---
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS magnitude NUMERIC(4, 3)")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS sentiment_reason TEXT")

    # --- Stage 4: market sentiment snapshot ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_sentiment_snapshot (
            id            BIGSERIAL PRIMARY KEY,
            snapshot_date DATE        NOT NULL,
            scope         TEXT        NOT NULL,
            label         TEXT        NOT NULL,
            score         NUMERIC(5,4) NOT NULL,
            item_count    INTEGER     NOT NULL DEFAULT 0,
            bullish_count INTEGER     NOT NULL DEFAULT 0,
            bearish_count INTEGER     NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_market_sentiment_scope_label_date "
        "ON market_sentiment_snapshot (snapshot_date, scope, label)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS market_sentiment_snapshot")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS sentiment_reason")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS magnitude")
