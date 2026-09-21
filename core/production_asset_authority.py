"""Provider-free repository and schema validator for Phase H2 assets.

This module deliberately stops at persistence validation.  It does not resolve
current assets, mutate PromptIR/Storyboard/ShotPlan, or call any provider.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from models import (
    CharacterAssetAuthority,
    CharacterAssetPointer,
    CharacterAssetVersion,
    ProductionAssetAuthorityRegistry,
    ProductionAssetVersionRegistry,
    PropAssetAuthority,
    PropAssetPointer,
    PropAssetVersion,
    SceneAssetAuthority,
    SceneAssetPointer,
    SceneAssetVersion,
    ShotAssetBinding,
)


ASSET_TYPES = ("CHARACTER", "SCENE", "PROP")
_AUTHORITY_STATUS = {"ACTIVE", "STALE"}
_VERSION_STATUS = {"CURRENT", "SUPERSEDED", "STALE"}
_BINDING_STATUS = {"ACTIVE", "STALE"}

_CONFIG: dict[str, dict[str, Any]] = {
    "CHARACTER": {"entity": "character_id", "authority": CharacterAssetAuthority, "version": CharacterAssetVersion, "pointer": CharacterAssetPointer},
    "SCENE": {"entity": "scene_id", "authority": SceneAssetAuthority, "version": SceneAssetVersion, "pointer": SceneAssetPointer},
    "PROP": {"entity": "prop_id", "authority": PropAssetAuthority, "version": PropAssetVersion, "pointer": PropAssetPointer},
}


class ProductionAssetSchemaError(ValueError):
    """Raised when typed H2 asset rows cannot form a valid schema envelope."""


class ProductionAssetAuthorityRepository:
    """Explicit persistence helpers for future asset ingestion.

    The repository never infers identity from prompt text, URLs, filenames or
    legacy ``asset_links``/``meta_info``.  Callers must supply stable IDs and
    fingerprints.  It also never resolves or silently moves a current pointer.
    """

    def __init__(self, session):
        self.session = session

    @staticmethod
    def _kind(asset_type: str) -> str:
        kind = str(asset_type or "").strip().upper()
        if kind not in ASSET_TYPES:
            raise ProductionAssetSchemaError(f"asset_type must be one of {ASSET_TYPES}")
        return kind

    def _config(self, asset_type: str) -> dict[str, Any]:
        return _CONFIG[self._kind(asset_type)]

    def register_authority(
        self,
        *,
        asset_type: str,
        entity_id: str,
        authority_id: str,
        fingerprint: str,
        status: str = "ACTIVE",
        current_version_id: str | None = None,
    ):
        config = self._config(asset_type)
        if status not in _AUTHORITY_STATUS:
            raise ProductionAssetSchemaError("invalid authority status")
        if not str(entity_id).strip() or not str(authority_id).strip() or not str(fingerprint).strip():
            raise ProductionAssetSchemaError("entity_id, authority_id and fingerprint are required")
        registry = ProductionAssetAuthorityRegistry(
            authority_id=authority_id,
            asset_type=self._kind(asset_type),
            source_table=config["authority"].__tablename__,
        )
        self.session.add(registry)
        self.session.flush()
        values = {
            config["entity"]: str(entity_id),
            "authority_id": authority_id,
            "current_version_id": current_version_id,
            "fingerprint": fingerprint,
            "status": status,
        }
        authority = config["authority"](**values)
        self.session.add(authority)
        self.session.flush()
        return authority

    def register_version(
        self,
        *,
        asset_type: str,
        entity_id: str,
        authority_id: str,
        version_id: str,
        revision: int,
        fingerprint: str | None = None,
        visual_asset_version_id: int | None = None,
        storage_identity: str | None = None,
        checksum: str | None = None,
        metadata_hash: str | None = None,
        status: str = "CURRENT",
    ):
        config = self._config(asset_type)
        if status not in _VERSION_STATUS:
            raise ProductionAssetSchemaError("invalid version status")
        if int(revision) < 1:
            raise ProductionAssetSchemaError("revision must be positive")
        if not str(version_id).strip() or not str(authority_id).strip():
            raise ProductionAssetSchemaError("version_id and authority_id are required")
        self.session.add(
            ProductionAssetVersionRegistry(
                version_id=version_id,
                authority_id=authority_id,
                asset_type=self._kind(asset_type),
            )
        )
        self.session.flush()
        values = {
            config["entity"]: str(entity_id),
            "version_id": version_id,
            "authority_id": authority_id,
            "visual_asset_version_id": visual_asset_version_id,
            "storage_identity": storage_identity,
            "checksum": checksum,
            "metadata_hash": metadata_hash,
            "revision": int(revision),
            "status": status,
        }
        version = config["version"](**values)
        self.session.add(version)
        self.session.flush()
        return version

    def create_pointer(
        self,
        *,
        asset_type: str,
        entity_id: str,
        authority_id: str,
        version_id: str,
        fingerprint: str,
    ):
        config = self._config(asset_type)
        if not str(fingerprint).strip():
            raise ProductionAssetSchemaError("pointer fingerprint is required")
        values = {
            config["entity"]: str(entity_id),
            "authority_id": authority_id,
            "version_id": version_id,
            "fingerprint": fingerprint,
        }
        pointer = config["pointer"](**values)
        self.session.add(pointer)
        self.session.flush()
        return pointer

    def create_shot_binding(
        self,
        *,
        storyboard_shot_id: int,
        asset_type: str,
        authority_id: str,
        version_id: str,
        binding_fingerprint: str,
        status: str = "ACTIVE",
    ) -> ShotAssetBinding:
        kind = self._kind(asset_type)
        if status not in _BINDING_STATUS:
            raise ProductionAssetSchemaError("invalid binding status")
        binding = ShotAssetBinding(
            storyboard_shot_id=storyboard_shot_id,
            asset_type=kind,
            authority_id=authority_id,
            version_id=version_id,
            binding_fingerprint=binding_fingerprint,
            status=status,
        )
        self.session.add(binding)
        self.session.flush()
        return binding


def _append_error(errors: list[dict[str, str]], code: str, message: str, **details: Any) -> None:
    errors.append({"code": code, "message": message, **{key: str(value) for key, value in details.items()}})


def validate_asset_authority_schema(session) -> dict[str, Any]:
    """Validate typed H2 rows and FK relationships without resolving assets.

    Empty tables are a valid migration result.  A non-empty table is checked
    for lifecycle values, registry ownership, current-version consistency and
    polymorphic binding consistency.  The return value is JSON serializable.
    """
    errors: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    authorities_by_id: dict[str, str] = {}
    versions_by_id: dict[str, tuple[str, str]] = {}
    registry_authorities = {row.authority_id: row.asset_type for row in session.query(ProductionAssetAuthorityRegistry).all()}
    registry_versions = {row.version_id: (row.authority_id, row.asset_type) for row in session.query(ProductionAssetVersionRegistry).all()}
    counts["production_asset_authority_registry"] = len(registry_authorities)
    counts["production_asset_version_registry"] = len(registry_versions)

    for kind, config in _CONFIG.items():
        authority_rows = session.query(config["authority"]).all()
        version_rows = session.query(config["version"]).all()
        pointer_rows = session.query(config["pointer"]).all()
        counts[config["authority"].__tablename__] = len(authority_rows)
        counts[config["version"].__tablename__] = len(version_rows)
        counts[config["pointer"].__tablename__] = len(pointer_rows)
        entity_field = config["entity"]
        for authority in authority_rows:
            aid = str(authority.authority_id)
            authorities_by_id[aid] = kind
            if registry_authorities.get(aid) != kind:
                _append_error(errors, "AUTHORITY_REGISTRY_MISMATCH", "authority registry type does not match typed authority", authority_id=aid, asset_type=kind)
            if authority.status not in _AUTHORITY_STATUS:
                _append_error(errors, "AUTHORITY_STATUS_INVALID", "authority status is not allowed", authority_id=aid)
            if authority.current_version_id:
                version = session.query(config["version"]).filter_by(version_id=authority.current_version_id).one_or_none()
                if version is None:
                    _append_error(errors, "CURRENT_VERSION_MISSING", "authority current version is missing", authority_id=aid)
                elif version.authority_id != aid or version.status != "CURRENT":
                    _append_error(errors, "CURRENT_VERSION_MISMATCH", "authority current version is not current or owned by authority", authority_id=aid, version_id=authority.current_version_id)
        for version in version_rows:
            vid = str(version.version_id)
            versions_by_id[vid] = (kind, str(version.authority_id))
            registry = registry_versions.get(vid)
            if registry != (str(version.authority_id), kind):
                _append_error(errors, "VERSION_REGISTRY_MISMATCH", "version registry does not match typed version", version_id=vid, asset_type=kind)
            if version.status not in _VERSION_STATUS:
                _append_error(errors, "VERSION_STATUS_INVALID", "version status is not allowed", version_id=vid)
            if int(version.revision or 0) < 1:
                _append_error(errors, "VERSION_REVISION_INVALID", "version revision must be positive", version_id=vid)
        for pointer in pointer_rows:
            aid = str(pointer.authority_id)
            vid = str(pointer.version_id)
            if authorities_by_id.get(aid) != kind:
                _append_error(errors, "POINTER_AUTHORITY_MISMATCH", "pointer authority is missing or typed differently", authority_id=aid, asset_type=kind)
            if versions_by_id.get(vid) != (kind, aid):
                _append_error(errors, "POINTER_VERSION_MISMATCH", "pointer version is missing or owned by another authority", version_id=vid, authority_id=aid)

    bindings = session.query(ShotAssetBinding).all()
    counts["shot_asset_bindings"] = len(bindings)
    for binding in bindings:
        kind = str(binding.asset_type or "").upper()
        if kind not in ASSET_TYPES:
            _append_error(errors, "BINDING_TYPE_INVALID", "binding asset type is not allowed", binding_id=binding.id)
            continue
        if registry_authorities.get(str(binding.authority_id)) != kind:
            _append_error(errors, "BINDING_AUTHORITY_MISMATCH", "binding authority is missing or typed differently", binding_id=binding.id)
        if registry_versions.get(str(binding.version_id), (None, None))[1] != kind or registry_versions.get(str(binding.version_id), (None, None))[0] != str(binding.authority_id):
            _append_error(errors, "BINDING_VERSION_MISMATCH", "binding version is missing or owned by another authority", binding_id=binding.id)
        if binding.status not in _BINDING_STATUS:
            _append_error(errors, "BINDING_STATUS_INVALID", "binding status is not allowed", binding_id=binding.id)

    return {
        "status": "PASS" if not errors else "FAIL",
        "schema": "phase_h2_production_asset_authority_v1",
        "counts": counts,
        "errors": errors,
        "resolver_created": False,
        "provider_calls": 0,
        "asset_generation_calls": 0,
        "prompt_ir_mutated": False,
        "storyboard_mutated": False,
    }


def assert_asset_authority_schema(session) -> dict[str, Any]:
    report = validate_asset_authority_schema(session)
    if report["status"] != "PASS":
        raise ProductionAssetSchemaError(str(report["errors"]))
    return report


__all__ = [
    "ProductionAssetSchemaError",
    "ProductionAssetAuthorityRepository",
    "validate_asset_authority_schema",
    "assert_asset_authority_schema",
]
