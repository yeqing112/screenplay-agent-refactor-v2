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
from models import DirectorTreatment, SceneBlocking, Script, ScriptIRVersion, Session, ShotPlan, StoryboardShot

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
        script_ir_id = script.current_script_ir_version_id
        script_ir = session.query(ScriptIRVersion).filter_by(id=script_ir_id, book_id=book_id, episode=episode, status="qualified").first() if script_ir_id else None
        if not script_ir:
            raise HTTPException(status_code=409, detail="Production materialization requires the script's qualified ScriptIR version.")
        try:
            script_ir_payload = json.loads(script_ir.payload_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail="Qualified ScriptIR payload is invalid.") from exc
        script_scene_names = {str(item.get("name") or "").strip() for item in (script_ir_payload.get("scenes", []) if isinstance(script_ir_payload, dict) and isinstance(script_ir_payload.get("scenes"), list) else []) if isinstance(item, dict) and str(item.get("name") or "").strip()}
        if not script_scene_names:
            raise HTTPException(status_code=409, detail="Qualified ScriptIR has no structured scenes for production materialization.")
        query = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, status="approved")
        if req.plan_id:
            query = query.filter_by(id=req.plan_id)
        plans = query.order_by(ShotPlan.scene_name, ShotPlan.revision.desc(), ShotPlan.id.desc()).all()
        if not plans:
            raise HTTPException(status_code=409, detail="No approved ShotPlan is available for materialization.")
        missing_script_scenes = sorted({str(plan.scene_name or "").strip() for plan in plans} - script_scene_names)
        if missing_script_scenes:
            raise HTTPException(status_code=409, detail=f"Qualified ScriptIR does not contain planned scenes: {', '.join(missing_script_scenes)}")
        created = []
        for plan in plans:
            treatment = session.query(DirectorTreatment).filter_by(id=plan.treatment_id, book_id=book_id, episode=episode, scene_name=plan.scene_name, status="approved").first() if plan.treatment_id else None
            blocking = session.query(SceneBlocking).filter_by(id=plan.blocking_id, book_id=book_id, episode=episode, scene_name=plan.scene_name, status="approved").first() if plan.blocking_id else None
            if not treatment or not blocking or blocking.treatment_id != treatment.id:
                raise HTTPException(status_code=409, detail=f"Production materialization requires approved Treatment and SceneBlocking lineage for scene: {plan.scene_name}")
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
            existing_refs = {str((json.loads(row.meta_info or "{}").get("shot_plan_ref") or {}).get("plan_shot_id") or "") for row in session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_name=plan.scene_name).all()}
            planned_refs = {str(draft["plan_shot_id"]) for draft in drafts}
            if existing_refs - planned_refs:
                raise HTTPException(status_code=409, detail=f"Existing StoryboardShot set does not match the approved ShotPlan for scene: {plan.scene_name}")
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
                    "upstream": {"script_ir_id": script_ir.id, "treatment_id": treatment.id, "blocking_id": blocking.id, "shot_plan_id": plan.id},
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
