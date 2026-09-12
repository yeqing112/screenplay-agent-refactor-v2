"""add unified artifact state and workflow profile fields"""

from alembic import op
import sqlalchemy as sa


revision = "j3d4e5f6g7h8"
down_revision = "i2c3d4e5f6g7"
branch_labels = None
depends_on = None


TABLES = ("scripts", "storyboard_shots", "director_treatments", "scene_blockings", "shot_plans")


def upgrade() -> None:
    defaults = {
        "execution_status": "queued",
        "quality_status": "draft",
        "production_status": "blocked",
        "workflow_profile": "creative_draft",
    }
    for table in TABLES:
        for name, default in defaults.items():
            op.add_column(table, sa.Column(name, sa.String(), nullable=False, server_default=default))


def downgrade() -> None:
    for table in reversed(TABLES):
        for name in ("workflow_profile", "production_status", "quality_status", "execution_status"):
            op.drop_column(table, name)

