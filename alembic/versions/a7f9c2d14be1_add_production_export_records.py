"""add production export records

Revision ID: a7f9c2d14be1
Revises: e3c1a8b9d201
Create Date: 2026-06-29 02:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a7f9c2d14be1"
down_revision = "e3c1a8b9d201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "production_export_records" not in inspector.get_table_names():
        op.create_table(
            "production_export_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("export_format", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("total_shots", sa.Integer(), nullable=True),
            sa.Column("deliverable_shots", sa.Integer(), nullable=True),
            sa.Column("pending_review_shots", sa.Integer(), nullable=True),
            sa.Column("blocked_shots", sa.Integer(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("meta_info", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "production_export_records" in inspector.get_table_names():
        op.drop_table("production_export_records")
