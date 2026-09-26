"""Add explicit media candidate validation and promotion review records.

Revision ID: c8d9e0f1a2b3
Revises: b2c3d4e5f6g7

The migration extends the existing Phase F/G media tables.  It does not
create a second asset system: OfficialMediaVersion and OfficialMediaPointer
remain the only production authority rows.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "c8d9e0f1a2b3"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(Inspector.from_engine(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {item["name"] for item in Inspector.from_engine(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "media_candidate_records" in tables:
        columns = _columns(bind, "media_candidate_records")
        if "validation_status" not in columns:
            op.add_column(
                "media_candidate_records",
                sa.Column("validation_status", sa.String(), nullable=False, server_default=sa.text("'PENDING'")),
            )
        if "metadata_json" not in columns:
            op.add_column(
                "media_candidate_records",
                sa.Column("metadata_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            )

    if "media_promotion_records" not in _tables(bind):
        op.create_table(
            "media_promotion_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("promotion_id", sa.String(), nullable=False),
            sa.Column("candidate_id", sa.String(), nullable=False),
            sa.Column("validation_id", sa.String(), nullable=False),
            sa.Column("execution_id", sa.String(), nullable=False),
            sa.Column("review_status", sa.String(), nullable=False, server_default=sa.text("'REVIEW_REQUIRED'")),
            sa.Column("decision", sa.String(), nullable=True),
            sa.Column("reviewer", sa.String(), nullable=False, server_default=sa.text("''")),
            sa.Column("review_notes", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("official_media_version_id", sa.String(), nullable=True),
            sa.Column("authority_id", sa.String(), nullable=True),
            sa.Column("promotion_fingerprint", sa.String(), nullable=False, server_default=sa.text("''")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["candidate_id"], ["media_candidate_records.candidate_id"], name="fk_media_promotion_candidate", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["validation_id"], ["media_validation_records.validation_id"], name="fk_media_promotion_validation", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["execution_id"], ["generation_execution_records.execution_id"], name="fk_media_promotion_execution", ondelete="RESTRICT"),
            sa.UniqueConstraint("promotion_id", name="uq_media_promotion_identity"),
            sa.UniqueConstraint("candidate_id", name="uq_media_promotion_candidate"),
            sa.CheckConstraint("review_status IN ('REVIEW_REQUIRED','APPROVED','REJECTED','REQUEST_CHANGE')", name="ck_media_promotion_review_status"),
            sa.CheckConstraint("decision IS NULL OR decision IN ('APPROVE','REJECT','REQUEST_CHANGE')", name="ck_media_promotion_decision"),
        )
        for name, columns in {
            "ix_media_promotion_candidate": ["candidate_id"],
            "ix_media_promotion_validation": ["validation_id"],
            "ix_media_promotion_execution": ["execution_id"],
            "ix_media_promotion_review_status": ["review_status"],
            "ix_media_promotion_official_version": ["official_media_version_id"],
            "ix_media_promotion_authority": ["authority_id"],
            "ix_media_promotion_created": ["created_at"],
        }.items():
            op.create_index(name, "media_promotion_records", columns)


def downgrade() -> None:
    bind = op.get_bind()
    if "media_promotion_records" in _tables(bind):
        for name in (
            "ix_media_promotion_created",
            "ix_media_promotion_authority",
            "ix_media_promotion_official_version",
            "ix_media_promotion_review_status",
            "ix_media_promotion_execution",
            "ix_media_promotion_validation",
            "ix_media_promotion_candidate",
        ):
            try:
                op.drop_index(name, table_name="media_promotion_records")
            except Exception:
                pass
        op.drop_table("media_promotion_records")
    if "media_candidate_records" in _tables(bind):
        columns = _columns(bind, "media_candidate_records")
        with op.batch_alter_table("media_candidate_records") as batch:
            if "metadata_json" in columns:
                batch.drop_column("metadata_json")
            if "validation_status" in columns:
                batch.drop_column("validation_status")
