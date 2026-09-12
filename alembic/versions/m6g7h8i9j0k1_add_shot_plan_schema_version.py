"""add ShotPlan schema version marker"""

from alembic import op
import sqlalchemy as sa


revision = "m6g7h8i9j0k1"
down_revision = "l5f6g7h8i9j0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shot_plans", sa.Column("schema_version", sa.String(), nullable=False, server_default="shot_plan_v1"))


def downgrade() -> None:
    op.drop_column("shot_plans", "schema_version")

