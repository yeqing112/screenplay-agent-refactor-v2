"""add explicit source/director/unknown Treatment projections"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "q0k1l2m3n4o5"
down_revision = "p9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {item["name"] for item in inspect(op.get_bind()).get_columns("director_treatments")}
    for name, default in (("source_constraints", "{}"), ("director_decisions", "{}"), ("unknown_unresolved", "[]")):
        if name not in existing:
            op.add_column("director_treatments", sa.Column(name, sa.Text(), nullable=False, server_default=default))


def downgrade() -> None:
    existing = {item["name"] for item in inspect(op.get_bind()).get_columns("director_treatments")}
    for name in ("unknown_unresolved", "director_decisions", "source_constraints"):
        if name in existing:
            op.drop_column("director_treatments", name)
