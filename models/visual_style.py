"""Visual style consistency relations over the existing asset authority graph."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import synonym

from .base import Base


STYLE_REFERENCE_TYPES = ("color", "camera", "lighting", "composition", "mood")
STYLE_BINDING_SCOPES = ("EPISODE_DEFAULT", "SHOT_OVERRIDE")
STYLE_BINDING_STATUSES = ("ACTIVE", "STALE")


class VisualStyleProfile(Base):
    """The canonical visual style identity used by production prompts."""

    __tablename__ = "visual_style_profiles"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    camera_profile = Column(Text, nullable=False, default="{}")
    lighting_profile = Column(Text, nullable=False, default="{}")
    color_profile = Column(Text, nullable=False, default="{}")
    composition_profile = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StyleReferenceAsset(Base):
    """A typed relation from one style profile to an existing asset identity."""

    __tablename__ = "style_reference_assets"

    id = Column(Integer, primary_key=True)
    style_id = Column(Integer, ForeignKey("visual_style_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    asset_id = Column(String, nullable=False, index=True)
    reference_type = Column(String, nullable=False, default="mood")
    priority = Column(Integer, nullable=False, default=0)
    visual_reference_asset_id = Column(Integer, ForeignKey("visual_reference_assets.id", ondelete="RESTRICT"), nullable=True, index=True)
    asset_version_id = Column(String, nullable=True, index=True)
    constraint_snapshot = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("style_id", "asset_id", "reference_type", name="uq_style_reference_asset_identity"),
        CheckConstraint("reference_type IN ('color','camera','lighting','composition','mood')", name="ck_style_reference_asset_type"),
        CheckConstraint("priority >= 0", name="ck_style_reference_asset_priority"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_style_reference_asset_status"),
    )


class ShotStyleBinding(Base):
    """Episode default or shot override for the effective visual style."""

    __tablename__ = "shot_style_bindings"

    id = Column(Integer, primary_key=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=True, index=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    style_id = Column(Integer, ForeignKey("visual_style_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    scope = Column(String, nullable=False, default="SHOT_OVERRIDE", index=True)
    reference_asset_ids = Column(Text, nullable=False, default="[]")
    style_rules = Column(Text, nullable=False, default="{}")
    constraint_snapshot = Column(Text, nullable=False, default="{}")
    asset_authority_id = Column(String, nullable=True, index=True)
    asset_version_id = Column(String, nullable=True, index=True)
    binding_fingerprint = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shot_id = synonym("storyboard_shot_id")

    __table_args__ = (
        CheckConstraint("scope IN ('EPISODE_DEFAULT','SHOT_OVERRIDE')", name="ck_shot_style_binding_scope"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_style_binding_status"),
    )


__all__ = [
    "STYLE_REFERENCE_TYPES",
    "STYLE_BINDING_SCOPES",
    "STYLE_BINDING_STATUSES",
    "VisualStyleProfile",
    "StyleReferenceAsset",
    "ShotStyleBinding",
]
