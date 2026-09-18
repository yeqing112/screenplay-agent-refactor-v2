"""Explicitly confirmed production Storyboard materialization endpoint."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.storyboard_materializer import materialize_storyboard_from_shot_plan
from core.prompt_ir_compiler import compile_phase_a, verbalize_phase_b_deterministic, validate_phase_a_state
from core.production_policy import evaluate_production_boundary
from core.qualification_loop import qualify_candidate
from core.script_ir import resolve_script_payload
from core.director_treatment_authority import resolve_current_authoritative_treatment
from core.scene_blocking_authority import resolve_current_authoritative_scene_blocking
from core.shot_plan_authority import resolve_current_authoritative_shot_plan
from models import DirectorTreatment, SceneBlocking, Script, ScriptIRVersion, Session, ShotPlan, ShotPlanAuthority, StoryboardShot

router = APIRouter(prefix="/api/books", tags=["storyboard-materializer"])


def _json_list(value: str | list | None) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


class MaterializeRequest(BaseModel):
    confirmed: bool = False
    plan_id: int | None = Field(default=None, validation_alias=AliasChoices("plan_id", "planId"))


@router.post("/{book_id}/episodes/{episode}/storyboard/materialize")
def materialize_storyboard(book_id: int, episode: int, req: MaterializeRequest) -> dict:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="Storyboard materialization requires confirmed=true.")
    with Session() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script:
            raise HTTPException(status_code=409, detail="Production materialization requires a script.")
        script_ir_payload = resolve_script_payload(session, script, workflow_profile="production")
        script_ir_id = script.current_script_ir_version_id
        script_ir = session.query(ScriptIRVersion).filter_by(id=script_ir_id, book_id=book_id, episode=episode, status="production_qualified").first() if script_ir_id else None
        if not script_ir:
            raise HTTPException(status_code=409, detail={"code": "SCRIPT_IR_AUTHORITY_POINTER_MISSING", "message": "Production materialization requires the script's production-qualified ScriptIR version."})
        script_scene_names = {str(item.get("name") or "").strip() for item in (script_ir_payload.get("scenes", []) if isinstance(script_ir_payload, dict) and isinstance(script_ir_payload.get("scenes"), list) else []) if isinstance(item, dict) and str(item.get("name") or "").strip()}
        if not script_scene_names:
            raise HTTPException(status_code=409, detail="Qualified ScriptIR has no structured scenes for production materialization.")
        # Production selection is pointer-only.  There is deliberately no
        # latest-approved fallback: an approved row without a pointer is a
        # migration/authority error, not an eligible production source.
        plans = []
        scene_by_id = {
            str(item.get("scene_id") or "").strip(): item
            for item in (script_ir_payload.get("scenes", []) if isinstance(script_ir_payload, dict) and isinstance(script_ir_payload.get("scenes"), list) else [])
            if isinstance(item, dict) and str(item.get("scene_id") or "").strip()
        }
        structured_scenes = [item for item in (script_ir_payload.get("scenes", []) if isinstance(script_ir_payload, dict) and isinstance(script_ir_payload.get("scenes"), list) else []) if isinstance(item, dict)]
        if len(scene_by_id) != len(structured_scenes):
            raise HTTPException(status_code=409, detail={"code": "SCENE_ID_REQUIRED", "message": "Every production ScriptIR scene requires a stable scene_id before materialization."})
        if req.plan_id:
            selected = session.query(ShotPlan).filter_by(id=req.plan_id, book_id=book_id, episode=episode).first()
            if not selected:
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_NOT_FOUND", "message": "Requested ShotPlan does not exist in this production scope."})
            selected_scene_id = str(getattr(selected, "scene_id", "") or "").strip()
            if selected_scene_id not in scene_by_id:
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_SCENE_NOT_IN_SCRIPT_IR", "message": "Requested ShotPlan scene is not in the current ScriptIR."})
            current, _ = resolve_current_authoritative_shot_plan(session, book_id=book_id, episode=episode, scene_id=selected_scene_id)
            if current.id != selected.id:
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_NOT_CURRENT_POINTER", "message": "Only the current authoritative ShotPlan pointer may be materialized."})
            plans = [current]
        else:
            for scene_id in scene_by_id:
                current, _ = resolve_current_authoritative_shot_plan(session, book_id=book_id, episode=episode, scene_id=scene_id)
                plans.append(current)
        if not plans:
            raise HTTPException(status_code=409, detail="No approved ShotPlan is available for materialization.")
        missing_script_scenes = sorted({str(plan.scene_name or "").strip() for plan in plans} - script_scene_names)
        if missing_script_scenes:
            raise HTTPException(status_code=409, detail=f"Qualified ScriptIR does not contain planned scenes: {', '.join(missing_script_scenes)}")
        created = []
        for plan in plans:
            plan_scene = scene_by_id.get(str(getattr(plan, "scene_id", "") or "").strip())
            plan_scene_id = str((plan_scene or {}).get("scene_id") or getattr(plan, "scene_id", "") or "").strip()
            treatment, treatment_authority = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=plan_scene_id)
            blocking, blocking_authority = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=plan_scene_id)
            if not treatment or not blocking or blocking.treatment_id != treatment.id or str(getattr(blocking, "scene_id", "") or "") != plan_scene_id:
                raise HTTPException(status_code=409, detail=f"Production materialization requires approved Treatment and SceneBlocking lineage for scene: {plan.scene_name}")
            authority_row = session.query(ShotPlanAuthority).filter_by(shot_plan_id=plan.id).first()
            if not authority_row:
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_AUTHORITY_MISSING", "message": f"ShotPlan authority envelope is missing: {plan.scene_name}"})
            try:
                shot_plan_authority_envelope = json.loads(authority_row.envelope_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                raise HTTPException(status_code=409, detail={"code": "SHOT_PLAN_AUTHORITY_INVALID", "message": f"ShotPlan authority envelope is invalid: {plan.scene_name}"})
            blocking_unknowns = _json_list(getattr(blocking, "unknowns", "[]"))
            blocking_unresolved = _json_list(getattr(blocking, "unresolved_facts", "[]"))
            if blocking_unknowns or blocking_unresolved:
                raise HTTPException(status_code=409, detail=f"Production materialization is blocked by unresolved SceneBlocking facts: {plan.scene_name}")
            if getattr(blocking, "schema_version", "scene_blocking_v1") == "scene_blocking_v2":
                try:
                    blocking_validation = json.loads(getattr(blocking, "validation", "{}") or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    blocking_validation = {}
                if blocking_validation.get("status") != "qualified":
                    raise HTTPException(status_code=409, detail=f"Production materialization requires qualified SceneBlocking validation: {plan.scene_name}")
            try:
                raw = json.loads(plan.shots or "[]")
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"Approved ShotPlan payload is invalid for scene: {plan.scene_name}",
                ) from exc
            try:
                drafts = materialize_storyboard_from_shot_plan({"scene_name": plan.scene_name, "shots": raw, "evidence_fingerprint": plan.evidence_fingerprint}, treatment={"id": treatment.id, "revision": treatment.revision}, blocking={"id": blocking.id, "revision": blocking.revision}, asset_snapshot={"script_ir_id": script_ir.id})
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=409, detail=f"Approved ShotPlan cannot be materialized: {exc}") from exc
            if len(drafts) != len(raw) or {str(item.get("plan_shot_id")) for item in drafts} != {str(item.get("plan_shot_id")) for item in raw}:
                raise HTTPException(status_code=409, detail=f"Materializer mapping does not preserve the approved ShotPlan cardinality: {plan.scene_name}")
            existing_refs: set[str] = set()
            existing_plan_ids: dict[str, set[str]] = {}
            for existing_row in session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_name=plan.scene_name).all():
                try:
                    existing_meta = json.loads(existing_row.meta_info or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    existing_meta = {}
                shot_plan_ref = existing_meta.get("shot_plan_ref") if isinstance(existing_meta, dict) else {}
                plan_shot_id = str((shot_plan_ref if isinstance(shot_plan_ref, dict) else {}).get("plan_shot_id") or "").strip()
                if not plan_shot_id:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Existing StoryboardShot has no shot_plan_ref for scene: {plan.scene_name}; "
                            "explicit migration is required before production materialization"
                        ),
                    )
                existing_refs.add(plan_shot_id)
                upstream = existing_meta.get("upstream") if isinstance(existing_meta, dict) else {}
                source_plan_id = str((upstream if isinstance(upstream, dict) else {}).get("shot_plan_id") or "").strip()
                if source_plan_id:
                    existing_plan_ids.setdefault(plan_shot_id, set()).add(source_plan_id)
            planned_refs = {str(draft["plan_shot_id"]) for draft in drafts}
            if existing_refs - planned_refs:
                raise HTTPException(status_code=409, detail=f"Existing StoryboardShot set does not match the approved ShotPlan for scene: {plan.scene_name}")
            conflicting_refs = sorted(
                plan_shot_id
                for plan_shot_id in planned_refs & existing_refs
                if existing_plan_ids.get(plan_shot_id) and str(plan.id) not in existing_plan_ids[plan_shot_id]
            )
            if conflicting_refs:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Existing StoryboardShot belongs to a different approved ShotPlan revision for scene: {plan.scene_name}; "
                        f"explicit migration is required for plan_shot_id: {', '.join(conflicting_refs)}"
                    ),
                )
            for draft in drafts:
                if draft["plan_shot_id"] in existing_refs:
                    continue
                phase_a = compile_phase_a(draft)
                verbalized = verbalize_phase_b_deterministic(phase_a)
                def _validate_compiler_candidate(candidate: dict) -> list[dict]:
                    report = validate_phase_a_state(candidate)
                    errors = list(report.get("errors", []))
                    if candidate.get("phase_a_status") == "blocked" and not errors:
                        diagnostics = candidate.get("compiler_diagnostics") if isinstance(candidate.get("compiler_diagnostics"), dict) else {}
                        errors = list(diagnostics.get("errors", [])) or [{"code": "PHASE_A_BLOCKED", "message": "Prompt Compiler Phase A is blocked."}]
                    return [
                        {"code": error.get("code") or "phase_a_validation", "severity": "blocked", "target_layer": "PROMPT_IR", "message": error.get("message", "")}
                        for error in errors
                    ]
                qualification = qualify_candidate(phase_a, [_validate_compiler_candidate], max_attempts=2)
                production_pass = evaluate_production_boundary(
                    "production",
                    script_ir_qualified=True,
                    director_treatment_approved=True,
                    scene_blocking_approved=True,
                    shot_plan_approved=True,
                    compiler_phase_a_pass=qualification["status"] == "qualified" and phase_a.get("phase_a_status") == "pass",
                    executability_pass=phase_a.get("executability", {}).get("status") != "blocked" if isinstance(phase_a.get("executability"), dict) else False,
                    # Asset/media readiness is intentionally left to the
                    # downstream readiness gate; materialization must never
                    # self-promote a shot merely because bindings exist.
                    required_assets_ready=False,
                )
                persisted_meta = {
                    **draft["meta_info"], "workflow_profile": "production",
                    "plan_shot_id": draft["plan_shot_id"], "action_beats": draft.get("action_beats", []),
                    "asset_bindings": draft.get("asset_bindings", {}), "continuity_contract": draft.get("continuity_contract", {}),
                    "upstream": {"script_ir_id": script_ir.id, "treatment_id": treatment.id, "blocking_id": blocking.id, "shot_plan_id": plan.id, "shot_plan_authority": shot_plan_authority_envelope},
                    "prompt_compiler": phase_a, "qualification": qualification, "production_pass": production_pass,
                }
                row = StoryboardShot(book_id=book_id, episode=episode, scene_name=draft["scene_name"], shot_id=draft["shot_id"], duration=draft["duration"], camera_angle=draft["camera_angle"], camera_movement=draft["camera_movement"], camera_speed=draft["camera_speed"], shot_purpose=draft["shot_purpose"], start_state=json.dumps(draft["start_state"], ensure_ascii=False) if isinstance(draft["start_state"], (dict, list)) else draft["start_state"], action_process=draft["action_process"], end_state=json.dumps(draft["end_state"], ensure_ascii=False) if isinstance(draft["end_state"], (dict, list)) else draft["end_state"], visual_prompt_static=verbalized["static_prompt"], visual_prompt_motion=verbalized["motion_prompt"], visual_prompt_final=verbalized["negative_prompt"], meta_info=json.dumps(persisted_meta, ensure_ascii=False), execution_status="succeeded", quality_status="qualified" if qualification["status"] == "qualified" else "needs_review", production_status="blocked", workflow_profile="production", created_at=datetime.now(), updated_at=datetime.now())
                session.add(row); created.append(draft["plan_shot_id"])
        session.commit()
        return {
            "confirmed": True,
            "mutated": bool(created),
            "materialized_count": len(created),
            "plan_shot_ids": created,
            # Materialization never self-promotes a shot into production. The
            # downstream readiness/Production Pass gate remains authoritative.
            "production_status": "blocked",
            "llm_called": False,
        }
