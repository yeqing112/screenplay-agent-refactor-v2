"""add_visual_models

Revision ID: c84a783f96d7
Revises: bf85be21e043
Create Date: 2026-06-13 12:00:16.761216

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c84a783f96d7'
down_revision: Union[str, Sequence[str], None] = 'bf85be21e043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('visual_era_specs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('timeline_start', sa.String(), nullable=True),
    sa.Column('timeline_end', sa.String(), nullable=True),
    sa.Column('time_periods', sa.Text(), nullable=True),
    sa.Column('clothing_spec', sa.Text(), nullable=True),
    sa.Column('color_palette', sa.Text(), nullable=True),
    sa.Column('architecture_spec', sa.Text(), nullable=True),
    sa.Column('environment_spec', sa.Text(), nullable=True),
    sa.Column('prop_spec', sa.Text(), nullable=True),
    sa.Column('color_curve', sa.Text(), nullable=True),
    sa.Column('genre_adapt_rules', sa.Text(), nullable=True),
    sa.Column('raw_periods', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('book_id')
    )
    op.create_table('visual_locations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('book_title', sa.String(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('style', sa.String(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('color_palette', sa.Text(), nullable=True),
    sa.Column('lighting_mood', sa.Text(), nullable=True),
    sa.Column('key_props', sa.Text(), nullable=True),
    sa.Column('episodes', sa.Text(), nullable=True),
    sa.Column('time_period', sa.String(), nullable=True),
    sa.Column('visual_prompt_en', sa.Text(), nullable=True),
    sa.Column('visual_prompt_zh', sa.Text(), nullable=True),
    sa.Column('core_prompt_en', sa.Text(), nullable=True),
    sa.Column('core_prompt_zh', sa.Text(), nullable=True),
    sa.Column('scene_mood_en', sa.Text(), nullable=True),
    sa.Column('scene_mood_zh', sa.Text(), nullable=True),
    sa.Column('importance', sa.String(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('visual_makeups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('book_title', sa.String(), nullable=True),
    sa.Column('episode', sa.Integer(), nullable=False),
    sa.Column('character_name', sa.String(), nullable=False),
    sa.Column('stage_name', sa.String(), nullable=True),
    sa.Column('refined_outfit', sa.Text(), nullable=True),
    sa.Column('refined_accessories', sa.Text(), nullable=True),
    sa.Column('makeup_spec', sa.Text(), nullable=True),
    sa.Column('hair_style', sa.Text(), nullable=True),
    sa.Column('expression_mood', sa.Text(), nullable=True),
    sa.Column('visual_prompt_en', sa.Text(), nullable=True),
    sa.Column('visual_prompt_zh', sa.Text(), nullable=True),
    sa.Column('core_prompt_en', sa.Text(), nullable=True),
    sa.Column('core_prompt_zh', sa.Text(), nullable=True),
    sa.Column('outfit_prompt_en', sa.Text(), nullable=True),
    sa.Column('outfit_prompt_zh', sa.Text(), nullable=True),
    sa.Column('scene_prompt_en', sa.Text(), nullable=True),
    sa.Column('scene_prompt_zh', sa.Text(), nullable=True),
    sa.Column('consistency_notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('visual_props',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('book_title', sa.String(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('associated_characters', sa.Text(), nullable=True),
    sa.Column('episodes', sa.Text(), nullable=True),
    sa.Column('time_period', sa.String(), nullable=True),
    sa.Column('visual_prompt_en', sa.Text(), nullable=True),
    sa.Column('visual_prompt_zh', sa.Text(), nullable=True),
    sa.Column('core_prompt_en', sa.Text(), nullable=True),
    sa.Column('core_prompt_zh', sa.Text(), nullable=True),
    sa.Column('style_ref_en', sa.Text(), nullable=True),
    sa.Column('style_ref_zh', sa.Text(), nullable=True),
    sa.Column('importance', sa.String(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('visual_props')
    op.drop_table('visual_makeups')
    op.drop_table('visual_locations')
    op.drop_table('visual_era_specs')
    # ### end Alembic commands ###
