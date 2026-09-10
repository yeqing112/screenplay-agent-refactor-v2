"""add smart director conversation messages

Revision ID: c4d5e6f7a8b9
Revises: c3d4e5f6a7b8
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "c4d5e6f7a8b9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "agent_messages" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("attachment_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_messages_session", "agent_messages", ["session_id"])


def downgrade() -> None:
    if "agent_messages" in inspect(op.get_bind()).get_table_names():
        op.drop_table("agent_messages")
