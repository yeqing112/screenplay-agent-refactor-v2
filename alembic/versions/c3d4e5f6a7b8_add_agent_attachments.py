"""add private smart director attachments

Revision ID: c3d4e5f6a7b8
Revises: c2d3e4f5a6b7, b9c0d1e2f3a4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "c3d4e5f6a7b8"
down_revision = ("c2d3e4f5a6b7", "b9c0d1e2f3a4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "agent_attachments" in inspect(bind).get_table_names():
        return
    op.create_table(
        "agent_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(), nullable=False, server_default=""),
        sa.Column("mime_type", sa.String(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(), nullable=False, server_default="document"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("sha256", sa.String(), nullable=False, server_default=""),
        sa.Column("extraction_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_attachments_book", "agent_attachments", ["book_id"])
    op.create_index("ix_agent_attachments_session", "agent_attachments", ["session_id"])
    op.create_index("ix_agent_attachments_sha", "agent_attachments", ["sha256"])


def downgrade() -> None:
    bind = op.get_bind()
    if "agent_attachments" in inspect(bind).get_table_names():
        op.drop_table("agent_attachments")
