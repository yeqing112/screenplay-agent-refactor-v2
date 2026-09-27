"""Add Video Generation Intent relation over StoryboardShot."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e6f7a8b9c0d1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "video_generation_intents" in _tables(bind):
        return
    op.create_table(
        "video_generation_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("aspect_ratio", sa.String(), nullable=False),
        sa.Column("motion_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("first_frame_asset", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("last_frame_asset", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("intent_fingerprint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'READY'")),
        sa.Column("generation_execution_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_video_generation_intent_shot", ondelete="RESTRICT"),
        sa.UniqueConstraint("intent_fingerprint", name="uq_video_generation_intent_fingerprint"),
        sa.UniqueConstraint("generation_execution_id", name="uq_video_generation_intent_execution"),
        sa.UniqueConstraint("task_id", name="uq_video_generation_intent_task"),
        sa.CheckConstraint("duration > 0", name="ck_video_generation_intent_duration_positive"),
        sa.CheckConstraint("status IN ('READY','EXECUTING','SUCCEEDED','FAILED')", name="ck_video_generation_intent_status"),
    )
    for name, fields in {
        "ix_video_generation_intents_shot": ["storyboard_shot_id"],
        "ix_video_generation_intents_fingerprint": ["intent_fingerprint"],
        "ix_video_generation_intents_status": ["status"],
        "ix_video_generation_intents_execution": ["generation_execution_id"],
        "ix_video_generation_intents_task": ["task_id"],
    }.items():
        op.create_index(name, "video_generation_intents", fields, unique=name.endswith(("fingerprint", "execution", "task")))


def downgrade() -> None:
    if "video_generation_intents" in _tables(op.get_bind()):
        op.drop_table("video_generation_intents")
