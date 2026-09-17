"""Production authority contract for SceneBlocking.

This module is deliberately provider-free.  It turns the already approved
ScriptIR and DirectorTreatment into an auditable spatial authority boundary;
it does not invent staging facts and it never resolves a production row by
``latest approved``.  Creative/legacy callers may continue using the V1
builder, while ShotPlan production callers must use the explicit pointer
resolver below.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException


SCHEMA_VERSION = "scene_blocking_authority_envelope_v1"
CONTRACT_SCHEMA_VERSION = "scene_blocking_authority_contract_v1"
AUTHORITY_POLICY_VERSION = "scene_blocking_authority_policy_v1"

SOURCE_SPATIAL_CONSTRAINT = "SOURCE_SPATIAL_CONSTRAINT"
DIRECTOR_CONSTRAINT = "DIRECTOR_CONSTRAINT"
BLOCKING_AUTHORING_DECISION = "BLOCKING_AUTHORING_DECISION"
DERIVED_SPATIAL_CONSTRAINT = "DERIVED_SPATIAL_CONSTRAINT"
UNKNOWN_UNRESOLVED = "UNKNOWN_UNRESOLVED"

QUALIFICATION_STATES = (
    "DRAFT", "CANDIDATE", "REVIEW_REQUIRED", "APPROVED", "AUTHORITY_BOUND",
    "STRUCTURALLY_VALID", "UPSTREAM_AUTHORITY_BOUND", "SPATIAL_CONSTRAINTS_VALID",
    "CONTINUITY_READY", "SHOT_PLAN_READY", "PRODUCTION_QUALIFIED", "STALE",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _envelope_fingerprint(value: dict[str, Any]) -> str:
    return fingerprint({key: item for key, item in value.items() if key != "envelope_fingerprint"})


def scene_blocking_contract() -> dict[str, Any]:
    """Contract derived from the fields read by the real ShotPlan builder."""
    fields = [
        {"field": "scene_id", "semantic_definition": "stable ScriptIR scene identity", "authority_class": SOURCE_SPATIAL_CONSTRAINT, "required": True, "shot_plan_blocking": True, "mutation": "immutable", "consumer": ["ShotPlan"]},
        {"field": "scene_name", "semantic_definition": "source-supported display identity", "authority_class": SOURCE_SPATIAL_CONSTRAINT, "required": True, "shot_plan_blocking": True, "mutation": "immutable_display_identity", "consumer": ["ShotPlan"]},
        {"field": "source_spatial_facts", "semantic_definition": "explicit spatial facts from ScriptIR/FactSnapshot", "authority_class": SOURCE_SPATIAL_CONSTRAINT, "required": False, "shot_plan_blocking": True, "mutation": "immutable", "consumer": ["ShotPlan"]},
        {"field": "participants", "semantic_definition": "staged participants and authored positions", "authority_class": BLOCKING_AUTHORING_DECISION, "required": True, "shot_plan_blocking": True, "mutation": "reviewed_edit_preserve_ids", "consumer": ["ShotPlan"]},
        {"field": "beat_transitions", "semantic_definition": "ordered treatment beat handoff into blocking", "authority_class": DIRECTOR_CONSTRAINT, "required": True, "shot_plan_blocking": True, "mutation": "preserve_beat_ids_order", "consumer": ["ShotPlan"]},
        {"field": "camera_axis", "semantic_definition": "axis planning constraint", "authority_class": BLOCKING_AUTHORING_DECISION, "required": False, "shot_plan_blocking": True, "mutation": "reviewed_edit", "consumer": ["ShotPlan"]},
        {"field": "spatial_model", "semantic_definition": "scene geometry projection", "authority_class": BLOCKING_AUTHORING_DECISION, "required": False, "shot_plan_blocking": True, "mutation": "source_locked_else_reviewed_edit", "consumer": ["ShotPlan"]},
        {"field": "creative_decisions", "semantic_definition": "blocking-level staging decisions", "authority_class": BLOCKING_AUTHORING_DECISION, "required": False, "shot_plan_blocking": True, "mutation": "reviewed_edit", "consumer": ["ShotPlan"]},
        {"field": "derived_constraints", "semantic_definition": "deterministically derived spatial/continuity constraints", "authority_class": DERIVED_SPATIAL_CONSTRAINT, "required": False, "shot_plan_blocking": True, "mutation": "rule_derived_with_provenance", "consumer": ["ShotPlan"]},
        {"field": "continuity_state", "semantic_definition": "scene entry character state initialization", "authority_class": DERIVED_SPATIAL_CONSTRAINT, "required": False, "shot_plan_blocking": True, "mutation": "inherit_or_author", "consumer": ["ShotPlan"]},
        {"field": "asset_authority", "semantic_definition": "scene asset authority classification", "authority_class": SOURCE_SPATIAL_CONSTRAINT, "required": False, "shot_plan_blocking": True, "mutation": "locked_reference_only", "consumer": ["ShotPlan"]},
        {"field": "unknowns", "semantic_definition": "unresolved information retained explicitly", "authority_class": UNKNOWN_UNRESOLVED, "required": False, "shot_plan_blocking": True, "mutation": "resolve_with_evidence_only", "consumer": ["ShotPlan"]},
    ]
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "fields": fields,
        "source_spatial_fields": ["scene_id", "scene_name", "source_spatial_facts"],
        "director_constraint_fields": ["beat_transitions", "character_intents", "visual_strategy"],
        "blocking_authoring_fields": ["participants", "spatial_model", "camera_axis", "creative_decisions"],
        "derived_constraint_fields": ["derived_constraints", "continuity_state"],
        "unknown_fields": ["unknowns", "unresolved_facts"],
        "shot_plan_blockers": [item["field"] for item in fields if item["shot_plan_blocking"]],
        "asset_priority": ["immutable_source", "approved_source_fact", "production_qualified_script_ir", "production_qualified_treatment", "approved_locked_production_asset", "draft_advisory_asset", "llm_proposal"],
        "consumer_basis": "core/shot_plan.py and api/shot_plan_api.py actual reads",
    }


def contract_fingerprint() -> str:
    return fingerprint(scene_blocking_contract())


def validation_fingerprint(validation: dict[str, Any]) -> str:
    return fingerprint(validation)


def blocking_payload_from_dict(blocking: dict[str, Any]) -> dict[str, Any]:
    """Canonical semantic payload; metadata and timestamps are excluded."""
    keys = (
        "scene_id", "scene_name", "space", "participants", "beat_transitions",
        "spatial_rules", "source_spatial_facts", "creative_decisions",
        "derived_constraints", "unresolved_facts", "unknowns", "camera_axis",
        "continuity_state", "asset_authority", "treatment_id",
        "treatment_revision", "treatment_fingerprint", "source_script_hash",
    )
    return {key: blocking.get(key) for key in keys if key in blocking}


def blocking_payload_from_row(row: Any) -> dict[str, Any]:
    return blocking_payload_from_dict({
        "scene_id": _text(getattr(row, "scene_id", "")),
        "scene_name": _text(getattr(row, "scene_name", "")),
        "space": _json(getattr(row, "spatial_model", "{}"), {}),
        "participants": _json(getattr(row, "participants", "[]"), []),
        "beat_transitions": _json(getattr(row, "beat_transitions", "[]"), []),
        "spatial_rules": _json(getattr(row, "spatial_rules", "[]"), []),
        "source_spatial_facts": _json(getattr(row, "source_spatial_facts", "[]"), []),
        "creative_decisions": _json(getattr(row, "creative_decisions", "[]"), []),
        "derived_constraints": _json(getattr(row, "derived_constraints", "{}"), {}),
        "unresolved_facts": _json(getattr(row, "unresolved_facts", "[]"), []),
        "unknowns": _json(getattr(row, "unknowns", "[]"), []),
        "camera_axis": _json(getattr(row, "camera_axis", "{}"), {}),
        "continuity_state": _json(getattr(row, "continuity_state", "{}"), {}),
        "asset_authority": _json(getattr(row, "asset_authority", "{}"), {}),
        "treatment_id": getattr(row, "treatment_id", None),
        "treatment_revision": getattr(row, "treatment_revision", None),
        "treatment_fingerprint": _text(getattr(row, "treatment_authority_fingerprint", "")),
        "source_script_hash": _text(getattr(row, "source_script_ir_hash", "") or getattr(row, "source_script_hash", "")),
    })


def blocking_payload_hash(blocking: dict[str, Any]) -> str:
    return fingerprint(blocking_payload_from_dict(blocking))


def _location_geometry(location: Any) -> dict[str, Any]:
    if not location:
        return {}
    canonical = _json(getattr(location, "canonical_facts", "{}"), {})
    board = _json(getattr(location, "board_spec", "{}"), {})
    state = _json(getattr(location, "state_variants", "{}"), {})
    merged: dict[str, Any] = {}
    for value in (canonical, board, state):
        if isinstance(value, dict):
            merged.update(value)
    return merged


def classify_scene_asset(location: Any | None, *, scene_id: str) -> dict[str, Any]:
    """Classify scene location rows without allowing name-only legacy data."""
    if location is None:
        return {"authority_class": "AUTHORING_PENDING", "status": "missing", "reason": "SCENE_ASSET_MISSING", "locked_constraints": [], "advisory_context": [], "authoring_pending": [{"code": "SCENE_ASSET_MISSING"}], "fingerprint": fingerprint({"scene_id": scene_id, "missing": True})}
    location_scene_id = _text(getattr(location, "scene_id", ""))
    # A blank scene_id is legacy/name-only data.  It can be shown as advisory
    # context, but it must never satisfy a production scene authority gate.
    # Treating an empty value as a match would silently promote an unrelated
    # locked location whenever two scenes share a display name.
    identity_match = bool(location_scene_id) and location_scene_id == _text(scene_id)
    geometry = _location_geometry(location)
    has_geometry = bool(geometry)
    locked = _text(getattr(location, "asset_status", "")).lower() == "locked"
    base = {
        "id": getattr(location, "id", None),
        "scene_id": location_scene_id,
        "name": _text(getattr(location, "name", "")),
        "category": _text(getattr(location, "category", "")),
        "revision": getattr(getattr(location, "updated_at", None), "isoformat", lambda: "")(),
        # Include every persisted visual authority input in the fingerprint,
        # not only geometry.  A locked reference/look/key-prop change must
        # invalidate downstream SceneBlocking as well.
        "canonical_facts": _json(getattr(location, "canonical_facts", "{}"), {}),
        "state_variants": _json(getattr(location, "state_variants", "{}"), {}),
        "look_profile": _json(getattr(location, "look_profile", "{}"), {}),
        "board_spec": _json(getattr(location, "board_spec", "{}"), {}),
        "key_props": _json(getattr(location, "key_props", "[]"), []),
        "image_url": _text(getattr(location, "image_url", "")),
        "local_path": _text(getattr(location, "local_path", "")),
        "geometry": geometry,
        "asset_status": getattr(location, "asset_status", ""),
    }
    fp = fingerprint(base)
    if not identity_match:
        return {"authority_class": "ADVISORY_SCENE_CONTEXT", "status": "identity_mismatch", "reason": "SCENE_ASSET_SCENE_ID_MISMATCH", "locked_constraints": [], "advisory_context": [{**base, "authority_class": "ADVISORY_SCENE_CONTEXT"}], "authoring_pending": [{"code": "SCENE_ASSET_SCENE_ID_MISMATCH"}], "fingerprint": fp}
    if locked and has_geometry:
        return {"authority_class": "LOCKED_PRODUCTION_CONSTRAINT", "status": "locked", "reason": "", "locked_constraints": [{**base, "authority_class": "LOCKED_PRODUCTION_CONSTRAINT"}], "advisory_context": [], "authoring_pending": [], "fingerprint": fp}
    if locked and not has_geometry:
        reason = "SCENE_ASSET_GEOMETRY_MISSING"
        return {"authority_class": "AUTHORING_PENDING", "status": "locked_incomplete", "reason": reason, "locked_constraints": [], "advisory_context": [], "authoring_pending": [{**base, "code": reason}], "fingerprint": fp}
    return {"authority_class": "ADVISORY_SCENE_CONTEXT", "status": "advisory", "reason": "SCENE_ASSET_NOT_LOCKED", "locked_constraints": [], "advisory_context": [{**base, "authority_class": "ADVISORY_SCENE_CONTEXT"}], "authoring_pending": [], "fingerprint": fp}


def initialize_continuity_state(*, scene: dict[str, Any], treatment: dict[str, Any], previous_blocking: dict[str, Any] | None = None) -> dict[str, Any]:
    """Initialize scene-entry character state with explicit provenance."""
    intents = treatment.get("character_intents") if isinstance(treatment.get("character_intents"), dict) else {}
    declared = scene.get("participants") if isinstance(scene.get("participants"), list) else []
    ids: list[str] = []
    for item in list(intents) + declared:
        value = item.get("character_id") or item.get("id") if isinstance(item, dict) else item
        value = _text(value)
        if value and value not in ids:
            ids.append(value)
    explicit = scene.get("character_states") or scene.get("current_state") or scene.get("state_in") or {}
    if not isinstance(explicit, dict):
        explicit = {}
    prior = previous_blocking.get("continuity_state") if isinstance(previous_blocking, dict) else {}
    prior = _json(prior, {})
    prior_states = prior.get("states") if isinstance(prior, dict) and isinstance(prior.get("states"), list) else []
    prior_by_id = {_text(item.get("character_id")): item for item in prior_states if isinstance(item, dict)}
    states: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    required = scene.get("required_continuity") or scene.get("continuity_requirements") or []
    required_ids = {_text(item.get("character_id") or item.get("id") or item) if isinstance(item, (dict, str)) else "" for item in (required if isinstance(required, list) else [])}
    for character_id in ids:
        value: Any = None
        authority = UNKNOWN_UNRESOLVED
        provenance: dict[str, Any] = {"scene_id": _text(scene.get("scene_id")), "character_id": character_id}
        raw = explicit.get(character_id)
        if raw is None:
            name = intents.get(character_id, {}).get("name") if isinstance(intents.get(character_id), dict) else ""
            raw = explicit.get(_text(name))
        if raw not in (None, "", []):
            value = raw.get("state") if isinstance(raw, dict) else raw
            authority = SOURCE_SPATIAL_CONSTRAINT
            provenance["source"] = "script.scene_state"
        elif character_id in prior_by_id and prior_by_id[character_id].get("state") not in (None, ""):
            value = prior_by_id[character_id].get("state")
            authority = DERIVED_SPATIAL_CONSTRAINT
            provenance["inherited_from_previous_scene"] = prior_by_id[character_id].get("scene_id") or "previous_authoritative_scene"
        elif character_id in required_ids or bool(scene.get("requires_character_state")):
            unresolved.append({"code": "CHARACTER_CONTINUITY_UNKNOWN", "character_id": character_id, "severity": "blocker", "message": f"character entry state is unresolved: {character_id}"})
        states.append({"character_id": character_id, "scene_id": _text(scene.get("scene_id")), "state": value, "authority_class": authority, "provenance": provenance, "unresolved": value in (None, "")})
    resolution = [{"code": "RESOLVED_BY_SOURCE", "count": sum(1 for item in states if item["authority_class"] == SOURCE_SPATIAL_CONSTRAINT)}, {"code": "RESOLVED_BY_DERIVATION", "count": sum(1 for item in states if item["authority_class"] == DERIVED_SPATIAL_CONSTRAINT)}, {"code": "STILL_UNKNOWN", "count": len(unresolved)}]
    result = {"states": states, "unresolved": unresolved, "resolution": resolution, "fingerprint": fingerprint({"states": states, "unresolved": unresolved})}
    return result


def validate_unknown_resolution(*, baseline_unknowns: list[Any], candidate_unknowns: list[Any], resolutions: list[Any] | None = None) -> None:
    """Require explicit authority for every closed unknown."""
    base = {_canonical(item) for item in baseline_unknowns}
    candidate = {_canonical(item) for item in candidate_unknowns}
    removed = base - candidate
    if not removed:
        return
    valid_codes = {"RESOLVED_BY_SOURCE", "RESOLVED_BY_AUTHORED_DECISION", "RESOLVED_BY_DERIVATION"}
    resolved = {
        _canonical(item.get("unknown") if isinstance(item, dict) else None)
        for item in (resolutions or [])
        if isinstance(item, dict) and _text(item.get("status")) in valid_codes
    }
    if not removed.issubset(resolved):
        raise ValueError("unknowns cannot be silently removed; each closure needs evidence/provenance")


def validate_scene_blocking_candidate_authority(raw: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Validate a reviewed candidate while preserving immutable boundaries."""
    if not isinstance(raw, dict):
        raise ValueError("SceneBlocking candidate must be an object")
    allowed = {"scene_id", "scene_name", "space", "spatial_model", "participants", "beat_transitions", "spatial_rules", "unknowns", "unknown_resolutions", "schema_version", "source_spatial_facts", "creative_decisions", "derived_constraints", "unresolved_facts", "camera_axis", "continuity_state", "asset_authority", "validation", "conflicts"}
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise ValueError(f"candidate contains non-whitelisted fields: {', '.join(unexpected)}")
    for key in ("scene_id", "scene_name"):
        if key in raw and _text(raw.get(key)) != _text(baseline.get(key)):
            raise ValueError(f"{key} is an immutable source identity")
    baseline_facts = baseline.get("source_spatial_facts") if isinstance(baseline.get("source_spatial_facts"), list) else []
    if raw.get("source_spatial_facts", baseline_facts) != baseline_facts:
        raise ValueError("source spatial constraints are immutable")
    if baseline.get("_locked_space"):
        candidate_space = raw.get("space", raw.get("spatial_model", baseline.get("space", {})))
        candidate_model = raw.get("spatial_model")
        baseline_space = baseline.get("space", baseline.get("spatial_model", {}))
        if candidate_space != baseline_space or (candidate_model is not None and candidate_model != baseline_space):
            raise ValueError("locked scene geometry is immutable")
    base_participants = baseline.get("participants") if isinstance(baseline.get("participants"), list) else []
    participants = raw.get("participants", base_participants)
    if not isinstance(participants, list) or any(not isinstance(item, dict) for item in participants):
        raise ValueError("participants must be a list of objects")
    base_ids = [_text(item.get("character_id")) for item in base_participants]
    ids = [_text(item.get("character_id")) for item in participants]
    if ids != base_ids:
        raise ValueError("participants must preserve declared character identity and order")
    for before, after in zip(base_participants, participants):
        if _text(before.get("name")) and _text(after.get("name")) != _text(before.get("name")):
            raise ValueError("participant names are immutable source identity")
        for field in ("entry", "exit"):
            if before.get(field) != after.get(field):
                raise ValueError(f"participant {field} state is a source constraint")
    base_beats = baseline.get("beat_transitions") if isinstance(baseline.get("beat_transitions"), list) else []
    beats = raw.get("beat_transitions", base_beats)
    if not isinstance(beats, list) or [_text(item.get("beat_id")) for item in beats if isinstance(item, dict)] != [_text(item.get("beat_id")) for item in base_beats if isinstance(item, dict)]:
        raise ValueError("beat_transitions must preserve beat ids and order")
    unknowns = raw.get("unknowns", baseline.get("unknowns", []))
    if not isinstance(unknowns, list):
        raise ValueError("unknowns must be a list")
    validate_unknown_resolution(baseline_unknowns=baseline.get("unknowns", []) if isinstance(baseline.get("unknowns"), list) else [], candidate_unknowns=unknowns, resolutions=raw.get("unknown_resolutions"))
    result = dict(baseline)
    for key in ("scene_id", "scene_name", "space", "spatial_model", "participants", "beat_transitions", "spatial_rules", "unknowns", "schema_version", "creative_decisions", "derived_constraints", "unresolved_facts", "camera_axis", "continuity_state", "asset_authority", "validation"):
        if key in raw:
            result[key] = raw[key]
    result["source_spatial_facts"] = baseline_facts
    result["participants"] = participants
    result["beat_transitions"] = beats
    result["unknowns"] = unknowns
    return result


def build_scene_blocking_authority_envelope(*, blocking: dict[str, Any], book_id: int, episode: int, scene_id: str, blocking_id: int, blocking_revision: int, script_ir_version: Any, script_ir_envelope: dict[str, Any], treatment: Any, treatment_envelope: dict[str, Any], fact_snapshot: Any | None, asset_authority: dict[str, Any], continuity_state: dict[str, Any], validation: dict[str, Any], qualification_state: str = "PRODUCTION_QUALIFIED", approved_at: str | None = None) -> dict[str, Any]:
    fact_meta = treatment_envelope.get("fact_snapshot") if isinstance(treatment_envelope.get("fact_snapshot"), dict) else {}
    if fact_snapshot is not None:
        fact_meta = {"id": getattr(fact_snapshot, "id", None), "revision": getattr(fact_snapshot, "revision", None), "payload_hash": _text(getattr(fact_snapshot, "payload_hash", ""))}
    payload = blocking_payload_from_dict(blocking)
    contract = scene_blocking_contract()
    envelope: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "book_id": int(book_id), "episode": int(episode), "scene_id": _text(scene_id),
        "scene_identity": {"scene_id": _text(scene_id), "scene_name": _text(blocking.get("scene_name"))},
        "blocking_id": int(blocking_id), "blocking_revision": int(blocking_revision),
        "payload_hash": fingerprint(payload), "workflow_profile": "production",
        "script_ir": {"id": getattr(script_ir_version, "id", None), "revision": getattr(script_ir_version, "revision", None), "payload_hash": _text(getattr(script_ir_version, "payload_hash", "")), "authority_envelope_fingerprint": _text(script_ir_envelope.get("envelope_fingerprint")), "authority_activation_revision": script_ir_envelope.get("authority_revision")},
        "treatment": {"id": getattr(treatment, "id", None), "revision": getattr(treatment, "revision", None), "payload_hash": _text(getattr(treatment, "payload_hash", "")), "authority_envelope_fingerprint": _text(treatment_envelope.get("envelope_fingerprint"))},
        "source_lineage": {"immutable_source_raw_hash": _text(script_ir_envelope.get("source_lineage", {}).get("immutable_source_raw_hash") or script_ir_envelope.get("immutable_source_raw_hash")), "source_package_id": _text(script_ir_envelope.get("source_package_id") or script_ir_envelope.get("source_lineage", {}).get("source_package_id")), "source_version_id": _text(script_ir_envelope.get("source_version_id") or script_ir_envelope.get("source_lineage", {}).get("source_version_id")), "source_evidence_index_fingerprint": _text(script_ir_envelope.get("source_evidence_index_fingerprint") or script_ir_envelope.get("source_lineage", {}).get("source_evidence_index_fingerprint"))},
        "fact_snapshot": fact_meta,
        "authority_classes": {"source_spatial_constraints": blocking.get("source_spatial_facts", []), "director_constraints": {"treatment_id": getattr(treatment, "id", None), "beat_transitions": blocking.get("beat_transitions", [])}, "blocking_authoring_decisions": {"participants": blocking.get("participants", []), "camera_axis": blocking.get("camera_axis", {}), "creative_decisions": blocking.get("creative_decisions", []), "spatial_model": blocking.get("space", blocking.get("spatial_model", {}))}, "derived_spatial_constraints": blocking.get("derived_constraints", {}), "unknown_unresolved": blocking.get("unknowns", [])},
        "asset_authority": asset_authority,
        "continuity_state": continuity_state,
        "contract": {"schema_version": CONTRACT_SCHEMA_VERSION, "fingerprint": contract_fingerprint(), "requirement_set_fingerprint": fingerprint({"blocking_fields": contract["shot_plan_blockers"]})},
        "validation": {"report": validation, "fingerprint": validation_fingerprint(validation)},
        "qualification_state": qualification_state, "stale_status": "FRESH", "stale_reasons": [],
        "approved_at": approved_at or datetime.now(timezone.utc).isoformat(), "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    envelope["envelope_fingerprint"] = _envelope_fingerprint(envelope)
    return envelope


def _raise(code: str, message: str, **extra: Any) -> None:
    raise HTTPException(status_code=409, detail={"code": code, "message": message, **extra})


def mark_scene_blocking_stale(session: Any, blocking: Any, reasons: list[str]) -> None:
    from models import SceneBlockingAuthority, SceneBlockingPointer
    normalized = sorted({_text(reason) for reason in reasons if _text(reason)})
    blocking.status = "stale"
    blocking.production_status = "blocked"
    blocking.qualification_state = "STALE"
    blocking.stale_status = "STALE"
    blocking.stale_reasons = json.dumps(normalized, ensure_ascii=False)
    blocking.updated_at = datetime.now()
    authority = session.query(SceneBlockingAuthority).filter_by(blocking_id=blocking.id).first()
    if authority:
        authority.qualification_state = "STALE"; authority.stale_status = "STALE"; authority.stale_reasons = json.dumps(normalized, ensure_ascii=False); authority.updated_at = datetime.now()
    session.query(SceneBlockingPointer).filter_by(blocking_id=blocking.id).delete(synchronize_session=False)


def _validate_envelope_shape(envelope: dict[str, Any], *, row: Any, authority: Any | None = None, pointer: Any | None = None, book_id: int | None = None, episode: int | None = None) -> list[str]:
    errors: list[str] = []
    if _text(envelope.get("schema_version")) != SCHEMA_VERSION:
        errors.append("SCENE_BLOCKING_AUTHORITY_SCHEMA_CHANGED")
    if _text(envelope.get("authority_policy_version")) != AUTHORITY_POLICY_VERSION:
        errors.append("SCENE_BLOCKING_AUTHORITY_POLICY_CHANGED")
    if book_id is not None and str(envelope.get("book_id")) != str(book_id):
        errors.append("SCENE_BLOCKING_BOOK_MISMATCH")
    if episode is not None and str(envelope.get("episode")) != str(episode):
        errors.append("SCENE_BLOCKING_EPISODE_MISMATCH")
    if _text(envelope.get("envelope_fingerprint")) != _envelope_fingerprint(envelope):
        errors.append("SCENE_BLOCKING_AUTHORITY_TAMPERED")
    if str(envelope.get("blocking_id")) != str(getattr(row, "id", "")) or str(envelope.get("blocking_revision")) != str(getattr(row, "revision", "")):
        errors.append("SCENE_BLOCKING_AUTHORITY_LINEAGE_CHANGED")
    if _text(envelope.get("scene_id")) != _text(getattr(row, "scene_id", "")):
        errors.append("SCENE_ID_MISMATCH")
    expected_hash = fingerprint(blocking_payload_from_row(row))
    if _text(envelope.get("payload_hash")) != expected_hash or _text(getattr(row, "payload_hash", "")) != expected_hash:
        errors.append("SCENE_BLOCKING_PAYLOAD_TAMPERED")
    if authority is not None:
        if str(getattr(authority, "payload_hash", "")) != expected_hash:
            errors.append("SCENE_BLOCKING_AUTHORITY_PAYLOAD_MISMATCH")
        if str(getattr(authority, "blocking_revision", "")) != str(getattr(row, "revision", "")):
            errors.append("SCENE_BLOCKING_AUTHORITY_LINEAGE_CHANGED")
        if _text(getattr(authority, "envelope_fingerprint", "")) != _text(envelope.get("envelope_fingerprint")):
            errors.append("SCENE_BLOCKING_AUTHORITY_TAMPERED")
    if pointer is not None:
        if str(getattr(pointer, "blocking_revision", "")) != str(getattr(row, "revision", "")):
            errors.append("SCENE_BLOCKING_POINTER_LINEAGE_CHANGED")
        if _text(getattr(pointer, "authority_envelope_fingerprint", "")) != _text(envelope.get("envelope_fingerprint")):
            errors.append("SCENE_BLOCKING_POINTER_TAMPERED")
        if _text(getattr(pointer, "qualification_state", "")) != "PRODUCTION_QUALIFIED":
            errors.append("SCENE_BLOCKING_POINTER_NOT_QUALIFIED")
    contract_meta = envelope.get("contract") if isinstance(envelope.get("contract"), dict) else {}
    if _text(contract_meta.get("fingerprint")) != contract_fingerprint():
        errors.append("SCENE_BLOCKING_CONTRACT_CHANGED")
    return errors


def resolve_current_authoritative_scene_blocking(session: Any, *, book_id: int, episode: int, scene_id: str) -> tuple[Any, dict[str, Any]]:
    """Resolve only the explicit current pointer and validate full lineage."""
    from models import FactSnapshot, SceneBlocking, SceneBlockingAuthority, SceneBlockingPointer, Script, ScriptIRVersion, VisualLocation
    from core.director_treatment_authority import resolve_current_authoritative_treatment

    scene_id = _text(scene_id)
    if not scene_id:
        _raise("SCENE_ID_REQUIRED", "Production ShotPlan requires a stable scene_id.")
    pointer = session.query(SceneBlockingPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
    if not pointer:
        _raise("SCENE_BLOCKING_POINTER_MISSING", "No current authoritative SceneBlocking pointer for scene.")
    row = session.query(SceneBlocking).filter_by(id=pointer.blocking_id, book_id=book_id, episode=episode, scene_id=scene_id).first()
    authority = session.query(SceneBlockingAuthority).filter_by(blocking_id=pointer.blocking_id, envelope_fingerprint=pointer.authority_envelope_fingerprint).first()
    if not row or not authority or row.status != "approved" or row.qualification_state != "PRODUCTION_QUALIFIED" or authority.qualification_state != "PRODUCTION_QUALIFIED" or _text(getattr(pointer, "qualification_state", "")) != "PRODUCTION_QUALIFIED" or row.stale_status == "STALE" or authority.stale_status == "STALE":
        _raise("SCENE_BLOCKING_NOT_PRODUCTION_QUALIFIED", "Current SceneBlocking is not production-qualified.")
    envelope = _json(authority.envelope_json, {})
    errors = _validate_envelope_shape(envelope, row=row, authority=authority, pointer=pointer, book_id=book_id, episode=episode)
    if errors:
        mark_scene_blocking_stale(session, row, errors); session.commit(); _raise(errors[0], "SceneBlocking authority envelope or payload is invalid.", stale_reasons=errors)
    try:
        treatment, treatment_envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        reason = _text(detail.get("code") or "DIRECTOR_TREATMENT_CHANGED")
        mark_scene_blocking_stale(session, row, [reason]); session.commit()
        raise
    treatment_meta = envelope.get("treatment") if isinstance(envelope.get("treatment"), dict) else {}
    if str(treatment_meta.get("id")) != str(treatment.id) or str(treatment_meta.get("revision")) != str(treatment.revision) or _text(treatment_meta.get("payload_hash")) != _text(getattr(treatment, "payload_hash", "")) or _text(treatment_meta.get("authority_envelope_fingerprint")) != _text(treatment_envelope.get("envelope_fingerprint")):
        mark_scene_blocking_stale(session, row, ["DIRECTOR_TREATMENT_CHANGED"]); session.commit(); _raise("DIRECTOR_TREATMENT_CHANGED", "SceneBlocking treatment lineage is stale.")
    script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
    ir = session.query(ScriptIRVersion).filter_by(id=getattr(script_row, "current_script_ir_version_id", None), book_id=book_id, episode=episode).first() if script_row else None
    ir_meta = envelope.get("script_ir") if isinstance(envelope.get("script_ir"), dict) else {}
    if not ir or str(ir_meta.get("id")) != str(ir.id) or str(ir_meta.get("revision")) != str(ir.revision) or _text(ir_meta.get("payload_hash")) != _text(ir.payload_hash):
        mark_scene_blocking_stale(session, row, ["SCRIPT_IR_CHANGED"]); session.commit(); _raise("SCRIPT_IR_CHANGED", "SceneBlocking ScriptIR lineage is stale.")
    fact_meta = envelope.get("fact_snapshot") if isinstance(envelope.get("fact_snapshot"), dict) else {}
    fact_id = fact_meta.get("id")
    if fact_id in (None, ""):
        mark_scene_blocking_stale(session, row, ["FACT_SNAPSHOT_LINEAGE_MISSING"]); session.commit(); _raise("FACT_SNAPSHOT_LINEAGE_MISSING", "SceneBlocking has no exact FactSnapshot binding.")
    fact = session.query(FactSnapshot).filter_by(id=int(fact_id), book_id=book_id, episode=episode).first() if str(fact_id).isdigit() else None
    if not fact or str(fact.revision) != str(fact_meta.get("revision")) or _text(fact.payload_hash) != _text(fact_meta.get("payload_hash")) or _text(fact.status).lower() != "confirmed":
        mark_scene_blocking_stale(session, row, ["FACT_SNAPSHOT_CHANGED"]); session.commit(); _raise("FACT_SNAPSHOT_CHANGED", "Bound FactSnapshot is missing or changed.")
    location = session.query(VisualLocation).filter(VisualLocation.book_id == book_id, VisualLocation.scene_id == scene_id).order_by(VisualLocation.id.desc()).first()
    if location is None:
        # A legacy location with no scene_id is advisory only; never promote it.
        asset_meta = envelope.get("asset_authority") if isinstance(envelope.get("asset_authority"), dict) else {}
        if asset_meta.get("locked_constraints"):
            mark_scene_blocking_stale(session, row, ["SCENE_ASSET_SCENE_ID_MISMATCH"]); session.commit(); _raise("SCENE_ASSET_SCENE_ID_MISMATCH", "Current scene asset is not bound by scene_id.")
    else:
        asset_state = classify_scene_asset(location, scene_id=scene_id)
        expected_asset_fp = _text((envelope.get("asset_authority") or {}).get("scene_asset_fingerprint")) if isinstance(envelope.get("asset_authority"), dict) else ""
        if expected_asset_fp and expected_asset_fp != _text(asset_state.get("fingerprint")):
            mark_scene_blocking_stale(session, row, ["SCENE_ASSET_CHANGED"]); session.commit(); _raise("SCENE_ASSET_CHANGED", "Bound scene asset authority is stale.")
    return row, envelope


__all__ = [
    "SCHEMA_VERSION", "CONTRACT_SCHEMA_VERSION", "AUTHORITY_POLICY_VERSION", "QUALIFICATION_STATES",
    "SOURCE_SPATIAL_CONSTRAINT", "DIRECTOR_CONSTRAINT", "BLOCKING_AUTHORING_DECISION", "DERIVED_SPATIAL_CONSTRAINT", "UNKNOWN_UNRESOLVED",
    "scene_blocking_contract", "contract_fingerprint", "fingerprint", "blocking_payload_from_dict", "blocking_payload_from_row", "blocking_payload_hash", "validation_fingerprint", "classify_scene_asset", "initialize_continuity_state", "validate_unknown_resolution", "validate_scene_blocking_candidate_authority", "build_scene_blocking_authority_envelope", "mark_scene_blocking_stale", "resolve_current_authoritative_scene_blocking",
]
