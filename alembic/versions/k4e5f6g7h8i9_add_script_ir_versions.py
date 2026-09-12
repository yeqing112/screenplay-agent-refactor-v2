"""add versioned ScriptIR persistence"""

from alembic import op
import sqlalchemy as sa


revision = "k4e5f6g7h8i9"
down_revision = "j3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "script_ir_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("schema_version", sa.String(), nullable=False, server_default="script_ir_v1"),
        sa.Column("source_outline_revision", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fact_snapshot_id", sa.String(), nullable=False, server_default=""),
        sa.Column("source_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("payload_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("validation_status", sa.String(), nullable=False, server_default="needs_review"),
        sa.Column("validation_report", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("previous_revision_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_script_ir_versions_book_id", "script_ir_versions", ["book_id"])
    op.create_index("ix_script_ir_versions_episode", "script_ir_versions", ["episode"])
    op.add_column("scripts", sa.Column("current_script_ir_version_id", sa.Integer(), nullable=True))
    op.create_index("ix_scripts_current_script_ir_version_id", "scripts", ["current_script_ir_version_id"])


def downgrade() -> None:
    op.drop_index("ix_scripts_current_script_ir_version_id", table_name="scripts")
    op.drop_column("scripts", "current_script_ir_version_id")
    op.drop_index("ix_script_ir_versions_episode", table_name="script_ir_versions")
    op.drop_index("ix_script_ir_versions_book_id", table_name="script_ir_versions")
    op.drop_table("script_ir_versions")

