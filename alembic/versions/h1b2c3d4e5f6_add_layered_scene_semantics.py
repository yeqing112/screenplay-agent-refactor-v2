"""add layered scene semantic fields"""

from alembic import op
import sqlalchemy as sa


revision = "h1b2c3d4e5f6"
down_revision = "g0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("canonical_facts", "state_variants", "look_profile", "board_spec"):
        op.add_column("visual_locations", sa.Column(name, sa.Text(), nullable=True, server_default="{}"))


def downgrade() -> None:
    for name in ("board_spec", "look_profile", "state_variants", "canonical_facts"):
        op.drop_column("visual_locations", name)
