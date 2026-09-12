"""add layered prop semantic fields"""

from alembic import op
import sqlalchemy as sa


revision = "i2c3d4e5f6g7"
down_revision = "h1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("canonical_facts", "state_variants", "look_profile"):
        op.add_column("visual_props", sa.Column(name, sa.Text(), nullable=True, server_default="{}"))


def downgrade() -> None:
    for name in ("look_profile", "state_variants", "canonical_facts"):
        op.drop_column("visual_props", name)

