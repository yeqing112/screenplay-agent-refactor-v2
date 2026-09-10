"""add asset semantic governance review records

Revision ID: e6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-08-31 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e6a7b8c9d0e1"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "asset_semantic_governance_records" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "asset_semantic_governance_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("plan_fingerprint", sa.String(), nullable=False, unique=True),
        sa.Column("source_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("proposal", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_asset_semantic_governance_book_asset", "asset_semantic_governance_records", ["book_id", "asset_type", "asset_id"])


def downgrade() -> None:
    if "asset_semantic_governance_records" in inspect(op.get_bind()).get_table_names():
        op.drop_table("asset_semantic_governance_records")
