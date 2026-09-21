"""add Phase F generation execution and media candidate records

Revision ID: y8h9i0j1k2l3
Revises: x7g8h9i0j1k2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "y8h9i0j1k2l3"
down_revision = "x7g8h9i0j1k2"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(Inspector.from_engine(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)
    if "generation_execution_records" not in tables:
        op.create_table(
            "generation_execution_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("execution_id", sa.String(), nullable=False),
            sa.Column("schema_version", sa.String(), nullable=False, server_default="generation_execution_request_v1"),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("plan_shot_id", sa.String(), nullable=False, server_default=""),
            sa.Column("execution_mode", sa.String(), nullable=False, server_default="PREVIEW"),
            sa.Column("status", sa.String(), nullable=False, server_default="PREVIEWED"),
            sa.Column("target_media", sa.String(), nullable=False, server_default="IMAGE"),
            sa.Column("prompt_ir_version_id", sa.Integer(), nullable=False),
            sa.Column("prompt_ir_authority_id", sa.Integer(), nullable=False),
            sa.Column("prompt_ir_payload_hash", sa.String(), nullable=False),
            sa.Column("generation_payload_fingerprint", sa.String(), nullable=False),
            sa.Column("generation_policy_fingerprint", sa.String(), nullable=False),
            sa.Column("model_profile_id", sa.String(), nullable=False),
            sa.Column("model_profile_fingerprint", sa.String(), nullable=False),
            sa.Column("provider_adapter_id", sa.String(), nullable=False),
            sa.Column("provider_adapter_version", sa.String(), nullable=False),
            sa.Column("reference_bindings_fingerprint", sa.String(), nullable=False, server_default=""),
            sa.Column("provider_request_fingerprint", sa.String(), nullable=False),
            sa.Column("request_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("confirmation_binding_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("provider", sa.String(), nullable=False, server_default=""),
            sa.Column("model", sa.String(), nullable=False, server_default=""),
            sa.Column("provider_request_id", sa.String(), nullable=False, server_default=""),
            sa.Column("provider_task_id", sa.String(), nullable=False, server_default=""),
            sa.Column("provider_response_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("logical_provider_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("transport_retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("failure_code", sa.String(), nullable=False, server_default=""),
            sa.Column("failure_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("official_promotion_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("candidate_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("execution_id", name="uq_generation_execution_records_execution_id"),
            sa.UniqueConstraint("provider_request_fingerprint", name="uq_generation_execution_provider_request_fingerprint"),
        )
        for name, columns in {
            "ix_generation_execution_records_execution_id": ["execution_id"],
            "ix_generation_execution_records_book_id": ["book_id"],
            "ix_generation_execution_records_episode": ["episode"],
            "ix_generation_execution_records_shot": ["storyboard_shot_id"],
            "ix_generation_execution_records_status": ["status"],
            "ix_generation_execution_records_prompt_ir": ["prompt_ir_version_id"],
            "ix_generation_execution_records_payload": ["generation_payload_fingerprint"],
            "ix_generation_execution_records_provider_request": ["provider_request_fingerprint"],
            "ix_generation_execution_records_created": ["created_at"],
        }.items():
            op.create_index(name, "generation_execution_records", columns)

    tables = _table_names(bind)
    if "media_candidate_records" not in tables:
        op.create_table(
            "media_candidate_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("execution_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="MEDIA_CANDIDATE"),
            sa.Column("media_type", sa.String(), nullable=False),
            sa.Column("storage_identity", sa.String(), nullable=False),
            sa.Column("storage_reference_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("checksum_sha256", sa.String(), nullable=False),
            sa.Column("mime_type", sa.String(), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("prompt_ir_version_id", sa.Integer(), nullable=False),
            sa.Column("prompt_ir_payload_hash", sa.String(), nullable=False),
            sa.Column("generation_payload_fingerprint", sa.String(), nullable=False),
            sa.Column("model_profile_id", sa.String(), nullable=False),
            sa.Column("model_profile_fingerprint", sa.String(), nullable=False),
            sa.Column("provider_request_fingerprint", sa.String(), nullable=False),
            sa.Column("provider_response_hash", sa.String(), nullable=False),
            sa.Column("provider_task_id", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("candidate_id", name="uq_media_candidate_records_candidate_id"),
            sa.UniqueConstraint("execution_id", name="uq_media_candidate_execution_id"),
            sa.UniqueConstraint("storage_identity", name="uq_media_candidate_storage_identity"),
        )
        for name, columns in {
            "ix_media_candidate_records_candidate_id": ["candidate_id"],
            "ix_media_candidate_records_execution_id": ["execution_id"],
            "ix_media_candidate_records_status": ["status"],
            "ix_media_candidate_records_storage_identity": ["storage_identity"],
            "ix_media_candidate_records_checksum": ["checksum_sha256"],
            "ix_media_candidate_records_prompt_ir": ["prompt_ir_version_id"],
            "ix_media_candidate_records_payload": ["generation_payload_fingerprint"],
            "ix_media_candidate_records_provider_request": ["provider_request_fingerprint"],
            "ix_media_candidate_records_created": ["created_at"],
        }.items():
            op.create_index(name, "media_candidate_records", columns)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)
    if "media_candidate_records" in tables:
        for name in (
            "ix_media_candidate_records_created",
            "ix_media_candidate_records_provider_request",
            "ix_media_candidate_records_payload",
            "ix_media_candidate_records_prompt_ir",
            "ix_media_candidate_records_checksum",
            "ix_media_candidate_records_storage_identity",
            "ix_media_candidate_records_status",
            "ix_media_candidate_records_execution_id",
            "ix_media_candidate_records_candidate_id",
        ):
            op.drop_index(name, table_name="media_candidate_records")
        op.drop_table("media_candidate_records")
    if "generation_execution_records" in tables:
        for name in (
            "ix_generation_execution_records_created",
            "ix_generation_execution_records_provider_request",
            "ix_generation_execution_records_payload",
            "ix_generation_execution_records_prompt_ir",
            "ix_generation_execution_records_status",
            "ix_generation_execution_records_shot",
            "ix_generation_execution_records_episode",
            "ix_generation_execution_records_book_id",
            "ix_generation_execution_records_execution_id",
        ):
            op.drop_index(name, table_name="generation_execution_records")
        op.drop_table("generation_execution_records")
