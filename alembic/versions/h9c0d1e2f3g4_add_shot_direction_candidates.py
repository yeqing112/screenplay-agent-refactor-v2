"""Add explicit ShotDirection candidate payload to DirectorPlan records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "h9c0d1e2f3g4"
down_revision = "g8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("director_plans")}
    if "shot_directions" not in columns:
        op.add_column("director_plans", sa.Column("shot_directions", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("director_plans")}
    if "shot_directions" in columns:
        op.drop_column("director_plans", "shot_directions")
