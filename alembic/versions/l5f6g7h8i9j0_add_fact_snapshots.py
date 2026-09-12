"""add versioned fact snapshots and fact records"""

from alembic import op
import sqlalchemy as sa


revision = "l5f6g7h8i9j0"
down_revision = "k4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fact_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("source_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("records_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("validation_report", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("previous_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_fact_snapshots_book_id", "fact_snapshots", ["book_id"])
    op.create_index("ix_fact_snapshots_episode", "fact_snapshots", ["episode"])
    op.create_table(
        "fact_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("fact_id", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(), nullable=False, server_default=""),
        sa.Column("subject_id", sa.String(), nullable=False, server_default=""),
        sa.Column("predicate", sa.String(), nullable=False, server_default=""),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="null"),
        sa.Column("scope", sa.String(), nullable=False, server_default="global"),
        sa.Column("authority", sa.String(), nullable=False, server_default="derived_fact"),
        sa.Column("status", sa.String(), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("conflict_group", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_fact_records_snapshot_id", "fact_records", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_fact_records_snapshot_id", table_name="fact_records")
    op.drop_table("fact_records")
    op.drop_index("ix_fact_snapshots_episode", table_name="fact_snapshots")
    op.drop_index("ix_fact_snapshots_book_id", table_name="fact_snapshots")
    op.drop_table("fact_snapshots")
