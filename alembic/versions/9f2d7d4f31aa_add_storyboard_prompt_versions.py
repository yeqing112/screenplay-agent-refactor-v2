"""add storyboard prompt versions

Revision ID: 9f2d7d4f31aa
Revises: 7c441d0a5a62
Create Date: 2026-06-28 20:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "9f2d7d4f31aa"
down_revision: Union[str, Sequence[str], None] = "7c441d0a5a62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "storyboard_prompt_versions" not in inspector.get_table_names():
        op.create_table(
            "storyboard_prompt_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("shot_id", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("compile_reason", sa.String(), nullable=True),
            sa.Column("prompt_static", sa.Text(), nullable=True),
            sa.Column("prompt_motion", sa.Text(), nullable=True),
            sa.Column("negative_prompt", sa.Text(), nullable=True),
            sa.Column("meta_info", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("storyboard_prompt_versions")
