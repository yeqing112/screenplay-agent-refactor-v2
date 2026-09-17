"""add DirectorTreatment authority envelope and current pointer"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "p9j0k1l2m3n4"
down_revision = "o8i9j0k1l2m3"
branch_labels = None
depends_on = None


def _add_column(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column("scene_blockings", sa.Column("scene_id", sa.String(), nullable=False, server_default=""))
    _add_column("shot_plans", sa.Column("scene_id", sa.String(), nullable=False, server_default=""))
    for column in (
        sa.Column("scene_id", sa.String(), nullable=False, server_default=""),
        sa.Column("source_script_ir_version_id", sa.Integer(), nullable=True),
        sa.Column("source_script_ir_revision", sa.Integer(), nullable=True),
        sa.Column("source_script_ir_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_script_authority_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fact_snapshot_id", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fact_snapshot_revision", sa.Integer(), nullable=True),
        sa.Column("source_fact_snapshot_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("source_constraints", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("director_decisions", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("unknown_unresolved", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("authority_envelope_id", sa.Integer(), nullable=True),
        sa.Column("qualification_state", sa.String(), nullable=False, server_default="DRAFT"),
        sa.Column("stale_status", sa.String(), nullable=False, server_default="UNKNOWN"),
        sa.Column("stale_reasons", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
    ):
        _add_column("director_treatments", column)
    op.create_index("ix_director_treatments_scene_id", "director_treatments", ["scene_id"])

    inspector = inspect(op.get_bind())
    if "director_treatment_authorities" not in inspector.get_table_names():
        op.create_table(
            "director_treatment_authorities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("treatment_id", sa.Integer(), nullable=False, unique=True),
            sa.Column("treatment_revision", sa.Integer(), nullable=False),
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
        op.create_index("ix_director_treatment_authorities_book_episode", "director_treatment_authorities", ["book_id", "episode"])
        op.create_index("ix_director_treatment_authorities_scene_id", "director_treatment_authorities", ["scene_id"])
        op.create_index("ix_director_treatment_authorities_treatment_id", "director_treatment_authorities", ["treatment_id"])
    if "director_treatment_pointers" not in inspector.get_table_names():
        op.create_table(
            "director_treatment_pointers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("scene_id", sa.String(), nullable=False),
            sa.Column("treatment_id", sa.Integer(), nullable=False),
            sa.Column("treatment_revision", sa.Integer(), nullable=False),
            sa.Column("authority_envelope_fingerprint", sa.String(), nullable=False),
            sa.Column("qualification_state", sa.String(), nullable=False, server_default="PRODUCTION_QUALIFIED"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_director_treatment_pointers_book_episode", "director_treatment_pointers", ["book_id", "episode"])
        op.create_index("ix_director_treatment_pointers_scene_id", "director_treatment_pointers", ["scene_id"])
        op.create_index("uq_director_treatment_pointer_scene", "director_treatment_pointers", ["book_id", "episode", "scene_id"], unique=True)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "director_treatment_pointers" in inspector.get_table_names():
        op.drop_table("director_treatment_pointers")
    if "director_treatment_authorities" in inspector.get_table_names():
        op.drop_table("director_treatment_authorities")
    for table, name in (("director_treatments", "activated_at"), ("director_treatments", "approved_at"), ("director_treatments", "stale_reasons"), ("director_treatments", "stale_status"), ("director_treatments", "qualification_state"), ("director_treatments", "authority_envelope_id"), ("director_treatments", "payload_hash"), ("director_treatments", "source_fact_snapshot_hash"), ("director_treatments", "source_fact_snapshot_revision"), ("director_treatments", "source_fact_snapshot_id"), ("director_treatments", "source_script_authority_fingerprint"), ("director_treatments", "source_script_ir_hash"), ("director_treatments", "source_script_ir_revision"), ("director_treatments", "source_script_ir_version_id"), ("director_treatments", "unknown_unresolved"), ("director_treatments", "director_decisions"), ("director_treatments", "source_constraints"), ("director_treatments", "scene_id"), ("scene_blockings", "scene_id"), ("shot_plans", "scene_id")):
        if name == "__none__":
            continue
        if name in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
            op.drop_column(table, name)
