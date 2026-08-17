"""add_shot_ids_to_visual_models

Revision ID: 33818b3e29bd
Revises: ab37bde7a5e2
Create Date: 2026-06-22 10:14:09.963826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '33818b3e29bd'
down_revision: Union[str, Sequence[str], None] = 'ab37bde7a5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('visual_makeups', sa.Column('shot_ids', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('visual_locations', sa.Column('shot_ids', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('visual_props', sa.Column('shot_ids', sa.Text(), nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('visual_makeups', 'shot_ids')
    op.drop_column('visual_locations', 'shot_ids')
    op.drop_column('visual_props', 'shot_ids')
