"""Lean IPS-based schema refactor.

Reduces risk_profiles to 8-question normalized columns, consolidates
asset class preferences into investment_preferences JSONB, and adds
investment_policy_statements and portfolio_recommendations tables.

Revision ID: 003
Revises: 002
Create Date: 2026-06-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1a. Add new columns before dropping old ones ──────────────────────────
    op.add_column("risk_profiles", sa.Column("monthly_contribution", sa.Numeric(18, 2), nullable=True))
    op.add_column("risk_profiles", sa.Column("investment_frequency", sa.Text, nullable=True))
    op.add_column("risk_profiles", sa.Column("risk_willingness", sa.Text, nullable=True))
    op.add_column("risk_profiles", sa.Column("loss_tolerance", sa.Text, nullable=True))
    op.add_column("risk_profiles", sa.Column("experience", sa.Text, nullable=True))
    op.add_column("risk_profiles", sa.Column("investment_preferences", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False))

    # ── 1b. Data migration: consolidate old JSONB columns ──────────────────────
    op.execute(text("""
        UPDATE risk_profiles SET
          investment_preferences = jsonb_build_object(
            'shariah', COALESCE((pakistan_prefs->>'shariah_compliant')::boolean, false),
            'asset_classes', (
              CASE WHEN pakistan_prefs->'preferred_sectors' IS NOT NULL
                        AND jsonb_array_length(COALESCE(pakistan_prefs->'preferred_sectors', '[]'::jsonb)) > 0
                   THEN '["psx"]'::jsonb ELSE '[]'::jsonb END
              ||
              CASE WHEN fixed_income_profile IS NOT NULL
                        AND (fixed_income_profile->>'interest_level') IS DISTINCT FROM 'none'
                   THEN '["fixed_income"]'::jsonb ELSE '[]'::jsonb END
              ||
              CASE WHEN commodity_profile IS NOT NULL
                        AND (commodity_profile->>'interest_level') IS DISTINCT FROM 'none'
                   THEN '["gold"]'::jsonb ELSE '[]'::jsonb END
              ||
              CASE WHEN crypto_profile IS NOT NULL
                        AND (crypto_profile->>'interest_level') IS DISTINCT FROM 'none'
                   THEN '["crypto"]'::jsonb ELSE '[]'::jsonb END
            ),
            'psx_sectors', COALESCE(pakistan_prefs->'preferred_sectors', '[]'::jsonb),
            'crypto_assets', COALESCE(crypto_profile->'preferred_coins', '[]'::jsonb),
            'fixed_income_products', COALESCE(fixed_income_profile->'preferred_products', '[]'::jsonb)
          ),
          risk_willingness = questionnaire_answers->>'risk_willingness',
          loss_tolerance   = questionnaire_answers->>'loss_tolerance',
          experience       = questionnaire_answers->>'experience',
          monthly_contribution = 0
        WHERE pakistan_prefs IS NOT NULL
           OR crypto_profile IS NOT NULL
           OR commodity_profile IS NOT NULL
           OR fixed_income_profile IS NOT NULL
    """))

    # ── 1c. Rename capital_pkr → initial_capital ──────────────────────────────
    op.alter_column("risk_profiles", "capital_pkr", new_column_name="initial_capital")

    # ── 1d. Drop legacy columns ───────────────────────────────────────────────
    op.drop_column("risk_profiles", "pakistan_prefs")
    op.drop_column("risk_profiles", "crypto_profile")
    op.drop_column("risk_profiles", "commodity_profile")
    op.drop_column("risk_profiles", "fixed_income_profile")
    op.drop_column("risk_profiles", "behavioral_profile")
    op.drop_column("risk_profiles", "news_preferences")
    op.drop_column("risk_profiles", "diversification_score")
    op.drop_column("risk_profiles", "portfolio_health_score")
    op.drop_column("risk_profiles", "crypto_exposure_score")
    op.drop_column("risk_profiles", "fixed_income_suitability")
    op.drop_column("risk_profiles", "questionnaire_answers")
    op.drop_column("risk_profiles", "evaluated_at")

    # ── 1e. Create investment_policy_statements ────────────────────────────────
    op.create_table(
        "investment_policy_statements",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_profile_id", sa.UUID(as_uuid=True), sa.ForeignKey("risk_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("investment_objective", sa.Text, nullable=True),
        sa.Column("time_horizon", sa.Text, nullable=True),
        sa.Column("risk_tolerance", sa.Text, nullable=True),
        sa.Column("liquidity_profile", sa.Text, nullable=True),
        sa.Column("investment_frequency", sa.Text, nullable=True),
        sa.Column("initial_capital", sa.Numeric(18, 2), nullable=True),
        sa.Column("monthly_contribution", sa.Numeric(18, 2), nullable=True),
        sa.Column("eligible_asset_classes", JSONB, nullable=True),
        sa.Column("investment_restrictions", JSONB, nullable=True),
        sa.Column("recommended_allocation", JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ips_user_id", "investment_policy_statements", ["user_id"])

    # ── 1f. Create portfolio_recommendations ──────────────────────────────────
    op.create_table(
        "portfolio_recommendations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_profile_id", sa.UUID(as_uuid=True), sa.ForeignKey("risk_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_score", sa.Integer, nullable=True),
        sa.Column("investor_persona", sa.Text, nullable=True),
        sa.Column("recommended_allocation", JSONB, nullable=True),
        sa.Column("expected_return_range", sa.Text, nullable=True),
        sa.Column("expected_volatility", sa.Text, nullable=True),
        sa.Column("rebalance_frequency", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_pr_user_id", "portfolio_recommendations", ["user_id"])


def downgrade() -> None:
    # Drop new tables
    op.drop_index("ix_pr_user_id", table_name="portfolio_recommendations")
    op.drop_table("portfolio_recommendations")
    op.drop_index("ix_ips_user_id", table_name="investment_policy_statements")
    op.drop_table("investment_policy_statements")

    # Restore capital_pkr name
    op.alter_column("risk_profiles", "initial_capital", new_column_name="capital_pkr")

    # Restore dropped columns (empty — data is not reversible)
    op.add_column("risk_profiles", sa.Column("pakistan_prefs", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("crypto_profile", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("commodity_profile", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("fixed_income_profile", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("behavioral_profile", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("news_preferences", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("diversification_score", sa.Float, nullable=True))
    op.add_column("risk_profiles", sa.Column("portfolio_health_score", sa.Float, nullable=True))
    op.add_column("risk_profiles", sa.Column("crypto_exposure_score", sa.Float, nullable=True))
    op.add_column("risk_profiles", sa.Column("fixed_income_suitability", sa.Float, nullable=True))
    op.add_column("risk_profiles", sa.Column("questionnaire_answers", JSONB, nullable=True))
    op.add_column("risk_profiles", sa.Column("evaluated_at", sa.TIMESTAMP(timezone=True), nullable=True))

    # Drop new columns
    op.drop_column("risk_profiles", "created_at")
    op.drop_column("risk_profiles", "investment_preferences")
    op.drop_column("risk_profiles", "experience")
    op.drop_column("risk_profiles", "loss_tolerance")
    op.drop_column("risk_profiles", "risk_willingness")
    op.drop_column("risk_profiles", "investment_frequency")
    op.drop_column("risk_profiles", "monthly_contribution")
