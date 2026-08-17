"""add meta_info to visual makeups

Revision ID: b1c2d3e4f5a6
Revises: a7f9c2d14be1
Create Date: 2026-07-01 19:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b1c2d3e4f5a6"
down_revision = "a7f9c2d14be1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("visual_makeups")}
    if "meta_info" not in columns:
        op.add_column("visual_makeups", sa.Column("meta_info", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("visual_makeups")}
    if "meta_info" in columns:
        op.drop_column("visual_makeups", "meta_info")
