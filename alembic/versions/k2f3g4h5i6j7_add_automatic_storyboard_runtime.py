"""Add reviewable automatic storyboard drafts and lineage columns."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "k2f3g4h5i6j7"
down_revision = "j1e2f3g4h5i6"
branch_labels = None
depends_on = None


def _add_columns(table: str, columns: list[sa.Column]) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "director_storyboard_plans" not in tables:
        op.create_table(
            "director_storyboard_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("episode_id", sa.String(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="REVIEW_REQUIRED"),
            sa.Column("storyboard_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("director_reasoning_id", sa.Integer(), nullable=True),
            sa.Column("director_reasoning_version", sa.Integer(), nullable=True),
            sa.Column("compiled_shot_plan_ids", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("lineage_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("episode_id", "version", name="uq_director_storyboard_episode_version"),
            sa.CheckConstraint("version >= 1", name="ck_director_storyboard_version_positive"),
            sa.CheckConstraint("status IN ('DRAFT','REVIEW_REQUIRED','COMPILED','SUPERSEDED','ROLLED_BACK','REJECTED')", name="ck_director_storyboard_status"),
        )
        for name, fields in {
            "ix_director_storyboard_plans_episode": ["episode_id"],
            "ix_director_storyboard_plans_status": ["status"],
            "ix_director_storyboard_plans_payload": ["payload_hash"],
            "ix_director_storyboard_plans_reasoning": ["director_reasoning_id"],
        }.items():
            op.create_index(name, "director_storyboard_plans", fields)

    tables = set(inspect(bind).get_table_names())
    if "director_storyboard_shots" not in tables:
        op.create_table(
            "director_storyboard_shots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("storyboard_id", sa.Integer(), sa.ForeignKey("director_storyboard_plans.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("shot_id", sa.String(), nullable=False, server_default=""),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("shot_type", sa.String(), nullable=False, server_default="medium"),
            sa.Column("camera", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("composition", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("character_actions", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("emotion", sa.Text(), nullable=False, server_default=""),
            sa.Column("duration", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("visual_style_id", sa.String(), nullable=False, server_default=""),
            sa.Column("source_lineage", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("storyboard_id", "sequence", name="uq_director_storyboard_shot_sequence"),
            sa.CheckConstraint("sequence >= 1", name="ck_director_storyboard_shot_sequence_positive"),
            sa.CheckConstraint("duration > 0 AND duration <= 60", name="ck_director_storyboard_shot_duration_range"),
        )
        for name, fields in {
            "ix_director_storyboard_shots_storyboard": ["storyboard_id"],
            "ix_director_storyboard_shots_scene": ["scene_id"],
        }.items():
            op.create_index(name, "director_storyboard_shots", fields)

    _add_columns("shot_plans", [
        sa.Column("storyboard_plan_id", sa.Integer(), nullable=True),
        sa.Column("storyboard_plan_version", sa.Integer(), nullable=True),
        sa.Column("storyboard_lineage", sa.Text(), nullable=False, server_default="{}"),
    ])
    _add_columns("production_generation_intents", [
        sa.Column("storyboard_plan_id", sa.Integer(), nullable=True),
        sa.Column("storyboard_plan_version", sa.Integer(), nullable=True),
        sa.Column("storyboard_lineage", sa.Text(), nullable=False, server_default="{}"),
    ])
    _add_columns("production_prompt_versions", [
        sa.Column("storyboard_plan_id", sa.Integer(), nullable=True),
        sa.Column("storyboard_plan_version", sa.Integer(), nullable=True),
        sa.Column("storyboard_lineage", sa.Text(), nullable=False, server_default="{}"),
    ])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table, columns in {
        "production_prompt_versions": ("storyboard_lineage", "storyboard_plan_version", "storyboard_plan_id"),
        "production_generation_intents": ("storyboard_lineage", "storyboard_plan_version", "storyboard_plan_id"),
        "shot_plans": ("storyboard_lineage", "storyboard_plan_version", "storyboard_plan_id"),
    }.items():
        if table not in inspector.get_table_names():
            continue
        existing = {item["name"] for item in inspect(bind).get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
    for table in ("director_storyboard_shots", "director_storyboard_plans"):
        if table in inspect(bind).get_table_names():
            op.drop_table(table)
