"""Add Keyframe Authoring Runtime relations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e5f6a7b8c9d0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "keyframe_sequences" not in _tables(bind):
        op.create_table(
            "keyframe_sequences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("duration", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("frame_plan", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("sequence_fingerprint", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_keyframe_sequence_shot", ondelete="RESTRICT"),
            sa.UniqueConstraint("sequence_fingerprint", name="uq_keyframe_sequence_fingerprint"),
            sa.CheckConstraint("duration > 0", name="ck_keyframe_sequence_duration_positive"),
            sa.CheckConstraint("revision >= 1", name="ck_keyframe_sequence_revision"),
            sa.CheckConstraint("status IN ('DRAFT','ACTIVE','STALE')", name="ck_keyframe_sequence_status"),
        )
        op.create_index("ix_keyframe_sequences_shot", "keyframe_sequences", ["storyboard_shot_id"])
        op.create_index("ix_keyframe_sequences_status", "keyframe_sequences", ["status"])
        op.create_index("ix_keyframe_sequences_fingerprint", "keyframe_sequences", ["sequence_fingerprint"], unique=True)
    if "keyframes" not in _tables(bind):
        op.create_table(
            "keyframes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("keyframe_sequence_id", sa.Integer(), nullable=False),
            sa.Column("frame_type", sa.String(), nullable=False),
            sa.Column("time_seconds", sa.Float(), nullable=False),
            sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("camera_state", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("character_state", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("scene_state", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("emotion_state", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("camera_motion", sa.String(), nullable=False, server_default=sa.text("''")),
            sa.Column("character_motion", sa.String(), nullable=False, server_default=sa.text("''")),
            sa.Column("environment_motion", sa.String(), nullable=False, server_default=sa.text("''")),
            sa.Column("emotion_transition", sa.String(), nullable=False, server_default=sa.text("''")),
            sa.Column("frame_fingerprint", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["keyframe_sequence_id"], ["keyframe_sequences.id"], name="fk_keyframe_sequence", ondelete="CASCADE"),
            sa.UniqueConstraint("frame_fingerprint", name="uq_keyframe_fingerprint"),
            sa.UniqueConstraint("keyframe_sequence_id", "time_seconds", name="uq_keyframe_sequence_time"),
            sa.CheckConstraint("frame_type IN ('start','middle','end')", name="ck_keyframe_type"),
            sa.CheckConstraint("time_seconds >= 0", name="ck_keyframe_time_nonnegative"),
            sa.CheckConstraint("order_index >= 0", name="ck_keyframe_order_nonnegative"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_keyframe_status"),
        )
        for name, fields in {"ix_keyframes_sequence": ["keyframe_sequence_id"], "ix_keyframes_fingerprint": ["frame_fingerprint"], "ix_keyframes_status": ["status"]}.items():
            op.create_index(name, "keyframes", fields, unique=name.endswith("fingerprint"))
    if "keyframe_asset_bindings" not in _tables(bind):
        op.create_table(
            "keyframe_asset_bindings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("keyframe_id", sa.Integer(), nullable=False),
            sa.Column("storyboard_shot_id", sa.Integer(), nullable=False),
            sa.Column("asset_type", sa.String(), nullable=False),
            sa.Column("authority_id", sa.String(), nullable=False),
            sa.Column("version_id", sa.String(), nullable=False),
            sa.Column("binding_fingerprint", sa.String(), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["keyframe_id"], ["keyframes.id"], name="fk_keyframe_asset_binding_keyframe", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["storyboard_shot_id"], ["storyboard_shots.id"], name="fk_keyframe_asset_binding_shot", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["authority_id"], ["production_asset_authority_registry.authority_id"], name="fk_keyframe_asset_binding_authority", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["authority_id", "version_id"], ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"], name="fk_keyframe_asset_binding_version", ondelete="RESTRICT"),
            sa.UniqueConstraint("keyframe_id", "asset_type", "authority_id", "version_id", name="uq_keyframe_asset_binding_identity"),
            sa.UniqueConstraint("binding_fingerprint", name="uq_keyframe_asset_binding_fingerprint"),
            sa.CheckConstraint("asset_type IN ('CHARACTER','SCENE','PROP')", name="ck_keyframe_asset_binding_type"),
            sa.CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_keyframe_asset_binding_status"),
        )
        for name, fields in {"ix_keyframe_asset_bindings_keyframe": ["keyframe_id"], "ix_keyframe_asset_bindings_shot": ["storyboard_shot_id"], "ix_keyframe_asset_bindings_asset": ["asset_type"], "ix_keyframe_asset_bindings_authority": ["authority_id"], "ix_keyframe_asset_bindings_version": ["version_id"], "ix_keyframe_asset_bindings_status": ["status"]}.items():
            op.create_index(name, "keyframe_asset_bindings", fields)


def downgrade() -> None:
    bind = op.get_bind()
    if "keyframe_asset_bindings" in _tables(bind):
        op.drop_table("keyframe_asset_bindings")
    if "keyframes" in _tables(bind):
        op.drop_table("keyframes")
    if "keyframe_sequences" in _tables(bind):
        op.drop_table("keyframe_sequences")
