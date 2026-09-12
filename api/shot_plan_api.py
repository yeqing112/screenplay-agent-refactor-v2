"""Evidence-gated ShotPlan API."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.shot_plan import build_shot_plan
from models import DirectorTreatment, SceneBlocking, Script, Session, ShotPlan, StoryboardShot

router = APIRouter(prefix="/api/books", tags=["shot-plan"])


class ShotPlanPreviewRequest(BaseModel):
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    persist: bool = False


class ShotPlanConfirmRequest(BaseModel):
    plan_id: int = Field(validation_alias=AliasChoices("plan_id", "planId"))
    evidence_fingerprint: str = Field(default="", validation_alias=AliasChoices("evidence_fingerprint", "evidenceFingerprint"))
    confirmed: bool = False
    plan: dict[str, Any] | None = None


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


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
    return {"id": row.id, "book_id": row.book_id, "episode": row.episode, "scene_name": row.scene_name, "revision": row.revision, "status": row.status,
            "execution_status": row.execution_status, "quality_status": row.quality_status,
            "production_status": row.production_status, "workflow_profile": row.workflow_profile,
            "treatment_id": row.treatment_id, "blocking_id": row.blocking_id, "shots": _json(row.shots, []), "unknowns": _json(row.unknowns, []), "evidence_fingerprint": row.evidence_fingerprint, "model_info": _json(row.model_info, {}), "created_at": row.created_at.isoformat() if row.created_at else None, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


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
        script = _json(script_row.content, {})
        scenes = _script_scenes(script)
        scene_names = [str(item.get("name") or "未命名场景").strip() for item in scenes]
        scene_name = req.scene_name.strip() or (scene_names[0] if scene_names else "")
        treatment = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
        blocking = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
        if not treatment or not blocking:
            raise HTTPException(status_code=409, detail=f"ShotPlan requires approved DirectorTreatment and SceneBlocking for scene: {scene_name or '未命名场景'}")
        if _json(blocking.unknowns, []):
            raise HTTPException(status_code=409, detail=f"ShotPlan is blocked by unresolved SceneBlocking unknowns: {scene_name}")
        scene = next((item for item in scenes if isinstance(item, dict) and str(item.get("name") or "").strip() == scene_name), None)
        if not scene:
            raise HTTPException(status_code=404, detail=f"Scene not found: {scene_name}")
        treatment_payload = {"scene_name": treatment.scene_name, "character_intents": _json(treatment.character_intents, {}), "beat_map": _json(treatment.beat_map, []), "prompt_fingerprint": treatment.prompt_fingerprint}
        blocking_payload = {"scene_name": blocking.scene_name, "participants": _json(blocking.participants, []), "unknowns": _json(blocking.unknowns, []), "evidence_fingerprint": blocking.evidence_fingerprint}
        plan = build_shot_plan(treatment=treatment_payload, blocking=blocking_payload)
        persisted_id = None
        if req.persist:
            existing = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, evidence_fingerprint=plan["evidence_fingerprint"]).first()
            if existing:
                persisted_id = existing.id
            else:
                row = ShotPlan(book_id=book_id, episode=episode, scene_name=scene_name, revision=1, status="draft", treatment_id=treatment.id, blocking_id=blocking.id, shots=json.dumps(plan["shots"], ensure_ascii=False), unknowns=json.dumps(plan["unknowns"], ensure_ascii=False), evidence_fingerprint=plan["evidence_fingerprint"], model_info=json.dumps(plan["model_info"], ensure_ascii=False), created_at=datetime.now(), updated_at=datetime.now())
                session.add(row); session.commit(); session.refresh(row); persisted_id = row.id
        return {"mode": "shadow_deterministic", "llm_called": False, "mutated": bool(persisted_id), "persisted_draft_id": persisted_id, "plan": plan, "treatment_id": treatment.id, "blocking_id": blocking.id, "message": "这是只读 ShotPlan 草案；尚未修改 StoryboardShot。"}


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
    with Session() as session:
        draft = session.query(ShotPlan).filter_by(id=req.plan_id, book_id=book_id, episode=episode).first()
        if not draft or draft.status != "draft":
            raise HTTPException(status_code=409, detail="ShotPlan draft not found or already finalized.")
        treatment = session.query(DirectorTreatment).filter_by(id=draft.treatment_id, book_id=book_id, episode=episode, status="approved").first()
        blocking = session.query(SceneBlocking).filter_by(id=draft.blocking_id, book_id=book_id, episode=episode, status="approved").first()
        if not treatment or not blocking:
            raise HTTPException(status_code=409, detail="ShotPlan upstream evidence is no longer approved.")
        scene_name = draft.scene_name
    preview = preview_shot_plan(book_id, episode, ShotPlanPreviewRequest(scene_name=scene_name))
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
        candidate = _validate_plan_candidate(req.plan or {field: baseline[field] for field in ("scene_name", "shots", "unknowns")}, baseline)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"ShotPlan candidate is invalid: {exc}") from exc
    with Session() as session:
        draft = session.query(ShotPlan).filter_by(id=req.plan_id, book_id=book_id, episode=episode).first()
        previous = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, scene_name=scene_name, status="approved").order_by(ShotPlan.revision.desc(), ShotPlan.id.desc()).first()
        if previous:
            previous.status = "superseded"; previous.updated_at = datetime.now()
        anchor = {"previous_plan_id": previous.id if previous else None, "previous_revision": previous.revision if previous else None}
        row = ShotPlan(book_id=book_id, episode=episode, scene_name=scene_name, revision=(previous.revision + 1 if previous else 1), status="approved", treatment_id=draft.treatment_id, blocking_id=draft.blocking_id, shots=json.dumps(candidate["shots"], ensure_ascii=False), unknowns="[]", evidence_fingerprint=draft.evidence_fingerprint, model_info=json.dumps({"mode": "confirmed_human_candidate", "rollback_anchor": anchor, "confirmed_at": datetime.now().isoformat()}, ensure_ascii=False), created_at=datetime.now(), updated_at=datetime.now())
        session.add(row); draft.status = "superseded"; draft.updated_at = datetime.now(); session.commit(); session.refresh(row)
        return {"approved": True, "mutated": True, "shot_plan": _payload(row), "rollback_anchor": anchor, "storyboard_generation_allowed": True}


@router.get("/{book_id}/episodes/{episode}/storyboard/readiness")
def storyboard_readiness(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        plans = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, status="approved").all()
    if not script_row:
        raise HTTPException(status_code=404, detail="No script found for this episode.")
    script = _json(script_row.content, {})
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
