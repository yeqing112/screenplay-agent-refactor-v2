"""add public asset storage migration audit records

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "public_asset_storage_migration_records" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "public_asset_storage_migration_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_fingerprint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("storage_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("plan_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_report", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("task_id", sa.String(), nullable=False, unique=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("old_objects_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_public_asset_migration_plan", "public_asset_storage_migration_records", ["plan_fingerprint"])
    op.create_index("ix_public_asset_migration_task", "public_asset_storage_migration_records", ["task_id"])


def downgrade() -> None:
    if "public_asset_storage_migration_records" in inspect(op.get_bind()).get_table_names():
        op.drop_table("public_asset_storage_migration_records")
