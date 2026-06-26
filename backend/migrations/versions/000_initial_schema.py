"""Initial schema — creates all 11 tables for a fresh Supabase database.

Revision ID: 000
Revises:
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision = "000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. users
    #    id comes from Supabase auth.users — no server default.
    # -------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # -------------------------------------------------------------------------
    # 2. instruments
    # -------------------------------------------------------------------------
    op.create_table(
        "instruments",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="PKR"),
        sa.Column("data_source", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"], unique=True)

    # -------------------------------------------------------------------------
    # 3. prices
    # -------------------------------------------------------------------------
    op.create_table(
        "prices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=True),
        sa.Column("high", sa.Numeric(18, 6), nullable=True),
        sa.Column("low", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("instrument_id", "price_date", name="uq_instrument_price_date"),
    )
    op.execute(
        "CREATE INDEX ix_instrument_price_date_desc ON prices (instrument_id, price_date DESC)"
    )

    # -------------------------------------------------------------------------
    # 4. risk_profiles  (includes questionnaire fields from day one)
    # -------------------------------------------------------------------------
    op.create_table(
        "risk_profiles",
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
        sa.Column("risk_tolerance", sa.Text(), nullable=False),
        sa.Column("horizon", sa.Text(), nullable=False),
        sa.Column("investor_mode", sa.Text(), nullable=False),
        sa.Column("capital_pkr", sa.Numeric(18, 2), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("constraints", JSONB, nullable=True),
        sa.Column("questionnaire_answers", JSONB, nullable=True),
        sa.Column("evaluated_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_risk_profiles_user_id"),
    )
    op.create_index("ix_risk_profiles_user_id", "risk_profiles", ["user_id"])

    # -------------------------------------------------------------------------
    # 5. portfolios
    # -------------------------------------------------------------------------
    op.create_table(
        "portfolios",
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
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("expected_return", sa.Numeric(8, 4), nullable=True),
        sa.Column("expected_risk", sa.Numeric(8, 4), nullable=True),
        sa.Column("sharpe", sa.Numeric(8, 4), nullable=True),
        sa.Column("risk_free_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_portfolios_user_id", "portfolios", ["user_id"])

    # -------------------------------------------------------------------------
    # 6. holdings
    # -------------------------------------------------------------------------
    op.create_table(
        "holdings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_weight", sa.Numeric(6, 4), nullable=True),
        sa.Column("actual_weight", sa.Numeric(6, 4), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("entry_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("portfolio_id", "instrument_id", name="uq_portfolio_instrument"),
    )

    # -------------------------------------------------------------------------
    # 7. portfolio_snapshots
    # -------------------------------------------------------------------------
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_value_pkr", sa.Numeric(18, 2), nullable=False),
        sa.Column("pnl_absolute", sa.Numeric(18, 2), nullable=True),
        sa.Column("pnl_percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("breakdown", JSONB, nullable=True),
        sa.UniqueConstraint("portfolio_id", "snapshot_date", name="uq_portfolio_snapshot_date"),
    )

    # -------------------------------------------------------------------------
    # 8. news_items
    # -------------------------------------------------------------------------
    op.create_table(
        "news_items",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("published_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("level", sa.Text(), nullable=True),
        sa.Column("sentiment", sa.Text(), nullable=True),
        sa.Column("materiality_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw", JSONB, nullable=True),
        sa.Column(
            "ingested_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # -------------------------------------------------------------------------
    # 9. news_holding_link
    # -------------------------------------------------------------------------
    op.create_table(
        "news_holding_link",
        sa.Column(
            "news_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "instrument_id",
            UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("relevance", sa.Numeric(4, 3), nullable=True),
    )

    # -------------------------------------------------------------------------
    # 10. flags
    # -------------------------------------------------------------------------
    op.create_table(
        "flags",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "news_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_flags_portfolio_id", "flags", ["portfolio_id"])

    # -------------------------------------------------------------------------
    # 11. chat_messages
    # -------------------------------------------------------------------------
    op.create_table(
        "chat_messages",
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
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", JSONB, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("flags")
    op.drop_table("news_holding_link")
    op.drop_table("news_items")
    op.drop_table("portfolio_snapshots")
    op.drop_table("holdings")
    op.drop_table("portfolios")
    op.drop_table("risk_profiles")
    op.drop_table("prices")
    op.drop_table("instruments")
    op.drop_table("users")
