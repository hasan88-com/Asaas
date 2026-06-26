"""Add maturity_date + face_value to instruments and retire matured debt.

Revision ID: 005
Revises: 004
Create Date: 2026-06-24

Re-chained from an orphaned duplicate revision "002" (which conflicted with
002_enhanced_profiling and was never applied — production reached 004 via the
other 002). Brings debt-instrument lifecycle out of the free-form ``metadata``
JSONB so the optimizer and daily jobs can filter matured instruments directly:

  * ``maturity_date`` (DATE, indexed) — NULL for non-maturing assets
    (stocks, crypto, commodities).
  * ``face_value`` (NUMERIC(18,2)) — face value in RUPEES, stored exactly as PSX
    reports it (the debt page already lists real values in rupees, e.g. 100,000;
    no ×1000 normalization is applied).

After adding the columns this migration:
  1. Backfills ``maturity_date`` from ``metadata->>'maturity_date'`` for any
     rows where it is already stored there (currently a no-op).
  2. Retires matured instruments: sets ``is_active = false`` where
     ``maturity_date < CURRENT_DATE`` (no-op until the refresh worker populates
     maturities). Existing ``is_active`` filters then exclude them unchanged.

Idempotent column adds (IF NOT EXISTS) so it is safe even if the columns were
created out-of-band.
"""

from __future__ import annotations

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE instruments ADD COLUMN IF NOT EXISTS maturity_date DATE")
    op.execute("ALTER TABLE instruments ADD COLUMN IF NOT EXISTS face_value NUMERIC(18, 2)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_instruments_maturity_date "
        "ON instruments (maturity_date)"
    )

    # Backfill from metadata JSONB where present (no-op today).
    op.execute(
        """
        UPDATE instruments
        SET maturity_date = (metadata->>'maturity_date')::date
        WHERE maturity_date IS NULL
          AND metadata IS NOT NULL
          AND metadata ? 'maturity_date'
        """
    )

    # Retire any instrument whose maturity has already passed.
    op.execute(
        """
        UPDATE instruments
        SET is_active = false
        WHERE maturity_date IS NOT NULL
          AND maturity_date < CURRENT_DATE
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_instruments_maturity_date")
    op.execute("ALTER TABLE instruments DROP COLUMN IF EXISTS face_value")
    op.execute("ALTER TABLE instruments DROP COLUMN IF EXISTS maturity_date")
