"""Provider-free repository and schema validator for Phase H2 assets.

This module deliberately stops at persistence validation.  It does not resolve
current assets, mutate PromptIR/Storyboard/ShotPlan, or call any provider.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
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


class AssetBindingInvalid(ProductionAssetSchemaError):
    """A shot binding cannot be resolved to one current authority/version."""

    status_code = 409
    code = "ASSET_BINDING_INVALID"

    def __init__(self, message: str, *, diagnostics: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics or []


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _source_contract(source: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an explicit asset source; never infer from display text/URLs."""
    if not isinstance(source, Mapping):
        raise ProductionAssetSchemaError("asset source must be an object")
    forbidden = {"character_name", "scene_name", "prop_name", "image_url", "filename", "prompt", "meta_info", "asset_links"}
    if forbidden.intersection(source):
        raise ProductionAssetSchemaError("asset source cannot use display names, prompt text, filename, URL or metadata binding")
    storage_identity = str(source.get("storage_identity") or "").strip()
    checksum = str(source.get("checksum") or "").strip()
    metadata = source.get("metadata")
    if not storage_identity or not checksum or not isinstance(metadata, Mapping):
        raise ProductionAssetSchemaError("asset source requires storage_identity, checksum and metadata")
    return {
        "storage_identity": storage_identity,
        "checksum": checksum,
        "metadata": dict(metadata),
        "metadata_hash": _sha256(dict(metadata)),
    }


def _asset_type(asset_type: str) -> str:
    kind = str(asset_type or "").strip().upper()
    if kind not in ASSET_TYPES:
        raise ProductionAssetSchemaError(f"asset_type must be one of {ASSET_TYPES}")
    return kind


def _authority_id(*, book_id: int, asset_type: str, entity_id: str) -> str:
    kind = _asset_type(asset_type).lower()
    return f"paa_{kind}_{_sha256({'book_id': book_id, 'entity_id': entity_id})[:24]}"


def _authority_fingerprint(*, book_id: int, asset_type: str, entity_id: str, authority_id: str) -> str:
    return _sha256({"schema": "production_asset_authority_v1", "book_id": book_id, "asset_type": _asset_type(asset_type), "entity_id": entity_id, "authority_id": authority_id})


def _version_id(*, authority_id: str, revision: int, source: Mapping[str, Any]) -> str:
    return f"pav_{_sha256({'authority_id': authority_id, 'revision': revision, 'storage_identity': source['storage_identity'], 'checksum': source['checksum'], 'metadata_hash': source['metadata_hash']})[:24]}"


def _version_fingerprint(*, authority_id: str, version_id: str, revision: int, source: Mapping[str, Any]) -> str:
    return _sha256({"schema": "production_asset_version_v1", "authority_id": authority_id, "version_id": version_id, "revision": revision, "storage_identity": source["storage_identity"], "checksum": source["checksum"], "metadata_hash": source["metadata_hash"]})


def _pointer_fingerprint(*, entity_id: str, authority_id: str, version_id: str) -> str:
    return _sha256({"schema": "production_asset_pointer_v1", "entity_id": entity_id, "authority_id": authority_id, "version_id": version_id})


def _binding_fingerprint(*, storyboard_shot_id: int, asset_type: str, authority_fingerprint: str, version_fingerprint: str, pointer_fingerprint: str) -> str:
    return _sha256({"schema": "shot_asset_binding_v1", "storyboard_shot_id": storyboard_shot_id, "asset_type": _asset_type(asset_type), "authority_fingerprint": authority_fingerprint, "version_fingerprint": version_fingerprint, "pointer_fingerprint": pointer_fingerprint})


def _entity_field(asset_type: str) -> str:
    return {"CHARACTER": "character_id", "SCENE": "scene_id", "PROP": "prop_id"}[_asset_type(asset_type)]


def _typed_config(asset_type: str) -> dict[str, Any]:
    return _CONFIG[_asset_type(asset_type)]


def ingest_production_asset(
    session,
    *,
    entity_type: str,
    entity_id: str,
    source: Mapping[str, Any],
    book_id: int = 990401,
):
    """Ingest one explicit Production Asset Authority/Version/Pointer triple.

    ``source`` is a declared file/storage identity plus checksum and metadata.
    The function never creates media, never reads PromptIR/Storyboard metadata
    to infer identity, and never accepts a display name or URL as authority.
    Re-ingesting changed source material creates a new immutable version and
    moves the pointer; existing shot bindings are marked stale and are never
    silently rebound.
    """
    kind = _asset_type(entity_type)
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        raise ProductionAssetSchemaError("entity_id is required and must be canonical")
    source = _source_contract(source)
    config = _typed_config(kind)
    authority_id = _authority_id(book_id=book_id, asset_type=kind, entity_id=entity_id)
    authority_fingerprint = _authority_fingerprint(book_id=book_id, asset_type=kind, entity_id=entity_id, authority_id=authority_id)
    authority = session.query(config["authority"]).filter_by(authority_id=authority_id).one_or_none()
    if authority is None:
        session.add(ProductionAssetAuthorityRegistry(authority_id=authority_id, asset_type=kind, source_table=config["authority"].__tablename__))
        session.flush()
        authority = config["authority"](**{config["entity"]: entity_id, "authority_id": authority_id, "fingerprint": authority_fingerprint, "status": "ACTIVE"})
        session.add(authority)
        session.flush()
    elif authority.fingerprint != authority_fingerprint or authority.status != "ACTIVE":
        raise ProductionAssetSchemaError("existing authority fingerprint/status does not match canonical identity")

    current = session.query(config["version"]).filter_by(version_id=authority.current_version_id).one_or_none() if authority.current_version_id else None
    if current is not None and current.storage_identity == source["storage_identity"] and current.checksum == source["checksum"] and current.metadata_hash == source["metadata_hash"]:
        version_id = current.version_id
        revision = int(current.revision)
        version_fingerprint = _version_fingerprint(authority_id=authority_id, version_id=version_id, revision=revision, source=source)
    else:
        revision = (int(current.revision) + 1) if current is not None else 1
        version_id = _version_id(authority_id=authority_id, revision=revision, source=source)
        version_fingerprint = _version_fingerprint(authority_id=authority_id, version_id=version_id, revision=revision, source=source)
        if current is not None:
            current.status = "SUPERSEDED"
            session.query(ShotAssetBinding).filter(ShotAssetBinding.authority_id == authority_id, ShotAssetBinding.version_id == current.version_id, ShotAssetBinding.status == "ACTIVE").update({"status": "STALE"}, synchronize_session=False)
        session.add(ProductionAssetVersionRegistry(version_id=version_id, authority_id=authority_id, asset_type=kind))
        session.flush()
        version = config["version"](**{config["entity"]: entity_id, "version_id": version_id, "authority_id": authority_id, "storage_identity": source["storage_identity"], "checksum": source["checksum"], "metadata_hash": source["metadata_hash"], "revision": revision, "status": "CURRENT"})
        session.add(version)
        session.flush()
        authority.current_version_id = version_id
    pointer = session.query(config["pointer"]).filter_by(**{config["entity"]: entity_id}).one_or_none()
    pointer_fingerprint = _pointer_fingerprint(entity_id=entity_id, authority_id=authority_id, version_id=version_id)
    if pointer is None:
        pointer = config["pointer"](**{config["entity"]: entity_id, "authority_id": authority_id, "version_id": version_id, "fingerprint": pointer_fingerprint})
        session.add(pointer)
    else:
        pointer.authority_id = authority_id
        pointer.version_id = version_id
        pointer.fingerprint = pointer_fingerprint
    session.flush()
    return {
        "asset_type": kind,
        "entity_id": entity_id,
        "authority_id": authority_id,
        "version_id": version_id,
        "revision": revision,
        "authority_fingerprint": authority_fingerprint,
        "version_fingerprint": version_fingerprint,
        "pointer_fingerprint": pointer_fingerprint,
        "storage_identity": source["storage_identity"],
        "checksum": source["checksum"],
        "metadata_hash": source["metadata_hash"],
        "provider_calls": 0,
        "image_calls": 0,
        "video_calls": 0,
    }


def _find_asset(session, *, asset_type: str, authority_id: str, version_id: str):
    kind = _asset_type(asset_type)
    config = _typed_config(kind)
    authority = session.query(config["authority"]).filter_by(authority_id=authority_id).one_or_none()
    version = session.query(config["version"]).filter_by(version_id=version_id, authority_id=authority_id).one_or_none()
    if authority is None or version is None:
        raise AssetBindingInvalid("asset authority/version does not exist", diagnostics=[{"asset_type": kind, "authority_id": authority_id, "version_id": version_id}])
    entity_id = str(getattr(authority, config["entity"]))
    pointer = session.query(config["pointer"]).filter_by(**{config["entity"]: entity_id, "authority_id": authority_id}).one_or_none()
    if pointer is None:
        raise AssetBindingInvalid("asset pointer does not exist", diagnostics=[{"asset_type": kind, "authority_id": authority_id}])
    source = {"storage_identity": version.storage_identity, "checksum": version.checksum, "metadata_hash": version.metadata_hash}
    expected_authority_fp = _authority_fingerprint(book_id=990401, asset_type=kind, entity_id=entity_id, authority_id=authority_id)
    expected_version_fp = _version_fingerprint(authority_id=authority_id, version_id=version.version_id, revision=int(version.revision), source=source)
    expected_pointer_fp = _pointer_fingerprint(entity_id=entity_id, authority_id=authority_id, version_id=version.version_id)
    if authority.status != "ACTIVE" or version.status != "CURRENT" or authority.current_version_id != version.version_id or pointer.version_id != version.version_id or authority.fingerprint != expected_authority_fp or pointer.fingerprint != expected_pointer_fp:
        raise AssetBindingInvalid("asset authority/version/pointer is stale or drifted", diagnostics=[{"asset_type": kind, "authority_id": authority_id, "version_id": version_id, "current_version_id": authority.current_version_id, "pointer_version_id": pointer.version_id}])
    return {"asset_type": kind, "entity_id": entity_id, "authority_id": authority_id, "version_id": version.version_id, "authority_fingerprint": authority.fingerprint, "version_fingerprint": expected_version_fp, "pointer_fingerprint": pointer.fingerprint}


def bind_shot_assets(session, *, storyboard_shot_id: int, characters: list[Mapping[str, Any]], scene: Mapping[str, Any], props: list[Mapping[str, Any]]):
    """Persist formal shot bindings using only authority/version IDs."""
    if not isinstance(scene, Mapping) or not scene.get("authority_id") or not scene.get("version_id"):
        raise AssetBindingInvalid("scene binding is required")
    requested = [("CHARACTER", item) for item in characters] + [("SCENE", scene)] + [("PROP", item) for item in props]
    resolved = []
    for kind, item in requested:
        resolved.append(_find_asset(session, asset_type=kind, authority_id=str(item["authority_id"]), version_id=str(item["version_id"])))
    for asset in resolved:
        binding_fp = _binding_fingerprint(storyboard_shot_id=storyboard_shot_id, asset_type=asset["asset_type"], authority_fingerprint=asset["authority_fingerprint"], version_fingerprint=asset["version_fingerprint"], pointer_fingerprint=asset["pointer_fingerprint"])
        existing = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=storyboard_shot_id, asset_type=asset["asset_type"], authority_id=asset["authority_id"], version_id=asset["version_id"]).one_or_none()
        if existing is None:
            session.add(ShotAssetBinding(storyboard_shot_id=storyboard_shot_id, asset_type=asset["asset_type"], authority_id=asset["authority_id"], version_id=asset["version_id"], binding_fingerprint=binding_fp, status="ACTIVE"))
        elif existing.status != "ACTIVE" or existing.binding_fingerprint != binding_fp:
            existing.status = "ACTIVE"
            existing.binding_fingerprint = binding_fp
        asset["binding_fingerprint"] = binding_fp
    session.flush()
    return resolved


def resolve_shot_assets(session, *, storyboard_shot_id: int) -> dict[str, Any]:
    """Resolve and validate a shot's formal bindings; failures are HTTP 409 compatible."""
    rows = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=storyboard_shot_id).all()
    if not rows:
        raise AssetBindingInvalid("shot has no formal asset bindings")
    result = {"storyboard_shot_id": storyboard_shot_id, "characters": [], "scene": None, "props": [], "status": "PASS"}
    for row in rows:
        asset = _find_asset(session, asset_type=row.asset_type, authority_id=row.authority_id, version_id=row.version_id)
        expected = _binding_fingerprint(storyboard_shot_id=storyboard_shot_id, asset_type=row.asset_type, authority_fingerprint=asset["authority_fingerprint"], version_fingerprint=asset["version_fingerprint"], pointer_fingerprint=asset["pointer_fingerprint"])
        if row.status != "ACTIVE" or row.binding_fingerprint != expected:
            raise AssetBindingInvalid("shot binding fingerprint or lifecycle is invalid", diagnostics=[{"binding_id": row.id, "asset_type": row.asset_type, "status": row.status}])
        asset["binding_fingerprint"] = row.binding_fingerprint
        if row.asset_type == "CHARACTER":
            result["characters"].append(asset)
        elif row.asset_type == "SCENE":
            if result["scene"] is not None:
                raise AssetBindingInvalid("shot has duplicate scene bindings")
            result["scene"] = asset
        else:
            result["props"].append(asset)
    if result["scene"] is None or not result["characters"]:
        raise AssetBindingInvalid("shot requires one scene and at least one character binding")
    return result


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
    "AssetBindingInvalid",
    "ingest_production_asset",
    "bind_shot_assets",
    "resolve_shot_assets",
    "ProductionAssetAuthorityRepository",
    "validate_asset_authority_schema",
    "assert_asset_authority_schema",
]
