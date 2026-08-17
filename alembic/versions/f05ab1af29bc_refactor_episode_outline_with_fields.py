"""refactor_episode_outline_with_fields

Revision ID: f05ab1af29bc
Revises: c84a783f96d7
Create Date: 2026-06-14 21:35:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "f05ab1af29bc"
down_revision: Union[str, Sequence[str], None] = "c84a783f96d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old table and recreate with new schema
    op.drop_table("episode_outlines")
    op.create_table("episode_outlines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False, default=0),
        sa.Column("title", sa.String(), default=""),
        sa.Column("core_event", sa.Text(), default=""),
        sa.Column("opening_hook", sa.Text(), default=""),
        sa.Column("core_conflict", sa.Text(), default=""),
        sa.Column("climax", sa.Text(), default=""),
        sa.Column("ending_hook", sa.Text(), default=""),
        sa.Column("characters", sa.Text(), default=""),
        sa.Column("scenes", sa.Text(), default=""),
        sa.Column("is_fixed", sa.Integer(), default=0, comment="是否为改编方案锁定的固定纲次"),
        sa.Column("raw_content", sa.Text(), default=""),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("episode_outlines")
    op.create_table("episode_outlines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), default=""),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
