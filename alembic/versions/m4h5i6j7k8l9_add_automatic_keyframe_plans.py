"""Add reviewable AutomaticKeyframePlan records over existing keyframes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "m4h5i6j7k8l9"
down_revision = "l3g4h5i6j7k8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "automatic_keyframe_plans" in set(inspect(bind).get_table_names()):
        return
    op.create_table(
        "automatic_keyframe_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.String(), nullable=False),
        sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
        sa.Column("storyboard_materialization_set_id", sa.Integer(), nullable=False),
        sa.Column("storyboard_materialization_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("materialization_set_fingerprint", sa.String(), nullable=False),
        sa.Column("shot_plan_id", sa.Integer(), nullable=False),
        sa.Column("shot_plan_revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("shot_direction_id", sa.Integer(), nullable=False),
        sa.Column("shot_direction_revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("shot_direction_fingerprint", sa.String(), nullable=False),
        sa.Column("generation_intent_id", sa.String(), nullable=False),
        sa.Column("generation_intent_fingerprint", sa.String(), nullable=False),
        sa.Column("production_prompt_version_id", sa.String(), nullable=False),
        sa.Column("production_prompt_fingerprint", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'REVIEW_REQUIRED'")),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_fingerprint", sa.String(), nullable=False),
        sa.Column("source_lineage_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", sa.String(), nullable=False, server_default=sa.text("'automatic-keyframe-planner'")),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_lineage_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("compiled_sequence_id", sa.Integer(), nullable=True),
        sa.Column("compiled_sequence_fingerprint", sa.String(), nullable=True),
        sa.Column("stale_reasons", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_automatic_keyframe_plan_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["storyboard_materialization_set_id"], ["storyboard_materialization_sets.id"], name="fk_automatic_keyframe_plan_materialization_set", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["shot_direction_id"], ["shot_directions.id"], name="fk_automatic_keyframe_plan_direction", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["compiled_sequence_id"], ["keyframe_sequences.id"], name="fk_automatic_keyframe_plan_sequence", ondelete="RESTRICT"),
        sa.UniqueConstraint("source_fingerprint", name="uq_automatic_keyframe_plan_source_fingerprint"),
        sa.UniqueConstraint("storyboard_shot_id", "version", name="uq_automatic_keyframe_plan_shot_version"),
        sa.CheckConstraint("version >= 1", name="ck_automatic_keyframe_plan_version"),
        sa.CheckConstraint("duration > 0", name="ck_automatic_keyframe_plan_duration"),
        sa.CheckConstraint("storyboard_materialization_version >= 1", name="ck_automatic_keyframe_plan_materialization_version"),
        sa.CheckConstraint("shot_plan_revision >= 1", name="ck_automatic_keyframe_plan_shot_plan_revision"),
        sa.CheckConstraint("shot_direction_revision >= 1", name="ck_automatic_keyframe_plan_direction_revision"),
        sa.CheckConstraint("status IN ('REVIEW_REQUIRED','APPROVED','REJECTED','REVISE','STALE','COMPILED','SUPERSEDED')", name="ck_automatic_keyframe_plan_status"),
    )
    for name, fields, unique in (
        ("ix_automatic_keyframe_plans_episode", ["episode_id"], False),
        ("ix_automatic_keyframe_plans_shot", ["storyboard_shot_id"], False),
        ("ix_automatic_keyframe_plans_set", ["storyboard_materialization_set_id"], False),
        ("ix_automatic_keyframe_plans_status", ["status"], False),
        ("ix_automatic_keyframe_plans_source", ["source_fingerprint"], True),
    ):
        op.create_index(name, "automatic_keyframe_plans", fields, unique=unique)


def downgrade() -> None:
    if "automatic_keyframe_plans" in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table("automatic_keyframe_plans")
