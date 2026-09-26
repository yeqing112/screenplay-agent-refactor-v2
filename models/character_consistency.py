"""Character consistency bindings built on the existing asset authority graph."""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import synonym

from .base import Base


CHARACTER_REFERENCE_TYPES = ("portrait", "full_body", "costume", "expression")
CHARACTER_BINDING_STATUSES = ("ACTIVE", "STALE")


class CharacterReferenceAsset(Base):
    """A typed relation from one CharacterProfile to an existing asset.

    ``asset_id`` is the stable asset identity used by existing visual asset
    authority records.  Optional ``visual_reference_asset_id`` and
    ``asset_version_id`` columns let callers attach the legacy preview row or
    the production Asset Version without creating a new media store.
    """

    __tablename__ = "character_reference_assets"

    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey("character_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    asset_id = Column(String, nullable=False, index=True)
    reference_type = Column(String, nullable=False, default="portrait")
    priority = Column(Integer, nullable=False, default=0)
    visual_reference_asset_id = Column(Integer, ForeignKey("visual_reference_assets.id", ondelete="RESTRICT"), nullable=True, index=True)
    asset_version_id = Column(String, nullable=True, index=True)
    constraint_snapshot = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("character_id", "asset_id", "reference_type", name="uq_character_reference_asset_identity"),
        CheckConstraint("reference_type IN ('portrait','full_body','costume','expression')", name="ck_character_reference_asset_type"),
        CheckConstraint("priority >= 0", name="ck_character_reference_asset_priority"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_character_reference_asset_status"),
    )


class ShotCharacterBinding(Base):
    """One role binding between a StoryboardShot and a CharacterProfile."""

    __tablename__ = "shot_character_bindings"

    id = Column(Integer, primary_key=True)
    storyboard_shot_id = Column(Integer, ForeignKey("storyboard_shots.id", ondelete="RESTRICT"), nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("character_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    role = Column(String, nullable=False, default="supporting")
    reference_asset_ids = Column(Text, nullable=False, default="[]")
    appearance_rules = Column(Text, nullable=False, default="{}")
    constraint_snapshot = Column(Text, nullable=False, default="{}")
    asset_authority_id = Column(String, nullable=True, index=True)
    asset_version_id = Column(String, nullable=True, index=True)
    binding_fingerprint = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ``shot_id`` is a compatibility spelling used by API callers; the
    # database remains anchored to StoryboardShot's authoritative row id.
    shot_id = synonym("storyboard_shot_id")

    __table_args__ = (
        UniqueConstraint("storyboard_shot_id", "character_id", "role", name="uq_shot_character_binding_role"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_character_binding_status"),
    )


__all__ = ["CHARACTER_REFERENCE_TYPES", "CHARACTER_BINDING_STATUSES", "CharacterReferenceAsset", "ShotCharacterBinding"]
