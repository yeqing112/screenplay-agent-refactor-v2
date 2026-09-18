"""add ShotPlan production authority envelope and current pointer"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "s2b3c4d5e6f7"
down_revision = "r1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    for column in (
        sa.Column("source_script_ir_version_id", sa.Integer(), nullable=True),
        sa.Column("source_script_ir_revision", sa.Integer(), nullable=True),
        sa.Column("source_script_ir_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_script_authority_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("treatment_authority_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("treatment_payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("blocking_authority_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("blocking_payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fact_snapshot_id", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fact_snapshot_revision", sa.Integer(), nullable=True),
        sa.Column("source_fact_snapshot_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_immutable_raw_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("contract_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("executability_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("continuity_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("authority_envelope_id", sa.Integer(), nullable=True),
        sa.Column("qualification_state", sa.String(), nullable=False, server_default="DRAFT"),
        sa.Column("stale_status", sa.String(), nullable=False, server_default="UNKNOWN"),
        sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_lineage", sa.Text(), nullable=False, server_default="{}"),
    ):
        _add_column("shot_plans", column)

    inspector = inspect(op.get_bind())
    if "shot_plan_authorities" not in inspector.get_table_names():
        op.create_table(
            "shot_plan_authorities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("shot_plan_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("plan_revision", sa.Integer(), nullable=False),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("envelope_fingerprint", sa.String(), nullable=False, unique=True),
            sa.Column("envelope_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="AUTHORITY_BOUND"),
            sa.Column("stale_status", sa.String(), nullable=False, server_default="FRESH"),
            sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("activated_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_shot_plan_authorities_book_episode", "shot_plan_authorities", ["book_id", "episode"])
        op.create_index("ix_shot_plan_authorities_scene_id", "shot_plan_authorities", ["scene_id"])
        op.create_index("ix_shot_plan_authorities_shot_plan_id", "shot_plan_authorities", ["shot_plan_id"])
    inspector = inspect(op.get_bind())
    if "shot_plan_pointers" not in inspector.get_table_names():
        op.create_table(
            "shot_plan_pointers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("shot_plan_id", sa.Integer(), nullable=False),
            sa.Column("plan_revision", sa.Integer(), nullable=False),
            sa.Column("authority_envelope_fingerprint", sa.String(), nullable=False),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="PRODUCTION_QUALIFIED"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_shot_plan_pointers_book_episode", "shot_plan_pointers", ["book_id", "episode"])
        op.create_index("ix_shot_plan_pointers_scene_id", "shot_plan_pointers", ["scene_id"])
        op.create_index("uq_shot_plan_pointer_scene", "shot_plan_pointers", ["book_id", "episode", "scene_id"], unique=True)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "shot_plan_pointers" in inspector.get_table_names():
        op.drop_table("shot_plan_pointers")
    if "shot_plan_authorities" in inspector.get_table_names():
        op.drop_table("shot_plan_authorities")
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("shot_plans")}
    for name in (
        "source_lineage", "stale_reasons", "stale_status", "qualification_state", "authority_envelope_id",
        "payload_hash", "continuity_fingerprint", "executability_fingerprint", "contract_fingerprint",
        "source_immutable_raw_hash", "source_fact_snapshot_hash", "source_fact_snapshot_revision", "source_fact_snapshot_id",
        "blocking_payload_hash", "blocking_authority_fingerprint", "treatment_payload_hash", "treatment_authority_fingerprint",
        "source_script_authority_fingerprint", "source_script_ir_hash", "source_script_ir_revision", "source_script_ir_version_id",
    ):
        if name in columns:
            op.drop_column("shot_plans", name)
