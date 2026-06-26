"""Add questionnaire_answers JSONB column to risk_profiles.

Stores the raw answers dict from the onboarding questionnaire so the
optimizer and chat agents can personalise responses without re-asking.

Revision ID: 004
Revises: 003
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_profiles",
        sa.Column("questionnaire_answers", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_profiles", "questionnaire_answers")
