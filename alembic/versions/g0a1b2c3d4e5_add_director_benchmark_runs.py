"""persist Director Benchmark runs"""
from alembic import op
import sqlalchemy as sa

revision = "g0a1b2c3d4e5"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("director_benchmark_runs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("book_id", sa.Integer(), nullable=False), sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("sample_label", sa.String(), nullable=False, server_default=""), sa.Column("model_id", sa.String(), nullable=False, server_default="deterministic"),
        sa.Column("report", sa.Text(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime(), nullable=True))
    op.create_index("ix_director_benchmark_runs_book_id", "director_benchmark_runs", ["book_id"])
    op.create_index("ix_director_benchmark_runs_episode", "director_benchmark_runs", ["episode"])


def downgrade() -> None:
    op.drop_index("ix_director_benchmark_runs_episode", table_name="director_benchmark_runs")
    op.drop_index("ix_director_benchmark_runs_book_id", table_name="director_benchmark_runs")
    op.drop_table("director_benchmark_runs")
