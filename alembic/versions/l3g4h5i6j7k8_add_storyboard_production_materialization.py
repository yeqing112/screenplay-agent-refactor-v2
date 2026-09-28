"""Add reviewed StoryboardPlan -> production materialization lineage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "l3g4h5i6j7k8"
down_revision = "k2f3g4h5i6j7"
branch_labels = None
depends_on = None


def _add_columns(table: str, columns: list[sa.Column]) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "director_storyboard_plans" in tables:
        # SQLite requires a table recreation to replace a CHECK constraint.
        # Batch mode also keeps this revision valid for other Alembic dialects.
        with op.batch_alter_table("director_storyboard_plans", recreate="always") as batch:
            try:
                batch.drop_constraint("ck_director_storyboard_status", type_="check")
            except Exception:
                pass
            batch.create_check_constraint(
                "ck_director_storyboard_status",
                "status IN ('DRAFT','REVIEW_REQUIRED','COMPILED','APPROVED','SUPERSEDED','ROLLED_BACK','REJECTED')",
            )
    _add_columns("director_storyboard_plans", [
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("review_lineage_json", sa.Text(), nullable=False, server_default="{}"),
    ])
    _add_columns("director_storyboard_shots", [
        sa.Column("shot_direction", sa.Text(), nullable=False, server_default="{}"),
    ])
    _add_columns("storyboard_materialization_sets", [
        sa.Column("storyboard_plan_id", sa.Integer(), nullable=True),
        sa.Column("storyboard_plan_version", sa.Integer(), nullable=True),
        sa.Column("director_reasoning_id", sa.Integer(), nullable=True),
        sa.Column("director_reasoning_version", sa.Integer(), nullable=True),
    ])
    _add_columns("storyboard_shots", [
        sa.Column("storyboard_plan_id", sa.Integer(), nullable=True),
        sa.Column("storyboard_plan_version", sa.Integer(), nullable=True),
        sa.Column("director_reasoning_id", sa.Integer(), nullable=True),
        sa.Column("director_reasoning_version", sa.Integer(), nullable=True),
        sa.Column("storyboard_lineage", sa.Text(), nullable=False, server_default="{}"),
    ])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table, names in {
        "storyboard_shots": ("storyboard_lineage", "director_reasoning_version", "director_reasoning_id", "storyboard_plan_version", "storyboard_plan_id"),
        "storyboard_materialization_sets": ("director_reasoning_version", "director_reasoning_id", "storyboard_plan_version", "storyboard_plan_id"),
        "director_storyboard_shots": ("shot_direction",),
        "director_storyboard_plans": ("review_lineage_json", "approved_at", "approved_by"),
    }.items():
        if table not in inspector.get_table_names():
            continue
        existing = {item["name"] for item in inspect(bind).get_columns(table)}
        for name in names:
            if name in existing:
                op.drop_column(table, name)

    if "director_storyboard_plans" in inspect(bind).get_table_names():
        with op.batch_alter_table("director_storyboard_plans", recreate="always") as batch:
            try:
                batch.drop_constraint("ck_director_storyboard_status", type_="check")
            except Exception:
                pass
            batch.create_check_constraint(
                "ck_director_storyboard_status",
                "status IN ('DRAFT','REVIEW_REQUIRED','COMPILED','SUPERSEDED','ROLLED_BACK','REJECTED')",
            )
