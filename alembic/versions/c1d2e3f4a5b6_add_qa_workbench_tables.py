"""add qa workbench tables

Revision ID: c1d2e3f4a5b6
Revises: a7f9c2d14be1
Create Date: 2026-07-04 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c1d2e3f4a5b6"
down_revision = "a7f9c2d14be1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "qa_issues" not in inspector.get_table_names():
        op.create_table(
            "qa_issues",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("issue_key", sa.String(), nullable=False, unique=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("qa_result_id", sa.Integer(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("issue_type", sa.String(), nullable=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("script_section", sa.String(), nullable=True),
            sa.Column("line_start", sa.Integer(), nullable=True),
            sa.Column("line_end", sa.Integer(), nullable=True),
            sa.Column("suggestion", sa.Text(), nullable=True),
            sa.Column("fix_mode", sa.String(), nullable=True),
            sa.Column("fix_status", sa.String(), nullable=True),
            sa.Column("status_reason", sa.Text(), nullable=True),
            sa.Column("source_excerpt", sa.Text(), nullable=True),
            sa.Column("meta_info", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if "script_versions" not in inspector.get_table_names():
        op.create_table(
            "script_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("script_id", sa.Integer(), nullable=True),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(), nullable=True),
            sa.Column("change_type", sa.String(), nullable=True),
            sa.Column("change_reason", sa.Text(), nullable=True),
            sa.Column("qa_issue_key", sa.String(), nullable=True),
            sa.Column("operator_name", sa.String(), nullable=True),
            sa.Column("content_before", sa.Text(), nullable=True),
            sa.Column("content_after", sa.Text(), nullable=True),
            sa.Column("diff_text", sa.Text(), nullable=True),
            sa.Column("recheck_status", sa.String(), nullable=True),
            sa.Column("recheck_summary", sa.Text(), nullable=True),
            sa.Column("meta_info", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "script_versions" in inspector.get_table_names():
        op.drop_table("script_versions")
    if "qa_issues" in inspector.get_table_names():
        op.drop_table("qa_issues")
