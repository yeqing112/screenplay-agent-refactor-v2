"""Evidence-first SceneBlocking / Spatial Engine API."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.scene_blocking import build_scene_blocking
from models import DirectorTreatment, SceneBlocking, Script, Session

router = APIRouter(prefix="/api/books", tags=["scene-blocking"])


class SceneBlockingPreviewRequest(BaseModel):
    scene_name: str = Field(default="", validation_alias=AliasChoices("scene_name", "sceneName"))
    treatment_id: int | None = Field(default=None, validation_alias=AliasChoices("treatment_id", "treatmentId"))
    persist: bool = False


class SceneBlockingConfirmRequest(BaseModel):
    blocking_id: int = Field(validation_alias=AliasChoices("blocking_id", "blockingId"))
    evidence_fingerprint: str = Field(default="", validation_alias=AliasChoices("evidence_fingerprint", "evidenceFingerprint"))
    confirmed: bool = False
    blocking: dict[str, Any] | None = None


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _row_payload(row: SceneBlocking) -> dict[str, Any]:
    return {
        "id": row.id, "book_id": row.book_id, "episode": row.episode, "scene_name": row.scene_name,
        "revision": row.revision, "status": row.status, "treatment_id": row.treatment_id,
        "treatment_revision": row.treatment_revision, "source_script_hash": row.source_script_hash,
        "participants": _json(row.participants, []), "beat_transitions": _json(row.beat_transitions, []),
        "spatial_rules": _json(row.spatial_rules, []), "unknowns": _json(row.unknowns, []),
        "evidence_fingerprint": row.evidence_fingerprint, "model_info": _json(row.model_info, {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_blocking_candidate(raw: Any, baseline: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("SceneBlocking candidate must be an object")
    allowed = {"scene_name", "participants", "beat_transitions", "spatial_rules", "unknowns"}
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
    return {
        "scene_name": baseline["scene_name"], "participants": participants, "beat_transitions": beats,
        "spatial_rules": [str(item) for item in rules], "unknowns": [str(item) for item in unknowns],
    }


@router.post("/{book_id}/episodes/{episode}/scene-blocking/preview")
def preview_scene_blocking(book_id: int, episode: int, req: SceneBlockingPreviewRequest) -> dict[str, Any]:
    with Session() as session:
        treatment_query = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode, status="approved")
        treatment = session.get(DirectorTreatment, req.treatment_id) if req.treatment_id else treatment_query.order_by(DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).first()
        if not treatment or treatment.book_id != book_id or treatment.episode != episode or treatment.status != "approved":
            raise HTTPException(status_code=409, detail="SceneBlocking requires an approved DirectorTreatment.")
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        script = _json(script_row.content, {})
        scenes = script.get("scenes") if isinstance(script, dict) else []
        wanted = req.scene_name.strip() or treatment.scene_name
        scene = next((item for item in scenes if isinstance(item, dict) and str(item.get("name") or "").strip() == wanted), None)
        if not scene:
            raise HTTPException(status_code=404, detail=f"Scene not found: {wanted}")
        treatment_payload = {
            "scene_name": treatment.scene_name, "character_intents": _json(treatment.character_intents, {}),
            "beat_map": _json(treatment.beat_map, []), "prompt_fingerprint": treatment.prompt_fingerprint,
        }
        source_hash = hashlib.sha256((script_row.content or "").encode("utf-8")).hexdigest()
        blocking = build_scene_blocking(scene=scene, treatment=treatment_payload, source_script_hash=source_hash)
        persisted_id = None
        if req.persist:
            existing = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=blocking["scene_name"], evidence_fingerprint=blocking["evidence_fingerprint"]).first()
            if existing:
                persisted_id = existing.id
            else:
                row = SceneBlocking(
                    book_id=book_id, episode=episode, scene_name=blocking["scene_name"], revision=1, status="draft",
                    treatment_id=treatment.id, treatment_revision=treatment.revision, source_script_hash=source_hash,
                    participants=json.dumps(blocking["participants"], ensure_ascii=False), beat_transitions=json.dumps(blocking["beat_transitions"], ensure_ascii=False),
                    spatial_rules=json.dumps(blocking["spatial_rules"], ensure_ascii=False), unknowns=json.dumps(blocking["unknowns"], ensure_ascii=False),
                    evidence_fingerprint=blocking["evidence_fingerprint"], model_info=json.dumps(blocking["model_info"], ensure_ascii=False),
                    created_at=datetime.now(), updated_at=datetime.now(),
                )
                session.add(row); session.commit(); session.refresh(row); persisted_id = row.id
        return {"mode": "shadow_deterministic", "llm_called": False, "mutated": bool(persisted_id), "persisted_draft_id": persisted_id, "treatment_id": treatment.id, "blocking": blocking, "message": "这是只读空间调度草案；未修改任何镜头。"}


@router.get("/{book_id}/episodes/{episode}/scene-blockings")
def list_scene_blockings(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        rows = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode).order_by(SceneBlocking.scene_name, SceneBlocking.revision.desc(), SceneBlocking.id.desc()).all()
    return {"items": [_row_payload(row) for row in rows]}


@router.get("/{book_id}/episodes/{episode}/shot-plan/readiness")
def shot_plan_readiness(book_id: int, episode: int) -> dict[str, Any]:
    """Return a hard gate for future ShotPlan generation."""
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        if not script_row:
            raise HTTPException(status_code=404, detail="No script found for this episode.")
        script = _json(script_row.content, {})
        scenes = [item for item in (script.get("scenes") if isinstance(script, dict) else []) if isinstance(item, dict)]
        approved = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, status="approved").all()
    by_scene = {row.scene_name: row for row in approved}
    missing = [str(scene.get("name") or "未命名场景") for scene in scenes if str(scene.get("name") or "未命名场景") not in by_scene]
    unresolved = []
    for row in approved:
        unresolved.extend([f"{row.scene_name}: {item}" for item in _json(row.unknowns, [])])
    blocking_issues = [f"缺少已批准 SceneBlocking：{name}" for name in missing] + unresolved
    return {"allowed": not blocking_issues, "status": "ready" if not blocking_issues else "blocked", "blocking_issues": blocking_issues, "approved_scene_count": len(approved), "scene_count": len(scenes)}


@router.post("/{book_id}/episodes/{episode}/scene-blocking/confirm")
def confirm_scene_blocking(book_id: int, episode: int, req: SceneBlockingConfirmRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="SceneBlocking approval requires confirmed=true.")
    with Session() as session:
        draft = session.query(SceneBlocking).filter_by(id=req.blocking_id, book_id=book_id, episode=episode).first()
        if not draft:
            raise HTTPException(status_code=404, detail="SceneBlocking draft not found.")
        if draft.status != "draft":
            raise HTTPException(status_code=409, detail="This SceneBlocking draft has already been finalized.")
        treatment = session.query(DirectorTreatment).filter_by(id=draft.treatment_id, book_id=book_id, episode=episode, status="approved").first()
        if not treatment:
            raise HTTPException(status_code=409, detail="The DirectorTreatment used by this draft is no longer approved.")
    preview = preview_scene_blocking(book_id, episode, SceneBlockingPreviewRequest(scene_name=draft.scene_name, treatment_id=draft.treatment_id))
    baseline = preview["blocking"]
    if req.evidence_fingerprint and req.evidence_fingerprint != draft.evidence_fingerprint:
        raise HTTPException(status_code=409, detail="SceneBlocking evidence fingerprint does not match.")
    if baseline["evidence_fingerprint"] != draft.evidence_fingerprint:
        with Session() as session:
            stale = session.query(SceneBlocking).filter_by(id=req.blocking_id, book_id=book_id).first()
            if stale and stale.status == "draft":
                stale.status = "superseded"; stale.updated_at = datetime.now(); session.commit()
        raise HTTPException(status_code=409, detail="SceneBlocking evidence changed; draft is stale and must be regenerated.")
    try:
        candidate_source = req.blocking or {field: baseline[field] for field in ("scene_name", "participants", "beat_transitions", "spatial_rules", "unknowns")}
        candidate = _validate_blocking_candidate(candidate_source, baseline)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"SceneBlocking candidate is invalid: {exc}") from exc
    with Session() as session:
        draft = session.query(SceneBlocking).filter_by(id=req.blocking_id, book_id=book_id, episode=episode).first()
        if not draft or draft.status != "draft":
            raise HTTPException(status_code=409, detail="This SceneBlocking draft has already been finalized.")
        previous = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode, scene_name=candidate["scene_name"], status="approved").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
        if previous:
            previous.status = "superseded"; previous.updated_at = datetime.now()
        anchor = {"previous_blocking_id": previous.id if previous else None, "previous_revision": previous.revision if previous else None}
        row = SceneBlocking(
            book_id=book_id, episode=episode, scene_name=candidate["scene_name"], revision=(previous.revision + 1 if previous else 1), status="approved",
            treatment_id=draft.treatment_id, treatment_revision=draft.treatment_revision, source_script_hash=draft.source_script_hash,
            participants=json.dumps(candidate["participants"], ensure_ascii=False), beat_transitions=json.dumps(candidate["beat_transitions"], ensure_ascii=False),
            spatial_rules=json.dumps(candidate["spatial_rules"], ensure_ascii=False), unknowns=json.dumps(candidate["unknowns"], ensure_ascii=False),
            evidence_fingerprint=draft.evidence_fingerprint, model_info=json.dumps({"mode": "confirmed_human_candidate", "rollback_anchor": anchor, "confirmed_at": datetime.now().isoformat()}, ensure_ascii=False),
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        session.add(row); draft.status = "superseded"; draft.updated_at = datetime.now(); session.commit(); session.refresh(row)
        return {"approved": True, "mutated": True, "scene_blocking": _row_payload(row), "rollback_anchor": anchor, "shot_plan_allowed": True}
