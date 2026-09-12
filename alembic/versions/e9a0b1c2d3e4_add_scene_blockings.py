"""add independent SceneBlocking spatial layer"""

from alembic import op
import sqlalchemy as sa


revision = "e9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_blockings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("scene_name", sa.String(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("treatment_id", sa.Integer(), nullable=True),
        sa.Column("treatment_revision", sa.Integer(), nullable=True),
        sa.Column("source_script_hash", sa.String(), nullable=False, server_default=""),
        sa.Column("participants", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("beat_transitions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("spatial_rules", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unknowns", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_fingerprint", sa.String(), nullable=False, server_default=""),
        sa.Column("model_info", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_scene_blockings_book_id", "scene_blockings", ["book_id"])
    op.create_index("ix_scene_blockings_episode", "scene_blockings", ["episode"])


def downgrade() -> None:
    op.drop_index("ix_scene_blockings_episode", table_name="scene_blockings")
    op.drop_index("ix_scene_blockings_book_id", table_name="scene_blockings")
    op.drop_table("scene_blockings")
