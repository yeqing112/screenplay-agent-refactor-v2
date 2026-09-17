"""add SceneBlocking production authority envelope and current pointer"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "r1a2b3c4d5e6"
down_revision = "q0k1l2m3n4o5"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if column.name not in {item["name"] for item in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    # Stable scene identity for production asset resolution.  Existing assets
    # retain an empty identity and stay advisory until explicitly rebound.
    _add_column("visual_locations", sa.Column("scene_id", sa.String(), nullable=False, server_default=""))
    for column in (
        sa.Column("source_script_ir_version_id", sa.Integer(), nullable=True),
        sa.Column("source_script_ir_revision", sa.Integer(), nullable=True),
        sa.Column("source_script_ir_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_script_authority_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("treatment_authority_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("treatment_payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fact_snapshot_id", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fact_snapshot_revision", sa.Integer(), nullable=True),
        sa.Column("source_fact_snapshot_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_immutable_raw_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("contract_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("validation_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("authority_envelope_id", sa.Integer(), nullable=True),
        sa.Column("qualification_state", sa.String(), nullable=False, server_default="DRAFT"),
        sa.Column("stale_status", sa.String(), nullable=False, server_default="UNKNOWN"),
        sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("asset_authority", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("continuity_state", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source_lineage", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
    ):
        _add_column("scene_blockings", column)

    inspector = inspect(op.get_bind())
    if "scene_blocking_authorities" not in inspector.get_table_names():
        op.create_table(
            "scene_blocking_authorities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("blocking_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("blocking_revision", sa.Integer(), nullable=False),
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
        op.create_index("ix_scene_blocking_authorities_book_episode", "scene_blocking_authorities", ["book_id", "episode"])
        op.create_index("ix_scene_blocking_authorities_scene_id", "scene_blocking_authorities", ["scene_id"])
        op.create_index("ix_scene_blocking_authorities_blocking_id", "scene_blocking_authorities", ["blocking_id"])
    inspector = inspect(op.get_bind())
    if "scene_blocking_pointers" not in inspector.get_table_names():
        op.create_table(
            "scene_blocking_pointers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("blocking_id", sa.Integer(), nullable=False),
            sa.Column("blocking_revision", sa.Integer(), nullable=False),
            sa.Column("authority_envelope_fingerprint", sa.String(), nullable=False),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="PRODUCTION_QUALIFIED"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_scene_blocking_pointers_book_episode", "scene_blocking_pointers", ["book_id", "episode"])
        op.create_index("ix_scene_blocking_pointers_scene_id", "scene_blocking_pointers", ["scene_id"])
        op.create_index("uq_scene_blocking_pointer_scene", "scene_blocking_pointers", ["book_id", "episode", "scene_id"], unique=True)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "scene_blocking_pointers" in inspector.get_table_names():
        op.drop_table("scene_blocking_pointers")
    if "scene_blocking_authorities" in inspector.get_table_names():
        op.drop_table("scene_blocking_authorities")
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("scene_blockings")}
    for name in (
        "activated_at", "source_lineage", "continuity_state", "asset_authority", "stale_reasons",
        "stale_status", "qualification_state", "authority_envelope_id", "payload_hash",
        "validation_fingerprint", "contract_fingerprint", "source_immutable_raw_hash",
        "source_fact_snapshot_hash", "source_fact_snapshot_revision", "source_fact_snapshot_id",
        "treatment_payload_hash", "treatment_authority_fingerprint", "source_script_authority_fingerprint",
        "source_script_ir_hash", "source_script_ir_revision", "source_script_ir_version_id",
    ):
        if name in columns:
            op.drop_column("scene_blockings", name)
    if "scene_id" in {item["name"] for item in inspect(op.get_bind()).get_columns("visual_locations")}:
        op.drop_column("visual_locations", "scene_id")
