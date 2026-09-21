"""add Phase G media validation and official authority foundation

Revision ID: z0a1b2c3d4e5
Revises: y8h9i0j1k2l3
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "z0a1b2c3d4e5"
down_revision = "y8h9i0j1k2l3"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(Inspector.from_engine(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "media_validation_records" not in tables:
        op.create_table(
            "media_validation_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("validation_id", sa.String(), nullable=False),
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("execution_id", sa.String(), nullable=False),
            sa.Column("candidate_fingerprint", sa.String(), nullable=False),
            sa.Column("technical_validation_payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("technical_validation_fingerprint", sa.String(), nullable=False),
            sa.Column("authority_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("authority_snapshot_fingerprint", sa.String(), nullable=False),
            sa.Column("validator_version", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="VALIDATION_PENDING"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["candidate_id"], ["media_candidate_records.candidate_id"], name="fk_media_validation_candidate"
            ),
            sa.ForeignKeyConstraint(
                ["execution_id"], ["generation_execution_records.execution_id"], name="fk_media_validation_execution"
            ),
            sa.UniqueConstraint("validation_id", name="uq_media_validation_validation_id"),
            sa.UniqueConstraint(
                "candidate_fingerprint",
                "authority_snapshot_fingerprint",
                "validator_version",
                name="uq_media_validation_idempotency",
            ),
            sa.CheckConstraint(
                "status IN ('VALIDATION_PENDING','TECHNICALLY_VALID','REVIEW_REQUIRED','REJECTED','STALE')",
                name="ck_media_validation_status",
            ),
        )
        for name, columns in {
            "ix_media_validation_candidate": ["candidate_id"],
            "ix_media_validation_execution": ["execution_id"],
            "ix_media_validation_candidate_fingerprint": ["candidate_fingerprint"],
            "ix_media_validation_status": ["status"],
            "ix_media_validation_created": ["created_at"],
        }.items():
            op.create_index(name, "media_validation_records", columns)

    tables = _table_names(bind)
    if "official_media_versions" not in tables:
        op.create_table(
            "official_media_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("official_media_version_id", sa.String(), nullable=False),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("plan_shot_id", sa.String(), nullable=False, server_default=""),
            sa.Column("media_role", sa.String(), nullable=False),
            sa.Column("media_type", sa.String(), nullable=False),
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("candidate_fingerprint", sa.String(), nullable=False),
            sa.Column("storage_identity", sa.String(), nullable=False),
            sa.Column("checksum_sha256", sa.String(), nullable=False),
            sa.Column("mime_type", sa.String(), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("prompt_ir_version_id", sa.Integer(), nullable=False),
            sa.Column("prompt_ir_payload_hash", sa.String(), nullable=False),
            sa.Column("generation_payload_fingerprint", sa.String(), nullable=False),
            sa.Column("provider_request_fingerprint", sa.String(), nullable=False),
            sa.Column("provider_response_hash", sa.String(), nullable=False),
            sa.Column("validation_id", sa.String(), nullable=False),
            sa.Column("validation_fingerprint", sa.String(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="CURRENT"),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["candidate_id"], ["media_candidate_records.candidate_id"], name="fk_official_media_version_candidate"
            ),
            sa.ForeignKeyConstraint(
                ["validation_id"], ["media_validation_records.validation_id"], name="fk_official_media_version_validation"
            ),
            sa.UniqueConstraint("official_media_version_id", name="uq_official_media_version_identity"),
            sa.UniqueConstraint(
                "book_id",
                "episode",
                "storyboard_shot_id",
                "media_role",
                "revision",
                name="uq_official_media_version_revision",
            ),
            sa.CheckConstraint("revision > 0", name="ck_official_media_version_revision_positive"),
            sa.CheckConstraint("status IN ('CURRENT','SUPERSEDED','STALE')", name="ck_official_media_version_status"),
            sa.CheckConstraint("byte_size >= 0", name="ck_official_media_version_byte_size_nonnegative"),
        )
        for name, columns in {
            "ix_official_media_version_shot": ["book_id", "episode", "storyboard_shot_id"],
            "ix_official_media_version_role": ["media_role"],
            "ix_official_media_version_candidate": ["candidate_id"],
            "ix_official_media_version_candidate_fingerprint": ["candidate_fingerprint"],
            "ix_official_media_version_validation": ["validation_id"],
            "ix_official_media_version_status": ["status"],
        }.items():
            op.create_index(name, "official_media_versions", columns)

    tables = _table_names(bind)
    if "official_media_authorities" not in tables:
        op.create_table(
            "official_media_authorities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("authority_id", sa.String(), nullable=False),
            sa.Column("official_media_version_id", sa.String(), nullable=False),
            sa.Column("authority_envelope_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("lineage_hash", sa.String(), nullable=False),
            sa.Column("validation_fingerprint", sa.String(), nullable=False),
            sa.Column("promotion_fingerprint", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="CURRENT"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["official_media_version_id"],
                ["official_media_versions.official_media_version_id"],
                name="fk_official_media_authority_version",
            ),
            sa.UniqueConstraint("authority_id", name="uq_official_media_authority_identity"),
            sa.UniqueConstraint("official_media_version_id", name="uq_official_media_authority_version"),
            sa.CheckConstraint("status IN ('CURRENT','SUPERSEDED','STALE')", name="ck_official_media_authority_status"),
        )
        for name, columns in {
            "ix_official_media_authority_version": ["official_media_version_id"],
            "ix_official_media_authority_status": ["status"],
            "ix_official_media_authority_lineage": ["lineage_hash"],
            "ix_official_media_authority_promotion": ["promotion_fingerprint"],
        }.items():
            op.create_index(name, "official_media_authorities", columns)

    tables = _table_names(bind)
    if "official_media_pointers" not in tables:
        op.create_table(
            "official_media_pointers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("media_role", sa.String(), nullable=False),
            sa.Column("official_media_version_id", sa.String(), nullable=False),
            sa.Column("authority_id", sa.String(), nullable=False),
            sa.Column("fingerprint", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["official_media_version_id"],
                ["official_media_versions.official_media_version_id"],
                name="fk_official_media_pointer_version",
            ),
            sa.ForeignKeyConstraint(
                ["authority_id"], ["official_media_authorities.authority_id"], name="fk_official_media_pointer_authority"
            ),
            sa.UniqueConstraint(
                "book_id", "episode", "storyboard_shot_id", "media_role", name="uq_official_media_pointer_scope"
            ),
        )
        for name, columns in {
            "ix_official_media_pointer_version": ["official_media_version_id"],
            "ix_official_media_pointer_authority": ["authority_id"],
            "ix_official_media_pointer_fingerprint": ["fingerprint"],
        }.items():
            op.create_index(name, "official_media_pointers", columns)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)
    if "official_media_pointers" in tables:
        for name in (
            "ix_official_media_pointer_fingerprint",
            "ix_official_media_pointer_authority",
            "ix_official_media_pointer_version",
        ):
            op.drop_index(name, table_name="official_media_pointers")
        op.drop_table("official_media_pointers")

    tables = _table_names(bind)
    if "official_media_authorities" in tables:
        for name in (
            "ix_official_media_authority_promotion",
            "ix_official_media_authority_lineage",
            "ix_official_media_authority_status",
            "ix_official_media_authority_version",
        ):
            op.drop_index(name, table_name="official_media_authorities")
        op.drop_table("official_media_authorities")

    tables = _table_names(bind)
    if "official_media_versions" in tables:
        for name in (
            "ix_official_media_version_status",
            "ix_official_media_version_validation",
            "ix_official_media_version_candidate_fingerprint",
            "ix_official_media_version_candidate",
            "ix_official_media_version_role",
            "ix_official_media_version_shot",
        ):
            op.drop_index(name, table_name="official_media_versions")
        op.drop_table("official_media_versions")

    tables = _table_names(bind)
    if "media_validation_records" in tables:
        for name in (
            "ix_media_validation_created",
            "ix_media_validation_status",
            "ix_media_validation_candidate_fingerprint",
            "ix_media_validation_execution",
            "ix_media_validation_candidate",
        ):
            op.drop_index(name, table_name="media_validation_records")
        op.drop_table("media_validation_records")
