"""Evidence-first SceneBlocking / Spatial Engine API."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.scene_blocking import build_scene_blocking, build_scene_blocking_v2, validate_scene_blocking, repair_scene_blocking
from core.scene_blocking_authority import (
    build_scene_blocking_authority_envelope,
    blocking_payload_from_row,
    blocking_payload_hash,
    classify_scene_asset,
    contract_fingerprint as scene_blocking_contract_fingerprint,
    initialize_continuity_state,
    resolve_current_authoritative_scene_blocking,
    validation_fingerprint as scene_blocking_validation_fingerprint,
    validate_scene_blocking_candidate_authority,
)
from core.blocking_state_compiler import COMPILER_VERSION, compile_blocking_states, validate_blocking_contract
from core.repair_ledger import record_repair_attempt
from core.script_ir import resolve_script_payload
from core.director_treatment_authority import resolve_current_authoritative_treatment
from models import DirectorTreatment, DirectorTreatmentAuthority, FactSnapshot, VisualLocation, SceneBlocking, SceneBlockingAuthority, SceneBlockingPointer, Script, Session, ScriptIRVersion

router = APIRouter(prefix="/api/books", tags=["scene-blocking"])


class SceneBlockingPreviewRequest(BaseModel):
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
    treatment_id: int | None = Field(default=None, validation_alias=AliasChoices("treatment_id", "treatmentId"))
    persist: bool = False
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))
    schema_version: str = Field(default="", validation_alias=AliasChoices("schema_version", "schemaVersion"))


class SceneBlockingConfirmRequest(BaseModel):
    blocking_id: int = Field(validation_alias=AliasChoices("blocking_id", "blockingId"))
    evidence_fingerprint: str = Field(default="", validation_alias=AliasChoices("evidence_fingerprint", "evidenceFingerprint"))
    confirmed: bool = False
    blocking: dict[str, Any] | None = None
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))
    schema_version: str = Field(default="", validation_alias=AliasChoices("schema_version", "schemaVersion"))
    unknown_resolutions: list[dict[str, Any]] = Field(default_factory=list, validation_alias=AliasChoices("unknown_resolutions", "unknownResolutions"))


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _text(value: Any) -> str:
    return str(value or "").strip()


def _row_payload(row: SceneBlocking) -> dict[str, Any]:
    return {
        "id": row.id, "book_id": row.book_id, "episode": row.episode, "scene_id": getattr(row, "scene_id", ""), "scene_name": row.scene_name,
        "revision": row.revision, "status": row.status,
        "execution_status": row.execution_status, "quality_status": row.quality_status,
        "production_status": row.production_status, "workflow_profile": row.workflow_profile,
        "treatment_id": row.treatment_id,
        "treatment_revision": row.treatment_revision, "source_script_hash": row.source_script_hash,
        "schema_version": getattr(row, "schema_version", "scene_blocking_v1"),
        "participants": _json(row.participants, []), "beat_transitions": _json(row.beat_transitions, []),
        "spatial_rules": _json(row.spatial_rules, []), "unknowns": _json(row.unknowns, []),
        "evidence_fingerprint": row.evidence_fingerprint, "model_info": _json(row.model_info, {}),
        "spatial_model": _json(getattr(row, "spatial_model", "{}"), {}),
        "source_spatial_facts": _json(getattr(row, "source_spatial_facts", "[]"), []),
        "creative_decisions": _json(getattr(row, "creative_decisions", "[]"), []),
        "derived_constraints": _json(getattr(row, "derived_constraints", "{}"), {}),
        "unresolved_facts": _json(getattr(row, "unresolved_facts", "[]"), []),
        "camera_axis": _json(getattr(row, "camera_axis", "{}"), {}),
        "validation": _json(getattr(row, "validation", "{}"), {}),
        "source_script_ir_version_id": getattr(row, "source_script_ir_version_id", None),
        "source_script_ir_revision": getattr(row, "source_script_ir_revision", None),
        "source_script_ir_hash": getattr(row, "source_script_ir_hash", ""),
        "source_script_authority_fingerprint": getattr(row, "source_script_authority_fingerprint", ""),
        "treatment_authority_fingerprint": getattr(row, "treatment_authority_fingerprint", ""),
        "treatment_payload_hash": getattr(row, "treatment_payload_hash", ""),
        "source_fact_snapshot_id": getattr(row, "source_fact_snapshot_id", ""),
        "source_fact_snapshot_revision": getattr(row, "source_fact_snapshot_revision", None),
        "source_fact_snapshot_hash": getattr(row, "source_fact_snapshot_hash", ""),
        "source_immutable_raw_hash": getattr(row, "source_immutable_raw_hash", ""),
        "contract_fingerprint": getattr(row, "contract_fingerprint", ""),
        "validation_fingerprint": getattr(row, "validation_fingerprint", ""),
        "payload_hash": getattr(row, "payload_hash", ""),
        "authority_envelope_id": getattr(row, "authority_envelope_id", None),
        "qualification_state": getattr(row, "qualification_state", "DRAFT"),
        "stale_status": getattr(row, "stale_status", "UNKNOWN"),
        "stale_reasons": _json(getattr(row, "stale_reasons", "[]"), []),
        "asset_authority": _json(getattr(row, "asset_authority", "{}"), {}),
        "continuity_state": _json(getattr(row, "continuity_state", "{}"), {}),
        "source_lineage": _json(getattr(row, "source_lineage", "{}"), {}),
        "activated_at": getattr(row, "activated_at", None).isoformat() if getattr(row, "activated_at", None) else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_blocking_candidate(raw: Any, baseline: dict[str, Any], *, production: bool = False) -> dict[str, Any]:
    if production:
        if not isinstance(raw, dict):
            raise ValueError("BLOCKING_SEMANTIC_CONTRACT_REQUIRED: candidate must contain the canonical blocking contract")
        candidate = validate_scene_blocking_candidate_authority(raw if isinstance(raw, dict) else {}, baseline)
        canonical_keys = {"initial_state", "blocking_transitions", "compiler_version", "compiled_states_hash"}
        missing = sorted(key for key in canonical_keys if key not in raw or raw.get(key) in (None, "", []))
        if missing:
            raise ValueError(f"BLOCKING_SEMANTIC_CONTRACT_REQUIRED: missing {', '.join(missing)}")
        if raw.get("compiler_version") != COMPILER_VERSION:
            raise ValueError(f"UNSUPPORTED_BLOCKING_COMPILER_VERSION: {raw.get('compiler_version')}")
        ordered_beats = [{"beat_id": item.get("beat_id")} for item in candidate.get("beat_transitions", []) if isinstance(item, dict) and item.get("beat_id")]
        zone_ids = {str(item.get("zone_id")) for item in candidate.get("zones", []) if isinstance(item, dict) and item.get("zone_id")}
        contract = validate_blocking_contract({"initial_state": candidate.get("initial_state"), "blocking_transitions": candidate.get("blocking_transitions"), "zone_ids": zone_ids}, ordered_beats=ordered_beats)
        if contract.get("status") != "qualified":
            raise ValueError(f"blocking transition contract is invalid: {contract.get('errors')}")
        if raw.get("compiled_states_hash") != contract.get("compiled_states_hash"):
            raise ValueError("BLOCKING_COMPILED_HASH_MISMATCH: compiled state hash does not match deterministic compiler output")
        compiled = compile_blocking_states(candidate["initial_state"], ordered_beats, candidate["blocking_transitions"], valid_zones=zone_ids)
        supplied = raw.get("beat_spatial_states")
        if supplied not in (None, []) and supplied != compiled.get("states"):
            raise ValueError("BLOCKING_DERIVED_STATE_EDIT_FORBIDDEN: beat_spatial_states is compiler output and cannot be edited")
        candidate["beat_spatial_states"] = compiled.get("states", [])
        candidate["compiled_states_hash"] = compiled.get("compiled_states_hash", "")
        candidate["movement_path_projection"] = [{"beat_ref": t.get("beat_ref"), "subject_ref": t.get("subject_ref"), "from": c.get("from"), "to": c.get("to"), "projection": "BlockingTransition"} for t in candidate["blocking_transitions"] for c in (t.get("changes") or []) if isinstance(c, dict) and str(c.get("property", "")).upper() == "ZONE"]
        # Production canonical validation is structural and deterministic. The
        # historical spatial/placeholder validator remains a creative legacy
        # diagnostic and is not an Authority hard gate.
        report = contract if production else validate_scene_blocking(candidate, scene_canonical=baseline.get("scene_canonical"), previous_blocking=baseline.get("previous_blocking"))
        # Preserve the explicit unknown set.  Validation success is not a
        # license to erase unresolved continuity/geometry requirements.
        if report.get("status") != "qualified" or candidate.get("unknowns"):
            raise ValueError(f"production SceneBlocking remains unresolved: {report.get('errors') or candidate.get('unknowns')}")
        candidate["validation"] = report
        return candidate
    if not isinstance(raw, dict):
        raise ValueError("SceneBlocking candidate must be an object")
    allowed = {"scene_name", "participants", "beat_transitions", "spatial_rules", "unknowns", "schema_version", "space", "spatial_model", "source_spatial_facts", "creative_decisions", "derived_constraints", "unresolved_facts", "camera_axis", "validation", "conflicts", "scene_id"}
    unexpected = sorted(set(raw) - allowed)
    if unexpected:
        raise ValueError(f"candidate contains non-whitelisted fields: {', '.join(unexpected)}")
    participants = raw.get("participants", baseline["participants"])
    if not isinstance(participants, list):
        raise ValueError("participants must be a list")
    baseline_ids = {str(item.get("character_id")) for item in baseline["participants"] if isinstance(item, dict)}
    candidate_ids = {str(item.get("character_id")) for item in participants if isinstance(item, dict)}
    if candidate_ids != baseline_ids or any(not isinstance(item, dict) for item in participants):
        raise ValueError("participants must preserve the declared character ids")
    beats = raw.get("beat_transitions", baseline["beat_transitions"])
    if not isinstance(beats, list) or any(not isinstance(item, dict) for item in beats):
        raise ValueError("beat_transitions must be a list of objects")
    baseline_beat_ids = {str(item.get("beat_id")) for item in baseline["beat_transitions"] if isinstance(item, dict)}
    if {str(item.get("beat_id")) for item in beats} != baseline_beat_ids:
        raise ValueError("beat_transitions must preserve the declared beat ids")
    rules = raw.get("spatial_rules", baseline["spatial_rules"])
    unknowns = raw.get("unknowns", baseline["unknowns"])
    if not isinstance(rules, list) or not all(str(item).strip() for item in rules):
        raise ValueError("spatial_rules must be a list of strings")
    if not isinstance(unknowns, list) or not all(str(item).strip() for item in unknowns):
        raise ValueError("unknowns must be a list of strings")
    if baseline.get("schema_version") == "scene_blocking_v2":
        source_facts = raw.get("source_spatial_facts", baseline.get("source_spatial_facts", []))
        if source_facts != baseline.get("source_spatial_facts", []):
            raise ValueError("source_spatial_facts are immutable and must match the evidence snapshot")
        if raw.get("schema_version", baseline.get("schema_version")) != "scene_blocking_v2":
            raise ValueError("V2 candidate must retain schema_version=scene_blocking_v2")
        candidate = {
            "scene_name": baseline["scene_name"], "scene_id": baseline.get("scene_id", ""),
            "space": raw.get("space", baseline.get("space", {})), "participants": participants,
            "camera_axis": raw.get("camera_axis", baseline.get("camera_axis", {})),
            "source_spatial_facts": source_facts,
            "creative_decisions": raw.get("creative_decisions", baseline.get("creative_decisions", [])),
            "derived_constraints": raw.get("derived_constraints", baseline.get("derived_constraints", {})),
            "conflicts": baseline.get("conflicts", []),
        }
        report = validate_scene_blocking(candidate)
        if report["status"] != "qualified":
            raise ValueError(f"spatial validation blocked: {report['errors']}")
        return {**candidate, "beat_transitions": beats, "spatial_rules": [str(item) for item in rules], "unknowns": []}
    return {
        "scene_name": baseline["scene_name"], "participants": participants, "beat_transitions": beats,
        "spatial_rules": [str(item) for item in rules], "unknowns": [str(item) for item in unknowns],
    }


@router.post("/{book_id}/episodes/{episode}/scene-blocking/preview")
def preview_scene_blocking(book_id: int, episode: int, req: SceneBlockingPreviewRequest) -> dict[str, Any]:
    profile = str(req.workflow_profile or "creative_draft").strip().lower()
    is_production = profile == "production"
    with Session() as session:
        treatment = None
        treatment_authority: dict[str, Any] = {}
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        if is_production:
            if not req.scene_id.strip():
                raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production SceneBlocking requires a ScriptIR scene_id."})
            script = resolve_script_payload(session, script_row, workflow_profile="production")
            scenes = script.get("scenes") if isinstance(script, dict) and isinstance(script.get("scenes"), list) else []
            scene = next((item for item in scenes if isinstance(item, dict) and _text(item.get("scene_id")) == req.scene_id.strip()), None)
            if scene is None:
                raise HTTPException(status_code=409, detail={"code": "SCENE_ID_NOT_FOUND", "message": "The requested scene_id is not present in the current ScriptIR."})
            scene_id = _text(scene.get("scene_id"))
            treatment, treatment_authority = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
        else:
            treatment_query = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, status="approved")
            if req.scene_name.strip() and not req.treatment_id:
                treatment_query = treatment_query.filter_by(scene_name=req.scene_name.strip())
            treatment = session.get(DirectorTreatment, req.treatment_id) if req.treatment_id else treatment_query.order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
            script = resolve_script_payload(session, script_row, workflow_profile=profile)
            wanted = req.scene_name.strip() or getattr(treatment, "scene_name", "")
            scenes = script.get("scenes") if isinstance(script, dict) and isinstance(script.get("scenes"), list) else []
            scene = next((item for item in scenes if isinstance(item, dict) and _text(item.get("name")) == wanted), None)
            scene_id = _text(req.scene_id or getattr(treatment, "scene_id", "") or (scene or {}).get("scene_id"))
        if not treatment or treatment.book_id != book_id or treatment.episode != episode or treatment.status != "approved":
            raise HTTPException(status_code=409, detail="SceneBlocking requires an approved DirectorTreatment.")
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found.")
        scene_name = _text(scene.get("name") or treatment.scene_name) or "未命名场景"
        treatment_payload = {"scene_name": treatment.scene_name, "scene_id": _text(getattr(treatment, "scene_id", "") or scene_id), "character_intents": _json(treatment.character_intents, {}), "beat_map": _json(treatment.beat_map, []), "prompt_fingerprint": treatment.prompt_fingerprint}
        source_hash = _text(getattr(treatment, "source_script_ir_hash", "")) if is_production else hashlib.sha256((script_row.content or "").encode("utf-8")).hexdigest()
        use_v2 = is_production or str(req.schema_version or "").lower() in {"scene_blocking_v2", "v2"}
        scene_canonical = None
        if is_production:
            location = session.query(VisualLocation).filter(VisualLocation.book_id == book_id, VisualLocation.scene_id == scene_id).order_by(VisualLocation.id.desc()).first()
            if location is None:
                # Production authority is identity-based.  A legacy name match
                # may be shown by an audit UI, but cannot satisfy this gate.
                location = None
        else:
            location = session.query(VisualLocation).filter(VisualLocation.book_id == book_id, VisualLocation.name == scene_name).order_by(VisualLocation.id.desc()).first()
        if location:
            scene_canonical = {"name": location.name, "scene_id": getattr(location, "scene_id", ""), "canonical_facts": _json(location.canonical_facts, {}), "state_variants": _json(location.state_variants, {}), "look_profile": _json(location.look_profile, {}), "board_spec": _json(location.board_spec, {}), "key_props": _json(location.key_props, [])}
        fact_snapshot = None
        if is_production:
            fact_meta = treatment_authority.get("fact_snapshot") if isinstance(treatment_authority, dict) else {}
            fact_id = fact_meta.get("id") if isinstance(fact_meta, dict) else None
            if fact_id in (None, ""):
                raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_LINEAGE_MISSING", "message": "Production SceneBlocking requires the exact FactSnapshot bound by DirectorTreatment."})
            fact_row = session.query(FactSnapshot).filter_by(id=int(fact_id), book_id=book_id, episode=episode).first() if str(fact_id).isdigit() else None
            if not fact_row or str(fact_row.revision) != str(fact_meta.get("revision")) or _text(fact_row.payload_hash) != _text(fact_meta.get("payload_hash")) or _text(fact_row.status).lower() != "confirmed":
                raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_CHANGED", "message": "The FactSnapshot bound by DirectorTreatment is missing or changed."})
            fact_snapshot = {"snapshot_id": str(fact_row.id), "revision": fact_row.revision, "source_fingerprint": fact_row.source_fingerprint, "payload_hash": fact_row.payload_hash, "records": _json(fact_row.records_json, [])}
        else:
            fact_row = session.query(FactSnapshot).filter_by(book_id=book_id, episode=episode, status="confirmed").order_by(FactSnapshot.revision.desc(), FactSnapshot.id.desc()).first()
            fact_snapshot = {"records": _json(fact_row.records_json, [])} if fact_row else None
        previous_payload = None
        if is_production:
            pointer = session.query(SceneBlockingPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
            if pointer:
                previous = session.query(SceneBlocking).filter_by(id=pointer.blocking_id, book_id=book_id, episode=episode, scene_id=scene_id).first()
                if previous:
                    previous_payload = _row_payload(previous)
        elif use_v2:
            previous = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved", schema_version="scene_blocking_v2").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
            previous_payload = _row_payload(previous) if previous else None
        blocking = build_scene_blocking_v2(scene=scene, treatment=treatment_payload, source_script_hash=source_hash, scene_canonical=scene_canonical, fact_snapshot=fact_snapshot, previous_blocking=previous_payload) if use_v2 else build_scene_blocking(scene=scene, treatment=treatment_payload, source_script_hash=source_hash)
        blocking["scene_id"] = scene_id
        blocking["scene_name"] = scene_name
        if is_production:
            # Preview exposes a reviewable canonical proposal.  The values are
            # still revalidated and deterministically recompiled at confirm.
            blocking.setdefault("initial_state", {"characters": {}, "props": {}, "exit_access": {}})
            blocking.setdefault("blocking_transitions", [])
            blocking["compiler_version"] = COMPILER_VERSION
            preview_beats = [{"beat_id": item.get("beat_id")} for item in blocking.get("beat_transitions", []) if isinstance(item, dict) and item.get("beat_id")]
            preview_zones = {str(item.get("zone_id")) for item in blocking.get("zones", []) if isinstance(item, dict) and item.get("zone_id")}
            preview_compile = compile_blocking_states(blocking["initial_state"], preview_beats, blocking["blocking_transitions"], valid_zones=preview_zones)
            blocking["beat_spatial_states"] = preview_compile.get("states", [])
            blocking["compiled_states_hash"] = preview_compile.get("compiled_states_hash", "")
            blocking["movement_path_projection"] = []
        # SceneBlocking's spatial classifier is retained as a compatibility
        # projection for existing geometry fixtures.  It is not consumed as
        # VisualAsset authority: production PromptIR resolves only the
        # versioned VisualAssetPointer/ReferenceAuthority chain.
        asset_authority = classify_scene_asset(location, scene_id=scene_id) if is_production else {"authority_class": "ADVISORY_SCENE_CONTEXT", "locked_constraints": [], "advisory_context": [], "authoring_pending": []}
        if is_production:
            asset_authority = {**asset_authority, "scene_asset_fingerprint": asset_authority.get("fingerprint", "")}
        blocking["_locked_space"] = asset_authority.get("authority_class") == "LOCKED_PRODUCTION_CONSTRAINT"
        continuity_state = initialize_continuity_state(scene=scene, treatment=treatment_payload, previous_blocking=previous_payload) if is_production else {"states": [], "unresolved": [], "resolution": [], "fingerprint": ""}
        blocking["asset_authority"] = asset_authority
        blocking["continuity_state"] = continuity_state
        if is_production:
            blocking["evidence_fingerprint"] = hashlib.sha256(json.dumps({"base": blocking.get("evidence_fingerprint", ""), "asset_authority": asset_authority, "continuity_state": continuity_state, "treatment_authority": treatment_authority.get("envelope_fingerprint", "")}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        blocking["treatment_id"] = treatment.id
        blocking["treatment_revision"] = treatment.revision
        blocking["treatment_fingerprint"] = treatment_authority.get("envelope_fingerprint", "") if is_production else treatment.prompt_fingerprint
        if is_production:
            # Geometry and required continuity are explicit production blockers;
            # advisory legacy rows never satisfy the gate.
            extra_errors = list(blocking.get("validation", {}).get("errors", []))
            if asset_authority.get("authority_class") != "LOCKED_PRODUCTION_CONSTRAINT":
                extra_errors.extend(asset_authority.get("authoring_pending", []) or [{"code": "SCENE_ASSET_NOT_LOCKED", "severity": "blocker"}])
            extra_errors.extend(continuity_state.get("unresolved", []))
            blocking["production_blockers"] = extra_errors
            blocking["validation"] = {**(blocking.get("validation") or {}), "status": "qualified" if not extra_errors else "blocked", "errors": extra_errors, "blocker_count": len(extra_errors), "warning_count": int((blocking.get("validation") or {}).get("warning_count") or 0)}
            # Keep the legacy V2 unknowns projection stable for callers that
            # only ask about spatial facts.  Production prerequisites such as
            # an unbound scene asset live in the explicit blocker list and are
            # enforced at confirmation/ShotPlan gates.
            blocking["unknowns"] = [str(item.get("message") or item.get("code") or item) for item in extra_errors if isinstance(item, dict) and item.get("code") not in {"SCENE_ASSET_MISSING", "SCENE_ASSET_NOT_LOCKED", "SCENE_ASSET_GEOMETRY_MISSING", "SCENE_ASSET_SCENE_ID_MISMATCH"}]
        repairs: list[dict[str, Any]] = []
        if blocking.get("validation", {}).get("status") == "blocked" and not is_production:
            repaired = repair_scene_blocking(blocking, max_attempts=2)
            if repaired.get("status") == "qualified":
                blocking = {**repaired["candidate"], "validation": validate_scene_blocking(repaired["candidate"], scene_canonical=scene_canonical, previous_blocking=previous_payload)}
                repairs = [item for attempt in repaired.get("attempts", []) for item in attempt.get("repairs", [])]
        blocking["repair_attempts"] = repairs
        if is_production:
            blocking["qualification_state"] = "REVIEW_REQUIRED" if blocking.get("validation", {}).get("status") == "qualified" else "STRUCTURALLY_VALID"
            blocking["source_lineage"] = {"script_ir_version_id": getattr(script_row, "current_script_ir_version_id", None), "script_ir_authority_fingerprint": _text(treatment_authority.get("script_ir", {}).get("authority_envelope_fingerprint") if isinstance(treatment_authority.get("script_ir"), dict) else ""), "source_immutable_raw_hash": _text(treatment_authority.get("source_lineage", {}).get("immutable_source_raw_hash") if isinstance(treatment_authority.get("source_lineage"), dict) else ""), "fact_snapshot_id": fact_snapshot.get("snapshot_id") if isinstance(fact_snapshot, dict) else "", "fact_snapshot_revision": fact_snapshot.get("revision") if isinstance(fact_snapshot, dict) else None, "fact_snapshot_hash": fact_snapshot.get("payload_hash") if isinstance(fact_snapshot, dict) else ""}
        blocking["payload_hash"] = blocking_payload_hash(blocking)
        blocking["contract_fingerprint"] = scene_blocking_contract_fingerprint()
        blocking["validation_fingerprint"] = scene_blocking_validation_fingerprint(blocking.get("validation", {}))
        persisted_id = None
        if req.persist:
            # Only an open candidate is reusable.  An approved/superseded row
            # with the same evidence must never be returned as a new draft;
            # otherwise a later confirm would target an already-finalized row.
            existing = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, evidence_fingerprint=blocking["evidence_fingerprint"], status="draft").first()
            if existing:
                persisted_id = existing.id
            else:
                persisted_spatial_model = dict(blocking.get("space", {}) if isinstance(blocking.get("space", {}), dict) else {})
                if is_production:
                    for key in ("initial_state", "blocking_transitions", "compiler_version", "compiled_states_hash", "beat_spatial_states", "movement_path_projection", "space_model", "zones", "anchors", "connections", "characters", "movement_paths", "eyelines", "prop_spatial_states", "critical_props", "interactions", "interaction_axes", "director_direction_refs", "provenance"):
                        if key in blocking:
                            persisted_spatial_model[key] = blocking[key]
                row = SceneBlocking(book_id=book_id, episode=episode, scene_id=scene_id, scene_name=scene_name, revision=1, status="draft", treatment_id=treatment.id, treatment_revision=treatment.revision, source_script_hash=source_hash, participants=json.dumps(blocking["participants"], ensure_ascii=False), beat_transitions=json.dumps(blocking["beat_transitions"], ensure_ascii=False), spatial_rules=json.dumps(blocking["spatial_rules"], ensure_ascii=False), unknowns=json.dumps(blocking["unknowns"], ensure_ascii=False), evidence_fingerprint=blocking["evidence_fingerprint"], model_info=json.dumps(blocking.get("model_info", {}), ensure_ascii=False), created_at=datetime.now(), updated_at=datetime.now(), workflow_profile=req.workflow_profile, schema_version=blocking.get("schema_version", "scene_blocking_v1"), spatial_model=json.dumps(persisted_spatial_model, ensure_ascii=False), source_spatial_facts=json.dumps(blocking.get("source_spatial_facts", []), ensure_ascii=False), creative_decisions=json.dumps(blocking.get("creative_decisions", []), ensure_ascii=False), derived_constraints=json.dumps(blocking.get("derived_constraints", {}), ensure_ascii=False), unresolved_facts=json.dumps(blocking.get("unresolved_facts", []), ensure_ascii=False), camera_axis=json.dumps(blocking.get("camera_axis", {}), ensure_ascii=False), validation=json.dumps(blocking.get("validation", {}), ensure_ascii=False), source_script_ir_version_id=(script_row.current_script_ir_version_id if is_production else None), source_script_ir_revision=(treatment.source_script_ir_revision if is_production else None), source_script_ir_hash=(treatment.source_script_ir_hash if is_production else ""), source_script_authority_fingerprint=(treatment.source_script_authority_fingerprint if is_production else ""), treatment_authority_fingerprint=(treatment_authority.get("envelope_fingerprint", "") if is_production else ""), treatment_payload_hash=(treatment.payload_hash if is_production else ""), source_fact_snapshot_id=(str(fact_snapshot.get("snapshot_id") or "") if is_production and isinstance(fact_snapshot, dict) else ""), source_fact_snapshot_revision=(fact_snapshot.get("revision") if is_production and isinstance(fact_snapshot, dict) else None), source_fact_snapshot_hash=(fact_snapshot.get("payload_hash", "") if is_production and isinstance(fact_snapshot, dict) else ""), source_immutable_raw_hash=(blocking.get("source_lineage", {}).get("source_immutable_raw_hash", "") if is_production else ""), contract_fingerprint=(blocking.get("contract_fingerprint", "") if is_production else ""), validation_fingerprint=(blocking.get("validation_fingerprint", "") if is_production else ""), payload_hash=(blocking.get("payload_hash", "") if is_production else ""), qualification_state=("CANDIDATE" if is_production else "DRAFT"), stale_status=("FRESH" if is_production else "UNKNOWN"), stale_reasons="[]", asset_authority=json.dumps(asset_authority, ensure_ascii=False), continuity_state=json.dumps(continuity_state, ensure_ascii=False), source_lineage=json.dumps(blocking.get("source_lineage", {}), ensure_ascii=False))
                session.add(row); session.commit(); session.refresh(row); persisted_id = row.id
                for repair in blocking.get("repair_attempts", []):
                    record_repair_attempt(repair=repair, issue=repair.get("issue"), context={"book_id": book_id, "episode": episode, "scene_id": blocking.get("scene_id"), "revalidation_status": blocking.get("validation", {}).get("status"), "revalidation_details": blocking.get("validation", {})}, session=session)
                if blocking.get("repair_attempts"):
                    session.commit()
        return {"mode": "deterministic_spatial_authority_v2" if use_v2 else "shadow_deterministic", "llm_called": False, "mutated": bool(persisted_id), "persisted_draft_id": persisted_id, "treatment_id": treatment.id, "scene_id": scene_id, "blocking": blocking, "review_status": "REVIEW_REQUIRED" if is_production else "DRAFT", "required_production_fields": ["initial_state", "blocking_transitions", "compiler_version", "compiled_states_hash"] if is_production else [], "authority_context": {"workflow_profile": profile, "fact_snapshot": fact_snapshot, "treatment_authority": treatment_authority if is_production else {}, "asset_authority": asset_authority, "continuity_state": continuity_state, "production_qualified": False}, "message": "这是只读空间调度草案；尚未批准 SceneBlocking 或更新生产指针。"}


@router.get("/{book_id}/episodes/{episode}/scene-blockings")
def list_scene_blockings(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        rows = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode).order_by(SceneBlocking.scene_name, SceneBlocking.revision.desc(), SceneBlocking.id.desc()).all()
    return {"items": [_row_payload(row) for row in rows]}


@router.get("/{book_id}/episodes/{episode}/shot-plan/readiness")
def shot_plan_readiness(book_id: int, episode: int, workflow_profile: str = "creative_draft") -> dict[str, Any]:
    """Return a hard gate for future ShotPlan generation."""
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        profile = _text(workflow_profile).lower() or "creative_draft"
        script = resolve_script_payload(session, script_row, workflow_profile="production" if profile == "production" else profile)
        scenes = [item for item in (script.get("scenes") if isinstance(script, dict) else []) if isinstance(item, dict)]
        if profile == "production":
            production_rows = []
            production_errors: list[str] = []
            for scene in scenes:
                scene_id = _text(scene.get("scene_id"))
                if not scene_id:
                    production_errors.append(f"{scene.get('name') or '未命名场景'}: SCENE_ID_REQUIRED")
                    continue
                try:
                    row, _ = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
                    production_rows.append(row)
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
                    production_errors.append(f"{scene.get('name') or scene_id}: {detail.get('code') or 'SCENE_BLOCKING_NOT_READY'}")
            approved = production_rows
        else:
            approved = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, status="approved").all()
            production_errors = []
    by_scene = {(_text(row.scene_id) if profile == "production" else row.scene_name): row for row in approved}
    missing = [(_text(scene.get("scene_id")) if profile == "production" else str(scene.get("name") or "未命名场景")) for scene in scenes if ((_text(scene.get("scene_id")) if profile == "production" else str(scene.get("name") or "未命名场景")) not in by_scene)]
    unresolved = []
    for row in approved:
        unresolved.extend([f"{row.scene_name}: {item}" for item in _json(row.unknowns, [])])
    blocking_issues = [f"缺少当前权威 SceneBlocking：{name}" for name in missing] + unresolved + production_errors
    return {"allowed": not blocking_issues, "status": "ready" if not blocking_issues else "blocked", "blocking_issues": blocking_issues, "approved_scene_count": len(approved), "scene_count": len(scenes), "workflow_profile": profile}


@router.post("/{book_id}/episodes/{episode}/scene-blocking/confirm")
def confirm_scene_blocking(book_id: int, episode: int, req: SceneBlockingConfirmRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="SceneBlocking approval requires confirmed=true.")
    profile = str(req.workflow_profile or "creative_draft").strip().lower()
    is_production = profile == "production"
    with Session() as session:
        draft = session.query(SceneBlocking).filter_by(id=req.blocking_id, book_id=book_id, episode=episode).first()
        if not draft:
            raise HTTPException(status_code=404, detail="SceneBlocking draft not found.")
        if draft.status != "draft":
            raise HTTPException(status_code=409, detail="This SceneBlocking draft has already been finalized.")
        draft_scene_id, draft_scene_name, draft_treatment_id = _text(getattr(draft, "scene_id", "")), draft.scene_name, draft.treatment_id
        if is_production:
            treatment, _authority = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=draft_scene_id)
            if treatment.id != draft_treatment_id:
                raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_POINTER_CHANGED", "message": "SceneBlocking draft references a non-current DirectorTreatment."})
        else:
            treatment = session.query(DirectorTreatment).filter_by(id=draft_treatment_id, book_id=book_id, episode=episode, status="approved").first()
        if not treatment:
            raise HTTPException(status_code=409, detail="The DirectorTreatment used by this draft is no longer approved.")
    preview = preview_scene_blocking(book_id, episode, SceneBlockingPreviewRequest(scene_id=draft_scene_id, scene_name=draft_scene_name, treatment_id=draft_treatment_id, workflow_profile=req.workflow_profile, schema_version=req.schema_version or getattr(draft, "schema_version", ""), persist=False))
    baseline = preview["blocking"]
    if is_production and baseline.get("production_blockers"):
        raise HTTPException(status_code=409, detail={"code": "SCENE_BLOCKING_NOT_READY", "message": "SceneBlocking production prerequisites are unresolved.", "blocking_issues": baseline.get("production_blockers")})
    if req.evidence_fingerprint and req.evidence_fingerprint != draft.evidence_fingerprint:
        raise HTTPException(status_code=409, detail="SceneBlocking evidence fingerprint does not match.")
    if baseline["evidence_fingerprint"] != draft.evidence_fingerprint:
        with Session() as session:
            stale = session.query(SceneBlocking).filter_by(id=req.blocking_id, book_id=book_id).first()
            if stale and stale.status == "draft":
                stale.status = "superseded"; stale.updated_at = datetime.now(); session.commit()
        raise HTTPException(status_code=409, detail="SceneBlocking evidence changed; draft is stale and must be regenerated.")
    try:
        if req.blocking:
            candidate_source = req.blocking
        else:
            fields = ("scene_name", "participants", "beat_transitions", "spatial_rules", "unknowns")
            if baseline.get("schema_version") == "scene_blocking_v2":
                fields = fields + ("schema_version", "space", "spatial_model", "source_spatial_facts", "creative_decisions", "derived_constraints", "unresolved_facts", "camera_axis", "validation", "scene_id")
            persisted_contract = _json(getattr(draft, "spatial_model", "{}"), {}) if is_production else {}
            candidate_source = {field: (persisted_contract.get(field) if isinstance(persisted_contract, dict) and field in persisted_contract else baseline.get(field)) for field in fields}
            if is_production and isinstance(persisted_contract, dict):
                for field in ("initial_state", "blocking_transitions", "compiler_version", "compiled_states_hash", "beat_spatial_states", "movement_path_projection", "space_model", "zones", "anchors", "connections", "characters", "movement_paths", "eyelines", "prop_spatial_states", "critical_props", "interactions", "interaction_axes", "director_direction_refs", "provenance"):
                    if field in persisted_contract:
                        candidate_source[field] = persisted_contract[field]
        if is_production:
            candidate_source["unknown_resolutions"] = req.unknown_resolutions
        candidate = _validate_blocking_candidate(candidate_source, baseline, production=is_production)
    except ValueError as exc:
        message = str(exc)
        code, _, detail = message.partition(":")
        known = {"BLOCKING_SEMANTIC_CONTRACT_REQUIRED", "UNSUPPORTED_BLOCKING_COMPILER_VERSION", "BLOCKING_COMPILED_HASH_MISMATCH", "BLOCKING_DERIVED_STATE_EDIT_FORBIDDEN"}
        if code in known:
            raise HTTPException(status_code=409, detail={"code": code, "message": detail.strip() or code}) from exc
        raise HTTPException(status_code=409, detail=f"SceneBlocking candidate is invalid: {exc}") from exc
    with Session() as session:
        draft = session.query(SceneBlocking).filter_by(id=req.blocking_id, book_id=book_id, episode=episode).first()
        if not draft or draft.status != "draft":
            raise HTTPException(status_code=409, detail="This SceneBlocking draft has already been finalized.")
        now = datetime.now()
        if not is_production:
            previous = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=candidate["scene_name"], status="approved").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
            if previous:
                previous.status = "superseded"; previous.updated_at = now
            anchor = {"previous_blocking_id": previous.id if previous else None, "previous_revision": previous.revision if previous else None}
            row = SceneBlocking(book_id=book_id, episode=episode, scene_id=_text(getattr(draft, "scene_id", "")), scene_name=candidate["scene_name"], revision=(previous.revision + 1 if previous else 1), status="approved", treatment_id=draft.treatment_id, treatment_revision=draft.treatment_revision, source_script_hash=draft.source_script_hash, participants=json.dumps(candidate["participants"], ensure_ascii=False), beat_transitions=json.dumps(candidate["beat_transitions"], ensure_ascii=False), spatial_rules=json.dumps(candidate["spatial_rules"], ensure_ascii=False), unknowns=json.dumps(candidate["unknowns"], ensure_ascii=False), evidence_fingerprint=draft.evidence_fingerprint, model_info=json.dumps({"mode": "confirmed_human_candidate", "rollback_anchor": anchor, "confirmed_at": now.isoformat()}, ensure_ascii=False), created_at=now, updated_at=now, workflow_profile=req.workflow_profile, schema_version=candidate.get("schema_version", getattr(draft, "schema_version", "scene_blocking_v1")), spatial_model=json.dumps(candidate.get("space", getattr(draft, "spatial_model", {})), ensure_ascii=False), source_spatial_facts=json.dumps(candidate.get("source_spatial_facts", []), ensure_ascii=False), creative_decisions=json.dumps(candidate.get("creative_decisions", []), ensure_ascii=False), derived_constraints=json.dumps(candidate.get("derived_constraints", {}), ensure_ascii=False), unresolved_facts=json.dumps(candidate.get("unresolved_facts", []), ensure_ascii=False), camera_axis=json.dumps(candidate.get("camera_axis", {}), ensure_ascii=False), validation=json.dumps(candidate.get("validation", {}), ensure_ascii=False))
            session.add(row); draft.status = "superseded"; draft.updated_at = now; session.commit(); session.refresh(row)
            return {"approved": True, "mutated": True, "scene_blocking": _row_payload(row), "rollback_anchor": anchor, "shot_plan_allowed": True}

        # Production activation is a single transaction: re-check the current
        # Treatment/ScriptIR/FactSnapshot lineage, then create authority and
        # update the scene pointer atomically.  No latest-approved fallback is
        # consulted at any point.
        treatment, treatment_envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=_text(draft.scene_id))
        if treatment.id != draft.treatment_id:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_TREATMENT_POINTER_CHANGED", "message": "Current DirectorTreatment changed; regenerate SceneBlocking."})
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        ir = session.query(ScriptIRVersion).filter_by(id=getattr(script_row, "current_script_ir_version_id", None), book_id=book_id, episode=episode).first() if script_row else None
        if not ir:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_CHANGED", "message": "Current ScriptIR is missing; regenerate SceneBlocking."})
        ir_envelope = _json(getattr(ir, "authority_envelope_json", "{}"), {})
        fact_id = _text(candidate.get("source_lineage", {}).get("fact_snapshot_id") if isinstance(candidate.get("source_lineage"), dict) else getattr(draft, "source_fact_snapshot_id", "")) or _text(getattr(draft, "source_fact_snapshot_id", ""))
        fact_row = session.query(FactSnapshot).filter_by(id=int(fact_id), book_id=book_id, episode=episode).first() if fact_id.isdigit() else None
        if not fact_row:
            raise HTTPException(status_code=409, detail={"code": "FACT_SNAPSHOT_LINEAGE_MISSING", "message": "SceneBlocking activation requires the exact bound FactSnapshot."})
        continuity_state = candidate.get("continuity_state") if isinstance(candidate.get("continuity_state"), dict) else _json(getattr(draft, "continuity_state", "{}"), {})
        asset_authority = candidate.get("asset_authority") if isinstance(candidate.get("asset_authority"), dict) else _json(getattr(draft, "asset_authority", "{}"), {})
        canonical_spatial_model = dict(candidate.get("space", candidate.get("spatial_model", {})) if isinstance(candidate.get("space", candidate.get("spatial_model", {})), dict) else {})
        for key in ("initial_state", "blocking_transitions", "compiler_version", "compiled_states_hash", "beat_spatial_states", "movement_path_projection", "space_model", "zones", "anchors", "connections", "characters", "movement_paths", "eyelines", "prop_spatial_states", "critical_props", "interactions", "interaction_axes", "director_direction_refs", "provenance"):
            if key in candidate:
                canonical_spatial_model[key] = candidate[key]
        previous_pointer = session.query(SceneBlockingPointer).filter_by(book_id=book_id, episode=episode, scene_id=_text(draft.scene_id)).first()
        previous = session.query(SceneBlocking).filter_by(id=previous_pointer.blocking_id).first() if previous_pointer else None
        anchor = {"previous_blocking_id": previous.id if previous else None, "previous_revision": previous.revision if previous else None}
        row = SceneBlocking(book_id=book_id, episode=episode, scene_id=_text(draft.scene_id), scene_name=candidate["scene_name"], revision=(previous.revision + 1 if previous else 1), status="approved", execution_status="ready", quality_status="qualified", production_status="ready", treatment_id=treatment.id, treatment_revision=treatment.revision, source_script_hash=_text(getattr(treatment, "source_script_ir_hash", "")), participants=json.dumps(candidate["participants"], ensure_ascii=False), beat_transitions=json.dumps(candidate["beat_transitions"], ensure_ascii=False), spatial_rules=json.dumps(candidate["spatial_rules"], ensure_ascii=False), unknowns=json.dumps(candidate["unknowns"], ensure_ascii=False), evidence_fingerprint=draft.evidence_fingerprint, model_info=json.dumps({"mode": "confirmed_human_candidate", "rollback_anchor": anchor, "confirmed_at": now.isoformat(), "provider_calls": 0}, ensure_ascii=False), created_at=now, updated_at=now, workflow_profile="production", schema_version="scene_blocking_v2", spatial_model=json.dumps(canonical_spatial_model, ensure_ascii=False), source_spatial_facts=json.dumps(candidate.get("source_spatial_facts", []), ensure_ascii=False), creative_decisions=json.dumps(candidate.get("creative_decisions", []), ensure_ascii=False), derived_constraints=json.dumps(candidate.get("derived_constraints", {}), ensure_ascii=False), unresolved_facts=json.dumps(candidate.get("unresolved_facts", []), ensure_ascii=False), camera_axis=json.dumps(candidate.get("camera_axis", {}), ensure_ascii=False), validation=json.dumps(candidate.get("validation", {}), ensure_ascii=False), source_script_ir_version_id=ir.id, source_script_ir_revision=ir.revision, source_script_ir_hash=ir.payload_hash, source_script_authority_fingerprint=_text(ir_envelope.get("envelope_fingerprint")), treatment_authority_fingerprint=_text(treatment_envelope.get("envelope_fingerprint")), treatment_payload_hash=_text(treatment.payload_hash), source_fact_snapshot_id=str(fact_row.id), source_fact_snapshot_revision=fact_row.revision, source_fact_snapshot_hash=fact_row.payload_hash, source_immutable_raw_hash=_text(treatment_envelope.get("source_lineage", {}).get("immutable_source_raw_hash") if isinstance(treatment_envelope.get("source_lineage"), dict) else ""), contract_fingerprint=scene_blocking_contract_fingerprint(), validation_fingerprint=scene_blocking_validation_fingerprint(candidate.get("validation", {})), asset_authority=json.dumps(asset_authority, ensure_ascii=False), continuity_state=json.dumps(continuity_state, ensure_ascii=False), source_lineage=json.dumps(candidate.get("source_lineage", {}), ensure_ascii=False), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", activated_at=now)
        session.add(row); session.flush()
        row.payload_hash = blocking_payload_hash(blocking_payload_from_row(row))
        envelope = build_scene_blocking_authority_envelope(blocking={**candidate, "treatment_id": treatment.id, "treatment_revision": treatment.revision, "treatment_fingerprint": treatment_envelope.get("envelope_fingerprint", ""), "source_script_hash": ir.payload_hash}, book_id=book_id, episode=episode, scene_id=_text(draft.scene_id), blocking_id=row.id, blocking_revision=row.revision, script_ir_version=ir, script_ir_envelope=ir_envelope, treatment=treatment, treatment_envelope=treatment_envelope, fact_snapshot=fact_row, asset_authority=asset_authority, continuity_state=continuity_state, validation=candidate.get("validation", {}))
        from core.scene_blocking_authority import _envelope_fingerprint as _blocking_envelope_fingerprint
        envelope["payload_hash"] = row.payload_hash
        envelope["envelope_fingerprint"] = _blocking_envelope_fingerprint(envelope)
        authority = SceneBlockingAuthority(book_id=book_id, episode=episode, scene_id=_text(draft.scene_id), blocking_id=row.id, blocking_revision=row.revision, payload_hash=row.payload_hash, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=now, activated_at=now)
        session.add(authority); session.flush(); row.authority_envelope_id = authority.id; row.activated_at = now
        if previous:
            previous.status = "superseded"; previous.updated_at = now
        if previous_pointer:
            previous_pointer.blocking_id = row.id; previous_pointer.blocking_revision = row.revision; previous_pointer.authority_envelope_fingerprint = envelope["envelope_fingerprint"]; previous_pointer.qualification_state = "PRODUCTION_QUALIFIED"; previous_pointer.updated_at = now
        else:
            session.add(SceneBlockingPointer(book_id=book_id, episode=episode, scene_id=_text(draft.scene_id), blocking_id=row.id, blocking_revision=row.revision, authority_envelope_fingerprint=envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED", created_at=now, updated_at=now))
        draft.status = "superseded"; draft.updated_at = now
        session.commit(); session.refresh(row)
        return {"approved": True, "mutated": True, "scene_blocking": _row_payload(row), "authority_envelope": envelope, "rollback_anchor": anchor, "shot_plan_allowed": True, "production_status": "ready"}
