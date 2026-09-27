"""Add AI Director runtime foundation plan records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "g8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "director_plans" not in tables:
        op.create_table(
            "director_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("episode_id", sa.String(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="DRAFT"),
            sa.Column("created_by", sa.String(), nullable=False, server_default="director-runtime"),
            sa.Column("reasoning_trace", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("scene_plans", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("shot_plans", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("shot_directions", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("generation_intents", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("source_script_ir_version_id", sa.Integer(), nullable=True),
            sa.Column("source_script_ir_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("source_fact_snapshot_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("source_immutable_raw_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("lineage_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("episode_id", "version", name="uq_director_plan_episode_version"),
            sa.CheckConstraint("version >= 1", name="ck_director_plan_version_positive"),
            sa.CheckConstraint("status IN ('DRAFT','REVIEW_REQUIRED','APPROVED','SUPERSEDED','REJECTED')", name="ck_director_plan_status"),
        )
        op.create_index("ix_director_plans_episode_id", "director_plans", ["episode_id"])
        op.create_index("ix_director_plans_status", "director_plans", ["status"])
        op.create_index("ix_director_plans_source_script_ir_version_id", "director_plans", ["source_script_ir_version_id"])
        op.create_index("ix_director_plans_payload_hash", "director_plans", ["payload_hash"])
    tables = _tables(bind)
    if "director_scene_plans" not in tables:
        op.create_table(
            "director_scene_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("director_plan_id", sa.Integer(), nullable=False),
            sa.Column("episode_id", sa.String(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("location", sa.String(), nullable=False, server_default=""),
            sa.Column("time", sa.String(), nullable=False, server_default=""),
            sa.Column("mood", sa.String(), nullable=False, server_default=""),
            sa.Column("characters", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("visual_requirements", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("source_lineage", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("director_plan_id", "scene_id", name="uq_director_scene_plan_scene"),
            sa.CheckConstraint("version >= 1", name="ck_director_scene_plan_version_positive"),
            sa.ForeignKeyConstraint(["director_plan_id"], ["director_plans.id"], ondelete="RESTRICT"),
        )
        for name, fields in {
            "ix_director_scene_plans_plan": ["director_plan_id"],
            "ix_director_scene_plans_episode": ["episode_id"],
            "ix_director_scene_plans_scene": ["scene_id"],
            "ix_director_scene_plans_payload_hash": ["payload_hash"],
        }.items():
            op.create_index(name, "director_scene_plans", fields)

    inspector = inspect(bind)
    shot_columns = {item["name"] for item in inspector.get_columns("shot_plans")}
    for column in (
        sa.Column("director_plan_id", sa.Integer(), nullable=True),
        sa.Column("director_plan_version", sa.Integer(), nullable=True),
        sa.Column("director_lineage", sa.Text(), nullable=False, server_default="{}"),
    ):
        if column.name not in shot_columns:
            op.add_column("shot_plans", column)
    inspector = inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("shot_plans")}
    if "ix_shot_plans_director_plan_id" not in indexes:
        op.create_index("ix_shot_plans_director_plan_id", "shot_plans", ["director_plan_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "shot_plans" in inspector.get_table_names():
        indexes = {item["name"] for item in inspector.get_indexes("shot_plans")}
        if "ix_shot_plans_director_plan_id" in indexes:
            op.drop_index("ix_shot_plans_director_plan_id", table_name="shot_plans")
        columns = {item["name"] for item in inspect(bind).get_columns("shot_plans")}
        for name in ("director_lineage", "director_plan_version", "director_plan_id"):
            if name in columns:
                op.drop_column("shot_plans", name)
    inspector = inspect(bind)
    if "director_scene_plans" in inspector.get_table_names():
        for name in ("ix_director_scene_plans_payload_hash", "ix_director_scene_plans_scene", "ix_director_scene_plans_episode", "ix_director_scene_plans_plan"):
            try:
                op.drop_index(name, table_name="director_scene_plans")
            except Exception:
                pass
        op.drop_table("director_scene_plans")
    if "director_plans" in inspector.get_table_names():
        for name in ("ix_director_plans_payload_hash", "ix_director_plans_source_script_ir_version_id", "ix_director_plans_status", "ix_director_plans_episode_id"):
            try:
                op.drop_index(name, table_name="director_plans")
            except Exception:
                pass
        op.drop_table("director_plans")
