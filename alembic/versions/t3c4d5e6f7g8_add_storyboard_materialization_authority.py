"""add deterministic Storyboard materialization authority and current pointer"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "t3c4d5e6f7g8"
down_revision = "s2b3c4d5e6f7"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    for column in (
        sa.Column("scene_id", sa.String(), nullable=True),
        sa.Column("plan_shot_id", sa.String(), nullable=True),
        sa.Column("materialization_set_id", sa.Integer(), nullable=True),
        sa.Column("source_shot_plan_id", sa.Integer(), nullable=True),
        sa.Column("source_shot_plan_revision", sa.Integer(), nullable=True),
        sa.Column("source_shot_plan_authority_fingerprint", sa.String(), nullable=True),
        sa.Column("projection_fingerprint", sa.String(), nullable=True),
        sa.Column("materialization_status", sa.String(), nullable=False, server_default="LEGACY"),
    ):
        _add_column("storyboard_shots", column)

    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "storyboard_materialization_sets" not in tables:
        op.create_table(
            "storyboard_materialization_sets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("shot_plan_id", sa.Integer(), nullable=False),
            sa.Column("shot_plan_revision", sa.Integer(), nullable=False),
            sa.Column("shot_plan_payload_hash", sa.String(), nullable=False),
            sa.Column("shot_plan_authority_fingerprint", sa.String(), nullable=False),
            sa.Column("expected_shot_count", sa.Integer(), nullable=False),
            sa.Column("materialized_shot_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ordered_plan_shot_ids", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("set_payload_fingerprint", sa.String(), nullable=False, unique=True),
            sa.Column("materializer_version", sa.String(), nullable=False),
            sa.Column("materializer_policy_version", sa.String(), nullable=False),
            sa.Column("authority_envelope_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="MATERIALIZED"),
            sa.Column("stale_status", sa.String(), nullable=False, server_default="FRESH"),
            sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("activated_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_storyboard_materialization_sets_book_episode", "storyboard_materialization_sets", ["book_id", "episode"])
        op.create_index("ix_storyboard_materialization_sets_scene_id", "storyboard_materialization_sets", ["scene_id"])
        op.create_index("ix_storyboard_materialization_sets_shot_plan_id", "storyboard_materialization_sets", ["shot_plan_id"])
        op.create_index("ix_storyboard_materialization_sets_authority", "storyboard_materialization_sets", ["shot_plan_authority_fingerprint"])

    inspector = inspect(op.get_bind())
    if "storyboard_materialization_pointers" not in set(inspector.get_table_names()):
        op.create_table(
            "storyboard_materialization_pointers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("materialization_set_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("shot_plan_id", sa.Integer(), nullable=False),
            sa.Column("shot_plan_revision", sa.Integer(), nullable=False),
            sa.Column("set_payload_fingerprint", sa.String(), nullable=False),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="MATERIALIZED"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_storyboard_materialization_pointers_book_episode", "storyboard_materialization_pointers", ["book_id", "episode"])
        op.create_index("ix_storyboard_materialization_pointers_scene_id", "storyboard_materialization_pointers", ["scene_id"])
        op.create_index("uq_storyboard_materialization_pointer_scene", "storyboard_materialization_pointers", ["book_id", "episode", "scene_id"], unique=True)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "storyboard_materialization_pointers" in set(inspector.get_table_names()):
        op.drop_table("storyboard_materialization_pointers")
    if "storyboard_materialization_sets" in set(inspector.get_table_names()):
        op.drop_table("storyboard_materialization_sets")
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("storyboard_shots")}
    for name in ("materialization_status", "projection_fingerprint", "source_shot_plan_authority_fingerprint", "source_shot_plan_revision", "source_shot_plan_id", "materialization_set_id", "plan_shot_id", "scene_id"):
        if name in columns:
            op.drop_column("storyboard_shots", name)
