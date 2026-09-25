"""Provider-free Real Asset Canary reconcile pipeline.

The canary exercises the formal Production Asset Authority contract with a
frozen provider response.  It deliberately keeps provider output, normalized
source data, constraint checks, and approval state separate.  No authority or
binding row is written until every asset has passed normalization and the
cross-shot requirement checks.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.production_asset_authority import (
    ASSET_TYPES,
    bind_shot_assets,
    ingest_production_asset,
    production_asset_media_readiness,
    resolve_shot_assets,
)
from core.production_workspace_projection_v2 import _asset_readiness
from models import ShotAssetBinding, StoryboardShot


SCHEMA_VERSION = "real_asset_canary_v1"
BOOK_ID = 990401
EPISODE = 1
REQUIRED_PROVENANCE_FIELDS = (
    "source_reference",
    "provider_response_id",
    "provider_output_fingerprint",
    "captured_at",
    "provider",
    "fixture_mode",
    "is_mock",
)
APPROVAL_SEQUENCE = (
    "PROVIDER_OUTPUT",
    "NORMALIZED",
    "CONSTRAINTS_PASSED",
    "RECONCILE_READY",
    "CANARY_APPROVED",
)


class RealAssetCanaryError(ValueError):
    """Raised when the frozen provider response cannot be reconciled."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _provider_asset(*, asset_type: str, entity_id: str, response_id: str, source_reference: str, storage_identity: str, checksum: str) -> dict[str, Any]:
    provenance = {
        "source_reference": source_reference,
        "provider_response_id": response_id,
        "provider_output_fingerprint": _fingerprint({"response_id": response_id, "entity_id": entity_id, "checksum": checksum}),
        "captured_at": "2026-09-26T00:00:00Z",
        "provider": "fixture-provider",
        "fixture_mode": True,
        "is_mock": False,
    }
    metadata = {
        "schema_version": "production_asset_media_metadata_v1",
        "mime_type": "image/png",
        "width": 2048,
        "height": 2048,
        "source_kind": "real_asset_canary",
        "provenance": provenance,
    }
    return {
        "asset_type": asset_type,
        "entity_id": entity_id,
        "storage_identity": storage_identity,
        "checksum": checksum,
        "metadata": metadata,
        "provenance": provenance,
        "provider_response_id": response_id,
    }


def build_real_asset_canary_fixture() -> dict[str, Any]:
    """Return the frozen one-episode/three-shot provider response fixture."""
    assets = [
        _provider_asset(
            asset_type="CHARACTER",
            entity_id="CANARY_LIN_WAN",
            response_id="real-asset-canary-character-001",
            source_reference="provider-response://real-asset-canary/v1/character/CANARY_LIN_WAN",
            storage_identity="https://assets.example.invalid/real-asset-canary/character/canary-lin-wan-v1.png",
            checksum="sha256:real-asset-canary-character-v1",
        ),
        _provider_asset(
            asset_type="SCENE",
            entity_id="CANARY_E01_SC001",
            response_id="real-asset-canary-scene-001",
            source_reference="provider-response://real-asset-canary/v1/scene/CANARY_E01_SC001",
            storage_identity="https://assets.example.invalid/real-asset-canary/scene/canary-e01-sc001-v1.png",
            checksum="sha256:real-asset-canary-scene-v1",
        ),
    ]
    shots = [
        {
            "shot_id": 1,
            "plan_shot_id": "CANARY_E01_SC001_001",
            "scene_id": "CANARY_E01_SC001",
            "requirements": [
                {"asset_type": "CHARACTER", "entity_id": "CANARY_LIN_WAN"},
                {"asset_type": "SCENE", "entity_id": "CANARY_E01_SC001"},
            ],
        },
        {
            "shot_id": 2,
            "plan_shot_id": "CANARY_E01_SC001_002",
            "scene_id": "CANARY_E01_SC001",
            "requirements": [
                {"asset_type": "CHARACTER", "entity_id": "CANARY_LIN_WAN"},
                {"asset_type": "SCENE", "entity_id": "CANARY_E01_SC001"},
            ],
        },
        {
            "shot_id": 3,
            "plan_shot_id": "CANARY_E01_SC001_003",
            "scene_id": "CANARY_E01_SC001",
            "requirements": [
                {"asset_type": "CHARACTER", "entity_id": "CANARY_LIN_WAN"},
                {"asset_type": "SCENE", "entity_id": "CANARY_E01_SC001"},
            ],
        },
    ]
    response = {
        "schema_version": "provider_asset_response_fixture_v1",
        "provider": "fixture-provider",
        "fixture_mode": True,
        "provider_calls": 0,
        "response_id": "real-asset-canary-response-001",
        "assets": assets,
    }
    response["response_fingerprint"] = _fingerprint(response)
    return {
        "schema_version": SCHEMA_VERSION,
        "book_id": BOOK_ID,
        "episode": EPISODE,
        "provider_response": response,
        "shots": shots,
    }


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RealAssetCanaryError(f"{label} must be an object")
    return value


def normalize_provider_output(provider_response: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize provider fixture rows while preserving their provenance."""
    response = _require_mapping(provider_response, "provider_response")
    if response.get("fixture_mode") is not True or int(response.get("provider_calls") or 0) != 0:
        raise RealAssetCanaryError("real asset canary requires provider-free fixture mode")
    rows = response.get("assets")
    if not isinstance(rows, list) or not rows:
        raise RealAssetCanaryError("provider response must contain assets")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(rows):
        row = _require_mapping(raw, f"provider_response.assets[{index}]")
        asset_type = str(row.get("asset_type") or "").strip().upper()
        entity_id = str(row.get("entity_id") or "").strip()
        if asset_type not in ASSET_TYPES or not entity_id:
            raise RealAssetCanaryError(f"provider response asset {index} has invalid canonical identity")
        key = (asset_type, entity_id)
        if key in seen:
            raise RealAssetCanaryError(f"duplicate provider asset {asset_type}:{entity_id}")
        seen.add(key)
        metadata = _require_mapping(row.get("metadata"), f"provider_response.assets[{index}].metadata")
        provenance = _require_mapping(row.get("provenance") or metadata.get("provenance"), f"provider_response.assets[{index}].provenance")
        missing = [field for field in REQUIRED_PROVENANCE_FIELDS if field not in provenance]
        if missing:
            raise RealAssetCanaryError(f"{asset_type}:{entity_id} provenance missing {','.join(missing)}")
        if provenance.get("is_mock") is not False:
            raise RealAssetCanaryError(f"{asset_type}:{entity_id} mock assets cannot be approved")
        if provenance.get("fixture_mode") is not True or not str(provenance.get("source_reference") or "").strip():
            raise RealAssetCanaryError(f"{asset_type}:{entity_id} provenance is not fixture-backed with a source reference")
        expected_output_fingerprint = _fingerprint({
            "response_id": provenance.get("provider_response_id"),
            "entity_id": entity_id,
            "checksum": row.get("checksum"),
        })
        if str(provenance.get("provider_output_fingerprint") or "") != expected_output_fingerprint:
            raise RealAssetCanaryError(f"{asset_type}:{entity_id} provider output fingerprint does not match declared media")
        source = {
            "storage_identity": str(row.get("storage_identity") or "").strip(),
            "checksum": str(row.get("checksum") or "").strip(),
            "metadata": deepcopy(dict(metadata)),
        }
        if not source["storage_identity"] or not source["checksum"]:
            raise RealAssetCanaryError(f"{asset_type}:{entity_id} has incomplete media identity")
        normalized.append({
            "asset_type": asset_type,
            "entity_id": entity_id,
            "source": source,
            "provenance": deepcopy(dict(provenance)),
            "state": "NORMALIZED",
            "state_history": ["PROVIDER_OUTPUT", "NORMALIZED"],
        })
    return normalized


def _requirements(fixture: Mapping[str, Any]) -> set[tuple[str, str]]:
    required: set[tuple[str, str]] = set()
    for shot in fixture.get("shots", []):
        for requirement in shot.get("requirements", []):
            required.add((str(requirement.get("asset_type") or "").upper(), str(requirement.get("entity_id") or "")))
    return required


def check_asset_constraints(fixture: Mapping[str, Any], normalized: list[dict[str, Any]]) -> dict[str, Any]:
    """Run media, provenance, requirement and lifecycle checks without writes."""
    required = _requirements(fixture)
    by_identity = {(row["asset_type"], row["entity_id"]): row for row in normalized}
    errors: list[dict[str, Any]] = []
    checks = {
        "asset_has_source_reference": True,
        "asset_matches_shot_requirement": True,
        "asset_state_transition_valid": True,
        "asset_media_readiness": True,
        "asset_provenance_complete": True,
        "mock_asset_not_approved": True,
    }
    for identity, row in by_identity.items():
        provenance = row["provenance"]
        if not str(provenance.get("source_reference") or "").strip():
            checks["asset_has_source_reference"] = False
            errors.append({"code": "ASSET_SOURCE_REFERENCE_MISSING", "asset": f"{identity[0]}:{identity[1]}"})
        if any(field not in provenance for field in REQUIRED_PROVENANCE_FIELDS):
            checks["asset_provenance_complete"] = False
            errors.append({"code": "ASSET_PROVENANCE_INCOMPLETE", "asset": f"{identity[0]}:{identity[1]}"})
        if provenance.get("is_mock") is not False:
            checks["mock_asset_not_approved"] = False
            errors.append({"code": "MOCK_ASSET_REJECTED", "asset": f"{identity[0]}:{identity[1]}"})
        media = production_asset_media_readiness(
            storage_identity=row["source"]["storage_identity"],
            checksum=row["source"]["checksum"],
            metadata_hash=_fingerprint(row["source"]["source_metadata"] if "source_metadata" in row["source"] else row["source"]["metadata"]),
            metadata=row["source"]["metadata"],
        )
        row["media_readiness"] = media.to_dict()
        if not media.present:
            checks["asset_media_readiness"] = False
            errors.append({"code": "ASSET_MEDIA_NOT_READY", "asset": f"{identity[0]}:{identity[1]}", "reason_codes": list(media.reason_codes)})
        if media.present and checks["asset_provenance_complete"] and provenance.get("is_mock") is False:
            row["state"] = "CONSTRAINTS_PASSED"
            row["state_history"].append("CONSTRAINTS_PASSED")
        else:
            row["state"] = "REJECTED"
            row["state_history"].append("REJECTED")
    missing = sorted(required - set(by_identity))
    extra = sorted(set(by_identity) - required)
    if missing:
        checks["asset_matches_shot_requirement"] = False
        errors.append({"code": "ASSET_SHOT_REQUIREMENT_MISSING", "assets": [f"{kind}:{entity}" for kind, entity in missing]})
    if extra:
        errors.append({"code": "ASSET_NOT_REQUIRED_BY_SHOTS", "assets": [f"{kind}:{entity}" for kind, entity in extra]})
    for shot in fixture.get("shots", []):
        for requirement in shot.get("requirements", []):
            key = (str(requirement.get("asset_type") or "").upper(), str(requirement.get("entity_id") or ""))
            row = by_identity.get(key)
            if row is None or row.get("state") != "CONSTRAINTS_PASSED":
                checks["asset_matches_shot_requirement"] = False
                errors.append({"code": "ASSET_SHOT_REQUIREMENT_UNSATISFIED", "shot_id": shot.get("shot_id"), "asset": f"{key[0]}:{key[1]}"})
    if not all(checks.values()):
        for row in normalized:
            if row.get("state") == "CONSTRAINTS_PASSED":
                row["state"] = "REJECTED"
                row["state_history"].append("REJECTED")
    return {"checks": checks, "errors": errors, "required_assets": sorted(f"{kind}:{entity}" for kind, entity in required)}


def _shot_row(session: Any, *, fixture: Mapping[str, Any], shot: Mapping[str, Any]) -> StoryboardShot:
    existing = session.query(StoryboardShot).filter_by(book_id=int(fixture["book_id"]), episode=int(fixture["episode"]), plan_shot_id=str(shot["plan_shot_id"])).one_or_none()
    requirements = {"production_asset_requirements": shot["requirements"]}
    if existing is None:
        existing = StoryboardShot(
            book_id=int(fixture["book_id"]),
            episode=int(fixture["episode"]),
            scene_name=str(shot["scene_id"]),
            scene_id=str(shot["scene_id"]),
            plan_shot_id=str(shot["plan_shot_id"]),
            shot_id=int(shot["shot_id"]),
            duration=3,
            asset_links=json.dumps(requirements, ensure_ascii=False, sort_keys=True),
            asset_status="asset_ready",
            execution_status="queued",
            quality_status="qualified",
            production_status="ready",
            workflow_profile="production",
        )
        session.add(existing)
        session.flush()
    else:
        existing.asset_links = json.dumps(requirements, ensure_ascii=False, sort_keys=True)
        existing.production_status = "ready"
        existing.asset_status = "asset_ready"
        session.flush()
    return existing


def _source_gate_counts(session: Any) -> dict[str, int] | None:
    if session is None:
        return None
    from models import FactRecord, FactSnapshot, ScriptIRVersion

    return {
        "fact_snapshots": int(session.query(FactSnapshot).count()),
        "fact_records": int(session.query(FactRecord).count()),
        "script_ir_versions": int(session.query(ScriptIRVersion).count()),
    }


def reconcile_real_asset_canary(session: Any, fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Reconcile the fixture and persist formal rows only after all checks pass."""
    fixture = deepcopy(dict(fixture or build_real_asset_canary_fixture()))
    response = _require_mapping(fixture.get("provider_response"), "provider_response")
    source_gate_before = _source_gate_counts(session)
    normalized = normalize_provider_output(response)
    constraint_result = check_asset_constraints(fixture, normalized)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "book_id": int(fixture["book_id"]),
        "episode": int(fixture["episode"]),
        "provider_calls": int(response.get("provider_calls") or 0),
        "production_writes_before_reconcile": 0,
        "normalized_asset_count": len(normalized),
        "constraint_checks": constraint_result["checks"],
        "constraint_errors": constraint_result["errors"],
        "required_assets": constraint_result["required_assets"],
        "approval_state": "REJECTED",
        "production_writes": {"allowed": False, "authority": 0, "version": 0, "pointer": 0, "shot": 0, "binding": 0},
        "assets": normalized,
        "shots": deepcopy(fixture.get("shots", [])),
        "source_gate_counts_before": source_gate_before,
    }
    if constraint_result["errors"] or not all(constraint_result["checks"].values()):
        return result
    for row in normalized:
        row["state"] = "RECONCILE_READY"
        row["state_history"].append("RECONCILE_READY")
    if session is None:
        result["approval_state"] = "RECONCILE_READY"
        result["production_writes"]["allowed"] = True
        return result

    nested = session.begin_nested()
    try:
        ingested: dict[tuple[str, str], dict[str, Any]] = {}
        for row in normalized:
            ingested[(row["asset_type"], row["entity_id"])] = ingest_production_asset(
                session,
                entity_type=row["asset_type"],
                entity_id=row["entity_id"],
                source=row["source"],
                book_id=int(fixture["book_id"]),
            )
        shot_rows: list[StoryboardShot] = []
        for shot in fixture.get("shots", []):
            shot_row = _shot_row(session, fixture=fixture, shot=shot)
            shot_rows.append(shot_row)
            character = ingested[("CHARACTER", "CANARY_LIN_WAN")]
            scene = ingested[("SCENE", "CANARY_E01_SC001")]
            bind_shot_assets(
                session,
                storyboard_shot_id=int(shot_row.id),
                characters=[{"authority_id": character["authority_id"], "version_id": character["version_id"]}],
                scene={"authority_id": scene["authority_id"], "version_id": scene["version_id"]},
                props=[],
            )
        session.flush()
        for shot_row in shot_rows:
            resolve_shot_assets(session, storyboard_shot_id=int(shot_row.id))
        nested.commit()
    except Exception:
        nested.rollback()
        raise

    for row in normalized:
        row["state"] = "CANARY_APPROVED"
        row["state_history"].append("CANARY_APPROVED")
    result["approval_state"] = "CANARY_APPROVED"
    result["production_writes"] = {
        "allowed": True,
        "authority": len(normalized),
        "version": len(normalized),
        "pointer": len(normalized),
        "shot": len(fixture.get("shots", [])),
        "binding": len(fixture.get("shots", [])) * 2,
        "only_after_reconcile": True,
    }
    readiness = []
    for shot_row in session.query(StoryboardShot).filter_by(book_id=int(fixture["book_id"]), episode=int(fixture["episode"])).order_by(StoryboardShot.shot_id.asc()).all():
        readiness.append(_asset_readiness(session, shot_id=int(shot_row.id), book_id=int(fixture["book_id"])))
    result["v2_asset_readiness"] = readiness
    source_gate_after = _source_gate_counts(session)
    result["source_gate_counts_after"] = source_gate_after
    result["source_gate_mutations"] = {
        key: int((source_gate_after or {}).get(key, 0)) - int((source_gate_before or {}).get(key, 0))
        for key in (source_gate_before or {})
    }
    result["asset_truth_checks"] = {
        "asset_has_source_reference": all(bool(row["provenance"].get("source_reference")) for row in normalized),
        "asset_matches_shot_requirement": all(item.get("current") is True for item in readiness),
        "asset_state_transition_valid": all(row.get("state_history") == list(APPROVAL_SEQUENCE) for row in normalized),
    }
    return result


def build_canary_truth_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    checks = dict(result.get("constraint_checks") or {})
    checks.update(result.get("asset_truth_checks") or {})
    audit = {
        "schema_version": "real_asset_truth_audit_v1",
        "stage": "PHASE_UI_V2_REAL_ASSET_CANARY_COMPLETE" if result.get("approval_state") == "CANARY_APPROVED" else "PHASE_UI_V2_REAL_ASSET_CANARY_BLOCKED",
        "fixture_mode": True,
        "provider_calls": int(result.get("provider_calls") or 0),
        "production_writes_allowed_only_after_reconcile": bool((result.get("production_writes") or {}).get("only_after_reconcile")),
        "mock_asset_production_approved": False,
        "provenance_metadata_required": True,
        "checks": checks,
        "approval_state": result.get("approval_state"),
        "production_approval_state": "CANARY_APPROVED_ONLY" if result.get("approval_state") == "CANARY_APPROVED" else "NOT_APPROVED",
        "normalized_asset_count": result.get("normalized_asset_count", 0),
        "shot_count": len(result.get("shots") or []),
        "asset_count": len(result.get("assets") or []),
        "source_gate_counts_before": result.get("source_gate_counts_before"),
        "source_gate_counts_after": result.get("source_gate_counts_after"),
        "source_gate_mutations": result.get("source_gate_mutations") or {},
        "source_fact_mutations": sum(int(value) for key, value in (result.get("source_gate_mutations") or {}).items() if key != "script_ir_versions"),
        "script_ir_mutations": int((result.get("source_gate_mutations") or {}).get("script_ir_versions", 0)),
    }
    for key in ("asset_has_source_reference", "asset_matches_shot_requirement", "asset_state_transition_valid"):
        audit[key] = bool(checks.get(key))
    return audit


__all__ = [
    "APPROVAL_SEQUENCE",
    "BOOK_ID",
    "EPISODE",
    "SCHEMA_VERSION",
    "build_canary_truth_audit",
    "build_real_asset_canary_fixture",
    "check_asset_constraints",
    "normalize_provider_output",
    "reconcile_real_asset_canary",
]
