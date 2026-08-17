"""add storyboard acceptance records

Revision ID: e3c1a8b9d201
Revises: 9f2d7d4f31aa
Create Date: 2026-06-28 20:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e3c1a8b9d201"
down_revision = "9f2d7d4f31aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "storyboard_acceptance_records" not in inspector.get_table_names():
        op.create_table(
            "storyboard_acceptance_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("shot_id", sa.Integer(), nullable=False),
            sa.Column("asset_kind", sa.String(), nullable=True),
            sa.Column("asset_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("failure_tags", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("meta_info", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "storyboard_acceptance_records" in inspector.get_table_names():
        op.drop_table("storyboard_acceptance_records")
