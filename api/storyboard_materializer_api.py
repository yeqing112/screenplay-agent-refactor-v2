"""Production Storyboard Materializer boundary.

The endpoint is an explicit, deterministic projection gate.  It never calls a
provider or Prompt Compiler and never promotes materialized structure to media
production readiness.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.script_ir import resolve_script_payload
from core.director_treatment_authority import resolve_current_authoritative_treatment
from core.scene_blocking_authority import resolve_current_authoritative_scene_blocking
from core.scene_blocking_authority import blocking_payload_from_row
from core.shot_plan_authority import resolve_current_authoritative_shot_plan, shot_plan_payload_from_row
from core.storyboard_handoff import project_shot_design_to_storyboard_handoff
from core.storyboard_materializer import (
    MATERIALIZATION_SCHEMA_VERSION,
    MATERIALIZER_POLICY_VERSION,
    MATERIALIZER_VERSION,
    build_materialization_authority_envelope,
    materialization_set_fingerprint,
    materialize_storyboard_from_handoff,
    projection_payload,
    validate_materialization_set,
)
from models import (
    Script,
    ScriptIRVersion,
    Session,
    ShotPlan,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardShot,
)

router = APIRouter(prefix="/api/books", tags=["storyboard-materializer"])


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


class MaterializeRequest(BaseModel):
    confirmed: bool = False
    plan_id: int | None = Field(default=None, validation_alias=AliasChoices("plan_id", "planId"))


def _conflict(code: str, message: str, **extra):
    raise HTTPException(status_code=409, detail={"code": code, "message": message, **extra})


def _authority_row_payload(row, envelope: dict, *, plan: ShotPlan) -> dict:
    return {
        "id": row.id,
        "revision": getattr(row, "revision", None),
        "payload_hash": str(getattr(row, "payload_hash", "") or envelope.get("payload_hash") or ""),
        "authority_fingerprint": str(envelope.get("envelope_fingerprint") or ""),
        "plan_revision": getattr(row, "revision", None),
        "scene_id": str(getattr(plan, "scene_id", "") or ""),
    }


def _existing_set_is_fresh(session, *, pointer, set_row, plan, authority_envelope, expected_ids):
    if not pointer or not set_row:
        return False, []
    if pointer.materialization_set_id != set_row.id or pointer.shot_plan_id != plan.id or pointer.shot_plan_revision != plan.revision:
        return False, []
    if pointer.set_payload_fingerprint != set_row.set_payload_fingerprint or set_row.stale_status != "FRESH" or set_row.status != "MATERIALIZED":
        return False, []
    if set_row.shot_plan_authority_fingerprint != str(authority_envelope.get("envelope_fingerprint") or ""):
        return False, []
    rows = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id, book_id=plan.book_id, episode=plan.episode).order_by(StoryboardShot.shot_id).all()
    if len(rows) != len(expected_ids) or [str(row.plan_shot_id or "") for row in rows] != expected_ids:
        return False, rows
    if any(row.materialization_status != "MATERIALIZED" or not row.projection_fingerprint for row in rows):
        return False, rows
    return True, rows


@router.post("/{book_id}/episodes/{episode}/storyboard/materialize")
def materialize_storyboard(book_id: int, episode: int, req: MaterializeRequest) -> dict:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="Storyboard materialization requires confirmed=true.")

    with Session() as session:
        script = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script:
            _conflict("SCRIPT_REQUIRED", "Production materialization requires a script.")
        script_ir_id = script.current_script_ir_version_id
        script_ir = session.query(ScriptIRVersion).filter_by(id=script_ir_id, book_id=book_id, episode=episode, status="production_qualified").first() if script_ir_id else None
        if not script_ir:
            _conflict("SCRIPT_IR_AUTHORITY_POINTER_MISSING", "Production materialization requires the script's production-qualified ScriptIR version.")
        script_ir_payload = resolve_script_payload(session, script, workflow_profile="production")
        scenes = script_ir_payload.get("scenes", []) if isinstance(script_ir_payload, dict) else []
        structured_scenes = [item for item in scenes if isinstance(item, dict)] if isinstance(scenes, list) else []
        scene_by_id = {str(item.get("scene_id") or "").strip(): item for item in structured_scenes if str(item.get("scene_id") or "").strip()}
        if not structured_scenes or len(scene_by_id) != len(structured_scenes):
            _conflict("SCENE_ID_REQUIRED", "Every production ScriptIR scene requires a stable scene_id before materialization.")

        if req.plan_id:
            selected = session.query(ShotPlan).filter_by(id=req.plan_id, book_id=book_id, episode=episode).first()
            if not selected:
                _conflict("SHOT_PLAN_NOT_FOUND", "Requested ShotPlan does not exist in this production scope.")
            scene_id = str(getattr(selected, "scene_id", "") or "").strip()
            if scene_id not in scene_by_id:
                _conflict("SHOT_PLAN_SCENE_NOT_IN_SCRIPT_IR", "Requested ShotPlan scene is not in the current ScriptIR.")
            current, authority_envelope = resolve_current_authoritative_shot_plan(session, book_id=book_id, episode=episode, scene_id=scene_id)
            if current.id != selected.id:
                _conflict("SHOT_PLAN_NOT_CURRENT_POINTER", "Only the current authoritative ShotPlan pointer may be materialized.")
            plans = [current]
        else:
            plans = []
            authority_by_plan = {}
            for scene_id in scene_by_id:
                current, envelope = resolve_current_authoritative_shot_plan(session, book_id=book_id, episode=episode, scene_id=scene_id)
                plans.append(current)
                authority_by_plan[current.id] = envelope
        if not plans:
            _conflict("SHOT_PLAN_POINTER_MISSING", "No current authoritative ShotPlan is available for materialization.")

        created_set_ids: list[int] = []
        created_shot_ids: list[str] = []
        reused_set_ids: list[int] = []

        for plan in plans:
            scene_id = str(getattr(plan, "scene_id", "") or "").strip()
            scene = scene_by_id.get(scene_id) or {}
            if str(scene.get("name") or scene.get("scene_name") or "").strip() != str(plan.scene_name or "").strip():
                _conflict("SCENE_NAME_LINEAGE_CHANGED", f"ShotPlan scene display identity changed: {scene_id}.")
            treatment, treatment_envelope = resolve_current_authoritative_treatment(session, book_id=book_id, episode=episode, scene_id=scene_id)
            blocking, blocking_envelope = resolve_current_authoritative_scene_blocking(session, book_id=book_id, episode=episode, scene_id=scene_id)
            if not treatment or not blocking or blocking.treatment_id != treatment.id or str(getattr(blocking, "scene_id", "") or "") != scene_id:
                _conflict("UPSTREAM_LINEAGE_MISSING", f"Production materialization requires approved Treatment and SceneBlocking lineage for scene: {plan.scene_name}")
            if _json(getattr(blocking, "unknowns", "[]"), []) or _json(getattr(blocking, "unresolved_facts", "[]"), []):
                _conflict("SCENE_BLOCKING_UNRESOLVED", f"Production materialization is blocked by unresolved SceneBlocking facts: {plan.scene_name}")
            if getattr(blocking, "schema_version", "scene_blocking_v1") == "scene_blocking_v2" and _json(getattr(blocking, "validation", "{}"), {}).get("status") != "qualified":
                _conflict("SCENE_BLOCKING_NOT_QUALIFIED", f"SceneBlocking is not qualified: {plan.scene_name}")

            raw = _json(plan.shots, None)
            if not isinstance(raw, list):
                _conflict("SHOT_PLAN_PAYLOAD_INVALID", f"Approved ShotPlan payload is invalid for scene: {plan.scene_name}")
            plan_payload = shot_plan_payload_from_row(plan)
            if plan_payload.get("phase_c_semantic_ready") is not True:
                _conflict(
                    "SHOT_PLAN_PHASE_C_NOT_READY",
                    "Production Storyboard materialization requires the current Phase C semantic-ready ShotPlan.",
                    scene_id=scene_id,
                )
            try:
                blocking_payload = blocking_payload_from_row(blocking)
                storyboard_handoff = project_shot_design_to_storyboard_handoff(plan_payload, blocking=blocking_payload, require_phase_c=True)
                projections = materialize_storyboard_from_handoff(storyboard_handoff, production=True)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                code = str(exc).split(":", 1)[0] if ":" in str(exc) else "SHOT_PLAN_MATERIALIZATION_BLOCKED"
                _conflict(code, str(exc))
            expected_ids = [str(item.get("plan_shot_id") or "") for item in raw]
            mapping_errors = validate_materialization_set(expected_plan_shot_ids=expected_ids, projections=projections)
            if mapping_errors:
                _conflict(mapping_errors[0]["code"], "ShotPlan N→N projection contract failed.", errors=mapping_errors)
            authority_envelope = authority_by_plan.get(plan.id) if not req.plan_id else authority_envelope
            authority_fp = str(authority_envelope.get("envelope_fingerprint") or "")
            plan_payload_hash = str(getattr(plan, "payload_hash", "") or authority_envelope.get("payload_hash") or "")
            set_basis = {
                "shot_plan_id": plan.id,
                "shot_plan_revision": plan.revision,
                "shot_plan_payload_hash": plan_payload_hash,
                "shot_plan_authority_fingerprint": authority_fp,
                "expected_shot_count": len(expected_ids),
                "ordered_plan_shot_ids": expected_ids,
                "materializer_version": MATERIALIZER_VERSION,
                "materializer_policy_version": MATERIALIZER_POLICY_VERSION,
                "handoff_schema_version": storyboard_handoff.get("schema_version"),
                "handoff_projection_version": storyboard_handoff.get("projection_version"),
                "handoff_fingerprint": storyboard_handoff.get("handoff_fingerprint"),
            }
            set_fingerprint = materialization_set_fingerprint(authority_envelope={"shot_plan": authority_envelope, "treatment": treatment_envelope, "blocking": blocking_envelope, "storyboard_handoff": storyboard_handoff}, projections=projections)
            pointer = session.query(StoryboardMaterializationPointer).filter_by(book_id=book_id, episode=episode, scene_id=scene_id).first()
            set_row = session.query(StoryboardMaterializationSet).filter_by(set_payload_fingerprint=set_fingerprint).first()
            is_fresh, existing_rows = _existing_set_is_fresh(session, pointer=pointer, set_row=set_row, plan=plan, authority_envelope=authority_envelope, expected_ids=expected_ids)
            if is_fresh:
                reused_set_ids.append(set_row.id)
                continue

            # A complete set with the same deterministic fingerprint can be
            # reactivated when its pointer was removed or interrupted.  An
            # incomplete set is never silently repaired or duplicated.
            if set_row is not None:
                candidate_rows = session.query(StoryboardShot).filter_by(materialization_set_id=set_row.id, book_id=book_id, episode=episode).order_by(StoryboardShot.shot_id).all()
                if len(candidate_rows) == len(expected_ids) and [str(row.plan_shot_id or "") for row in candidate_rows] == expected_ids and all(str(row.projection_fingerprint or "") for row in candidate_rows):
                    set_row.status = "MATERIALIZED"
                    set_row.stale_status = "FRESH"
                    set_row.stale_reasons = "[]"
                    set_row.updated_at = datetime.now()
                    pointer = pointer or StoryboardMaterializationPointer(book_id=book_id, episode=episode, scene_id=scene_id)
                    pointer.materialization_set_id = set_row.id
                    pointer.shot_plan_id = plan.id
                    pointer.shot_plan_revision = plan.revision
                    pointer.set_payload_fingerprint = set_fingerprint
                    pointer.qualification_state = "MATERIALIZED"
                    pointer.updated_at = datetime.now()
                    session.add(pointer)
                    reused_set_ids.append(set_row.id)
                    continue
                _conflict("STORYBOARD_MATERIALIZATION_SET_INCOMPLETE", f"Existing materialization set is incomplete for scene: {plan.scene_name}")

            # Any legacy row in this scene is an explicit migration boundary;
            # never guess its relation to the current ShotPlan.
            scene_rows = session.query(StoryboardShot).filter(StoryboardShot.book_id == book_id, StoryboardShot.episode == episode, StoryboardShot.scene_name == plan.scene_name).all()
            legacy_rows = [row for row in scene_rows if not str(getattr(row, "scene_id", "") or "").strip() or not str(getattr(row, "plan_shot_id", "") or "").strip() or not getattr(row, "materialization_set_id", None) or not getattr(row, "source_shot_plan_id", None)]
            if legacy_rows:
                _conflict("LEGACY_STORYBOARD_MIGRATION_REQUIRED", f"Legacy StoryboardShot rows exist for scene: {plan.scene_name}")
            if pointer and pointer.materialization_set_id:
                old_set = session.query(StoryboardMaterializationSet).filter_by(id=pointer.materialization_set_id).first()
                if old_set and (old_set.shot_plan_id != plan.id or old_set.set_payload_fingerprint != set_fingerprint):
                    old_set.status = "SUPERSEDED"
                    old_set.stale_status = "STALE"
                    old_set.stale_reasons = json.dumps(["SHOT_PLAN_POINTER_CHANGED"], ensure_ascii=False)
                    session.query(StoryboardShot).filter_by(materialization_set_id=old_set.id).update({"materialization_status": "STALE", "production_status": "blocked"}, synchronize_session=False)

            set_row = StoryboardMaterializationSet(book_id=book_id, episode=episode, scene_id=scene_id, shot_plan_id=plan.id, shot_plan_revision=plan.revision, shot_plan_payload_hash=plan_payload_hash, shot_plan_authority_fingerprint=authority_fp, expected_shot_count=len(expected_ids), materialized_shot_count=len(projections), ordered_plan_shot_ids=json.dumps(expected_ids, ensure_ascii=False), set_payload_fingerprint=set_fingerprint, materializer_version=MATERIALIZER_VERSION, materializer_policy_version=MATERIALIZER_POLICY_VERSION, status="MATERIALIZED", stale_status="FRESH", stale_reasons="[]", created_at=datetime.now(), activated_at=datetime.now(), updated_at=datetime.now())
            session.add(set_row)
            session.flush()
            set_envelope = build_materialization_authority_envelope(
                script_ir={"id": script_ir.id, "revision": script_ir.revision, "payload_hash": script_ir.payload_hash, "authority_fingerprint": _json(getattr(script_ir, "authority_envelope_json", "{}"), {}).get("envelope_fingerprint", "")},
                treatment={"id": treatment.id, "revision": treatment.revision, "payload_hash": getattr(treatment, "payload_hash", ""), "authority_fingerprint": treatment_envelope.get("envelope_fingerprint", "")},
                blocking={"id": blocking.id, "revision": blocking.revision, "payload_hash": getattr(blocking, "payload_hash", ""), "authority_fingerprint": blocking_envelope.get("envelope_fingerprint", "")},
                shot_plan={"id": plan.id, "revision": plan.revision, "payload_hash": plan_payload_hash, "authority_fingerprint": authority_fp},
                materialization_set={"id": set_row.id, "fingerprint": set_fingerprint, "expected_shot_count": len(expected_ids), "actual_shot_count": len(projections), "ordered_plan_shot_ids": expected_ids, "materializer_version": MATERIALIZER_VERSION, "materializer_policy_version": MATERIALIZER_POLICY_VERSION},
            )
            set_envelope["storyboard_handoff"] = {
                "schema_version": storyboard_handoff.get("schema_version"),
                "projection_version": storyboard_handoff.get("projection_version"),
                "source_shot_plan_fingerprint": storyboard_handoff.get("source_shot_plan_fingerprint"),
                "handoff_fingerprint": storyboard_handoff.get("handoff_fingerprint"),
            }
            set_row.authority_envelope_json = json.dumps(set_envelope, ensure_ascii=False, sort_keys=True)
            for projection in projections:
                handoff = {"schema_version": "storyboard_prompt_handoff_v1", "storyboard_handoff_schema_version": storyboard_handoff.get("schema_version"), "storyboard_handoff_projection_version": storyboard_handoff.get("projection_version"), "storyboard_handoff_fingerprint": storyboard_handoff.get("handoff_fingerprint"), "materialization_set_id": set_row.id, "storyboard_shot_id": None, "plan_shot_id": projection["plan_shot_id"], "beat_id": projection.get("beat_id", ""), "scene_id": scene_id, "shot_plan_id": plan.id, "shot_plan_revision": plan.revision, "shot_plan_authority_fingerprint": authority_fp, "storyboard_projection_fingerprint": projection["projection_fingerprint"], "asset_identity_bindings": projection["asset_bindings"], "continuity_contract": projection["continuity_contract"], "camera": projection["meta_info"].get("camera", {}), "duration": projection["duration"], "action_beats": projection["action_beats"], "entry_state": projection["start_state"], "exit_state": projection["end_state"], "shot_purpose": projection["shot_purpose"], "transition": projection["transition"]}
                meta = {**projection["meta_info"], "action_beats": projection["action_beats"], "asset_bindings": projection["asset_bindings"], "continuity_contract": projection["continuity_contract"], "projection_payload": projection_payload(projection), "upstream": {"script_ir_id": script_ir.id, "treatment_id": treatment.id, "blocking_id": blocking.id, "shot_plan_id": plan.id, "shot_plan_authority_fingerprint": authority_fp}, "prompt_compiler_handoff": handoff}
                row = StoryboardShot(book_id=book_id, episode=episode, scene_name=projection["scene_name"], scene_id=scene_id, plan_shot_id=projection["plan_shot_id"], materialization_set_id=set_row.id, source_shot_plan_id=plan.id, source_shot_plan_revision=plan.revision, source_shot_plan_authority_fingerprint=authority_fp, projection_fingerprint=projection["projection_fingerprint"], materialization_status="MATERIALIZED", shot_id=projection["shot_id"], dialogue=projection["dialogue"], duration=int(float(projection["duration"])), camera_angle=projection["camera_angle"], camera_movement=projection["camera_movement"], camera_speed=projection["camera_speed"], shot_purpose=projection["shot_purpose"], transition=projection["transition"], lighting=projection["lighting"], start_state=json.dumps(projection["start_state"], ensure_ascii=False) if isinstance(projection["start_state"], (dict, list)) else projection["start_state"], action_process=projection["action_process"], end_state=json.dumps(projection["end_state"], ensure_ascii=False) if isinstance(projection["end_state"], (dict, list)) else projection["end_state"], visual_prompt_static="", visual_prompt_motion="", visual_prompt_final="", asset_links=json.dumps(projection["asset_bindings"], ensure_ascii=False), meta_info=json.dumps(meta, ensure_ascii=False, sort_keys=True), execution_status="succeeded", quality_status="materialized", production_status="blocked", workflow_profile="production", created_at=datetime.now(), updated_at=datetime.now())
                session.add(row)
                session.flush()
                handoff["storyboard_shot_id"] = row.id
                meta["prompt_compiler_handoff"] = handoff
                row.meta_info = json.dumps(meta, ensure_ascii=False, sort_keys=True)
                created_shot_ids.append(projection["plan_shot_id"])
            pointer = pointer or StoryboardMaterializationPointer(book_id=book_id, episode=episode, scene_id=scene_id)
            pointer.materialization_set_id = set_row.id
            pointer.shot_plan_id = plan.id
            pointer.shot_plan_revision = plan.revision
            pointer.set_payload_fingerprint = set_fingerprint
            pointer.qualification_state = "MATERIALIZED"
            pointer.updated_at = datetime.now()
            session.add(pointer)
            created_set_ids.append(set_row.id)

        session.commit()
        return {"confirmed": True, "mutated": bool(created_set_ids), "reused": bool(reused_set_ids), "materialized_count": len(created_shot_ids), "plan_shot_ids": created_shot_ids, "materialization_set_ids": created_set_ids or reused_set_ids, "production_status": "blocked", "materialization_status": "MATERIALIZED", "llm_called": False, "provider_calls": 0}


__all__ = ["router", "MaterializeRequest", "materialize_storyboard"]
