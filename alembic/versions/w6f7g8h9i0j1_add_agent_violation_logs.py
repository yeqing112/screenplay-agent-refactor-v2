"""add persisted agent violation log table

Revision ID: w6f7g8h9i0j1
Revises: v5e6f7g8h9i0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "w6f7g8h9i0j1"
down_revision: Union[str, Sequence[str], None] = "v5e6f7g8h9i0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "agent_violation_logs" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "agent_violation_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_type", sa.String(length=32), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("scene_name", sa.String(length=128), nullable=True),
        sa.Column("shot_id", sa.Integer(), nullable=True),
        sa.Column("violation_id", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("actual_value", sa.String(length=256), nullable=True),
        sa.Column("expected_source", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("repair_strategy", sa.String(length=16), nullable=True),
        sa.Column("repair_result", sa.String(length=16), nullable=True),
        sa.Column("fix_details", sa.Text(), nullable=True),
        sa.Column("regression", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    for name, columns in (
        ("ix_agent_violation_logs_agent_type", ["agent_type"]),
        ("ix_agent_violation_logs_book_id", ["book_id"]),
        ("ix_agent_violation_logs_violation_id", ["violation_id"]),
        ("ix_agent_violation_logs_created_at", ["created_at"]),
    ):
        op.create_index(name, "agent_violation_logs", columns)


def downgrade() -> None:
    if "agent_violation_logs" in inspect(op.get_bind()).get_table_names():
        op.drop_table("agent_violation_logs")
