"""add storyboard transition continuity records

Revision ID: f7b8c9d0e1f2
Revises: e6a7b8c9d0e1
Create Date: 2026-09-01 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f7b8c9d0e1f2"
down_revision = "e6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = inspect(op.get_bind()).get_table_names()
    if "storyboard_transition_contracts" not in tables:
        op.create_table(
            "storyboard_transition_contracts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("source_shot_id", sa.Integer(), nullable=False),
            sa.Column("target_shot_id", sa.Integer(), nullable=False),
            sa.Column("continuity_level", sa.String(), nullable=False, server_default="independent"),
            sa.Column("entry_state", sa.Text(), nullable=False, server_default=""),
            sa.Column("exit_state", sa.Text(), nullable=False, server_default=""),
            sa.Column("inherit_rules", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("allowed_changes", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("forbidden_changes", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("required_transition_frame", sa.String(), nullable=False, server_default=""),
            sa.Column("source_snapshot", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_transition_contract_pair", "storyboard_transition_contracts", ["book_id", "episode", "source_shot_id", "target_shot_id"])
    if "storyboard_transition_frames" not in tables:
        op.create_table(
            "storyboard_transition_frames",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("book_id", sa.Integer(), nullable=False),
            sa.Column("episode", sa.Integer(), nullable=False),
            sa.Column("source_shot_id", sa.Integer(), nullable=False),
            sa.Column("target_shot_id", sa.Integer(), nullable=False),
            sa.Column("source_video_asset_id", sa.String(), nullable=False, server_default=""),
            sa.Column("frame_time_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("frame_kind", sa.String(), nullable=False, server_default="last"),
            sa.Column("storage_key", sa.Text(), nullable=False, server_default=""),
            sa.Column("public_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("checksum", sa.String(), nullable=False, server_default=""),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="candidate"),
            sa.Column("extraction_profile", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_transition_frame_pair", "storyboard_transition_frames", ["book_id", "episode", "source_shot_id", "target_shot_id"])


def downgrade() -> None:
    tables = inspect(op.get_bind()).get_table_names()
    if "storyboard_transition_frames" in tables:
        op.drop_table("storyboard_transition_frames")
    if "storyboard_transition_contracts" in tables:
        op.drop_table("storyboard_transition_contracts")
