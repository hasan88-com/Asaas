"""Enable RLS and create row-level security policies on all user-owned tables.

Revision ID: 001
Revises: 000
Create Date: 2026-06-16

Note: If migrating from an old schema that still has password_hash,
run the commented-out block in upgrade() below.
"""

from __future__ import annotations

from alembic import op

revision = "001"
down_revision = "000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Optional: uncomment these two lines ONLY if upgrading from an existing
    # database that still has the old password_hash column.
    # For fresh Supabase installs, migration 000 creates the correct schema
    # so these are not needed.
    # -------------------------------------------------------------------------
    # op.drop_column("users", "password_hash")
    # op.execute("ALTER TABLE users ALTER COLUMN id DROP DEFAULT")

    # -------------------------------------------------------------------------
    # Enable Row-Level Security on all user-owned tables.
    # The FastAPI service role bypasses RLS; these policies guard against
    # direct DB access without going through the API.
    # -------------------------------------------------------------------------
    for table in (
        "users",
        "risk_profiles",
        "portfolios",
        "holdings",
        "portfolio_snapshots",
        "flags",
        "chat_messages",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # users
    op.execute(
        "CREATE POLICY users_select_own ON users FOR SELECT USING (id = auth.uid())"
    )
    op.execute(
        "CREATE POLICY users_update_own ON users FOR UPDATE USING (id = auth.uid())"
    )

    # risk_profiles
    op.execute(
        "CREATE POLICY risk_profiles_own ON risk_profiles FOR ALL USING (user_id = auth.uid())"
    )

    # portfolios
    op.execute(
        "CREATE POLICY portfolios_own ON portfolios FOR ALL USING (user_id = auth.uid())"
    )

    # holdings (ownership via portfolio)
    op.execute(
        """
        CREATE POLICY holdings_own ON holdings FOR ALL USING (
            portfolio_id IN (SELECT id FROM portfolios WHERE user_id = auth.uid())
        )
        """
    )

    # portfolio_snapshots (ownership via portfolio)
    op.execute(
        """
        CREATE POLICY portfolio_snapshots_own ON portfolio_snapshots FOR ALL USING (
            portfolio_id IN (SELECT id FROM portfolios WHERE user_id = auth.uid())
        )
        """
    )

    # flags (ownership via portfolio)
    op.execute(
        """
        CREATE POLICY flags_own ON flags FOR ALL USING (
            portfolio_id IN (SELECT id FROM portfolios WHERE user_id = auth.uid())
        )
        """
    )

    # chat_messages
    op.execute(
        "CREATE POLICY chat_messages_own ON chat_messages FOR ALL USING (user_id = auth.uid())"
    )


def downgrade() -> None:
    for policy, table in (
        ("users_select_own", "users"),
        ("users_update_own", "users"),
        ("risk_profiles_own", "risk_profiles"),
        ("portfolios_own", "portfolios"),
        ("holdings_own", "holdings"),
        ("portfolio_snapshots_own", "portfolio_snapshots"),
        ("flags_own", "flags"),
        ("chat_messages_own", "chat_messages"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")

    for table in (
        "users",
        "risk_profiles",
        "portfolios",
        "holdings",
        "portfolio_snapshots",
        "flags",
        "chat_messages",
    ):
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
