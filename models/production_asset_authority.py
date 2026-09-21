"""Phase H2 typed Production Asset Authority models.

These models intentionally do not inherit from or alias VisualReferenceAuthority.
The registry rows are an internal polymorphic FK bridge for shot bindings; the
migration leaves every production asset table empty until explicit ingestion.
"""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)

from .base import Base


ASSET_TYPES = ("CHARACTER", "SCENE", "PROP")
AUTHORITY_STATUSES = ("ACTIVE", "STALE")
VERSION_STATUSES = ("CURRENT", "SUPERSEDED", "STALE")
BINDING_STATUSES = ("ACTIVE", "STALE")


class ProductionAssetAuthorityRegistry(Base):
    __tablename__ = "production_asset_authority_registry"

    authority_id = Column(String, primary_key=True)
    asset_type = Column(String, nullable=False, index=True)
    source_table = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("asset_type IN ('CHARACTER','SCENE','PROP')", name="ck_production_asset_authority_registry_type"),
    )


class ProductionAssetVersionRegistry(Base):
    __tablename__ = "production_asset_version_registry"

    version_id = Column(String, primary_key=True)
    authority_id = Column(
        String,
        ForeignKey("production_asset_authority_registry.authority_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_type = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("authority_id", "version_id", name="uq_production_asset_version_registry_authority_version"),
        CheckConstraint("asset_type IN ('CHARACTER','SCENE','PROP')", name="ck_production_asset_version_registry_type"),
    )


class _AssetAuthorityMixin:
    id = Column(Integer, primary_key=True)
    authority_id = Column(
        String,
        ForeignKey("production_asset_authority_registry.authority_id", ondelete="RESTRICT"),
        nullable=False,
    )
    fingerprint = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class _AssetVersionMixin:
    id = Column(Integer, primary_key=True)
    version_id = Column(String, nullable=False, unique=True)
    authority_id = Column(String, nullable=False)
    visual_asset_version_id = Column(
        Integer,
        ForeignKey("visual_asset_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    storage_identity = Column(String, nullable=True)
    checksum = Column(String, nullable=True)
    metadata_hash = Column(String, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="CURRENT")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class _AssetPointerMixin:
    id = Column(Integer, primary_key=True)
    fingerprint = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CharacterAssetVersion(_AssetVersionMixin, Base):
    __tablename__ = "character_asset_versions"
    character_id = Column(String, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"],
            name="fk_character_asset_version_registry_identity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("authority_id", "version_id", name="uq_character_asset_version_authority_identity"),
        UniqueConstraint("authority_id", "revision", name="uq_character_asset_version_revision"),
        CheckConstraint("revision > 0", name="ck_character_asset_version_revision_positive"),
        CheckConstraint("status IN ('CURRENT','SUPERSEDED','STALE')", name="ck_character_asset_version_status"),
    )


class CharacterAssetAuthority(_AssetAuthorityMixin, Base):
    __tablename__ = "character_asset_authorities"
    character_id = Column(String, nullable=False, unique=True)
    current_version_id = Column(String, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "current_version_id"],
            ["character_asset_versions.authority_id", "character_asset_versions.version_id"],
            name="fk_character_asset_authority_current_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("authority_id", name="uq_character_asset_authority_identity"),
        UniqueConstraint("character_id", name="uq_character_asset_authority_entity"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_character_asset_authority_status"),
    )


class CharacterAssetPointer(_AssetPointerMixin, Base):
    __tablename__ = "character_asset_pointers"
    character_id = Column(String, nullable=False, unique=True)
    authority_id = Column(
        String,
        ForeignKey("character_asset_authorities.authority_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    version_id = Column(String, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["character_asset_versions.authority_id", "character_asset_versions.version_id"],
            name="fk_character_asset_pointer_version",
            ondelete="RESTRICT",
        ),
    )


class SceneAssetVersion(_AssetVersionMixin, Base):
    __tablename__ = "scene_asset_versions"
    scene_id = Column(String, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"],
            name="fk_scene_asset_version_registry_identity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("authority_id", "version_id", name="uq_scene_asset_version_authority_identity"),
        UniqueConstraint("authority_id", "revision", name="uq_scene_asset_version_revision"),
        CheckConstraint("revision > 0", name="ck_scene_asset_version_revision_positive"),
        CheckConstraint("status IN ('CURRENT','SUPERSEDED','STALE')", name="ck_scene_asset_version_status"),
    )


class SceneAssetAuthority(_AssetAuthorityMixin, Base):
    __tablename__ = "scene_asset_authorities"
    scene_id = Column(String, nullable=False, unique=True)
    current_version_id = Column(String, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "current_version_id"],
            ["scene_asset_versions.authority_id", "scene_asset_versions.version_id"],
            name="fk_scene_asset_authority_current_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("authority_id", name="uq_scene_asset_authority_identity"),
        UniqueConstraint("scene_id", name="uq_scene_asset_authority_entity"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_scene_asset_authority_status"),
    )


class SceneAssetPointer(_AssetPointerMixin, Base):
    __tablename__ = "scene_asset_pointers"
    scene_id = Column(String, nullable=False, unique=True)
    authority_id = Column(
        String,
        ForeignKey("scene_asset_authorities.authority_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    version_id = Column(String, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["scene_asset_versions.authority_id", "scene_asset_versions.version_id"],
            name="fk_scene_asset_pointer_version",
            ondelete="RESTRICT",
        ),
    )


class PropAssetVersion(_AssetVersionMixin, Base):
    __tablename__ = "prop_asset_versions"
    prop_id = Column(String, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"],
            name="fk_prop_asset_version_registry_identity",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("authority_id", "version_id", name="uq_prop_asset_version_authority_identity"),
        UniqueConstraint("authority_id", "revision", name="uq_prop_asset_version_revision"),
        CheckConstraint("revision > 0", name="ck_prop_asset_version_revision_positive"),
        CheckConstraint("status IN ('CURRENT','SUPERSEDED','STALE')", name="ck_prop_asset_version_status"),
    )


class PropAssetAuthority(_AssetAuthorityMixin, Base):
    __tablename__ = "prop_asset_authorities"
    prop_id = Column(String, nullable=False, unique=True)
    current_version_id = Column(String, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "current_version_id"],
            ["prop_asset_versions.authority_id", "prop_asset_versions.version_id"],
            name="fk_prop_asset_authority_current_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("authority_id", name="uq_prop_asset_authority_identity"),
        UniqueConstraint("prop_id", name="uq_prop_asset_authority_entity"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_prop_asset_authority_status"),
    )


class PropAssetPointer(_AssetPointerMixin, Base):
    __tablename__ = "prop_asset_pointers"
    prop_id = Column(String, nullable=False, unique=True)
    authority_id = Column(
        String,
        ForeignKey("prop_asset_authorities.authority_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    version_id = Column(String, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["prop_asset_versions.authority_id", "prop_asset_versions.version_id"],
            name="fk_prop_asset_pointer_version",
            ondelete="RESTRICT",
        ),
    )


class ShotAssetBinding(Base):
    __tablename__ = "shot_asset_bindings"

    id = Column(Integer, primary_key=True)
    storyboard_shot_id = Column(
        Integer,
        ForeignKey("storyboard_shots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_type = Column(String, nullable=False, index=True)
    authority_id = Column(
        String,
        ForeignKey("production_asset_authority_registry.authority_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_id = Column(String, nullable=False, index=True)
    binding_fingerprint = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["authority_id", "version_id"],
            ["production_asset_version_registry.authority_id", "production_asset_version_registry.version_id"],
            name="fk_shot_asset_binding_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "storyboard_shot_id",
            "asset_type",
            "authority_id",
            "version_id",
            name="uq_shot_asset_binding_identity",
        ),
        CheckConstraint("asset_type IN ('CHARACTER','SCENE','PROP')", name="ck_shot_asset_binding_type"),
        CheckConstraint("status IN ('ACTIVE','STALE')", name="ck_shot_asset_binding_status"),
    )


__all__ = [
    "ASSET_TYPES",
    "AUTHORITY_STATUSES",
    "VERSION_STATUSES",
    "BINDING_STATUSES",
    "ProductionAssetAuthorityRegistry",
    "ProductionAssetVersionRegistry",
    "CharacterAssetAuthority",
    "CharacterAssetVersion",
    "CharacterAssetPointer",
    "SceneAssetAuthority",
    "SceneAssetVersion",
    "SceneAssetPointer",
    "PropAssetAuthority",
    "PropAssetVersion",
    "PropAssetPointer",
    "ShotAssetBinding",
]
