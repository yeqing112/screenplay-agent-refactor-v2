"""Explicitly confirmed production Storyboard materialization endpoint."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.storyboard_materializer import materialize_storyboard_from_shot_plan
from models import Script, Session, ShotPlan, StoryboardShot

router = APIRouter(prefix="/api/books", tags=["storyboard-materializer"])


class MaterializeRequest(BaseModel):
    confirmed: bool = False
    plan_id: int | None = Field(default=None, validation_alias=AliasChoices("plan_id", "planId"))


@router.post("/{book_id}/episodes/{episode}/storyboard/materialize")
def materialize_storyboard(book_id: int, episode: int, req: MaterializeRequest) -> dict:
    if not req.confirmed:
        raise HTTPException(status_code=409, detail="Storyboard materialization requires confirmed=true.")
    with Session() as session:
        query = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode, status="approved")
        if req.plan_id:
            query = query.filter_by(id=req.plan_id)
        plans = query.order_by(ShotPlan.scene_name, ShotPlan.revision.desc(), ShotPlan.id.desc()).all()
        if not plans:
            raise HTTPException(status_code=409, detail="No approved ShotPlan is available for materialization.")
        created = []
        for plan in plans:
            raw = json.loads(plan.shots or "[]")
            drafts = materialize_storyboard_from_shot_plan({"scene_name": plan.scene_name, "shots": raw, "evidence_fingerprint": plan.evidence_fingerprint})
            existing_refs = {str((json.loads(row.meta_info or "{}").get("shot_plan_ref") or {}).get("plan_shot_id") or "") for row in session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode, scene_name=plan.scene_name).all()}
            for draft in drafts:
                if draft["plan_shot_id"] in existing_refs:
                    continue
                row = StoryboardShot(book_id=book_id, episode=episode, scene_name=draft["scene_name"], shot_id=draft["shot_id"], duration=draft["duration"], camera_angle=draft["camera_angle"], camera_movement=draft["camera_movement"], camera_speed=draft["camera_speed"], shot_purpose=draft["shot_purpose"], start_state=json.dumps(draft["start_state"], ensure_ascii=False) if isinstance(draft["start_state"], (dict, list)) else draft["start_state"], action_process=draft["action_process"], end_state=json.dumps(draft["end_state"], ensure_ascii=False) if isinstance(draft["end_state"], (dict, list)) else draft["end_state"], meta_info=json.dumps({**draft["meta_info"], "workflow_profile": "production"}, ensure_ascii=False), execution_status="succeeded", quality_status="qualified", production_status="blocked", workflow_profile="production", created_at=datetime.now(), updated_at=datetime.now())
                session.add(row); created.append(draft["plan_shot_id"])
        session.commit()
        return {"confirmed": True, "mutated": bool(created), "materialized_count": len(created), "plan_shot_ids": created, "production_status": "blocked", "llm_called": False}

