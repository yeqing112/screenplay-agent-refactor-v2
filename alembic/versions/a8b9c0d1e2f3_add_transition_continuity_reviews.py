"""add transition continuity reviews

Revision ID: a8b9c0d1e2f3
Revises: f7b8c9d0e1f2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "a8b9c0d1e2f3"
down_revision = "f7b8c9d0e1f2"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if "storyboard_transition_continuity_reviews" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "storyboard_transition_continuity_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("source_shot_id", sa.Integer(), nullable=False),
        sa.Column("target_shot_id", sa.Integer(), nullable=False),
        sa.Column("transition_frame_id", sa.Integer(), nullable=False),
        sa.Column("target_video_asset_id", sa.String(), nullable=False),
        sa.Column("target_first_frame_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_first_frame_storage_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_first_frame_checksum", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="candidate"),
        sa.Column("review_result", sa.String(), nullable=False, server_default=""),
        sa.Column("drift_categories", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("review_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_transition_review_pair", "storyboard_transition_continuity_reviews", ["book_id", "episode", "source_shot_id", "target_shot_id"])

def downgrade() -> None:
    if "storyboard_transition_continuity_reviews" in inspect(op.get_bind()).get_table_names():
        op.drop_table("storyboard_transition_continuity_reviews")
