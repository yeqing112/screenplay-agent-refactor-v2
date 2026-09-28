"""Automatic keyframe planning API over the existing authoring runtime."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.automatic_keyframe_authoring import (
    AutomaticKeyframePlanError,
    compile_keyframe_plan,
    get_keyframe_plan,
    plan_keyframes,
    review_keyframe_plan,
)
from models import Session


router = APIRouter(tags=["automatic-keyframe-authoring"])


class AutomaticKeyframeGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    created_by: str = Field(default="automatic-keyframe-planner", validation_alias=AliasChoices("created_by", "createdBy"))


class AutomaticKeyframeReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    decision: str
    reviewer: str = "human-review"
    note: str = ""
    frames: list[dict[str, Any]] | None = None


def _raise(exc: AutomaticKeyframePlanError) -> None:
    status = 404 if exc.code in {"SHOT_NOT_FOUND", "PLAN_NOT_FOUND"} else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


@router.post("/shots/{shot_id}/keyframe-plan/generate", status_code=201)
def generate_keyframe_plan(shot_id: int, req: AutomaticKeyframeGenerateRequest):
    with Session() as session:
        try:
            payload = plan_keyframes(session, shot_id=shot_id, created_by=req.created_by)
            session.commit()
            return {"plan": payload, "status": payload["status"], "provider_calls": {"llm": 0, "image": 0, "video": 0}, "human_review_required": True}
        except AutomaticKeyframePlanError as exc:
            session.rollback()
            _raise(exc)


@router.get("/shots/{shot_id}/keyframe-plan")
def read_keyframe_plan(shot_id: int, version: int | None = None):
    with Session() as session:
        try:
            return {"plan": get_keyframe_plan(session, shot_id=shot_id, version=version), "provider_calls": {"llm": 0, "image": 0, "video": 0}}
        except AutomaticKeyframePlanError as exc:
            session.commit()
            _raise(exc)


@router.post("/shots/{shot_id}/keyframe-plan/{version}/review", status_code=201)
def review_keyframe_plan_route(shot_id: int, version: int, req: AutomaticKeyframeReviewRequest):
    with Session() as session:
        try:
            payload = review_keyframe_plan(session, shot_id=shot_id, version=version, decision=req.decision, reviewer=req.reviewer, note=req.note, frames=req.frames)
            session.commit()
            return {"plan": payload, "provider_calls": {"llm": 0, "image": 0, "video": 0}, "human_review_required": payload["status"] != "COMPILED"}
        except AutomaticKeyframePlanError as exc:
            session.commit() if exc.code == "PLAN_STALE" else session.rollback()
            _raise(exc)


@router.post("/shots/{shot_id}/keyframe-plan/{version}/compile", status_code=201)
def compile_keyframe_plan_route(shot_id: int, version: int):
    with Session() as session:
        try:
            payload = compile_keyframe_plan(session, shot_id=shot_id, version=version)
            session.commit()
            return payload
        except AutomaticKeyframePlanError as exc:
            session.commit() if exc.code == "PLAN_STALE" else session.rollback()
            _raise(exc)


__all__ = ["router"]
