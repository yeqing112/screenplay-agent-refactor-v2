"""Keyframe authoring relations anchored to the existing StoryboardShot."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint

from .base import Base


KEYFRAME_TYPES = ("start", "middle", "end")
KEYFRAME_SEQUENCE_STATUSES = ("DRAFT", "ACTIVE", "STALE")
KEYFRAME_STATUSES = ("ACTIVE", "STALE")


class KeyframeSequence(Base):
    """Versioned keyframe plan for one existing storyboard shot."""

    __tablename__ = "keyframe_sequences"

    id = Column(Integer, primary_key=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    duration = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    frame_plan = Column(Text, nullable=False, default="{}")
    revision = Column(Integer, nullable=False, default=1)
    sequence_fingerprint = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("duration > 0", name="ck_keyframe_sequence_duration_positive"),
        CheckConstraint("revision >= 1", name="ck_keyframe_sequence_revision"),
        CheckConstraint("status IN ('DRAFT','ACTIVE','STALE')", name="ck_keyframe_sequence_status"),
    )

    @property
    def shot_id(self) -> int:
        return int(self.storyboard_shot_id)


class Keyframe(Base):
    """One ordered frame state and motion intent in a keyframe sequence."""

    __tablename__ = "keyframes"

    id = Column(Integer, primary_key=True)
    keyframe_sequence_id = Column(Integer, ForeignKey("keyframe_sequences.id", ondelete="CASCADE"), nullable=False, index=True)
    frame_type = Column(String, nullable=False)
    time_seconds = Column(Float, nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    description = Column(Text, nullable=False, default="")
    camera_state = Column(Text, nullable=False, default="{}")
    character_state = Column(Text, nullable=False, default="{}")
    scene_state = Column(Text, nullable=False, default="{}")
    emotion_state = Column(Text, nullable=False, default="{}")
    camera_motion = Column(String, nullable=False, default="")
    character_motion = Column(String, nullable=False, default="")
    environment_motion = Column(String, nullable=False, default="")
    emotion_transition = Column(String, nullable=False, default="")
    frame_fingerprint = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("frame_type IN ('start','middle','end')", name="ck_keyframe_type"),
        CheckConstraint("time_seconds >= 0", name="ck_keyframe_time_nonnegative"),
        CheckConstraint("order_index >= 0", name="ck_keyframe_order_nonnegative"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_keyframe_status"),
        UniqueConstraint("keyframe_sequence_id", "time_seconds", name="uq_keyframe_sequence_time"),
    )


class KeyframeAssetBinding(Base):
    """A keyframe-to-existing-production-asset edge.

    The authority/version pair deliberately points at the existing H2 asset
    registries.  It is a relation over those identities, not a new asset
    system.
    """

    __tablename__ = "keyframe_asset_bindings"

    id = Column(Integer, primary_key=True)
    keyframe_id = Column(Integer, ForeignKey("keyframes.id", ondelete="RESTRICT"), nullable=False, index=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    asset_type = Column(String, nullable=False, index=True)
    authority_id = Column(String, ForeignKey("production_asset_authority_registry.authority_id", ondelete="RESTRICT"), nullable=False, index=True)
    version_id = Column(String, nullable=False, index=True)
    binding_fingerprint = Column(String, nullable=False, unique=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"],
            name="fk_keyframe_asset_binding_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("keyframe_id", "asset_type", "authority_id", "version_id", name="uq_keyframe_asset_binding_identity"),
        CheckConstraint("asset_type IN ('CHARACTER','SCENE','PROP')", name="ck_keyframe_asset_binding_type"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_keyframe_asset_binding_status"),
    )


__all__ = [
    "KEYFRAME_TYPES",
    "KEYFRAME_SEQUENCE_STATUSES",
    "KEYFRAME_STATUSES",
    "KeyframeSequence",
    "Keyframe",
    "KeyframeAssetBinding",
]
