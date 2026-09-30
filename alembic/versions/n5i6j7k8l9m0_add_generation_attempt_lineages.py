"""Add durable retry/regenerate business attempt lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "n5i6j7k8l9m0"
down_revision = "m4h5i6j7k8l9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "generation_execution_attempt_lineages" in set(inspect(bind).get_table_names()):
        return
    op.create_table(
        "generation_execution_attempt_lineages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attempt_lineage_id", sa.String(), nullable=False),
        sa.Column("operation_idempotency_key", sa.String(), nullable=False),
        sa.Column("operation_kind", sa.String(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
        sa.Column("target_media", sa.String(), nullable=False),
        sa.Column("source_execution_id", sa.String(), nullable=False),
        sa.Column("root_execution_id", sa.String(), nullable=False),
        sa.Column("produced_execution_id", sa.String(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("variant_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_candidate_id", sa.String(), nullable=True),
        sa.Column("source_official_media_version_id", sa.String(), nullable=True),
        sa.Column("source_snapshot_fingerprint", sa.String(), nullable=False),
        sa.Column("operation_identity_fingerprint", sa.String(), nullable=False),
        sa.Column("confirmation_binding_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PREVIEWED"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["source_execution_id"], ["generation_execution_records.execution_id"], name="fk_generation_attempt_source_execution", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["root_execution_id"], ["generation_execution_records.execution_id"], name="fk_generation_attempt_root_execution", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["produced_execution_id"], ["generation_execution_records.execution_id"], name="fk_generation_attempt_produced_execution", ondelete="RESTRICT"),
        sa.UniqueConstraint("attempt_lineage_id", name="uq_generation_attempt_lineage_id"),
        sa.UniqueConstraint("book_id", "operation_idempotency_key", name="uq_generation_attempt_operation_key"),
        sa.UniqueConstraint("produced_execution_id", name="uq_generation_attempt_produced_execution"),
        sa.CheckConstraint("operation_kind IN ('RETRY','REGENERATE')", name="ck_generation_attempt_operation_kind"),
        sa.CheckConstraint("target_media IN ('IMAGE','VIDEO')", name="ck_generation_attempt_target_media"),
        sa.CheckConstraint("status IN ('PREVIEWED','BOUND','CANCELLED')", name="ck_generation_attempt_status"),
        sa.CheckConstraint("attempt_number >= 1", name="ck_generation_attempt_number"),
        sa.CheckConstraint("variant_index >= 0", name="ck_generation_attempt_variant_index"),
    )
    for name, columns in {
        "ix_generation_attempt_lineage_id": ["attempt_lineage_id"],
        "ix_generation_attempt_operation_kind": ["operation_kind"],
        "ix_generation_attempt_book": ["book_id"],
        "ix_generation_attempt_episode": ["episode"],
        "ix_generation_attempt_shot": ["storyboard_shot_id"],
        "ix_generation_attempt_target_media": ["target_media"],
        "ix_generation_attempt_source_execution": ["source_execution_id"],
        "ix_generation_attempt_root_execution": ["root_execution_id"],
        "ix_generation_attempt_produced_execution": ["produced_execution_id"],
        "ix_generation_attempt_source_candidate": ["source_candidate_id"],
        "ix_generation_attempt_source_official": ["source_official_media_version_id"],
        "ix_generation_attempt_source_snapshot": ["source_snapshot_fingerprint"],
        "ix_generation_attempt_operation_identity": ["operation_identity_fingerprint"],
        "ix_generation_attempt_status": ["status"],
    }.items():
        op.create_index(name, "generation_execution_attempt_lineages", columns)


def downgrade() -> None:
    bind = op.get_bind()
    if "generation_execution_attempt_lineages" not in set(inspect(bind).get_table_names()):
        return
    for name in (
        "ix_generation_attempt_status", "ix_generation_attempt_operation_identity",
        "ix_generation_attempt_source_snapshot", "ix_generation_attempt_source_official",
        "ix_generation_attempt_source_candidate", "ix_generation_attempt_produced_execution",
        "ix_generation_attempt_root_execution", "ix_generation_attempt_source_execution",
        "ix_generation_attempt_target_media", "ix_generation_attempt_shot",
        "ix_generation_attempt_episode", "ix_generation_attempt_book",
        "ix_generation_attempt_operation_kind", "ix_generation_attempt_lineage_id",
    ):
        op.drop_index(name, table_name="generation_execution_attempt_lineages")
    op.drop_table("generation_execution_attempt_lineages")
