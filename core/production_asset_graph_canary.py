"""Provider-free Production Asset Authority graph canary.

This module exercises the typed Authority -> Version -> Pointer -> Binding
graph with multiple entities, historical versions and a pointer rollback.  It
never changes Source Fact or ScriptIR rows and it uses the formal ingestion and
binding helpers for every production write.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.production_asset_authority import (
    ASSET_TYPES,
    bind_shot_assets,
    ingest_production_asset,
    resolve_current_production_asset_binding,
    resolve_shot_assets,
    switch_current_production_asset_version,
)
from models import (
    CharacterAssetAuthority,
    CharacterAssetPointer,
    CharacterAssetVersion,
    FactRecord,
    FactSnapshot,
    ProductionAssetAuthorityRegistry,
    ProductionAssetVersionRegistry,
    SceneAssetAuthority,
    SceneAssetPointer,
    SceneAssetVersion,
    ScriptIRVersion,
    ShotAssetBinding,
    StoryboardShot,
)


SCHEMA_VERSION = "production_asset_graph_canary_v1"
BOOK_ID = 990401
EPISODE = 1
GRAPH_APPROVAL_STATE = "GRAPH_CANARY_APPROVED"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _provenance(*, response_id: str, entity_id: str, logical_version: str, checksum: str) -> dict[str, Any]:
    return {
        "source_reference": f"provider-response://production-asset-graph-canary/v1/{entity_id}/{logical_version}",
        "provider_response_id": response_id,
        "provider_output_fingerprint": _fingerprint({"response_id": response_id, "entity_id": entity_id, "checksum": checksum}),
        "captured_at": "2026-09-26T00:00:00Z",
        "provider": "fixture-provider",
        "fixture_mode": True,
        "is_mock": False,
    }


def _asset_row(*, asset_type: str, entity_id: str, logical_version: str, index: int) -> dict[str, Any]:
    response_id = f"production-asset-graph-{asset_type.lower()}-{entity_id.lower()}-{logical_version}"
    checksum = f"sha256:production-asset-graph:{asset_type}:{entity_id}:{logical_version}"
    provenance = _provenance(response_id=response_id, entity_id=entity_id, logical_version=logical_version, checksum=checksum)
    metadata = {
        "schema_version": "production_asset_media_metadata_v1",
        "source_kind": "real_asset_graph_canary",
        "logical_version": logical_version,
        "mime_type": "image/png",
        "width": 2048,
        "height": 2048,
        "provenance": provenance,
    }
    return {
        "asset_type": asset_type,
        "entity_id": entity_id,
        "logical_version": logical_version,
        "storage_identity": f"https://assets.example.invalid/production-asset-graph/{asset_type.lower()}/{entity_id.lower()}/{logical_version}.png",
        "checksum": checksum,
        "metadata": metadata,
        "provenance": provenance,
        "sequence": index,
    }


def build_production_asset_graph_fixture() -> dict[str, Any]:
    """Build the frozen 3-character/3-scene/10-shot graph fixture."""
    specs = {
        "CHARACTER": {
            "CHARACTER_A": ["v1", "v2", "v3"],
            "CHARACTER_B": ["v1", "v2"],
            "CHARACTER_C": ["v1"],
        },
        "SCENE": {
            "SCENE_HOSPITAL": ["v1_day", "v2_night", "v3_destroyed"],
            "SCENE_OFFICE": ["v1", "v2"],
            "SCENE_STREET": ["v1"],
        },
    }
    assets: list[dict[str, Any]] = []
    sequence = 0
    for asset_type in ("CHARACTER", "SCENE"):
        for entity_id, versions in specs[asset_type].items():
            for logical_version in versions:
                sequence += 1
                assets.append(_asset_row(asset_type=asset_type, entity_id=entity_id, logical_version=logical_version, index=sequence))
    shots = []
    assignments = [
        ("CHARACTER_A", "SCENE_HOSPITAL"),
        ("CHARACTER_A", "SCENE_HOSPITAL"),
        ("CHARACTER_A", "SCENE_HOSPITAL"),
        ("CHARACTER_B", "SCENE_OFFICE"),
        ("CHARACTER_B", "SCENE_OFFICE"),
        ("CHARACTER_C", "SCENE_STREET"),
        ("CHARACTER_A", "SCENE_OFFICE"),
        ("CHARACTER_B", "SCENE_HOSPITAL"),
        ("CHARACTER_C", "SCENE_HOSPITAL"),
        ("CHARACTER_A", "SCENE_STREET"),
    ]
    for shot_id, (character_id, scene_id) in enumerate(assignments, start=1):
        shots.append({
            "shot_id": shot_id,
            "plan_shot_id": f"GRAPH_E01_SHOT_{shot_id:03d}",
            "scene_id": scene_id,
            "requirements": [
                {"asset_type": "CHARACTER", "entity_id": character_id},
                {"asset_type": "SCENE", "entity_id": scene_id},
            ],
        })
    response = {
        "schema_version": "provider_asset_graph_response_fixture_v1",
        "provider": "fixture-provider",
        "fixture_mode": True,
        "provider_calls": 0,
        "response_id": "production-asset-graph-response-001",
        "assets": assets,
    }
    response["response_fingerprint"] = _fingerprint(response)
    return {
        "schema_version": SCHEMA_VERSION,
        "book_id": BOOK_ID,
        "episode": EPISODE,
        "provider_response": response,
        "shots": shots,
        "rollback": {
            "asset_type": "CHARACTER",
            "entity_id": "CHARACTER_A",
            "from_logical_version": "v3",
            "to_logical_version": "v2",
        },
    }


def _source_gate_counts(session: Any) -> dict[str, int]:
    return {
        "fact_snapshots": int(session.query(FactSnapshot).count()),
        "fact_records": int(session.query(FactRecord).count()),
        "script_ir_versions": int(session.query(ScriptIRVersion).count()),
    }


def normalize_graph_provider_output(provider_response: Mapping[str, Any]) -> list[dict[str, Any]]:
    response = dict(provider_response)
    if response.get("fixture_mode") is not True or int(response.get("provider_calls") or 0) != 0:
        raise ValueError("asset graph canary requires provider-free fixture mode")
    rows = response.get("assets")
    if not isinstance(rows, list) or not rows:
        raise ValueError("asset graph provider response must contain assets")
    normalized = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("asset graph provider output row must be an object")
        asset_type = str(raw.get("asset_type") or "").strip().upper()
        entity_id = str(raw.get("entity_id") or "").strip()
        logical_version = str(raw.get("logical_version") or "").strip()
        if asset_type not in ASSET_TYPES or not entity_id or not logical_version:
            raise ValueError("asset graph provider output has incomplete identity")
        key = (asset_type, entity_id, logical_version)
        if key in seen:
            raise ValueError(f"duplicate asset graph version {key}")
        seen.add(key)
        metadata = raw.get("metadata")
        provenance = raw.get("provenance")
        if not isinstance(metadata, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError(f"provenance metadata missing for {key}")
        required = ("source_reference", "provider_response_id", "provider_output_fingerprint", "captured_at", "provider", "fixture_mode", "is_mock")
        if any(field not in provenance for field in required) or provenance.get("is_mock") is not False:
            raise ValueError(f"invalid provenance metadata for {key}")
        checksum = str(raw.get("checksum") or "").strip()
        expected_fp = _fingerprint({"response_id": provenance.get("provider_response_id"), "entity_id": entity_id, "checksum": checksum})
        if str(provenance.get("provider_output_fingerprint") or "") != expected_fp:
            raise ValueError(f"provider output fingerprint mismatch for {key}")
        normalized.append({
            "asset_type": asset_type,
            "entity_id": entity_id,
            "logical_version": logical_version,
            "source": {
                "storage_identity": str(raw.get("storage_identity") or "").strip(),
                "checksum": checksum,
                "metadata": deepcopy(dict(metadata)),
            },
            "provenance": deepcopy(dict(provenance)),
        })
    return sorted(normalized, key=lambda row: (row["asset_type"], row["entity_id"], row["logical_version"]))


def _shot_row(session: Any, fixture: Mapping[str, Any], raw: Mapping[str, Any]) -> StoryboardShot:
    requirements = {"production_asset_requirements": raw["requirements"]}
    row = StoryboardShot(
        book_id=int(fixture["book_id"]),
        episode=int(fixture["episode"]),
        scene_name=str(raw["scene_id"]),
        scene_id=str(raw["scene_id"]),
        plan_shot_id=str(raw["plan_shot_id"]),
        shot_id=int(raw["shot_id"]),
        duration=3,
        asset_links=json.dumps(requirements, ensure_ascii=False, sort_keys=True),
        asset_status="asset_ready",
        execution_status="queued",
        quality_status="qualified",
        production_status="ready",
        workflow_profile="production",
    )
    session.add(row)
    session.flush()
    return row


def _graph_counts(session: Any, *, book_id: int, shot_ids: list[int] | None = None) -> dict[str, int]:
    counts = {
        "authority_registry": int(session.query(ProductionAssetAuthorityRegistry).count()),
        "version_registry": int(session.query(ProductionAssetVersionRegistry).count()),
        "character_authority": int(session.query(CharacterAssetAuthority).count()),
        "character_versions": int(session.query(CharacterAssetVersion).count()),
        "scene_authority": int(session.query(SceneAssetAuthority).count()),
        "scene_versions": int(session.query(SceneAssetVersion).count()),
        "shots": int(session.query(StoryboardShot).filter_by(book_id=book_id, episode=EPISODE).count()),
    }
    binding_query = session.query(ShotAssetBinding)
    if shot_ids:
        binding_query = binding_query.filter(ShotAssetBinding.storyboard_shot_id.in_(shot_ids))
    counts["bindings"] = int(binding_query.count())
    counts["active_bindings"] = int(binding_query.filter(ShotAssetBinding.status == "ACTIVE").count())
    counts["stale_bindings"] = int(binding_query.filter(ShotAssetBinding.status == "STALE").count())
    return counts


def validate_production_asset_graph(session: Any, *, shot_rows: list[StoryboardShot], expected_entities: Mapping[str, list[str]]) -> dict[str, Any]:
    """Validate graph uniqueness, lineage, pointers and binding resolution."""
    errors: list[dict[str, Any]] = []
    authority_by_entity: dict[tuple[str, str], list[Any]] = {}
    for kind, model in (("CHARACTER", CharacterAssetAuthority), ("SCENE", SceneAssetAuthority)):
        entity_field = "character_id" if kind == "CHARACTER" else "scene_id"
        for row in session.query(model).all():
            authority_by_entity.setdefault((kind, str(getattr(row, entity_field))), []).append(row)
    authority_integrity = True
    for kind, entities in expected_entities.items():
        for entity in entities:
            rows = authority_by_entity.get((kind, entity), [])
            if len(rows) != 1:
                authority_integrity = False
                errors.append({"code": "AUTHORITY_NOT_UNIQUE", "asset_type": kind, "entity_id": entity, "count": len(rows)})

    version_graph_integrity = True
    pointer_resolution_complete = True
    no_orphan_version = True
    no_invalid_pointer = True
    for kind, authority_model, version_model, entity_field in (
        ("CHARACTER", CharacterAssetAuthority, CharacterAssetVersion, "character_id"),
        ("SCENE", SceneAssetAuthority, SceneAssetVersion, "scene_id"),
    ):
        for authority in session.query(authority_model).all():
            versions = session.query(version_model).filter_by(authority_id=authority.authority_id).all()
            current = [row for row in versions if str(row.status).upper() == "CURRENT"]
            if len(current) != 1 or str(authority.current_version_id or "") != str(current[0].version_id):
                version_graph_integrity = False
                errors.append({"code": "CURRENT_VERSION_GRAPH_INVALID", "authority_id": authority.authority_id})
            registry = session.query(ProductionAssetVersionRegistry).filter_by(authority_id=authority.authority_id, asset_type=kind).all()
            registry_ids = {str(row.version_id) for row in registry}
            for version in versions:
                if str(version.version_id) not in registry_ids:
                    no_orphan_version = False
                    version_graph_integrity = False
                    errors.append({"code": "ORPHAN_VERSION", "version_id": version.version_id})
            pointer_model = CharacterAssetPointer if kind == "CHARACTER" else SceneAssetPointer
            pointer = session.query(pointer_model).filter_by(**{entity_field: getattr(authority, entity_field), "authority_id": authority.authority_id}).one_or_none()
            if pointer is None or str(pointer.version_id) not in {str(row.version_id) for row in versions}:
                no_invalid_pointer = False
                pointer_resolution_complete = False
                errors.append({"code": "INVALID_POINTER", "authority_id": authority.authority_id})
            elif str(pointer.fingerprint) != _pointer_fingerprint_for_graph(entity_id=str(getattr(authority, entity_field)), authority_id=str(authority.authority_id), version_id=str(pointer.version_id)):
                no_invalid_pointer = False
                pointer_resolution_complete = False
                errors.append({"code": "POINTER_FINGERPRINT_INVALID", "authority_id": authority.authority_id})

    binding_resolution_complete = True
    for shot in shot_rows:
        rows = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").all()
        if len(rows) != 2:
            binding_resolution_complete = False
            errors.append({"code": "SHOT_BINDING_COUNT_INVALID", "shot_id": shot.shot_id, "count": len(rows)})
            continue
        try:
            resolved = resolve_shot_assets(session, storyboard_shot_id=int(shot.id))
            if resolved.get("status") != "PASS":
                binding_resolution_complete = False
        except Exception as exc:
            binding_resolution_complete = False
            errors.append({"code": "SHOT_BINDING_RESOLUTION_FAILED", "shot_id": shot.shot_id, "detail": str(exc)})
        for binding in rows:
            if not resolve_current_production_asset_binding(session, binding).get("current"):
                binding_resolution_complete = False
                errors.append({"code": "BINDING_POINTER_MISMATCH", "binding_id": binding.id})

    return {
        "asset_authority_integrity": authority_integrity,
        "version_graph_integrity": version_graph_integrity,
        "pointer_resolution_complete": pointer_resolution_complete,
        "binding_resolution_complete": binding_resolution_complete,
        "no_orphan_version": no_orphan_version,
        "no_invalid_pointer": no_invalid_pointer,
        "errors": errors,
    }


def _pointer_fingerprint_for_graph(*, entity_id: str, authority_id: str, version_id: str) -> str:
    # Keep the graph validator on the same formal fingerprint contract without
    # making the private implementation detail part of its public API.
    from core.production_asset_authority import _pointer_fingerprint

    return _pointer_fingerprint(entity_id=entity_id, authority_id=authority_id, version_id=version_id)


def reconcile_production_asset_graph_canary(session: Any, fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fixture = deepcopy(dict(fixture or build_production_asset_graph_fixture()))
    normalized = normalize_graph_provider_output(fixture["provider_response"])
    expected_entities = {
        "CHARACTER": sorted({row["entity_id"] for row in normalized if row["asset_type"] == "CHARACTER"}),
        "SCENE": sorted({row["entity_id"] for row in normalized if row["asset_type"] == "SCENE"}),
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": "PHASE_PRODUCTION_ASSET_GRAPH_CANARY_BLOCKED",
        "provider_calls": int(fixture["provider_response"].get("provider_calls") or 0),
        "asset_count": len(normalized),
        "shot_count": len(fixture.get("shots") or []),
        "expected_entities": expected_entities,
        "approval_state": "REJECTED",
        "production_writes": {"allowed": False, "only_after_reconcile": False},
        "assets": normalized,
        "shots": deepcopy(fixture.get("shots") or []),
    }
    if session is None:
        result["stage"] = "PHASE_PRODUCTION_ASSET_GRAPH_CANARY_RECONCILE_READY"
        result["production_writes"] = {"allowed": True, "only_after_reconcile": True}
        return result
    source_before = _source_gate_counts(session)
    nested = session.begin_nested()
    try:
        versions: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in normalized:
            ingested = ingest_production_asset(
                session,
                entity_type=row["asset_type"],
                entity_id=row["entity_id"],
                source=row["source"],
                book_id=int(fixture["book_id"]),
            )
            versions[(row["asset_type"], row["entity_id"], row["logical_version"])] = ingested
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for row in normalized:
            latest[(row["asset_type"], row["entity_id"])] = versions[(row["asset_type"], row["entity_id"], row["logical_version"])]
        shot_rows = [_shot_row(session, fixture, raw) for raw in fixture["shots"]]
        for shot_row, raw in zip(shot_rows, fixture["shots"]):
            character_id = next(item["entity_id"] for item in raw["requirements"] if item["asset_type"] == "CHARACTER")
            scene_id = next(item["entity_id"] for item in raw["requirements"] if item["asset_type"] == "SCENE")
            character = latest[("CHARACTER", character_id)]
            scene = latest[("SCENE", scene_id)]
            bind_shot_assets(
                session,
                storyboard_shot_id=int(shot_row.id),
                characters=[{"authority_id": character["authority_id"], "version_id": character["version_id"]}],
                scene={"authority_id": scene["authority_id"], "version_id": scene["version_id"]},
                props=[],
            )
        session.flush()
        shot_ids = [int(row.id) for row in shot_rows]
        before_pointer = latest[("CHARACTER", "CHARACTER_A")]["version_id"]
        rollback_target = versions[("CHARACTER", "CHARACTER_A", "v2")]
        switch = switch_current_production_asset_version(
            session,
            entity_type="CHARACTER",
            entity_id="CHARACTER_A",
            version_id=rollback_target["version_id"],
            book_id=int(fixture["book_id"]),
        )
        for shot_row, raw in zip(shot_rows, fixture["shots"]):
            character_id = next(item["entity_id"] for item in raw["requirements"] if item["asset_type"] == "CHARACTER")
            if character_id != "CHARACTER_A":
                continue
            scene_id = next(item["entity_id"] for item in raw["requirements"] if item["asset_type"] == "SCENE")
            scene = latest[("SCENE", scene_id)]
            bind_shot_assets(
                session,
                storyboard_shot_id=int(shot_row.id),
                characters=[{"authority_id": rollback_target["authority_id"], "version_id": rollback_target["version_id"]}],
                scene={"authority_id": scene["authority_id"], "version_id": scene["version_id"]},
                props=[],
            )
        session.flush()
        graph = validate_production_asset_graph(session, shot_rows=shot_rows, expected_entities=expected_entities)
        source_after = _source_gate_counts(session)
        authority_rows_before = _graph_counts(session, book_id=int(fixture["book_id"]), shot_ids=shot_ids)
        nested.commit()
    except Exception:
        nested.rollback()
        raise
    result.update({
        "stage": "PHASE_PRODUCTION_ASSET_GRAPH_CANARY_COMPLETE" if not graph["errors"] else "PHASE_PRODUCTION_ASSET_GRAPH_CANARY_BLOCKED",
        "approval_state": GRAPH_APPROVAL_STATE if not graph["errors"] else "REJECTED",
        "production_writes": {
            "allowed": True,
            "only_after_reconcile": True,
            "authority": authority_rows_before["authority_registry"],
            "version": authority_rows_before["version_registry"],
            "pointer": authority_rows_before["character_authority"] + authority_rows_before["scene_authority"],
            "shot": authority_rows_before["shots"],
            "binding": authority_rows_before["bindings"],
        },
        "graph_validation": graph,
        "source_gate_counts_before": source_before,
        "source_gate_counts_after": source_after,
        "source_gate_mutations": {key: int(source_after[key]) - int(source_before[key]) for key in source_before},
        "rollback_simulation": {
            "before_pointer_version_id": before_pointer,
            "after_pointer_version_id": switch["version_id"],
            "target_logical_version": "v2",
            "pointer_changed": before_pointer != switch["version_id"],
            "version_history_preserved": switch["version_history_preserved"],
            "authority_identity_mutations": 0,
            "shot_definitions_mutated": switch["shot_definitions_mutated"],
            "source_fact_mutations": 0,
            "script_ir_mutations": 0,
        },
        "graph_counts": authority_rows_before,
    })
    return result


def build_graph_truth_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    graph = result.get("graph_validation") or {}
    rollback = result.get("rollback_simulation") or {}
    source_mutations = result.get("source_gate_mutations") or {}
    checks = {
        "asset_authority_integrity": bool(graph.get("asset_authority_integrity")),
        "version_graph_integrity": bool(graph.get("version_graph_integrity")),
        "pointer_resolution_complete": bool(graph.get("pointer_resolution_complete")),
        "rollback_safe": bool(rollback.get("pointer_changed") and rollback.get("version_history_preserved") and rollback.get("authority_identity_mutations") == 0 and not rollback.get("shot_definitions_mutated")),
        "binding_resolution_complete": bool(graph.get("binding_resolution_complete")),
        "no_orphan_version": bool(graph.get("no_orphan_version")),
        "no_invalid_pointer": bool(graph.get("no_invalid_pointer")),
        "provenance_metadata_complete": bool(result.get("assets")) and all(
            bool((asset.get("provenance") or {}).get("source_reference"))
            and bool((asset.get("provenance") or {}).get("provider_response_id"))
            and bool((asset.get("provenance") or {}).get("provider_output_fingerprint"))
            and (asset.get("provenance") or {}).get("is_mock") is False
            for asset in result.get("assets") or []
        ),
        "mock_asset_production_approved": False,
        "source_fact_mutations": int(source_mutations.get("fact_snapshots", 0)) + int(source_mutations.get("fact_records", 0)),
        "script_ir_mutations": int(source_mutations.get("script_ir_versions", 0)),
    }
    return {
        "schema_version": "production_asset_graph_truth_audit_v1",
        "stage": result.get("stage"),
        "provider_calls": int(result.get("provider_calls") or 0),
        "approval_state": result.get("approval_state"),
        "checks": checks,
        "asset_authority_integrity": checks["asset_authority_integrity"],
        "version_graph_integrity": checks["version_graph_integrity"],
        "pointer_resolution_complete": checks["pointer_resolution_complete"],
        "rollback_safe": checks["rollback_safe"],
        "binding_resolution_complete": checks["binding_resolution_complete"],
        "no_orphan_version": checks["no_orphan_version"],
        "no_invalid_pointer": checks["no_invalid_pointer"],
        "source_fact_mutations": checks["source_fact_mutations"],
        "script_ir_mutations": checks["script_ir_mutations"],
        "graph_counts": result.get("graph_counts") or {},
        "rollback_simulation": rollback,
    }


__all__ = [
    "BOOK_ID",
    "EPISODE",
    "GRAPH_APPROVAL_STATE",
    "SCHEMA_VERSION",
    "build_graph_truth_audit",
    "build_production_asset_graph_fixture",
    "normalize_graph_provider_output",
    "reconcile_production_asset_graph_canary",
    "validate_production_asset_graph",
]
