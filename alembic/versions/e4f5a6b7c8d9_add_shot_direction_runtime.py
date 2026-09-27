"""Add Shot Direction Runtime relation over StoryboardShot."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e4f5a6b7c8d9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "shot_directions" in _tables(bind):
        return
    op.create_table(
        "shot_directions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
        sa.Column("shot_type", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("camera_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("movement_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("composition_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("performance_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("emotion_profile", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("direction_fingerprint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_shot_direction_shot", ondelete="RESTRICT"),
        sa.UniqueConstraint("storyboard_shot_id", name="uq_shot_direction_shot"),
        sa.UniqueConstraint("direction_fingerprint", name="uq_shot_direction_fingerprint"),
        sa.CheckConstraint("revision >= 1", name="ck_shot_direction_revision"),
        sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_direction_status"),
    )
    op.create_index("ix_shot_directions_shot", "shot_directions", ["storyboard_shot_id"])
    op.create_index("ix_shot_directions_status", "shot_directions", ["status"])


def downgrade() -> None:
    if "shot_directions" in _tables(op.get_bind()):
        op.drop_table("shot_directions")
