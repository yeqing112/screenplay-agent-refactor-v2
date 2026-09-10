"""add proactive smart director project updates

Revision ID: c5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "c5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "agent_project_updates" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "agent_project_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="progress"),
        sa.Column("severity", sa.String(), nullable=False, server_default="info"),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("action_proposal", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("requires_confirmation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="unread"),
        sa.Column("dedupe_key", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    for name, column in (
        ("ix_agent_project_updates_book", "book_id"),
        ("ix_agent_project_updates_type", "type"),
        ("ix_agent_project_updates_severity", "severity"),
        ("ix_agent_project_updates_status", "status"),
        ("ix_agent_project_updates_dedupe", "dedupe_key"),
        ("ix_agent_project_updates_evidence", "evidence_fingerprint"),
        ("ix_agent_project_updates_created", "created_at"),
        ("ix_agent_project_updates_updated", "updated_at"),
    ):
        op.create_index(name, "agent_project_updates", [column])


def downgrade() -> None:
    if "agent_project_updates" in inspect(op.get_bind()).get_table_names():
        op.drop_table("agent_project_updates")
