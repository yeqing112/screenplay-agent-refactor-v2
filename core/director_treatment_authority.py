"""Authority contract and resolver for production DirectorTreatment.

The Treatment layer is deliberately split into source constraints, director
decisions and unresolved information.  This module is provider-free: it only
derives evidence, validates immutable lineage and atomically binds an approved
Treatment to an explicit scene pointer.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

SCHEMA_VERSION = "director_treatment_authority_envelope_v1"
CONTRACT_SCHEMA_VERSION = "director_treatment_authority_contract_v1"
AUTHORITY_POLICY_VERSION = "director_treatment_authority_policy_v1"
QUALIFICATION_STATES = ("DRAFT", "CANDIDATE", "REVIEW_REQUIRED", "APPROVED", "AUTHORITY_BOUND", "PRODUCTION_QUALIFIED", "STALE")
STALE_STATUSES = ("UNKNOWN", "FRESH", "STALE")

SOURCE_CONSTRAINT_FIELDS = ("scene_id", "scene_name", "declared_participants", "source_beats", "explicit_story_constraints")
DIRECTOR_DECISION_FIELDS = (
    "dramatic_objective", "audience_question", "character_intents",
    "relationship_power_shift", "audience_emotion", "information_strategy",
    "performance_direction", "visual_strategy", "coverage_strategy",
    "sound_strategy", "edit_rhythm",
    # Phase B semantic projections live in the same director_decisions JSON
    # column.  They are additive to the existing authority spine; no second
    # Treatment production truth is introduced.
    "scene_objective", "dramatic_question", "audience_state_in", "audience_state_out",
    "suspicion_or_information_strategy", "character_directions", "beat_directions",
    "director_beat_decisions", "director_contract_version", "performance_arc", "rhythm_strategy", "visual_priority", "scene_exit_intent",
    "prohibited_interpretations",
)
DOWNSTREAM_AUTHORING_FIELDS = ("character_blocking", "scene_geometry", "production_prop_continuity", "shot_coverage", "camera_placement")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _envelope_fingerprint(value: dict[str, Any]) -> str:
    return fingerprint({key: item for key, item in value.items() if key != "envelope_fingerprint"})


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _text(value: Any) -> str:
    return str(value or "").strip()


def treatment_contract() -> dict[str, Any]:
    """Single source of truth, derived from actual SceneBlocking consumers."""
    fields: list[dict[str, Any]] = []
    source_defs = {
        "scene_id": ("Stable ScriptIR scene identity", "required", True),
        "scene_name": ("Source-supported display name", "required", True),
        "declared_participants": ("Participants declared by ScriptIR scene", "required", True),
        "source_beats": ("Ordered source beats with stable beat_id", "required", True),
        "explicit_story_constraints": ("Explicit source constraints only", "optional", False),
    }
    for field, (definition, required, blocking) in source_defs.items():
        fields.append({"field": field, "semantic_definition": definition, "authority_class": "SOURCE_CONSTRAINT", "origin": "source", "value_schema": "object_or_array", "required": required == "required", "blocking_downstream_stage": "SCENE_BLOCKING" if blocking else None, "allowed_mutation": "immutable", "evidence_requirement": "ScriptIR authority envelope", "provenance_requirement": "scene_id + source lineage", "consumer": ["SceneBlocking", "ShotPlan"], "stale_dependency": ["script_ir", "source", "fact_snapshot"]})
    for field in DIRECTOR_DECISION_FIELDS:
        fields.append({"field": field, "semantic_definition": "Director authoring decision; not a source fact", "authority_class": "DIRECTOR_DECISION", "origin": "authoring_or_proposal", "value_schema": "string_or_structured", "required": field in {"dramatic_objective", "audience_question", "character_intents", "visual_strategy"}, "blocking_downstream_stage": "SCENE_BLOCKING" if field in {"character_intents", "visual_strategy"} else None, "allowed_mutation": "reviewed_edit", "evidence_requirement": "DecisionPacket evidence", "provenance_requirement": "candidate + reviewer", "consumer": ["SceneBlocking", "ShotPlan"], "stale_dependency": ["script_ir", "contract", "authority_policy"]})
    for field in ("unknowns", "asset_context"):
        fields.append({"field": field, "semantic_definition": "Unresolved or advisory information retained explicitly", "authority_class": "UNKNOWN_UNRESOLVED", "origin": "derived_or_review", "value_schema": "array_or_object", "required": False, "blocking_downstream_stage": "SCENE_BLOCKING" if field == "unknowns" else None, "allowed_mutation": "append_or_resolve_with_evidence", "evidence_requirement": "DecisionPacket or asset authority", "provenance_requirement": "reason + evidence", "consumer": ["SceneBlocking"], "stale_dependency": ["source", "assets"]})
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "source_constraint_fields": list(SOURCE_CONSTRAINT_FIELDS),
        "director_decision_fields": list(DIRECTOR_DECISION_FIELDS),
        "downstream_authoring_fields": list(DOWNSTREAM_AUTHORING_FIELDS),
        "fields": fields,
        "asset_priority": ["immutable_source", "approved_source_fact", "production_qualified_script_ir", "approved_locked_production_decision", "draft_advisory_asset", "llm_proposal"],
        "consumer_basis": "SceneBlocking and ShotPlan actual reads in api/scene_blocking_api.py and api/shot_plan_api.py",
    }


def contract_fingerprint() -> str:
    return fingerprint(treatment_contract())


def treatment_payload_from_row(row: Any) -> dict[str, Any]:
    """Canonical formal payload; metadata never participates in payload hash."""
    payload = {
        "scene_id": _text(getattr(row, "scene_id", "")),
        "scene_name": _text(getattr(row, "scene_name", "")),
        "dramatic_objective": _text(getattr(row, "dramatic_objective", "")),
        "audience_question": _text(getattr(row, "audience_question", "")),
        "character_intents": _json(getattr(row, "character_intents", "{}"), {}),
        "beat_map": _json(getattr(row, "beat_map", "[]"), []),
        "relationship_power_shift": _text(getattr(row, "relationship_power_shift", "")),
        "audience_emotion": _text(getattr(row, "audience_emotion", "")),
        "information_strategy": _text(getattr(row, "information_strategy", "")),
        "performance_direction": _text(getattr(row, "performance_direction", "")),
        "visual_strategy": _text(getattr(row, "visual_strategy", "")),
        "coverage_strategy": _text(getattr(row, "coverage_strategy", "")),
        "sound_strategy": _text(getattr(row, "sound_strategy", "")),
        "edit_rhythm": _text(getattr(row, "edit_rhythm", "")),
        "constraints": _json(getattr(row, "constraints", "[]"), []),
        "unknowns": _json(getattr(row, "unknowns", "[]"), []),
    }
    # Phase B fields are persisted in the existing director_decisions JSON
    # projection so deployments do not need a parallel table or pointer.  Do
    # not add empty keys for legacy rows: their payload hashes remain stable.
    decisions = _json(getattr(row, "director_decisions", "{}"), {})
    if isinstance(decisions, dict):
        for field in DIRECTOR_DECISION_FIELDS:
            if field in decisions and decisions[field] not in (None, "", [], {}):
                payload[field] = decisions[field]
    return payload


def payload_hash(payload: dict[str, Any]) -> str:
    return fingerprint(payload)


def classify_asset_authority(evidence: dict[str, Any]) -> dict[str, Any]:
    """Classify assets without allowing advisory rows to become constraints."""
    locked: list[dict[str, Any]] = []
    advisory: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for item in evidence.get("locked_references", []) if isinstance(evidence, dict) else []:
        if not isinstance(item, dict):
            continue
        has_reference = bool(_text(item.get("image_url")) or _text(item.get("local_path")) or _text(item.get("reference_token")))
        target = locked if str(item.get("status") or "").lower() == "locked" and has_reference else pending
        target.append({**item, "authority_class": "LOCKED_PRODUCTION_CONSTRAINT" if target is locked else "AUTHORING_PENDING"})
    for item in evidence.get("characters", []) if isinstance(evidence, dict) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("asset_status") or "").lower() == "locked":
            locked.append({"id": item.get("id"), "name": item.get("name"), "asset_type": "character", "authority_class": "LOCKED_PRODUCTION_CONSTRAINT", "fingerprint": fingerprint(item)})
        else:
            advisory.append({"id": item.get("id"), "name": item.get("name"), "asset_type": "character", "authority_class": "ADVISORY_ASSET_CONTEXT", "fingerprint": fingerprint(item)})
    return {"locked_constraints": locked, "advisory_context": advisory, "authoring_pending": pending, "locked_constraint_fingerprint": fingerprint(locked)}


def build_treatment_authority_envelope(*, treatment: dict[str, Any], evidence: dict[str, Any], script_ir: dict[str, Any], script_ir_version: Any, script_ir_envelope: dict[str, Any], treatment_id: int, treatment_revision: int, qualification_state: str = "PRODUCTION_QUALIFIED", approved_at: str | None = None, provenance: dict[str, Any] | None = None, confirmation: dict[str, Any] | None = None, canonical_origin: str = "") -> dict[str, Any]:
    scene_id = _text(treatment.get("scene_id") or evidence.get("scene_id"))
    contract = treatment_contract()
    assets = classify_asset_authority(evidence)
    provenance = provenance if isinstance(provenance, dict) else {}
    confirmation = confirmation if isinstance(confirmation, dict) else {}
    canonical_origin = _text(canonical_origin)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "authority_policy_version": AUTHORITY_POLICY_VERSION,
        "book_id": int(evidence["book_id"]),
        "episode": int(evidence["episode"]),
        "scene_id": scene_id,
        "scene_identity": {"scene_id": scene_id, "scene_name": _text(evidence.get("scene_name")), "location_id": _text((evidence.get("scene") or {}).get("location_id")) if isinstance(evidence.get("scene"), dict) else ""},
        "treatment_id": int(treatment_id),
        "treatment_revision": int(treatment_revision),
        "treatment_payload_hash": payload_hash(treatment),
        "workflow_profile": "production",
        "script_ir": {"id": int(script_ir_version.id), "revision": int(script_ir_version.revision), "payload_hash": _text(script_ir_version.payload_hash) or fingerprint(script_ir), "authority_envelope_fingerprint": _text(script_ir_envelope.get("envelope_fingerprint")), "authority_activation_revision": script_ir_envelope.get("authority_revision")},
        "source_lineage": {"source_package_id": _text(script_ir_envelope.get("source_package_id")), "source_version_id": _text(script_ir_envelope.get("source_version_id")), "immutable_source_raw_hash": _text(script_ir_envelope.get("immutable_source_raw_hash")), "source_evidence_index_fingerprint": _text(script_ir_envelope.get("source_evidence_index_fingerprint"))},
        "fact_snapshot": {"id": script_ir_envelope.get("fact_snapshot_id"), "revision": script_ir_envelope.get("fact_snapshot_revision"), "payload_hash": _text(script_ir_envelope.get("fact_snapshot_payload_hash"))},
        "contract": {"schema_version": CONTRACT_SCHEMA_VERSION, "fingerprint": contract_fingerprint(), "requirement_set_fingerprint": fingerprint({"scene_id": scene_id, "required": [item["field"] for item in contract["fields"] if item.get("required")]})},
        "semantic_contract": {"version": _text(treatment.get("director_contract_version")), "decision_count": len(treatment.get("director_beat_decisions") or []) if isinstance(treatment.get("director_beat_decisions"), list) else 0},
        "provenance": {
            "proposal_provenance": provenance,
            "confirmation_event": confirmation,
            "canonical_origin": canonical_origin,
            "provider": provenance.get("provider", {}) if isinstance(provenance, dict) else {},
        },
        "proposal_provenance": provenance,
        "confirmation_event": confirmation,
        "canonical_origin_summary": canonical_origin,
        "provider_provenance": provenance.get("provider", {}) if isinstance(provenance, dict) else {},
        "asset_authority": assets,
        "qualification_state": qualification_state,
        "stale_status": "FRESH",
        "stale_reasons": [],
        "approved_at": approved_at or datetime.now(timezone.utc).isoformat(),
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    envelope["envelope_fingerprint"] = _envelope_fingerprint(envelope)
    return envelope


def validate_treatment_candidate(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Reject authority mutations while allowing director decisions to change."""
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    allowed = set(DIRECTOR_DECISION_FIELDS) | {"scene_id", "scene_name", "beat_map", "constraints", "unknowns", "decision", "confidence", "human_confirmation_required", "note", "proposal_origin", "proposal_provenance"}
    unexpected = sorted(set(candidate) - allowed)
    if unexpected:
        raise ValueError(f"non-whitelisted fields: {', '.join(unexpected)}")
    if "scene_id" in candidate and _text(candidate.get("scene_id")) != _text(baseline.get("scene_id")):
        raise ValueError("scene_id is an immutable source constraint")
    if "scene_name" in candidate and _text(candidate.get("scene_name")) != _text(baseline.get("scene_name")):
        raise ValueError("scene_name is an immutable source-supported identity")
    baseline_beats = baseline.get("beat_map") if isinstance(baseline.get("beat_map"), list) else []
    if "beat_map" in candidate and candidate["beat_map"] != baseline_beats:
        raise ValueError("beat_map is an immutable SOURCE_CONSTRAINT")
    result = {field: candidate.get(field, baseline.get(field)) for field in DIRECTOR_DECISION_FIELDS}
    base_intents = baseline.get("character_intents") if isinstance(baseline.get("character_intents"), dict) else {}
    raw_intents = result.get("character_intents")
    if not isinstance(raw_intents, dict) or set(raw_intents) != set(base_intents):
        raise ValueError("character_intents must preserve all declared participant ids")
    merged: dict[str, Any] = {}
    for key, base in base_intents.items():
        proposed = raw_intents.get(key)
        if not isinstance(proposed, dict):
            raise ValueError("character intent values must be objects")
        merged[key] = {**(base if isinstance(base, dict) else {}), **proposed}
        if isinstance(base, dict) and base.get("name"):
            merged[key]["name"] = base["name"]
    result["character_intents"] = merged
    base_unknowns = baseline.get("unknowns") if isinstance(baseline.get("unknowns"), list) else []
    proposed_unknowns = candidate.get("unknowns", base_unknowns)
    if not isinstance(proposed_unknowns, list):
        raise ValueError("unknowns must be a list")
    if not set(map(str, base_unknowns)).issubset(set(map(str, proposed_unknowns))):
        raise ValueError("unknowns cannot be silently removed")
    result["constraints"] = candidate.get("constraints", baseline.get("constraints", []))
    result["unknowns"] = proposed_unknowns
    result.update({"scene_id": baseline.get("scene_id", ""), "scene_name": baseline.get("scene_name", ""), "beat_map": baseline_beats, "decision": _text(candidate.get("decision") or "ready_for_review"), "confidence": candidate.get("confidence", 0.0), "human_confirmation_required": True, "note": _text(candidate.get("note") or "candidate only")})
    return result


def validate_phase_b_provenance_readiness(*, envelope: dict[str, Any], model_info: dict[str, Any]) -> dict[str, Any]:
    """Validate the structured provenance contract used by Phase B readiness.

    Missing provenance is a legacy compatibility state: the authority remains
    readable, but it cannot feed a Phase B production consumer.  Once a
    provenance field is present, contradictory or malformed values are
    authority tamper and must be handled by the resolver as fail-closed.
    """
    from core.director_provenance import project_legacy_flags, proposal_provenance, resolve_canonical_origin

    envelope = envelope if isinstance(envelope, dict) else {}
    model_info = model_info if isinstance(model_info, dict) else {}
    raw_provenance = envelope.get("proposal_provenance")
    raw_event = envelope.get("confirmation_event")
    raw_canonical = envelope.get("canonical_origin_summary")
    raw_provider = envelope.get("provider_provenance")
    nested = envelope.get("provenance") if isinstance(envelope.get("provenance"), dict) else {}
    missing = []
    if not isinstance(raw_provenance, dict) or not raw_provenance:
        missing.append("proposal_provenance")
    if not isinstance(raw_event, dict) or not raw_event:
        missing.append("confirmation_event")
    if not _text(raw_canonical):
        missing.append("canonical_origin_summary")
    if not isinstance(raw_provider, dict) or not raw_provider:
        missing.append("provider_provenance")
    if missing:
        return {"ready": False, "invalid": False, "reasons": ["DIRECTOR_PROVENANCE_CONTRACT_MISSING"], "missing": missing}

    try:
        provenance = proposal_provenance(
            raw_provenance.get("proposal_origin", ""),
            provider=raw_provenance.get("provider"),
            human_input=(raw_provenance.get("authoring") or {}).get("human_input", False),
        )
    except (TypeError, ValueError) as exc:
        return {"ready": False, "invalid": True, "reasons": ["DIRECTOR_PROVENANCE_TAMPERED"], "detail": str(exc)}

    if provenance != raw_provenance or raw_provider != provenance["provider"]:
        return {"ready": False, "invalid": True, "reasons": ["DIRECTOR_PROVENANCE_TAMPERED"], "detail": "proposal/provider provenance projection mismatch"}
    if nested and (
        nested.get("proposal_provenance") != provenance
        or nested.get("confirmation_event") != raw_event
        or _text(nested.get("canonical_origin")) != _text(raw_canonical)
        or nested.get("provider") != provenance["provider"]
    ):
        return {"ready": False, "invalid": True, "reasons": ["DIRECTOR_PROVENANCE_TAMPERED"], "detail": "nested provenance projection mismatch"}

    try:
        expected_canonical = resolve_canonical_origin(provenance, raw_event)
    except (TypeError, ValueError) as exc:
        return {"ready": False, "invalid": True, "reasons": ["DIRECTOR_PROVENANCE_TAMPERED"], "detail": str(exc)}
    if (
        raw_event.get("source_proposal_origin") != provenance["proposal_origin"]
        or raw_event.get("confirmation_type") != "HUMAN_CONFIRMATION"
        or not _text(raw_event.get("confirmed_at"))
        or raw_event.get("canonical_origin") != expected_canonical
        or _text(raw_canonical) != expected_canonical
    ):
        return {"ready": False, "invalid": True, "reasons": ["DIRECTOR_PROVENANCE_TAMPERED"], "detail": "confirmation or canonical origin mismatch"}

    if (
        model_info.get("proposal_provenance") != provenance
        or model_info.get("confirmation_event") != raw_event
        or _text(model_info.get("canonical_origin")) != expected_canonical
        or any(model_info.get(key) != value for key, value in project_legacy_flags(provenance).items())
    ):
        return {"ready": False, "invalid": True, "reasons": ["DIRECTOR_PROVENANCE_TAMPERED"], "detail": "model_info provenance projection mismatch"}
    return {"ready": True, "invalid": False, "reasons": [], "missing": [], "proposal_origin": provenance["proposal_origin"], "canonical_origin": expected_canonical, "provider": provenance["provider"]}


def _current_script_ir(session: Any, script_row: Any) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    from models import ScriptIRVersion
    current_id = getattr(script_row, "current_script_ir_version_id", None)
    version = session.query(ScriptIRVersion).filter_by(id=current_id, book_id=script_row.book_id, episode=script_row.episode).first() if current_id else None
    if not version or version.status != "production_qualified" or getattr(version, "qualification_state", "") != "PRODUCTION_QUALIFIED":
        raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_NOT_PRODUCTION_QUALIFIED", "message": "Production Treatment requires the current production-qualified ScriptIR."})
    # Reuse the canonical production resolver instead of validating only the
    # envelope self-hash here.  This also rechecks immutable source bytes,
    # evidence-index anchors, FactSnapshot coverage and requirement
    # fingerprints, so Treatment cannot bind to a stale ScriptIR merely
    # because its local envelope hash is still intact.
    from core.script_ir import resolve_script_payload
    payload = resolve_script_payload(session, script_row, workflow_profile="production")
    envelope = _json(getattr(version, "authority_envelope_json", "{}"), {})
    if not isinstance(payload, dict) or not isinstance(envelope, dict) or not envelope.get("envelope_fingerprint"):
        raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_ENVELOPE_INVALID", "message": "Current ScriptIR authority envelope is missing."})
    from core.script_ir_authority import validate_authority_envelope
    report = validate_authority_envelope(envelope, payload=payload)
    if report.get("status") != "PASS":
        raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_STALE", "message": "Current ScriptIR authority is stale.", "errors": report.get("errors", [])})
    return version, payload, envelope


def resolve_scene_for_treatment(session: Any, script_row: Any, *, scene_id: str = "", scene_name: str = "", workflow_profile: str = "creative_draft") -> tuple[dict[str, Any], Any | None, dict[str, Any] | None, dict[str, Any] | None]:
    profile = _text(workflow_profile).lower() or "creative_draft"
    version = None; payload = None; envelope = None
    wanted_id = _text(scene_id)
    wanted_name = _text(scene_name)
    if profile == "production" and not wanted_id:
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production Treatment requires a stable scene_id."})
    if profile == "production":
        version, payload, envelope = _current_script_ir(session, script_row)
    else:
        payload = _json(script_row.content, {})
    scenes = payload.get("scenes") if isinstance(payload, dict) and isinstance(payload.get("scenes"), list) else []
    scene = next((item for item in scenes if isinstance(item, dict) and wanted_id and _text(item.get("scene_id")) == wanted_id), None)
    if scene is None and wanted_name:
        scene = next((item for item in scenes if isinstance(item, dict) and _text(item.get("name")) == wanted_name), None)
    if scene is None and scenes and not wanted_id and not wanted_name:
        scene = scenes[0] if isinstance(scenes[0], dict) else None
    if not scene:
        raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": "Scene not found."})
    if profile == "production" and not _text(scene.get("scene_id")):
        raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production Treatment requires a stable scene_id."})
    return scene, version, payload, envelope


def resolve_current_authoritative_treatment(session: Any, *, book_id: int, episode: int, scene_id: str) -> tuple[Any, dict[str, Any]]:
    """Resolve only the explicit pointer; never latest-approved fallback."""
    from models import DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, Script, ScriptIRVersion, FactSnapshot, VisualMakeup, VisualReferenceAsset
    pointer = session.query(DirectorTreatmentPointer).filter_by(book_id=book_id, episode=episode, scene_id=_text(scene_id)).first()
    if not pointer:
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_POINTER_MISSING", "message": "No current authoritative DirectorTreatment pointer for scene."})
    treatment = session.query(DirectorTreatment).filter_by(id=pointer.treatment_id, book_id=book_id, episode=episode, scene_id=_text(scene_id)).first()
    authority = session.query(DirectorTreatmentAuthority).filter_by(treatment_id=pointer.treatment_id, envelope_fingerprint=pointer.authority_envelope_fingerprint).first()
    if not treatment or not authority or str(pointer.treatment_revision) != str(getattr(treatment, "revision", "")) or str(authority.treatment_revision) != str(getattr(treatment, "revision", "")) or str(authority.scene_id) != _text(scene_id) or str(authority.book_id) != str(book_id) or str(authority.episode) != str(episode) or treatment.status != "approved" or treatment.qualification_state != "PRODUCTION_QUALIFIED" or authority.qualification_state != "PRODUCTION_QUALIFIED":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_NOT_PRODUCTION_QUALIFIED", "message": "Current DirectorTreatment is not production-qualified."})
    envelope = _json(authority.envelope_json, {})
    model_info = _json(getattr(treatment, "model_info", "{}"), {})
    provenance_readiness = validate_phase_b_provenance_readiness(envelope=envelope, model_info=model_info)
    if provenance_readiness.get("invalid"):
        mark_treatment_stale(session, treatment, ["DIRECTOR_PROVENANCE_TAMPERED"]); session.commit()
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_PROVENANCE_TAMPERED", "message": provenance_readiness.get("detail", "Treatment provenance contract is invalid.")})
    if authority.stale_status == "STALE" or treatment.stale_status == "STALE":
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_STALE", "message": "Current DirectorTreatment is stale.", "stale_reasons": _json(authority.stale_reasons, [])})
    if treatment.payload_hash != payload_hash(treatment_payload_from_row(treatment)):
        mark_treatment_stale(session, treatment, ["DIRECTOR_TREATMENT_PAYLOAD_TAMPERED"]); session.commit()
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_PAYLOAD_TAMPERED", "message": "DirectorTreatment payload hash does not match."})
    if authority.envelope_fingerprint != _envelope_fingerprint(envelope):
        mark_treatment_stale(session, treatment, ["DIRECTOR_TREATMENT_AUTHORITY_TAMPERED"]); session.commit()
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_AUTHORITY_TAMPERED", "message": "DirectorTreatment authority envelope fingerprint does not match."})
    if str(envelope.get("schema_version") or "") != SCHEMA_VERSION or str(envelope.get("authority_policy_version") or "") != AUTHORITY_POLICY_VERSION:
        _stale_reasons = ["TREATMENT_AUTHORITY_POLICY_CHANGED"]
        mark_treatment_stale(session, treatment, _stale_reasons); session.commit()
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_STALE", "message": "Treatment authority policy is no longer current.", "stale_reasons": _stale_reasons})
    envelope_identity = envelope.get("scene_identity") if isinstance(envelope.get("scene_identity"), dict) else {}
    envelope_script = envelope.get("script_ir") if isinstance(envelope.get("script_ir"), dict) else {}
    if _text(envelope.get("scene_id")) != _text(scene_id) or _text(envelope_identity.get("scene_id")) != _text(scene_id) or str(envelope.get("treatment_id")) != str(treatment.id) or str(envelope.get("treatment_revision")) != str(treatment.revision) or _text(envelope.get("treatment_payload_hash")) != _text(treatment.payload_hash):
        mark_treatment_stale(session, treatment, ["DIRECTOR_TREATMENT_AUTHORITY_LINEAGE_CHANGED"]); session.commit()
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_AUTHORITY_TAMPERED", "message": "Treatment authority lineage does not match the bound rows."})
    script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
    current_ir = session.query(ScriptIRVersion).filter_by(id=getattr(script_row, "current_script_ir_version_id", None), book_id=book_id, episode=episode).first() if script_row else None
    ir_meta = envelope.get("script_ir") if isinstance(envelope.get("script_ir"), dict) else {}
    def _stale_raise(message: str, reasons: list[str]) -> None:
        mark_treatment_stale(session, treatment, reasons)
        session.commit()
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_STALE", "message": message, "stale_reasons": reasons})

    if not current_ir or current_ir.status != "production_qualified" or str(ir_meta.get("id")) != str(current_ir.id) or str(ir_meta.get("revision")) != str(current_ir.revision) or str(ir_meta.get("payload_hash")) != str(current_ir.payload_hash):
        _stale_raise("Treatment ScriptIR lineage is stale or no longer current.", ["SCRIPT_IR_CHANGED"])
    if script_row is None or _text((envelope.get("source_lineage") if isinstance(envelope.get("source_lineage"), dict) else {}).get("immutable_source_raw_hash")) != hashlib.sha256(str(script_row.content or "").encode("utf-8")).hexdigest():
        _stale_raise("Treatment immutable source lineage is stale.", ["SOURCE_CHANGED"])
    # The ScriptIR authority envelope is itself an input to Treatment
    # authority.  A changed or tampered upstream envelope must invalidate the
    # downstream pointer even when the ScriptIR row id/hash is unchanged.
    from core.script_ir_authority import validate_authority_envelope
    current_ir_envelope = _json(getattr(current_ir, "authority_envelope_json", "{}"), {})
    upstream_report = validate_authority_envelope(current_ir_envelope, payload=_json(current_ir.payload_json, {}))
    if upstream_report.get("status") != "PASS" or _text(envelope_script.get("authority_envelope_fingerprint")) != _text(current_ir_envelope.get("envelope_fingerprint")):
        _stale_raise("Treatment upstream ScriptIR authority is stale.", ["SCRIPT_IR_AUTHORITY_CHANGED"])
    current_scene = None
    ir_payload = _json(current_ir.payload_json, {})
    for item in ir_payload.get("scenes", []) if isinstance(ir_payload, dict) and isinstance(ir_payload.get("scenes"), list) else []:
        if isinstance(item, dict) and _text(item.get("scene_id")) == _text(scene_id):
            current_scene = item; break
    if not current_scene or _text(current_scene.get("name")) != _text(envelope.get("scene_identity", {}).get("scene_name")):
        _stale_raise("Scene identity was deleted, renamed or reidentified.", ["SCENE_IDENTITY_CHANGED"])
    contract_meta = envelope.get("contract") if isinstance(envelope.get("contract"), dict) else {}
    if str(contract_meta.get("fingerprint") or "") != contract_fingerprint():
        _stale_raise("Treatment contract has changed.", ["TREATMENT_CONTRACT_CHANGED"])
    # Recompute the locked asset constraint fingerprint from current rows. A
    # changed reference revision cannot silently remain production authority.
    current_locked: list[dict[str, Any]] = []
    for asset in session.query(VisualReferenceAsset).filter_by(book_id=book_id, episode=episode, status="locked").order_by(VisualReferenceAsset.id).all():
        if _text(asset.image_url) or _text(asset.local_path) or _text(asset.reference_token):
            current_locked.append({"id": asset.id, "asset_type": asset.asset_type, "asset_id": asset.asset_id, "asset_name": asset.asset_name, "status": asset.status, "image_url": asset.image_url, "local_path": asset.local_path, "reference_token": asset.reference_token, "revision": asset.updated_at.isoformat() if asset.updated_at else "", "authority_class": "LOCKED_PRODUCTION_CONSTRAINT"})
    for asset in session.query(VisualMakeup).filter_by(book_id=book_id, episode=episode).order_by(VisualMakeup.id).all():
        if str(asset.asset_status or "").lower() == "locked":
            meta = _json(asset.meta_info, {})
            structured = meta.get("structured_result") if isinstance(meta, dict) and isinstance(meta.get("structured_result"), dict) else {}
            item = {"id": str(asset.id), "name": asset.character_name, "gender": str(structured.get("gender") or ""), "asset_status": asset.asset_status, "stage_name": asset.stage_name, "refined_outfit": asset.refined_outfit, "hair_style": asset.hair_style}
            current_locked.append({"id": item["id"], "name": item["name"], "asset_type": "character", "authority_class": "LOCKED_PRODUCTION_CONSTRAINT", "fingerprint": fingerprint(item)})
    asset_meta = envelope.get("asset_authority") if isinstance(envelope.get("asset_authority"), dict) else {}
    if str(asset_meta.get("locked_constraint_fingerprint") or "") and str(asset_meta.get("locked_constraint_fingerprint")) != fingerprint(current_locked):
        _stale_raise("Relevant locked asset authority has changed.", ["LOCKED_ASSET_CHANGED"])
    fact_meta = envelope.get("fact_snapshot") if isinstance(envelope.get("fact_snapshot"), dict) else {}
    if str(fact_meta.get("id") or "").isdigit():
        fact = session.query(FactSnapshot).filter_by(id=int(fact_meta["id"]), book_id=book_id, episode=episode).first()
        if not fact or str(fact.revision) != str(fact_meta.get("revision")) or str(fact.payload_hash) != str(fact_meta.get("payload_hash")) or str(fact.status).lower() != "confirmed":
            _stale_raise("Bound FactSnapshot has changed.", ["FACT_SNAPSHOT_CHANGED"])
    semantic = envelope.get("semantic_contract") if isinstance(envelope.get("semantic_contract"), dict) else {}
    decisions = _json(getattr(treatment, "director_decisions", "{}"), {})
    from core.director_semantics import DIRECTOR_CONTRACT_VERSION
    semantic_ready = bool(_text(semantic.get("version")) == DIRECTOR_CONTRACT_VERSION and isinstance(decisions.get("director_beat_decisions"), list))
    envelope["semantic_contract_ready"] = semantic_ready
    envelope["provenance_contract_ready"] = bool(provenance_readiness.get("ready"))
    envelope["phase_b_readiness_reasons"] = ([] if semantic_ready else ["DIRECTOR_SEMANTIC_CONTRACT_REQUIRED"]) + list(provenance_readiness.get("reasons", []))
    envelope["phase_b_semantic_ready"] = bool(semantic_ready and provenance_readiness.get("ready"))
    return treatment, envelope


def mark_treatment_stale(session: Any, treatment: Any, reasons: list[str]) -> None:
    from models import DirectorTreatmentAuthority, DirectorTreatmentPointer
    # Keep the lifecycle state explicit.  ``approved`` alone is not enough to
    # remain consumable once any bound authority changed; production resolvers
    # should see the stale state directly rather than infer it from metadata.
    treatment.status = "stale"
    treatment.stale_status = "STALE"; treatment.qualification_state = "STALE"; treatment.stale_reasons = json.dumps(sorted(set(reasons)), ensure_ascii=False); treatment.updated_at = datetime.now()
    authority = session.query(DirectorTreatmentAuthority).filter_by(treatment_id=treatment.id).first()
    if authority:
        authority.stale_status = "STALE"; authority.qualification_state = "STALE"; authority.stale_reasons = json.dumps(sorted(set(reasons)), ensure_ascii=False); authority.updated_at = datetime.now()
    session.query(DirectorTreatmentPointer).filter_by(treatment_id=treatment.id).delete(synchronize_session=False)


__all__ = ["SCHEMA_VERSION", "CONTRACT_SCHEMA_VERSION", "AUTHORITY_POLICY_VERSION", "QUALIFICATION_STATES", "STALE_STATUSES", "SOURCE_CONSTRAINT_FIELDS", "DIRECTOR_DECISION_FIELDS", "DOWNSTREAM_AUTHORING_FIELDS", "treatment_contract", "contract_fingerprint", "treatment_payload_from_row", "payload_hash", "classify_asset_authority", "build_treatment_authority_envelope", "validate_treatment_candidate", "validate_phase_b_provenance_readiness", "resolve_scene_for_treatment", "resolve_current_authoritative_treatment", "mark_treatment_stale"]
