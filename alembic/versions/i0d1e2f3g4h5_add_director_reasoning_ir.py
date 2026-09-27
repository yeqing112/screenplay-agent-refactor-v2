"""Add DirectorReasoningIR, StoryBeat and VisualDecision authority tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "i0d1e2f3g4h5"
down_revision = "h9c0d1e2f3g4"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(inspect(bind).get_table_names())


def _add_columns(table, columns):
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "director_reasonings" not in tables:
        op.create_table(
            "director_reasonings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("episode_id", sa.String(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="DRAFT"),
            sa.Column("reasoning_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("source_script_ir_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("source_fact_snapshot_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("compiled_shot_plan_ids", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("lineage_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("episode_id", "version", name="uq_director_reasoning_episode_version"),
            sa.CheckConstraint("version >= 1", name="ck_director_reasoning_version_positive"),
            sa.CheckConstraint("status IN ('DRAFT','REVIEW_REQUIRED','COMPILED','SUPERSEDED','ROLLED_BACK','REJECTED')", name="ck_director_reasoning_status"),
        )
        op.create_index("ix_director_reasonings_episode", "director_reasonings", ["episode_id"])
        op.create_index("ix_director_reasonings_status", "director_reasonings", ["status"])
        op.create_index("ix_director_reasonings_payload", "director_reasonings", ["payload_hash"])

    tables = _tables(bind)
    if "director_story_beats" not in tables:
        op.create_table(
            "director_story_beats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("director_reasoning_id", sa.Integer(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False, server_default=""),
            sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
            sa.Column("emotion", sa.Text(), nullable=False, server_default=""),
            sa.Column("visual_goal", sa.Text(), nullable=False, server_default=""),
            sa.Column("character_refs", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("shot_refs", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("director_reasoning_id", "sequence", name="uq_director_story_beat_sequence"),
            sa.CheckConstraint("sequence >= 1", name="ck_director_story_beat_sequence_positive"),
            sa.ForeignKeyConstraint(["director_reasoning_id"], ["director_reasonings.id"], ondelete="RESTRICT"),
        )
        for name, fields in {"ix_director_story_beats_reasoning": ["director_reasoning_id"], "ix_director_story_beats_scene": ["scene_id"]}.items():
            op.create_index(name, "director_story_beats", fields)

    tables = _tables(bind)
    if "director_visual_decisions" not in tables:
        op.create_table(
            "director_visual_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("director_reasoning_id", sa.Integer(), nullable=False),
            sa.Column("story_beat_sequence", sa.Integer(), nullable=False),
            sa.Column("visual_style_id", sa.String(), nullable=False, server_default=""),
            sa.Column("camera_strategy", sa.Text(), nullable=False, server_default=""),
            sa.Column("lighting_strategy", sa.Text(), nullable=False, server_default=""),
            sa.Column("color_strategy", sa.Text(), nullable=False, server_default=""),
            sa.Column("composition_strategy", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("director_reasoning_id", "story_beat_sequence", name="uq_director_visual_decision_beat"),
            sa.CheckConstraint("story_beat_sequence >= 1", name="ck_director_visual_decision_sequence_positive"),
            sa.ForeignKeyConstraint(["director_reasoning_id"], ["director_reasonings.id"], ondelete="RESTRICT"),
        )
        for name, fields in {"ix_director_visual_decisions_reasoning": ["director_reasoning_id"], "ix_director_visual_decisions_style": ["visual_style_id"]}.items():
            op.create_index(name, "director_visual_decisions", fields)

    _add_columns("shot_plans", [
        sa.Column("director_reasoning_id", sa.Integer(), nullable=True),
        sa.Column("director_reasoning_version", sa.Integer(), nullable=True),
        sa.Column("reasoning_lineage", sa.Text(), nullable=False, server_default="{}"),
    ])
    _add_columns("production_generation_intents", [
        sa.Column("director_reasoning_id", sa.Integer(), nullable=True),
        sa.Column("director_reasoning_version", sa.Integer(), nullable=True),
        sa.Column("reasoning_lineage", sa.Text(), nullable=False, server_default="{}"),
    ])
    for table, name, field in (("shot_plans", "ix_shot_plans_director_reasoning_id", "director_reasoning_id"), ("production_generation_intents", "ix_generation_intents_director_reasoning_id", "director_reasoning_id")):
        if table not in inspect(bind).get_table_names():
            continue
        indexes = {item["name"] for item in inspect(bind).get_indexes(table)}
        if name not in indexes:
            op.create_index(name, table, [field])


def downgrade() -> None:
    bind = op.get_bind()
    for table, name in (("production_generation_intents", "ix_generation_intents_director_reasoning_id"), ("shot_plans", "ix_shot_plans_director_reasoning_id")):
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass
    for table, names in (("production_generation_intents", ("reasoning_lineage", "director_reasoning_version", "director_reasoning_id")), ("shot_plans", ("reasoning_lineage", "director_reasoning_version", "director_reasoning_id"))):
        columns = {item["name"] for item in inspect(bind).get_columns(table)}
        for name in names:
            if name in columns:
                op.drop_column(table, name)
    inspector = inspect(bind)
    if "director_visual_decisions" in inspector.get_table_names():
        for name in ("ix_director_visual_decisions_style", "ix_director_visual_decisions_reasoning"):
            try: op.drop_index(name, table_name="director_visual_decisions")
            except Exception: pass
        op.drop_table("director_visual_decisions")
    if "director_story_beats" in inspector.get_table_names():
        for name in ("ix_director_story_beats_scene", "ix_director_story_beats_reasoning"):
            try: op.drop_index(name, table_name="director_story_beats")
            except Exception: pass
        op.drop_table("director_story_beats")
    if "director_reasonings" in inspector.get_table_names():
        for name in ("ix_director_reasonings_payload", "ix_director_reasonings_status", "ix_director_reasonings_episode"):
            try: op.drop_index(name, table_name="director_reasonings")
            except Exception: pass
        op.drop_table("director_reasonings")
