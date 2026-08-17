"""v2 baseline

Revision ID: bf85be21e043
Revises: 
Create Date: 2026-06-12 15:48:21.668494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bf85be21e043"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables from models schema."""
    from models import Base, engine
    Base.metadata.create_all(engine)


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("character_stages")
    op.drop_table("character_profiles")
    op.drop_table("qa_results")
    op.drop_table("scripts")
    op.drop_table("episode_outlines")
    op.drop_table("book_bibles")
    op.drop_table("chapters")
    op.drop_table("books")
    op.drop_table("kv")
