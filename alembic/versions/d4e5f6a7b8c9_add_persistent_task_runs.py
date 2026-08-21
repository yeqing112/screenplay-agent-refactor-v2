"""add persistent task runs

Revision ID: d4e5f6a7b8c9
Revises: b1c2d3e4f5a6, c1d2e3f4a5b6
Create Date: 2026-08-21 23:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = ("b1c2d3e4f5a6", "c1d2e3f4a5b6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "task_runs" not in inspector.get_table_names():
        op.create_table(
            "task_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.String(), nullable=False),
            sa.Column("task_kind", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("progress", sa.Integer(), nullable=True),
            sa.Column("book_id", sa.Integer(), nullable=True),
            sa.Column("episode", sa.Integer(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("task_id"),
        )

    existing_indexes = {item["name"] for item in inspector.get_indexes("task_runs")}
    for index_name, columns in {
        "ix_task_runs_task_id": ["task_id"],
        "ix_task_runs_task_kind": ["task_kind"],
        "ix_task_runs_status": ["status"],
        "ix_task_runs_book_id": ["book_id"],
        "ix_task_runs_episode": ["episode"],
        "ix_task_runs_created_at": ["created_at"],
        "ix_task_runs_updated_at": ["updated_at"],
        "ix_task_runs_finished_at": ["finished_at"],
    }.items():
        if index_name not in existing_indexes:
            op.create_index(index_name, "task_runs", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "task_runs" in inspector.get_table_names():
        op.drop_table("task_runs")
