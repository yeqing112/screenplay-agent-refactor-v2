"""Add Director LLM adapter generation audit records."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "j1e2f3g4h5i6"
down_revision = "i0d1e2f3g4h5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "director_reasoning_generations" in tables:
        return
    op.create_table(
        "director_reasoning_generations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("generation_id", sa.String(), nullable=False),
        sa.Column("episode_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="RUNNING"),
        sa.Column("provider", sa.String(), nullable=False, server_default="mock"),
        sa.Column("adapter_name", sa.String(), nullable=False, server_default=""),
        sa.Column("context_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("request_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("response_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("director_reasoning_id", sa.Integer(), sa.ForeignKey("director_reasonings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("director_reasoning_version", sa.Integer(), nullable=True),
        sa.Column("provider_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_fact_mutated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("script_ir_mutated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("human_review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("generation_id", name="uq_director_reasoning_generation_id"),
        sa.CheckConstraint("status IN ('RUNNING','REVIEW_REQUIRED','FAILED')", name="ck_director_reasoning_generation_status"),
        sa.CheckConstraint("provider_calls >= 0", name="ck_director_reasoning_generation_provider_calls_nonnegative"),
    )
    for name, fields in {
        "ix_director_reasoning_generations_generation_id": ["generation_id"],
        "ix_director_reasoning_generations_episode_id": ["episode_id"],
        "ix_director_reasoning_generations_status": ["status"],
        "ix_director_reasoning_generations_reasoning_id": ["director_reasoning_id"],
    }.items():
        op.create_index(name, "director_reasoning_generations", fields)


def downgrade() -> None:
    bind = op.get_bind()
    if "director_reasoning_generations" not in inspect(bind).get_table_names():
        return
    for name in (
        "ix_director_reasoning_generations_reasoning_id",
        "ix_director_reasoning_generations_status",
        "ix_director_reasoning_generations_episode_id",
        "ix_director_reasoning_generations_generation_id",
    ):
        try:
            op.drop_index(name, table_name="director_reasoning_generations")
        except Exception:
            pass
    op.drop_table("director_reasoning_generations")
