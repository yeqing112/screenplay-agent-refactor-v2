"""add independent ShotPlan layer"""

from alembic import op
import sqlalchemy as sa


revision = "f0a1b2c3d4e5"
down_revision = "e9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shot_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("scene_name", sa.String(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("treatment_id", sa.Integer(), nullable=True),
        sa.Column("blocking_id", sa.Integer(), nullable=True),
        sa.Column("shots", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unknowns", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("model_info", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_shot_plans_book_id", "shot_plans", ["book_id"])
    op.create_index("ix_shot_plans_episode", "shot_plans", ["episode"])


def downgrade() -> None:
    op.drop_index("ix_shot_plans_episode", table_name="shot_plans")
    op.drop_index("ix_shot_plans_book_id", table_name="shot_plans")
    op.drop_table("shot_plans")
