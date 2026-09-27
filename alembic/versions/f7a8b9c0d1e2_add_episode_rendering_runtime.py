"""Add episode rendering plans and ordered dependency items."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "episode_render_plans" not in tables:
        op.create_table(
            "episode_render_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("episode_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("episode_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'DRAFT'")),
            sa.Column("render_strategy", sa.String(), nullable=False, server_default=sa.text("'SEQUENTIAL'")),
            sa.Column("production_batch_id", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["episode_id"], ["episode_outlines.id"], name="fk_episode_render_plan_episode", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["production_batch_id"], ["production_batches.id"], name="fk_episode_render_plan_batch", ondelete="RESTRICT"),
            sa.CheckConstraint("status IN ('DRAFT','PREPARING','GENERATING','REVIEWING','COMPLETED','FAILED')", name="ck_episode_render_plan_status"),
        )
        for name, fields in {
            "ix_episode_render_plan_episode": ["episode_id"],
            "ix_episode_render_plan_project": ["project_id"],
            "ix_episode_render_plan_episode_number": ["episode_number"],
            "ix_episode_render_plan_status": ["status"],
            "ix_episode_render_plan_batch": ["production_batch_id"],
        }.items():
            op.create_index(name, "episode_render_plans", fields)

    tables = _tables(bind)
    if "episode_render_items" not in tables:
        op.create_table(
            "episode_render_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("render_plan_id", sa.Integer(), nullable=False),
            sa.Column("episode_id", sa.Integer(), nullable=False),
            sa.Column("shot_id", sa.Integer(), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("dependency", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'PENDING'")),
            sa.Column("production_batch_item_id", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["render_plan_id"], ["episode_render_plans.id"], name="fk_episode_render_item_plan", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["shot_id"], ["storyboard_shots.id"], name="fk_episode_render_item_shot", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["production_batch_item_id"], ["production_batch_items.id"], name="fk_episode_render_item_batch_item", ondelete="SET NULL"),
            sa.UniqueConstraint("render_plan_id", "shot_id", name="uq_episode_render_item_shot"),
            sa.UniqueConstraint("render_plan_id", "order_index", name="uq_episode_render_item_order"),
            sa.CheckConstraint("status IN ('PENDING','QUEUED','RUNNING','COMPLETED','FAILED','SKIPPED')", name="ck_episode_render_item_status"),
            sa.CheckConstraint("order_index >= 0", name="ck_episode_render_item_order_nonnegative"),
        )
        for name, fields in {
            "ix_episode_render_item_plan": ["render_plan_id"],
            "ix_episode_render_item_episode": ["episode_id"],
            "ix_episode_render_item_shot": ["shot_id"],
            "ix_episode_render_item_status": ["status"],
            "ix_episode_render_item_batch_item": ["production_batch_item_id"],
        }.items():
            op.create_index(name, "episode_render_items", fields)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "episode_render_items" in tables:
        for name in ("ix_episode_render_item_batch_item", "ix_episode_render_item_status", "ix_episode_render_item_shot", "ix_episode_render_item_episode", "ix_episode_render_item_plan"):
            try:
                op.drop_index(name, table_name="episode_render_items")
            except Exception:
                pass
        op.drop_table("episode_render_items")
    if "episode_render_plans" in tables:
        for name in ("ix_episode_render_plan_batch", "ix_episode_render_plan_status", "ix_episode_render_plan_episode_number", "ix_episode_render_plan_project", "ix_episode_render_plan_episode"):
            try:
                op.drop_index(name, table_name="episode_render_plans")
            except Exception:
                pass
        op.drop_table("episode_render_plans")
