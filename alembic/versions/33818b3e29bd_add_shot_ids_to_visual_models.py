"""add_shot_ids_to_visual_models

Revision ID: 33818b3e29bd
Revises: ab37bde7a5e2
Create Date: 2026-06-22 10:14:09.963826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = '33818b3e29bd'
down_revision: Union[str, Sequence[str], None] = 'ab37bde7a5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in ('visual_makeups', 'visual_locations', 'visual_props'):
        columns = {item['name'] for item in inspect(bind).get_columns(table)}
        if 'shot_ids' not in columns:
            op.add_column(table, sa.Column('shot_ids', sa.Text(), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('visual_makeups', 'shot_ids')
    op.drop_column('visual_locations', 'shot_ids')
    op.drop_column('visual_props', 'shot_ids')
