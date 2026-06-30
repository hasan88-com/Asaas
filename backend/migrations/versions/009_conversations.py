"""Add conversations table + chat_messages.conversation_id (Raabta AI threads).

Revision ID: 009
Revises: 008
Create Date: 2026-06-30

Groups chat messages into ChatGPT-style conversations with auto-titles. The
conversation_id column is nullable so pre-existing messages stay valid.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
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
        sa.Column("title", sa.Text(), nullable=False, server_default="New chat"),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.add_column(
        "chat_messages",
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_messages_conversation_id",
        "chat_messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_constraint("fk_chat_messages_conversation_id", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "conversation_id")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")
