"""add visual asset library fields

Revision ID: 7c441d0a5a62
Revises: 33818b3e29bd
Create Date: 2026-06-28 10:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "7c441d0a5a62"
down_revision: Union[str, Sequence[str], None] = "33818b3e29bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    def add_column_if_missing(table_name: str, column: sa.Column) -> None:
        existing = {item["name"] for item in inspector.get_columns(table_name)}
        if column.name not in existing:
            op.add_column(table_name, column)

    add_column_if_missing("visual_locations", sa.Column("jimeng_ref_name", sa.String(), nullable=False, server_default=""))
    add_column_if_missing("visual_locations", sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""))
    add_column_if_missing("visual_locations", sa.Column("asset_status", sa.String(), nullable=False, server_default="draft"))

    add_column_if_missing("visual_props", sa.Column("jimeng_ref_name", sa.String(), nullable=False, server_default=""))
    add_column_if_missing("visual_props", sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""))
    add_column_if_missing("visual_props", sa.Column("asset_status", sa.String(), nullable=False, server_default="draft"))

    add_column_if_missing("visual_makeups", sa.Column("jimeng_ref_name", sa.String(), nullable=False, server_default=""))
    add_column_if_missing("visual_makeups", sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""))
    add_column_if_missing("visual_makeups", sa.Column("asset_status", sa.String(), nullable=False, server_default="draft"))

    if "visual_reference_assets" not in inspector.get_table_names():
        op.create_table(
            "visual_reference_assets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=True),
            sa.Column("asset_type", sa.String(), nullable=False),
            sa.Column("asset_id", sa.String(), nullable=False),
            sa.Column("asset_name", sa.String(), nullable=True),
            sa.Column("image_url", sa.Text(), nullable=True),
            sa.Column("local_path", sa.Text(), nullable=True),
            sa.Column("reference_token", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("prompt", sa.Text(), nullable=True),
            sa.Column("model", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("meta_info", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("visual_reference_assets")

    op.drop_column("visual_makeups", "asset_status")
    op.drop_column("visual_makeups", "negative_prompt")
    op.drop_column("visual_makeups", "jimeng_ref_name")

    op.drop_column("visual_props", "asset_status")
    op.drop_column("visual_props", "negative_prompt")
    op.drop_column("visual_props", "jimeng_ref_name")

    op.drop_column("visual_locations", "asset_status")
    op.drop_column("visual_locations", "negative_prompt")
    op.drop_column("visual_locations", "jimeng_ref_name")
