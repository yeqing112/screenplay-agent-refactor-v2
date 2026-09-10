"""add auditable storyboard video retry attempts

Revision ID: c0d1e2f3a4b5
Revises: a8b9c0d1e2f3
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c0d1e2f3a4b5"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "storyboard_video_retry_attempts" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "storyboard_video_retry_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("shot_id", sa.Integer(), nullable=False),
        sa.Column("source_task_id", sa.String(), nullable=False, unique=True),
        sa.Column("retry_root_task_id", sa.String(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="failed"),
        sa.Column("input_fingerprint", sa.String(), nullable=False),
        sa.Column("input_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("provider_response", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("retry_task_id", sa.String(), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_storyboard_video_retry_target", "storyboard_video_retry_attempts", ["book_id", "episode", "shot_id"])
    op.create_index("ix_storyboard_video_retry_root", "storyboard_video_retry_attempts", ["retry_root_task_id", "attempt_number"])


def downgrade() -> None:
    if "storyboard_video_retry_attempts" in inspect(op.get_bind()).get_table_names():
        op.drop_table("storyboard_video_retry_attempts")
