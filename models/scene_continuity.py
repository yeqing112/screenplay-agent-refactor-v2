"""Scene continuity relations over the existing VisualLocation authority."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import synonym

from .base import Base


SCENE_REFERENCE_TYPES = ("overview", "layout", "lighting", "detail", "prop")
SCENE_BINDING_STATUSES = ("ACTIVE", "STALE")


class SceneReferenceAsset(Base):
    """A typed relation from VisualLocation to an existing asset identity."""

    __tablename__ = "scene_reference_assets"

    id = Column(Integer, primary_key=True)
    scene_id = Column(Integer, ForeignKey("visual_locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    asset_id = Column(String, nullable=False, index=True)
    reference_type = Column(String, nullable=False, default="overview")
    priority = Column(Integer, nullable=False, default=0)
    visual_reference_asset_id = Column(Integer, ForeignKey("visual_reference_assets.id", ondelete="RESTRICT"), nullable=True, index=True)
    asset_version_id = Column(String, nullable=True, index=True)
    constraint_snapshot = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("scene_id", "asset_id", "reference_type", name="uq_scene_reference_asset_identity"),
        CheckConstraint("reference_type IN ('overview','layout','lighting','detail','prop')", name="ck_scene_reference_asset_type"),
        CheckConstraint("priority >= 0", name="ck_scene_reference_asset_priority"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_scene_reference_asset_status"),
    )


class ShotSceneBinding(Base):
    """The one primary Scene Identity bound to a storyboard shot."""

    __tablename__ = "shot_scene_bindings"

    id = Column(Integer, primary_key=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    scene_id = Column(Integer, ForeignKey("visual_locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    reference_asset_ids = Column(Text, nullable=False, default="[]")
    environment_rules = Column(Text, nullable=False, default="{}")
    constraint_snapshot = Column(Text, nullable=False, default="{}")
    asset_authority_id = Column(String, nullable=True, index=True)
    asset_version_id = Column(String, nullable=True, index=True)
    binding_fingerprint = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shot_id = synonym("storyboard_shot_id")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_scene_binding_status"),
    )


__all__ = ["SCENE_REFERENCE_TYPES", "SCENE_BINDING_STATUSES", "SceneReferenceAsset", "ShotSceneBinding"]
