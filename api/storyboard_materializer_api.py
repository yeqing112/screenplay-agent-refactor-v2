"""Explicitly confirmed production Storyboard materialization endpoint."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from core.storyboard_materializer import materialize_storyboard_from_shot_plan
from core.prompt_ir_compiler import compile_phase_a, verbalize_phase_b_deterministic
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
                phase_a = compile_phase_a(draft)
                verbalized = verbalize_phase_b_deterministic(phase_a)
                row = StoryboardShot(book_id=book_id, episode=episode, scene_name=draft["scene_name"], shot_id=draft["shot_id"], duration=draft["duration"], camera_angle=draft["camera_angle"], camera_movement=draft["camera_movement"], camera_speed=draft["camera_speed"], shot_purpose=draft["shot_purpose"], start_state=json.dumps(draft["start_state"], ensure_ascii=False) if isinstance(draft["start_state"], (dict, list)) else draft["start_state"], action_process=draft["action_process"], end_state=json.dumps(draft["end_state"], ensure_ascii=False) if isinstance(draft["end_state"], (dict, list)) else draft["end_state"], visual_prompt_static=verbalized["static_prompt"], visual_prompt_motion=verbalized["motion_prompt"], visual_prompt_final=verbalized["negative_prompt"], meta_info=json.dumps({**draft["meta_info"], "workflow_profile": "production", "prompt_compiler": phase_a}, ensure_ascii=False), execution_status="succeeded", quality_status="qualified" if phase_a["phase_a_status"] == "pass" else "needs_review", production_status="blocked", workflow_profile="production", created_at=datetime.now(), updated_at=datetime.now())
                session.add(row); created.append(draft["plan_shot_id"])
        session.commit()
        return {"confirmed": True, "mutated": bool(created), "materialized_count": len(created), "plan_shot_ids": created, "production_status": "blocked", "llm_called": False}
