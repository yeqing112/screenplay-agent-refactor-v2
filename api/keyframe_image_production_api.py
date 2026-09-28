"""Keyframe scoped convenience facade over the canonical production runtime."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.keyframe_image_production import (
    KeyframeImageProductionError,
    get_keyframe_image_production,
    produce_keyframe_image,
    promote_keyframe_image,
)
from models import Session


router = APIRouter(tags=["keyframe-image-production"])


class ProduceKeyframeImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    model_profile_id: str | None = Field(default=None, validation_alias="modelProfileId")
    fixture: bool = True


class ReviewKeyframeImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    validation_id: str = Field(validation_alias="validationId", min_length=1)
    reviewer: str = Field(min_length=1)
    decision: str = "APPROVE"
    review_notes: str = Field(default="", validation_alias="reviewNotes")


def _raise(exc: KeyframeImageProductionError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/keyframes/{keyframe_id}/image-production")
def produce(keyframe_id: int, req: ProduceKeyframeImageRequest):
    with Session() as session:
        try:
            result = produce_keyframe_image(session, keyframe_id=keyframe_id, model_profile_id=req.model_profile_id, fixture=req.fixture)
            return result
        except KeyframeImageProductionError as exc:
            session.rollback()
            _raise(exc)


@router.get("/keyframes/{keyframe_id}/image-production")
def status(keyframe_id: int):
    with Session() as session:
        try:
            return get_keyframe_image_production(session, keyframe_id=keyframe_id)
        except KeyframeImageProductionError as exc:
            _raise(exc)


@router.post("/keyframes/{keyframe_id}/image-production/review")
def review(keyframe_id: int, req: ReviewKeyframeImageRequest):
    with Session() as session:
        try:
            return promote_keyframe_image(session, keyframe_id=keyframe_id, validation_id=req.validation_id, reviewer=req.reviewer, decision=req.decision, review_notes=req.review_notes)
        except KeyframeImageProductionError as exc:
            session.rollback()
            _raise(exc)


__all__ = ["router", "ProduceKeyframeImageRequest", "ReviewKeyframeImageRequest"]
