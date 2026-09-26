"""Add the reusable production batch orchestration runtime."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(Inspector.from_engine(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "production_batches" not in tables:
        op.create_table(
            "production_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_key", sa.String(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("episode_id", sa.Integer(), nullable=False),
            sa.Column("episode_number", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'CREATED'")),
            sa.Column("total_tasks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("completed_tasks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("failed_tasks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("error", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["task_id"], ["task_runs.task_id"], name="fk_production_batch_task", ondelete="RESTRICT"),
            sa.UniqueConstraint("batch_key", name="uq_production_batch_key"),
            sa.UniqueConstraint("task_id", name="uq_production_batch_task_id"),
            sa.CheckConstraint("status IN ('CREATED','QUEUED','RUNNING','COMPLETED','FAILED')", name="ck_production_batch_status"),
        )
        for name, columns in {
            "ix_production_batch_key": ["batch_key"],
            "ix_production_batch_project": ["project_id"],
            "ix_production_batch_episode": ["episode_id"],
            "ix_production_batch_episode_number": ["episode_number"],
            "ix_production_batch_task": ["task_id"],
            "ix_production_batch_status": ["status"],
            "ix_production_batch_created": ["created_at"],
        }.items():
            op.create_index(name, "production_batches", columns)

    tables = _tables(bind)
    if "production_batch_items" not in tables:
        op.create_table(
            "production_batch_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), nullable=False),
            sa.Column("shot_id", sa.Integer(), nullable=False),
            sa.Column("execution_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'CREATED'")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("candidate_id", sa.String(), nullable=True),
            sa.Column("promotion_id", sa.String(), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["batch_id"], ["production_batches.id"], name="fk_production_batch_item_batch", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["execution_id"], ["generation_execution_records.execution_id"], name="fk_production_batch_item_execution", ondelete="RESTRICT"),
            sa.UniqueConstraint("batch_id", "shot_id", name="uq_production_batch_item_shot"),
            sa.UniqueConstraint("execution_id", name="uq_production_batch_item_execution"),
            sa.CheckConstraint("status IN ('CREATED','QUEUED','RUNNING','SUCCEEDED','FAILED','RETRYING','SKIPPED')", name="ck_production_batch_item_status"),
        )
        for name, columns in {
            "ix_production_batch_item_batch": ["batch_id"],
            "ix_production_batch_item_shot": ["shot_id"],
            "ix_production_batch_item_execution": ["execution_id"],
            "ix_production_batch_item_status": ["status"],
            "ix_production_batch_item_priority": ["priority"],
            "ix_production_batch_item_candidate": ["candidate_id"],
            "ix_production_batch_item_promotion": ["promotion_id"],
            "ix_production_batch_item_created": ["created_at"],
        }.items():
            op.create_index(name, "production_batch_items", columns)


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "production_batch_items" in tables:
        for name in (
            "ix_production_batch_item_created",
            "ix_production_batch_item_promotion",
            "ix_production_batch_item_candidate",
            "ix_production_batch_item_priority",
            "ix_production_batch_item_status",
            "ix_production_batch_item_execution",
            "ix_production_batch_item_shot",
            "ix_production_batch_item_batch",
        ):
            try:
                op.drop_index(name, table_name="production_batch_items")
            except Exception:
                pass
        op.drop_table("production_batch_items")
    if "production_batches" in tables:
        for name in (
            "ix_production_batch_created",
            "ix_production_batch_status",
            "ix_production_batch_task",
            "ix_production_batch_episode_number",
            "ix_production_batch_episode",
            "ix_production_batch_project",
            "ix_production_batch_key",
        ):
            try:
                op.drop_index(name, table_name="production_batches")
            except Exception:
                pass
        op.drop_table("production_batches")
