"""Evidence-gated ShotPlan API."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.shot_plan import build_shot_plan
from core.director_creative_planner import build_creative_shot_plan_candidate, DirectorFactOverride, DirectorCreativeError
from core.director_creative_planner import build_creative_patch_candidate
from core.director_creative_contract import build_director_creative_contract
from core.scene_directing_strategy import build_scene_directing_strategy, SceneDirectingStrategyError
from core.director_patch_validator import validate_compiled_patch_result
from core.director_patch_compiler import compile_creative_patches, DirectorPatchCompileError
from core.director_quality_validator import score_director_quality
from core.director_local_repair import build_director_repair_options
from core.director_prompt import build_director_patch_prompt
import core.llm as llm_client
from core.prompt_cache import llm_request_fingerprint, summarize_audit_records
from core.script_ir import resolve_script_payload
from core.director_treatment_authority import resolve_current_authoritative_treatment
from core.scene_blocking_authority import resolve_current_authoritative_scene_blocking
from core.executability import preflight_shot_plan, build_executability_repair_plan
from core.shot_plan_authority import (
    build_shot_plan_authority_envelope,
    contract_fingerprint as shot_plan_contract_fingerprint,
    resolve_current_authoritative_shot_plan,
    shot_plan_payload_hash,
    shot_plan_payload_from_row,
    validate_shot_plan_candidate_authority,
)
from models import DirectorTreatment, FactSnapshot, SceneBlocking, Script, ScriptIRVersion, Session, ShotPlan, ShotPlanAuthority, ShotPlanPointer, StoryboardShot, VisualLocation

router = APIRouter(prefix="/api/books", tags=["shot-plan"])


class ShotPlanPreviewRequest(BaseModel):
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
    persist: bool = False
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


class ShotPlanConfirmRequest(BaseModel):
    plan_id: int = Field(validation_alias=AliasChoices("plan_id", "planId"))
    evidence_fingerprint: str = Field(default="", validation_alias=AliasChoices("evidence_fingerprint", "evidenceFingerprint"))
    confirmed: bool = False
    plan: dict[str, Any] | None = None
    workflow_profile: str = Field(default="creative_draft", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


class CreativeShotPlanPreviewRequest(BaseModel):
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    persist: bool = False
    # This is a candidate returned by a separately controlled LLM call.  The
    # endpoint never calls a provider itself; it validates and stores only a
    # draft, keeping the production path untouched.
    llm_candidate: dict[str, Any] | list[dict[str, Any]] | None = Field(default=None, validation_alias=AliasChoices("llm_candidate", "llmCandidate"))
    workflow_profile: str = Field(default="shadow", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


class CreativeShotPlanLlmDraftRequest(CreativeShotPlanPreviewRequest):
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))
    model_profile: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("model_profile", "modelProfile"))


class CreativePatchPreviewRequest(BaseModel):
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    persist: bool = False
    patch_document: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("patch_document", "patchDocument"))
    workflow_profile: str = Field(default="shadow", validation_alias=AliasChoices("workflow_profile", "workflowProfile"))


class CreativePatchLlmDraftRequest(CreativePatchPreviewRequest):
    confirmed: bool = False
    allow_external_call: bool = Field(default=False, validation_alias=AliasChoices("allow_external_call", "allowExternalCall"))
    model_profile: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("model_profile", "modelProfile"))


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _v21_runtime_summary(*, candidate: dict[str, Any], compilation: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    """Expose patch-level acceptance and contract diagnostics at the API boundary.

    Schema-level item rejections happen before the compiler sees a document;
    keeping them only in ``model_info`` makes the API appear to have accepted
    more work than it actually did.  Normalize both sources into one redacted,
    machine-readable summary for UI, audit and benchmark callers.
    """
    model_info = _dict(candidate.get("model_info"))
    schema_rejections = [item for item in (model_info.get("schema_rejections") or []) if isinstance(item, dict)]
    compiler_rejections = [item for item in (compilation.get("rejected_patches") or []) if isinstance(item, dict)]
    auxiliary = _dict(validation.get("auxiliary"))
    auxiliary_rejections = [item for item in (auxiliary.get("rejected") or []) if isinstance(item, dict)]
    rejected = [*compiler_rejections, *schema_rejections, *auxiliary_rejections]
    validation_errors = [item for item in (validation.get("errors") or []) if isinstance(item, dict)]
    authority_codes = {"DIRECTOR_FACT_OVERRIDE", "DIRECTOR_PATCH_FIELD_FORBIDDEN", "DIRECTOR_PATCH_PATH_FORBIDDEN"}
    fact_override_attempts = sum(1 for item in [*rejected, *validation_errors] if str(item.get("code") or item.get("issue_code") or "") == "DIRECTOR_FACT_OVERRIDE")
    return {
        "partial_acceptance": {
            "accepted_patch_count": int(compilation.get("accepted_patch_count") or 0),
            "rejected_patch_count": len(rejected),
            "repaired_patch_count": 0,
            "fallback_patch_count": len(rejected),
        },
        "contract_reliability": {
            "schema_pass": bool(model_info.get("schema_pass", True)),
            "contract_pass": bool(validation.get("contract_pass", True)),
            "patch_path_pass": not any(str(item.get("code") or item.get("issue_code") or "") in {"DIRECTOR_PATCH_PATH_FORBIDDEN", "DIRECTOR_FACT_OVERRIDE"} for item in [*rejected, *validation_errors]),
            "fact_override_count": 0,
            "fact_override_attempt_count": fact_override_attempts,
            "forbidden_field_attempt": bool(model_info.get("forbidden_field_attempt")),
            "forbidden_field_attempt_count": sum(1 for item in [*rejected, *validation_errors] if str(item.get("code") or item.get("issue_code") or "") in authority_codes),
            "schema_rejection_count": len(schema_rejections),
            "schema_rejections": schema_rejections,
            "auxiliary_binding_pass": not bool(auxiliary_rejections),
            "parse_success": not bool(schema_rejections),
            "repair_success": None,
            "scene_planner_success": True,
        },
        "rejected_patches": rejected,
    }


def _script_scenes(script: Any) -> list[dict[str, Any]]:
    """Return structurally valid scene objects from any persisted script shape.

    Imported/LLM scripts may still be Markdown or may contain ``scenes: null``.
    ShotPlan preview/readiness must remain read-only and fail closed with a
    useful missing-plan result instead of raising ``TypeError`` while
    iterating a null value.
    """
    if not isinstance(script, dict):
        return []
    scenes = script.get("scenes")
    if not isinstance(scenes, list):
        return []
    return [item for item in scenes if isinstance(item, dict)]


def _payload(row: ShotPlan) -> dict[str, Any]:
    return {"id": row.id, "book_id": row.book_id, "episode": row.episode, "scene_id": getattr(row, "scene_id", ""), "scene_name": row.scene_name, "revision": row.revision, "status": row.status, "schema_version": row.schema_version,
            "execution_status": row.execution_status, "quality_status": row.quality_status,
            "production_status": row.production_status, "workflow_profile": row.workflow_profile,
            "treatment_id": row.treatment_id, "blocking_id": row.blocking_id, "shots": _json(row.shots, []), "unknowns": _json(row.unknowns, []), "evidence_fingerprint": row.evidence_fingerprint, "model_info": _json(row.model_info, {}), "payload_hash": getattr(row, "payload_hash", ""), "qualification_state": getattr(row, "qualification_state", "DRAFT"), "stale_status": getattr(row, "stale_status", "UNKNOWN"), "stale_reasons": _json(getattr(row, "stale_reasons", "[]"), []), "contract_fingerprint": getattr(row, "contract_fingerprint", ""), "executability_fingerprint": getattr(row, "executability_fingerprint", ""), "continuity_fingerprint": getattr(row, "continuity_fingerprint", ""), "authority_envelope_id": getattr(row, "authority_envelope_id", None), "source_lineage": _json(getattr(row, "source_lineage", "{}"), {}), "created_at": row.created_at.isoformat() if row.created_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


def _validate_plan_candidate(raw: Any, baseline: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("ShotPlan candidate must be an object")
    unexpected = sorted(set(raw) - {"scene_name", "shots", "unknowns"})
    if unexpected:
        raise ValueError(f"candidate contains non-whitelisted fields: {', '.join(unexpected)}")
    shots = raw.get("shots", baseline["shots"])
    if not isinstance(shots, list) or any(not isinstance(item, dict) for item in shots):
        raise ValueError("shots must be a list of objects")
    baseline_ids = [str(item.get("plan_shot_id")) for item in baseline["shots"]]
    candidate_ids = [str(item.get("plan_shot_id")) for item in shots]
    if candidate_ids != baseline_ids:
        raise ValueError("shots must preserve plan_shot_id order")
    for item in shots:
        camera = item.get("camera")
        duration = item.get("duration_hint_seconds")
        if not isinstance(camera, dict) or not str(camera.get("shot_size") or "").strip() or not str(camera.get("movement") or "").strip():
            raise ValueError(f"{item.get('plan_shot_id')} must define camera.shot_size and camera.movement")
        if not isinstance(duration, (int, float)) or duration <= 0:
            raise ValueError(f"{item.get('plan_shot_id')} must define a positive duration_hint_seconds")
    unknowns = raw.get("unknowns", [])
    if not isinstance(unknowns, list) or any(not str(item).strip() for item in unknowns):
        raise ValueError("unknowns must be a list of strings")
    if unknowns:
        raise ValueError("unknowns must be empty before ShotPlan approval")
    return {"scene_name": baseline["scene_name"], "shots": shots, "unknowns": []}


@router.post("/{book_id}/episodes/{episode}/shot-plan/preview")
def preview_shot_plan(book_id: int, episode: int, req: ShotPlanPreviewRequest) -> dict[str, Any]:
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        script = resolve_script_payload(session, script_row, workflow_profile=req.workflow_profile)
        scenes = _script_scenes(script)
        scene_names = [str(item.get("name") or "未命名场景").strip() for item in scenes]
        scene_name = req.scene_name.strip() or (scene_names[0] if scene_names else "")
        if str(req.workflow_profile or "creative_draft").strip().lower() == "production" and not req.scene_id.strip():
            raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production ShotPlan requires a stable scene_id."})
        scene = next((item for item in scenes if isinstance(item, dict) and ((req.scene_id.strip() and str(item.get("scene_id") or "").strip() == req.scene_id.strip()) or (not req.scene_id.strip() and str(item.get("name") or "").strip() == scene_name))), None)
        if str(req.workflow_profile or "creative_draft").strip().lower() == "production":
            if not scene or not str(scene.get("scene_id") or "").strip():
                raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production ShotPlan requires a stable scene_id."})
            scene_id = str(scene.get("scene_id") or "").strip()
            treatment, _authority = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
            blocking, blocking_authority = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
        else:
            scene_id = str(scene.get("scene_id") or "").strip() if scene else ""
            treatment = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
            blocking = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
        if not treatment or not blocking:
            raise HTTPException(status_code=409, detail=f"ShotPlan requires approved DirectorTreatment and SceneBlocking for scene: {scene_name or '未命名场景'}")
        if str(req.workflow_profile or "creative_draft").strip().lower() == "production" and (blocking.production_status != "ready" or blocking.qualification_state != "PRODUCTION_QUALIFIED"):
            raise HTTPException(status_code=409, detail={"code": "SCENE_BLOCKING_NOT_PRODUCTION_QUALIFIED", "message": "Current SceneBlocking is not production-qualified."})
        if _json(blocking.unknowns, []):
            raise HTTPException(status_code=409, detail=f"ShotPlan is blocked by unresolved SceneBlocking unknowns: {scene_name}")
        if not scene:
            raise HTTPException(status_code=404, detail=f"Scene not found: {scene_name}")
        treatment_payload = {"scene_name": treatment.scene_name, "scene_id": getattr(treatment, "scene_id", scene_id), "character_intents": _json(treatment.character_intents, {}), "beat_map": _json(treatment.beat_map, []), "prompt_fingerprint": treatment.prompt_fingerprint}
        blocking_payload = {"scene_name": blocking.scene_name, "scene_id": getattr(blocking, "scene_id", scene_id), "participants": _json(blocking.participants, []), "unknowns": _json(blocking.unknowns, []), "evidence_fingerprint": blocking.evidence_fingerprint, "source_spatial_facts": _json(getattr(blocking, "source_spatial_facts", "[]"), []), "continuity_state": _json(getattr(blocking, "continuity_state", "{}"), {}), "asset_authority": _json(getattr(blocking, "asset_authority", "{}"), {}), "props": (scene.get("props") if isinstance(scene.get("props"), list) else []), "scene_asset_id": str(scene.get("location_id") or blocking.scene_name or ""), "screen_direction": "maintain"}
        plan = build_shot_plan(treatment=treatment_payload, blocking=blocking_payload)
        plan["scene_id"] = scene_id
        plan["schema_version"] = "shot_plan_v2"
        persisted_id = None
        if req.persist:
            existing_query = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, evidence_fingerprint=plan["evidence_fingerprint"], workflow_profile=req.workflow_profile, status="draft")
            if str(req.workflow_profile or "creative_draft").strip().lower() == "production":
                existing_query = existing_query.filter_by(scene_id=scene_id)
            existing = existing_query.first()
            if existing:
                persisted_id = existing.id
            else:
                row = ShotPlan(book_id=book_id, episode=episode, scene_id=scene_id, scene_name=scene_name, revision=1, status="draft", treatment_id=treatment.id, blocking_id=blocking.id, shots=json.dumps(plan["shots"], ensure_ascii=False), unknowns=json.dumps(plan["unknowns"], ensure_ascii=False), evidence_fingerprint=plan["evidence_fingerprint"], model_info=json.dumps(plan["model_info"], ensure_ascii=False), workflow_profile=req.workflow_profile, schema_version="shot_plan_v2" if str(req.workflow_profile).lower() == "production" else "shot_plan_v1", qualification_state="CANDIDATE" if str(req.workflow_profile).lower() == "production" else "DRAFT", stale_status="FRESH" if str(req.workflow_profile).lower() == "production" else "UNKNOWN", contract_fingerprint=(shot_plan_contract_fingerprint() if str(req.workflow_profile).lower() == "production" else ""), payload_hash=(shot_plan_payload_hash(plan) if str(req.workflow_profile).lower() == "production" else ""), source_script_ir_version_id=(script_row.current_script_ir_version_id if str(req.workflow_profile).lower() == "production" else None), source_script_ir_revision=(getattr(treatment, "source_script_ir_revision", None) if str(req.workflow_profile).lower() == "production" else None), source_script_ir_hash=(getattr(treatment, "source_script_ir_hash", "") if str(req.workflow_profile).lower() == "production" else ""), source_script_authority_fingerprint=(_text(_authority.get("script_ir", {}).get("authority_envelope_fingerprint")) if str(req.workflow_profile).lower() == "production" and isinstance(_authority, dict) else ""), treatment_authority_fingerprint=(_text(_authority.get("envelope_fingerprint")) if str(req.workflow_profile).lower() == "production" and isinstance(_authority, dict) else ""), treatment_payload_hash=(getattr(treatment, "payload_hash", "") if str(req.workflow_profile).lower() == "production" else ""), blocking_authority_fingerprint=(_text(blocking_authority.get("envelope_fingerprint")) if str(req.workflow_profile).lower() == "production" and isinstance(blocking_authority, dict) else ""), blocking_payload_hash=(_text(blocking_authority.get("payload_hash")) if str(req.workflow_profile).lower() == "production" and isinstance(blocking_authority, dict) else ""), source_fact_snapshot_id=(_text(blocking_authority.get("fact_snapshot", {}).get("id")) if str(req.workflow_profile).lower() == "production" and isinstance(blocking_authority, dict) else ""), source_fact_snapshot_revision=(blocking_authority.get("fact_snapshot", {}).get("revision") if str(req.workflow_profile).lower() == "production" and isinstance(blocking_authority, dict) else None), source_fact_snapshot_hash=(_text(blocking_authority.get("fact_snapshot", {}).get("payload_hash")) if str(req.workflow_profile).lower() == "production" and isinstance(blocking_authority, dict) else ""), source_immutable_raw_hash=(_text(blocking_authority.get("source_lineage", {}).get("immutable_source_raw_hash")) if str(req.workflow_profile).lower() == "production" and isinstance(blocking_authority, dict) else ""), source_lineage=json.dumps({"script_ir_id": script_row.current_script_ir_version_id, "treatment_id": treatment.id, "blocking_id": blocking.id}, ensure_ascii=False), created_at=datetime.now(), updated_at=datetime.now())
                session.add(row); session.commit(); session.refresh(row); persisted_id = row.id
        return {"mode": "shadow_deterministic", "llm_called": False, "mutated": bool(persisted_id), "persisted_draft_id": persisted_id, "scene_id": scene_id, "plan": plan, "treatment_id": treatment.id, "blocking_id": blocking.id, "message": "这是只读 ShotPlan 草案；尚未修改 StoryboardShot。"}


def _load_v21_director_context(session: Session, book_id: int, episode: int, scene_name: str, workflow_profile: str = "shadow") -> dict[str, Any]:
    """Load only approved evidence required by the Contract-First planner."""
    script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
    if not script_row:
        raise HTTPException(status_code=404, detail="No script found for this episode.")
    script = resolve_script_payload(session, script_row, workflow_profile=workflow_profile)
    scenes = _script_scenes(script)
    resolved_scene_name = scene_name.strip() or (str(scenes[0].get("name") or "未命名场景") if scenes else "")
    scene = next((item for item in scenes if isinstance(item, dict) and str(item.get("name") or "").strip() == resolved_scene_name), None)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene not found: {resolved_scene_name}")
    scene_id = str(scene.get("scene_id") or "").strip()
    if str(workflow_profile or "shadow").strip().lower() == "production":
        if not scene_id:
            raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Production ShotPlan requires a stable scene_id."})
        treatment, _authority = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
        blocking, blocking_authority = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
    else:
        treatment = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_name=resolved_scene_name, status="approved").order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
        blocking = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=resolved_scene_name, status="approved").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
    if not treatment or not blocking:
        raise HTTPException(status_code=409, detail=f"Contract-First planner requires approved DirectorTreatment and SceneBlocking for scene: {resolved_scene_name or '未命名场景'}")
    if _json(blocking.unknowns, []):
        raise HTTPException(status_code=409, detail=f"Contract-First planner blocked by unresolved SceneBlocking unknowns: {resolved_scene_name}")
    treatment_payload = {
        "scene_name": treatment.scene_name,
        "scene_id": getattr(treatment, "scene_id", ""),
        "character_intents": _json(treatment.character_intents, {}),
        "beat_map": _json(treatment.beat_map, []),
        "prompt_fingerprint": treatment.prompt_fingerprint,
        "status": treatment.status,
        "visual_strategy": treatment.visual_strategy,
    }
    blocking_payload = {
        "scene_name": blocking.scene_name,
        "scene_id": getattr(blocking, "scene_id", ""),
        "participants": _json(blocking.participants, []),
        "scene_asset_id": str(scene.get("location_id") or "").strip(),
        "props": scene.get("props") if isinstance(scene.get("props"), list) else [],
        "unknowns": _json(blocking.unknowns, []),
        "source_spatial_facts": _json(getattr(blocking, "source_spatial_facts", "[]"), []),
        "evidence_fingerprint": blocking.evidence_fingerprint,
        "status": blocking.status,
    }
    baseline = build_shot_plan(treatment=treatment_payload, blocking=blocking_payload)
    # Contract-First must carry the same approved ScriptIR/fact/asset evidence
    # that qualified SceneBlocking used.  Omitting these projections would
    # leave the planner with an apparently valid contract whose immutable
    # boundary is weaker than the upstream approval boundary.
    scene_canonical: dict[str, Any] = {}
    location = session.query(VisualLocation).filter(
        VisualLocation.book_id == book_id,
        VisualLocation.name == resolved_scene_name,
    ).order_by(VisualLocation.id.desc()).first()
    if location:
        scene_canonical = {
            "name": location.name,
            "canonical_facts": _json(location.canonical_facts, {}),
            "state_variants": _json(location.state_variants, {}),
            "look_profile": _json(location.look_profile, {}),
            "board_spec": _json(location.board_spec, {}),
            "key_props": _json(location.key_props, []),
        }
    fact_snapshot: dict[str, Any] = {}
    if str(workflow_profile or "shadow").strip().lower() == "production":
        bound_fact = blocking_authority.get("fact_snapshot") if isinstance(blocking_authority, dict) else {}
        fact_row = session.query(FactSnapshot).filter_by(id=int(bound_fact.get("id")), book_id=book_id, episode=episode).first() if isinstance(bound_fact, dict) and str(bound_fact.get("id") or "").isdigit() else None
    else:
        fact_row = session.query(FactSnapshot).filter_by(book_id=book_id, episode=episode, status="confirmed").order_by(FactSnapshot.revision.desc(), FactSnapshot.id.desc()).first()
    if fact_row:
        fact_snapshot = {"snapshot_id": str(fact_row.id), "revision": fact_row.revision, "source_fingerprint": fact_row.source_fingerprint, "payload_hash": fact_row.payload_hash, "records": _json(fact_row.records_json, [])}
    asset_bindings: dict[str, Any] = {}
    location_id = str(scene.get("location_id") or "").strip()
    if location_id:
        asset_bindings["scene"] = location_id
    character_ids = []
    for raw in scene.get("participants", []) if isinstance(scene.get("participants"), list) else []:
        value = raw.get("character_id") or raw.get("id") if isinstance(raw, dict) else raw
        value = str(value or "").strip()
        if value and value not in character_ids:
            character_ids.append(value)
    if character_ids:
        asset_bindings["characters"] = character_ids
    prop_ids = []
    for raw in scene.get("props", []) if isinstance(scene.get("props"), list) else []:
        value = raw.get("prop_id") or raw.get("id") if isinstance(raw, dict) else raw
        value = str(value or "").strip()
        if value and value not in prop_ids:
            prop_ids.append(value)
    if prop_ids:
        asset_bindings["props"] = prop_ids
    contract = build_director_creative_contract(
        fact_snapshot=fact_snapshot,
        script_scene=scene,
        treatment=treatment_payload,
        blocking=blocking_payload,
        structural_shot_plan=baseline,
        scene_canonical=scene_canonical,
        asset_bindings=asset_bindings,
    )
    try:
        strategy = build_scene_directing_strategy(treatment=treatment_payload, contract=contract, structural_shot_plan=baseline)
    except SceneDirectingStrategyError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    return {
        "scene_name": resolved_scene_name,
        "scene": scene,
        "treatment": treatment,
        "blocking": blocking,
        "treatment_payload": treatment_payload,
        "blocking_payload": blocking_payload,
        "fact_snapshot": fact_snapshot,
        "scene_canonical": scene_canonical,
        "asset_bindings": asset_bindings,
        "baseline": baseline,
        "contract": contract,
        "strategy": strategy,
    }


def _persist_v21_patch_draft(book_id: int, episode: int, context: dict[str, Any], candidate: dict[str, Any], *, request_fingerprint: str = "") -> tuple[int | None, bool]:
    """Persist a reviewable patch draft without creating an approved version."""
    model_info = {
        **_dict(candidate.get("model_info")),
        "v21_patch_document": candidate.get("patch_document", {}),
        "contract_fingerprint": context["contract"].get("contract_fingerprint", ""),
        "strategy_fingerprint": context["strategy"].get("strategy_fingerprint", ""),
        "request_fingerprint": request_fingerprint,
    }
    with Session() as session:
        if request_fingerprint:
            drafts = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_name=context["scene_name"], status="draft").order_by(ShotPlan.id.desc()).all()
            for row in drafts:
                info = _json(row.model_info, {})
                if isinstance(info, dict) and info.get("request_fingerprint") == request_fingerprint:
                    return row.id, True
        row = ShotPlan(
            book_id=book_id,
            episode=episode,
            scene_name=context["scene_name"],
            revision=1,
            status="draft",
            schema_version="shot_plan_v2_1_patch_candidate",
            quality_status="creative_patch_candidate",
            production_status="blocked",
            treatment_id=context["treatment"].id,
            blocking_id=context["blocking"].id,
            shots=json.dumps(context["baseline"].get("shots", []), ensure_ascii=False),
            unknowns=json.dumps(context["baseline"].get("unknowns", []), ensure_ascii=False),
            evidence_fingerprint=str(context["baseline"].get("evidence_fingerprint") or ""),
            model_info=json.dumps(model_info, ensure_ascii=False),
            workflow_profile="shadow",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id, False


@router.post("/{book_id}/episodes/{episode}/shot-plan/creative-patch-preview")
def preview_creative_patch(book_id: int, episode: int, req: CreativePatchPreviewRequest) -> dict[str, Any]:
    """Preview a V2.1 CreativePatch document without creating a ShotPlan version."""
    with Session() as session:
        context = _load_v21_director_context(session, book_id, episode, req.scene_name, req.workflow_profile)
        candidate = build_creative_patch_candidate(
            structural_shot_plan=context["baseline"],
            contract=context["contract"],
            strategy=context["strategy"],
            llm_output=req.patch_document,
            mode="shadow",
        )
        patch_document = candidate["patch_document"]
        try:
            compilation = compile_creative_patches(context["baseline"], patch_document, context["contract"], allow_partial=True)
            validation = validate_compiled_patch_result(compilation, context["baseline"], context["contract"], treatment=context["treatment_payload"], blocking=context["blocking_payload"])
        except (DirectorPatchCompileError, ValueError) as exc:
            raise HTTPException(status_code=409, detail={"code": getattr(exc, "code", "DIRECTOR_PATCH_INVALID"), "message": str(exc)}) from exc
        persisted_id = None
        deduplicated = False
        if req.persist:
            preview_fingerprint = f"{context['contract'].get('contract_fingerprint', '')}:{candidate['patch_document'].get('patch_fingerprint', '')}"
            persisted_id, deduplicated = _persist_v21_patch_draft(book_id, episode, context, candidate, request_fingerprint=preview_fingerprint)
        runtime_summary = _v21_runtime_summary(candidate=candidate, compilation=compilation, validation=validation)
        return {
            "mode": candidate.get("director_mode"),
            "llm_called": bool(candidate.get("model_info", {}).get("llm_called")),
            "mutated": bool(persisted_id),
            "persisted_draft_id": persisted_id,
            "deduplicated": deduplicated,
            "candidate": candidate,
            "compiled": compilation,
            "validation": validation,
            "contract": context["contract"],
            "strategy": context["strategy"],
            "treatment_id": context["treatment"].id,
            "blocking_id": context["blocking"].id,
            "requires_approval": True,
            **runtime_summary,
            "message": "Contract-First 仅生成 CreativePatch 候选；尚未写入 ShotPlan 或触发生产。",
        }


@router.post("/{book_id}/episodes/{episode}/shot-plan/creative-patch-llm-draft")
def generate_creative_patch_llm_draft(book_id: int, episode: int, req: CreativePatchLlmDraftRequest) -> dict[str, Any]:
    """Call the configured LLM only after explicit confirmation, saving no version."""
    if not (req.confirmed and req.allow_external_call):
        raise HTTPException(status_code=409, detail="Calling the Contract-First CreativePatch LLM requires confirmed=true and allowExternalCall=true.")
    with Session() as session:
        context = _load_v21_director_context(session, book_id, episode, req.scene_name, req.workflow_profile)
    prompt_bundle = build_director_patch_prompt(
        contract=context["contract"],
        strategy=context["strategy"],
        structural_shot_plan={
            "scene_name": context["baseline"].get("scene_name"),
            "shots": context["baseline"].get("shots", []),
            "unknowns": context["baseline"].get("unknowns", []),
        },
        model_profile=req.model_profile,
        stage="director_patch_planner",
    )
    system_prompt = prompt_bundle["system_prompt"]
    user_prompt = prompt_bundle["user_prompt"]
    request_fingerprint = prompt_bundle["request_fingerprint"]
    audit_records: list[dict[str, Any]] = []
    try:
        raw = llm_client.call_llm_json(
            user_prompt,
            system=system_prompt,
            model_profile=req.model_profile,
            required_keys={"schema_version", "patches", "auxiliary_shot_proposals"},
            estimated_tokens=5000,
            audit_callback=audit_records.append,
            audit_extra={
                "stage": "director_patch_planner",
                "book_id": book_id,
                "episode": episode,
                "scene_name": context["scene_name"],
                "prompt_prefix_fingerprint": prompt_bundle["prompt_prefix_fingerprint"],
                "prompt_request_fingerprint": request_fingerprint,
                "system_prompt_hash": prompt_bundle["system_prompt_hash"],
                "user_prompt_hash": prompt_bundle["user_prompt_hash"],
            },
        )
        candidate = build_creative_patch_candidate(structural_shot_plan=context["baseline"], contract=context["contract"], strategy=context["strategy"], llm_output=raw, mode="shadow")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Contract-First CreativePatch LLM draft failed: {str(exc)[:500]}") from exc
    patch_document = candidate["patch_document"]
    compilation = compile_creative_patches(context["baseline"], patch_document, context["contract"], allow_partial=True)
    validation = validate_compiled_patch_result(compilation, context["baseline"], context["contract"], treatment=context["treatment_payload"], blocking=context["blocking_payload"])
    runtime_summary = _v21_runtime_summary(candidate=candidate, compilation=compilation, validation=validation)
    candidate["model_info"] = {
        **_dict(candidate.get("model_info")),
        "request_fingerprint": request_fingerprint,
        "system_prompt_hash": prompt_bundle["system_prompt_hash"],
        "user_prompt_hash": prompt_bundle["user_prompt_hash"],
        "prompt_prefix_fingerprint": prompt_bundle["prompt_prefix_fingerprint"],
        "model_snapshot": prompt_bundle["model_snapshot"],
        "llm_called": True,
        "llm_usage": summarize_audit_records(audit_records),
    }
    persisted_id = None
    deduplicated = False
    if req.persist:
        persisted_id, deduplicated = _persist_v21_patch_draft(book_id, episode, context, candidate, request_fingerprint=request_fingerprint)
    return {
        "mode": candidate.get("director_mode"),
        "llm_called": True,
        "mutated": bool(persisted_id),
        "persisted_draft_id": persisted_id,
        "deduplicated": deduplicated,
        "candidate": candidate,
        "compiled": compilation,
        "validation": validation,
        "contract": context["contract"],
        "strategy": context["strategy"],
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "system_prompt_hash": prompt_bundle["system_prompt_hash"],
        "user_prompt_hash": prompt_bundle["user_prompt_hash"],
        "prompt_prefix_fingerprint": prompt_bundle["prompt_prefix_fingerprint"],
        "model_snapshot": prompt_bundle["model_snapshot"],
        "requires_approval": True,
        **runtime_summary,
        "request_fingerprint": request_fingerprint,
        "treatment_id": context["treatment"].id,
        "blocking_id": context["blocking"].id,
        "message": "真实 LLM 只生成 CreativePatch 草案；尚未写入 Prompt/ShotPlan 版本或触发生产。",
    }


@router.post("/{book_id}/episodes/{episode}/shot-plan/creative-preview")
def preview_creative_shot_plan(book_id: int, episode: int, req: CreativeShotPlanPreviewRequest) -> dict[str, Any]:
    """Build a controlled creative candidate in shadow/benchmark mode.

    No external model is invoked by this route.  ``llm_candidate`` is an
    optional already-returned proposal and is subject to the same immutable
    evidence checks as every other planner caller.
    """
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        script = resolve_script_payload(session, script_row, workflow_profile=req.workflow_profile)
        scenes = _script_scenes(script)
        scene_name = req.scene_name.strip() or (str(scenes[0].get("name") or "未命名场景") if scenes else "")
        treatment = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
        blocking = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
        if not treatment or not blocking:
            raise HTTPException(status_code=409, detail=f"Creative ShotPlan requires approved DirectorTreatment and SceneBlocking for scene: {scene_name or '未命名场景'}")
        if _json(blocking.unknowns, []):
            raise HTTPException(status_code=409, detail=f"Creative ShotPlan blocked by unresolved SceneBlocking unknowns: {scene_name}")
        treatment_payload = {"scene_name": treatment.scene_name, "scene_id": getattr(treatment, "scene_id", ""), "character_intents": _json(treatment.character_intents, {}), "beat_map": _json(treatment.beat_map, []), "prompt_fingerprint": treatment.prompt_fingerprint, "status": treatment.status}
        blocking_payload = {"scene_name": blocking.scene_name, "scene_id": getattr(blocking, "scene_id", ""), "participants": _json(blocking.participants, []), "unknowns": _json(blocking.unknowns, []), "source_spatial_facts": _json(getattr(blocking, "source_spatial_facts", "[]"), []), "evidence_fingerprint": blocking.evidence_fingerprint, "status": blocking.status, "qualification_state": getattr(blocking, "qualification_state", ""), "authority_envelope": blocking_authority if str(req.workflow_profile or "").strip().lower() == "production" else {}}
        baseline = build_shot_plan(treatment=treatment_payload, blocking=blocking_payload)
        try:
            candidate = build_creative_shot_plan_candidate(structural_shot_plan=baseline, treatment=treatment_payload, blocking=blocking_payload, llm_output=req.llm_candidate, mode="shadow")
        except DirectorFactOverride as exc:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_FACT_OVERRIDE", "message": str(exc)}) from exc
        except DirectorCreativeError as exc:
            raise HTTPException(status_code=409, detail={"code": "DIRECTOR_CREATIVE_INVALID", "message": str(exc)}) from exc
        persisted_id = None
        if req.persist:
            existing = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, evidence_fingerprint=candidate.get("evidence_fingerprint", "")).first()
            if existing:
                persisted_id = existing.id
            else:
                row = ShotPlan(book_id=book_id, episode=episode, scene_name=scene_name, revision=1, status="draft", quality_status="creative_candidate", production_status="blocked", treatment_id=treatment.id, blocking_id=blocking.id, shots=json.dumps(candidate["shots"], ensure_ascii=False), unknowns=json.dumps(candidate.get("unknowns", []), ensure_ascii=False), evidence_fingerprint=candidate.get("evidence_fingerprint", ""), model_info=json.dumps(candidate.get("model_info", {}), ensure_ascii=False), workflow_profile="shadow", created_at=datetime.now(), updated_at=datetime.now())
                session.add(row); session.commit(); session.refresh(row); persisted_id = row.id
        quality = score_director_quality(candidate, treatment=treatment_payload, blocking=blocking_payload)
        return {"mode": candidate.get("director_mode", "creative_planner_shadow"), "llm_called": bool(candidate.get("model_info", {}).get("llm_called")), "mutated": bool(persisted_id), "persisted_draft_id": persisted_id, "candidate": candidate, "quality": quality, "repair_options": build_director_repair_options(candidate, quality.get("issues", [])), "treatment_id": treatment.id, "blocking_id": blocking.id, "message": "这是导演创意候选草案；尚未批准 ShotPlan，也不会触发生产。"}


@router.post("/{book_id}/episodes/{episode}/shot-plan/creative-llm-draft")
def generate_creative_shot_plan_llm_draft(book_id: int, episode: int, req: CreativeShotPlanLlmDraftRequest) -> dict[str, Any]:
    """Generate a reviewable creative planner candidate behind an explicit gate.

    This route is intentionally separate from ``creative-preview``.  Without
    both flags it fails closed and never calls ``call_llm_json``; with both
    flags it still creates only a draft and never approves a ShotPlan or
    triggers storyboard/media generation.
    """
    if not (req.confirmed and req.allow_external_call):
        raise HTTPException(status_code=409, detail="Calling the Director Creative Planner LLM requires confirmed=true and allowExternalCall=true.")
    preview = preview_creative_shot_plan(book_id, episode, CreativeShotPlanPreviewRequest(scene_name=req.scene_name, persist=False, workflow_profile=req.workflow_profile))
    candidate = preview.get("candidate") if isinstance(preview.get("candidate"), dict) else {}
    evidence = {
        "protocol_version": "director-quality-v2-controlled-planner-2026-09",
        "scene_name": candidate.get("scene_name"),
        "structural_plan_fingerprint": candidate.get("structural_plan_fingerprint"),
        "shots": candidate.get("shots", []),
        "creative_fields_only": True,
        "constraints": ["preserve facts", "preserve beat order", "preserve locked assets", "no production side effects"],
    }
    system_prompt = "你是受事实边界约束的导演创意 ShotPlan 编译器。只输出 JSON object；只能修改 camera、composition、performance_direction、edit、information_strategy、why_this_shot 等导演创意字段；不得修改剧情事实、beat 顺序、资产绑定、首尾状态或连续性合同。"
    user_prompt = "冻结证据包如下，请给出可供人工审核的 ShotPlan 创意候选，不要执行任何生产操作：\n" + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    request_fingerprint = llm_request_fingerprint(system=system_prompt, user=user_prompt, profile=req.model_profile, extra={"book_id": book_id, "episode": episode, "scene_name": candidate.get("scene_name")})
    # Persisted draft rows provide durable de-duplication for the same frozen
    # evidence/model request.  A repeated request with persist=true returns
    # the existing candidate without another billable call.
    if req.persist:
        with Session() as session:
            rows = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_name=str(candidate.get("scene_name") or ""), status="draft").order_by(ShotPlan.id.desc()).all()
            for row in rows:
                info = _json(row.model_info, {})
                if isinstance(info, dict) and info.get("request_fingerprint") == request_fingerprint:
                    cached_candidate = {"scene_name": row.scene_name, "shots": _json(row.shots, []), "unknowns": _json(row.unknowns, []), "status": "ready_for_review", "director_mode": "creative_planner_llm", "model_info": info, "evidence_fingerprint": row.evidence_fingerprint}
                    return {"mode": "creative_planner_llm", "llm_called": False, "deduplicated": True, "mutated": False, "persisted_draft_id": row.id, "candidate": cached_candidate, "quality": score_director_quality(cached_candidate), "system_prompt": system_prompt, "user_prompt": user_prompt, "requires_approval": True, "treatment_id": row.treatment_id, "blocking_id": row.blocking_id, "message": "相同证据包已有未过期草案，已复用而未重复调用模型。"}
    audit_records: list[dict[str, Any]] = []
    try:
        raw = llm_client.call_llm_json(user_prompt, system=system_prompt, model_profile=req.model_profile, required_keys={"shots"}, estimated_tokens=5000, audit_callback=audit_records.append, audit_extra={"stage": "director_creative_planner", "book_id": book_id, "episode": episode, "scene_name": str(candidate.get("scene_name") or "")})
        candidate = build_creative_shot_plan_candidate(structural_shot_plan={"scene_name": candidate.get("scene_name"), "shots": candidate.get("shots", []), "unknowns": candidate.get("unknowns", [])}, llm_output=raw, mode="shadow")
    except DirectorFactOverride as exc:
        raise HTTPException(status_code=409, detail={"code": "DIRECTOR_FACT_OVERRIDE", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Director Creative Planner LLM draft failed: {str(exc)[:500]}") from exc
    quality = score_director_quality(candidate)
    candidate["model_info"] = {**(_json(candidate.get("model_info"), {}) if isinstance(candidate.get("model_info"), str) else (candidate.get("model_info") if isinstance(candidate.get("model_info"), dict) else {})), "request_fingerprint": request_fingerprint, "llm_called": True, "llm_usage": summarize_audit_records(audit_records)}
    persisted_id = None
    if req.persist:
        with Session() as session:
            row = ShotPlan(book_id=book_id, episode=episode, scene_name=str(candidate.get("scene_name") or ""), revision=1, status="draft", quality_status="creative_candidate", production_status="blocked", treatment_id=preview.get("treatment_id"), blocking_id=preview.get("blocking_id"), shots=json.dumps(candidate.get("shots", []), ensure_ascii=False), unknowns=json.dumps(candidate.get("unknowns", []), ensure_ascii=False), evidence_fingerprint=str(candidate.get("evidence_fingerprint") or ""), model_info=json.dumps(candidate.get("model_info", {}), ensure_ascii=False), workflow_profile="shadow", created_at=datetime.now(), updated_at=datetime.now())
            session.add(row); session.commit(); session.refresh(row); persisted_id = row.id
    return {"mode": "creative_planner_llm", "llm_called": True, "deduplicated": False, "mutated": bool(persisted_id), "persisted_draft_id": persisted_id, "candidate": candidate, "quality": quality, "system_prompt": system_prompt, "user_prompt": user_prompt, "requires_approval": True, "treatment_id": preview.get("treatment_id"), "blocking_id": preview.get("blocking_id"), "message": "LLM 仅生成导演创意候选草案；尚未写入批准版本或触发生产。"}


@router.get("/{book_id}/episodes/{episode}/shot-plans")
def list_shot_plans(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        rows = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode).order_by(ShotPlan.scene_name, ShotPlan.revision.desc(), ShotPlan.id.desc()).all()
    return {"items": [_payload(row) for row in rows]}


@router.get("/{book_id}/episodes/{episode}/shot-plans/{plan_id}/diff")
def shot_plan_diff(book_id: int, episode: int, plan_id: int) -> dict[str, Any]:
    """Replay approved plan intent against generated storyboard output."""
    with Session() as session:
        plan = session.query(ShotPlan).filter_by(id=plan_id, book_id=book_id, episode=episode).first()
        if not plan:
            raise HTTPException(status_code=404, detail="ShotPlan not found.")
        shots = session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_name=plan.scene_name).order_by(StoryboardShot.shot_id).all()
    plan_items = _json(plan.shots, [])
    generated_by_ref: dict[str, dict[str, Any]] = {}
    for shot in shots:
        meta = _json(shot.meta_info, {})
        ref = meta.get("shot_plan_ref") if isinstance(meta, dict) else None
        ref_id = str(ref.get("plan_shot_id") or "") if isinstance(ref, dict) else ""
        if ref_id:
            generated_by_ref[ref_id] = {"shot_id": shot.shot_id, "camera_angle": shot.camera_angle, "camera_movement": shot.camera_movement, "duration": shot.duration, "dialogue": shot.dialogue or "", "visual_prompt_static": shot.visual_prompt_static or "", "visual_prompt_motion": shot.visual_prompt_motion or ""}
    items = []
    for item in plan_items if isinstance(plan_items, list) else []:
        if not isinstance(item, dict):
            continue
        plan_shot_id = str(item.get("plan_shot_id") or "")
        generated = generated_by_ref.get(plan_shot_id)
        items.append({"plan_shot_id": plan_shot_id, "beat_id": item.get("beat_id"), "purpose": item.get("purpose"), "plan": item, "generated": generated, "status": "matched" if generated else "missing_generated_shot"})
    return {"plan_id": plan.id, "scene_name": plan.scene_name, "plan_revision": plan.revision, "items": items, "unmapped_generated_shot_count": max(0, len(shots) - len(generated_by_ref)), "mutated": False}


@router.post("/{book_id}/episodes/{episode}/shot-plan/confirm")
def confirm_shot_plan(book_id: int, episode: int, req: ShotPlanConfirmRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="ShotPlan approval requires confirmed=true.")
    is_production = str(req.workflow_profile or "creative_draft").strip().lower() == "production"
    with Session() as session:
        draft = session.query(ShotPlan).filter_by(id=req.plan_id, book_id=book_id, episode=episode).first()
        if not draft or draft.status != "draft":
            raise HTTPException(status_code=409, detail="ShotPlan draft not found or already finalized.")
        if is_production:
            scene_id = _text(getattr(draft, "scene_id", ""))
            treatment, treatment_authority = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
            blocking, blocking_authority = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
            if treatment.id != draft.treatment_id or blocking.id != draft.blocking_id:
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_UPSTREAM_POINTER_CHANGED", "message": "ShotPlan draft references a non-current Treatment or SceneBlocking."})
            script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
            script_ir = session.query(ScriptIRVersion).filter_by(id=getattr(script_row, "current_script_ir_version_id", None), book_id=book_id, episode=episode).first() if script_row else None
            if not script_ir:
                raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_POINTER_MISSING", "message": "Production ShotPlan requires the current production-qualified ScriptIR."})
            script_ir_authority = _json(getattr(script_ir, "authority_envelope_json", "{}"), {})
            if not isinstance(script_ir_authority, dict) or not script_ir_authority.get("envelope_fingerprint"):
                raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_ENVELOPE_INVALID", "message": "Current ScriptIR authority envelope is missing."})
        else:
            treatment = session.query(DirectorTreatment).filter_by(id=draft.treatment_id, book_id=book_id, episode=episode, status="approved").first()
            blocking = session.query(SceneBlocking).filter_by(id=draft.blocking_id, book_id=book_id, episode=episode, status="approved").first()
        if not treatment or not blocking:
            raise HTTPException(status_code=409, detail="ShotPlan upstream evidence is no longer approved.")
        scene_name = draft.scene_name
    preview = preview_shot_plan(book_id, episode, ShotPlanPreviewRequest(scene_name=scene_name, scene_id=str(getattr(draft, "scene_id", "") or ""), workflow_profile=req.workflow_profile))
    baseline = preview["plan"]
    if req.evidence_fingerprint and req.evidence_fingerprint != draft.evidence_fingerprint:
        raise HTTPException(status_code=409, detail="ShotPlan evidence fingerprint does not match.")
    if baseline["evidence_fingerprint"] != draft.evidence_fingerprint:
        with Session() as session:
            stale = session.query(ShotPlan).filter_by(id=req.plan_id, book_id=book_id).first()
            if stale and stale.status == "draft":
                stale.status = "superseded"; stale.updated_at = datetime.now(); session.commit()
        raise HTTPException(status_code=409, detail="ShotPlan evidence changed; draft is stale and must be regenerated.")
    try:
        raw_candidate = req.plan or {field: baseline[field] for field in ("scene_id", "scene_name", "schema_version", "shots", "unknowns")}
        if is_production:
            candidate, continuity, executability = validate_shot_plan_candidate_authority(
                raw_candidate, baseline, scene_entry=_json(getattr(blocking, "continuity_state", "{}"), {})
            )
        else:
            candidate = _validate_plan_candidate(raw_candidate, baseline)
            continuity = {"status": "pass", "errors": [], "warnings": [], "fingerprint": ""}
            executability = preflight_shot_plan(candidate["shots"])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_CANDIDATE_INVALID", "message": str(exc)}) from exc
    if executability["status"] == "blocked":
        raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_EXECUTABILITY_BLOCKED", "executability": executability, "repair_plan": build_executability_repair_plan(executability)})
    if is_production and continuity.get("status") != "pass":
        raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_CONTINUITY_BLOCKED", "continuity": continuity})
    with Session() as session:
        draft = session.query(ShotPlan).filter_by(id=req.plan_id, book_id=book_id, episode=episode).first()
        if not draft or draft.status != "draft":
            raise HTTPException(status_code=409, detail="ShotPlan draft not found or already finalized.")
        now = datetime.now()
        if not is_production:
            previous = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(ShotPlan.revision.desc(), ShotPlan.id.desc()).first()
            if previous:
                previous.status = "superseded"; previous.updated_at = now
            anchor = {"previous_plan_id": previous.id if previous else None, "previous_revision": previous.revision if previous else None}
            row = ShotPlan(book_id=book_id, episode=episode, scene_id=_text(getattr(draft, "scene_id", "")), scene_name=scene_name, revision=(previous.revision + 1 if previous else 1), status="approved", treatment_id=draft.treatment_id, blocking_id=draft.blocking_id, shots=json.dumps(candidate["shots"], ensure_ascii=False), unknowns="[]", evidence_fingerprint=draft.evidence_fingerprint, model_info=json.dumps({"mode": "confirmed_human_candidate", "rollback_anchor": anchor, "confirmed_at": now.isoformat()}, ensure_ascii=False), workflow_profile=req.workflow_profile, created_at=now, updated_at=now)
            session.add(row); draft.status = "superseded"; draft.updated_at = now; session.commit(); session.refresh(row)
            return {"approved": True, "mutated": True, "shot_plan": _payload(row), "rollback_anchor": anchor, "storyboard_generation_allowed": True}

        # Production activation has exactly one selection mechanism: the
        # scene pointer.  Legacy approved rows without a pointer are never
        # silently promoted or treated as "latest".
        scene_id = _text(getattr(draft, "scene_id", ""))
        # Re-resolve all upstream pointers inside the write transaction.  The
        # preview/validation session above is advisory; an upstream approval
        # changing between preview and confirm must invalidate this draft.
        treatment, treatment_authority = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
        blocking, blocking_authority = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        script_ir = session.query(ScriptIRVersion).filter_by(id=getattr(script_row, "current_script_ir_version_id", None), book_id=book_id, episode=episode).first() if script_row else None
        if not script_ir:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_POINTER_MISSING", "message": "Current ScriptIR changed; regenerate ShotPlan."})
        script_ir_authority = _json(getattr(script_ir, "authority_envelope_json", "{}"), {})
        if treatment.id != draft.treatment_id or blocking.id != draft.blocking_id or not isinstance(script_ir_authority, dict) or not script_ir_authority.get("envelope_fingerprint"):
            raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_UPSTREAM_POINTER_CHANGED", "message": "Upstream authority changed; regenerate ShotPlan."})
        current_pointer = session.query(ShotPlanPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
        previous = None
        if current_pointer:
            previous = session.query(ShotPlan).filter_by(id=current_pointer.shot_plan_id, book_id=book_id, episode=episode, scene_id=scene_id).first()
            if not previous or previous.status != "approved":
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_POINTER_INVALID", "message": "Current ShotPlan pointer does not resolve to an approved row."})
        else:
            legacy_approved = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_id=scene_id, status="approved").first()
            if legacy_approved:
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_POINTER_MISSING", "message": "Approved ShotPlan exists without a current pointer; explicit migration is required."})
        revision = (previous.revision + 1) if previous else 1
        anchor = {"previous_plan_id": previous.id if previous else None, "previous_revision": previous.revision if previous else None}
        row = ShotPlan(book_id=book_id, episode=episode, scene_id=scene_id, scene_name=scene_name, revision=revision, status="approved", schema_version="shot_plan_v2", execution_status="ready", quality_status="qualified", production_status="ready", workflow_profile="production", treatment_id=treatment.id, blocking_id=blocking.id, shots=json.dumps(candidate["shots"], ensure_ascii=False), unknowns="[]", evidence_fingerprint=draft.evidence_fingerprint, model_info=json.dumps({"mode": "confirmed_human_candidate", "rollback_anchor": anchor, "confirmed_at": now.isoformat(), "provider_calls": 0}, ensure_ascii=False), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", contract_fingerprint=shot_plan_contract_fingerprint(), executability_fingerprint=executability.get("fingerprint", ""), continuity_fingerprint=continuity.get("fingerprint", ""), source_script_ir_version_id=script_ir.id, source_script_ir_revision=script_ir.revision, source_script_ir_hash=_text(script_ir.payload_hash), source_script_authority_fingerprint=_text(script_ir_authority.get("envelope_fingerprint")), treatment_authority_fingerprint=_text(treatment_authority.get("envelope_fingerprint")), treatment_payload_hash=_text(getattr(treatment, "payload_hash", "")), blocking_authority_fingerprint=_text(blocking_authority.get("envelope_fingerprint")), blocking_payload_hash=_text(blocking_authority.get("payload_hash", "")), source_fact_snapshot_id=_text(blocking_authority.get("fact_snapshot", {}).get("id")), source_fact_snapshot_revision=blocking_authority.get("fact_snapshot", {}).get("revision"), source_fact_snapshot_hash=_text(blocking_authority.get("fact_snapshot", {}).get("payload_hash")), source_immutable_raw_hash=_text(blocking_authority.get("source_lineage", {}).get("immutable_source_raw_hash")), source_lineage=json.dumps({"script_ir_id": script_ir.id, "treatment_id": treatment.id, "blocking_id": blocking.id}, ensure_ascii=False), created_at=now, updated_at=now)
        session.add(row); session.flush()
        row.payload_hash = shot_plan_payload_hash(candidate)
        envelope = build_shot_plan_authority_envelope(plan=candidate, book_id=book_id, episode=episode, plan_id=row.id, plan_revision=row.revision, script_ir=script_ir, script_ir_envelope=script_ir_authority, treatment=treatment, treatment_envelope=treatment_authority, blocking=blocking, blocking_envelope=blocking_authority, executability=executability, continuity=continuity)
        authority = ShotPlanAuthority(book_id=book_id, episode=episode, scene_id=scene_id, shot_plan_id=row.id, plan_revision=row.revision, payload_hash=row.payload_hash, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PRODUCTION_QUALIFIED", stale_status="FRESH", stale_reasons="[]", approved_at=now, activated_at=now)
        session.add(authority); session.flush(); row.authority_envelope_id = authority.id
        if previous:
            previous.status = "superseded"; previous.updated_at = now
        if current_pointer:
            current_pointer.shot_plan_id = row.id; current_pointer.plan_revision = row.revision; current_pointer.authority_envelope_fingerprint = envelope["envelope_fingerprint"]; current_pointer.qualification_state = "PRODUCTION_QUALIFIED"; current_pointer.updated_at = now
        else:
            session.add(ShotPlanPointer(book_id=book_id, episode=episode, scene_id=scene_id, shot_plan_id=row.id, plan_revision=row.revision, authority_envelope_fingerprint=envelope["envelope_fingerprint"], qualification_state="PRODUCTION_QUALIFIED", created_at=now, updated_at=now))
        draft.status = "superseded"; draft.updated_at = now
        session.commit(); session.refresh(row)
        return {"approved": True, "mutated": True, "shot_plan": _payload(row), "authority_envelope": envelope, "rollback_anchor": anchor, "storyboard_generation_allowed": True, "production_status": "ready", "provider_calls": 0}


@router.get("/{book_id}/episodes/{episode}/storyboard/readiness")
def storyboard_readiness(book_id: int, episode: int, workflow_profile: str = "creative_draft") -> dict[str, Any]:
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
    if not script_row:
        raise HTTPException(status_code=404, detail="No script found for this episode.")
    is_production = str(workflow_profile or "creative_draft").strip().lower() == "production"
    with Session() as session:
        script = resolve_script_payload(session, script_row, workflow_profile="production" if is_production else workflow_profile)
        scenes = _script_scenes(script)
        issues: list[Any] = []
        current_plans: list[ShotPlan] = []
        if is_production:
            for scene in scenes:
                scene_id = _text(scene.get("scene_id"))
                scene_name = _text(scene.get("name") or "未命名场景")
                if not scene_id:
                    issues.append({"code": "SCENE_ID_REQUIRED", "scene_name": scene_name})
                    continue
                try:
                    row, _ = resolve_current_authoritative_shot_plan(session, book_id=book_id, episode=episode, scene_id=scene_id)
                    current_plans.append(row)
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "SHOT_PLAN_NOT_READY", "message": str(exc.detail)}
                    issues.append({"scene_id": scene_id, "scene_name": scene_name, **detail})
            return {"allowed": not issues, "status": "ready" if not issues else "blocked", "blocking_issues": issues, "approved_plan_count": len(current_plans), "scene_count": len(scenes), "workflow_profile": "production"}
        plans = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, status="approved").all()
    scenes = _script_scenes(script)
    scene_names = [str(item.get("name") or "未命名场景").strip() for item in scenes]
    by_scene = {row.scene_name: row for row in plans}
    issues = []
    if not scenes:
        issues.append("剧本缺少结构化 scenes；请先完成剧本结构化后再审核 ShotPlan。")
    issues.extend(f"缺少已批准 ShotPlan：{name}" for name in scene_names if name not in by_scene)
    for row in plans:
        if _json(row.unknowns, []):
            issues.append(f"{row.scene_name}: ShotPlan 仍有未决信息")
    return {"allowed": not issues, "status": "ready" if not issues else "blocked", "blocking_issues": issues, "approved_plan_count": len(plans), "scene_count": len(scene_names)}
