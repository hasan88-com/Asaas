"""Add enhanced investor profiling columns to risk_profiles.

Revision ID: 002
Revises: 001
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Investor Persona & Behavioral
    op.add_column("risk_profiles", sa.Column("investor_persona", sa.Text, nullable=True))
    op.add_column("risk_profiles", sa.Column("behavioral_profile", JSONB, nullable=True))

    # Pakistan Market Preferences
    op.add_column("risk_profiles", sa.Column("pakistan_prefs", JSONB, nullable=True))

    # Asset Class Profiles
    op.add_column("risk_profiles", sa.Column("crypto_profile", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("commodity_profile", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("fixed_income_profile", JSONB, nullable=True))

    # News & Interests
    op.add_column("risk_profiles", sa.Column("news_preferences", JSONB, nullable=True))

    # Computed Scores
    op.add_column("risk_profiles", sa.Column("risk_score", sa.Integer, nullable=True))
    op.add_column("risk_profiles", sa.Column("diversification_score", sa.Float, nullable=True))
    op.add_column("risk_profiles", sa.Column("portfolio_health_score", sa.Float, nullable=True))
    op.add_column("risk_profiles", sa.Column("crypto_exposure_score", sa.Float, nullable=True))
    op.add_column("risk_profiles", sa.Column("fixed_income_suitability", sa.Float, nullable=True))

    # AI Insights
    op.add_column("risk_profiles", sa.Column("agent_remarks", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("recommendations", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("risk_profiles", "investor_persona")
    op.drop_column("risk_profiles", "behavioral_profile")
    op.drop_column("risk_profiles", "pakistan_prefs")
    op.drop_column("risk_profiles", "crypto_profile")
    op.drop_column("risk_profiles", "commodity_profile")
    op.drop_column("risk_profiles", "fixed_income_profile")
    op.drop_column("risk_profiles", "news_preferences")
    op.drop_column("risk_profiles", "risk_score")
    op.drop_column("risk_profiles", "diversification_score")
    op.drop_column("risk_profiles", "portfolio_health_score")
    op.drop_column("risk_profiles", "crypto_exposure_score")
    op.drop_column("risk_profiles", "fixed_income_suitability")
    op.drop_column("risk_profiles", "agent_remarks")
    op.drop_column("risk_profiles", "recommendations")
