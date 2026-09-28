"""Video Generation Runtime API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.video_generation_runtime import (
    VideoGenerationError,
    create_video_generation_intent,
    execute_video_generation,
    get_video_generation_intent,
    get_video_generation_status,
)
from core.shot_video_production import (
    ShotVideoProductionError,
    execute_shot_video_production,
    get_shot_video_production,
    reconcile_video_intent,
)
from models import Session


router = APIRouter(tags=["video-generation-runtime"])


class VideoIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    duration: float = Field(gt=0)
    aspect_ratio: str = Field(min_length=1, validation_alias=AliasChoices("aspect_ratio", "aspectRatio"))
    motion_profile: dict[str, Any] = Field(validation_alias=AliasChoices("motion_profile", "motionProfile"))
    first_frame_asset: dict[str, Any] = Field(validation_alias=AliasChoices("first_frame_asset", "firstFrameAsset"))
    last_frame_asset: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("last_frame_asset", "lastFrameAsset"))
    prompt_version: str = Field(min_length=1, validation_alias=AliasChoices("prompt_version", "promptVersion"))


class VideoExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider_id: str = Field(default="mock-video", validation_alias=AliasChoices("provider_id", "providerId"))
    model_profile_id: str | None = Field(default=None, validation_alias=AliasChoices("model_profile_id", "modelProfileId"))


class ShotVideoProductionRequest(BaseModel):
    """Shot-scoped orchestration request; source assets are authority-resolved."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider_id: str = Field(default="mock-video", validation_alias=AliasChoices("provider_id", "providerId"))
    model_profile_id: str | None = Field(default=None, validation_alias=AliasChoices("model_profile_id", "modelProfileId"))


def _raise(exc: VideoGenerationError) -> None:
    status = 404 if exc.code in {"SHOT_NOT_FOUND", "VIDEO_INTENT_NOT_FOUND"} else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


def _raise_shot(exc: ShotVideoProductionError) -> None:
    status = 404 if exc.code == "SHOT_NOT_FOUND" else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


@router.get("/shots/{shot_id}/video-intent")
def get_video_intent(shot_id: int):
    with Session() as session:
        try:
            return get_video_generation_intent(session, shot_id=shot_id)
        except VideoGenerationError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/video-intent", status_code=201)
def create_video_intent(shot_id: int, req: VideoIntentRequest):
    with Session() as session:
        try:
            result = create_video_generation_intent(session, shot_id=shot_id, duration=req.duration, aspect_ratio=req.aspect_ratio, motion_profile=req.motion_profile, first_frame_asset=req.first_frame_asset, last_frame_asset=req.last_frame_asset, prompt_version=req.prompt_version)
            session.commit()
            return result
        except VideoGenerationError as exc:
            session.rollback()
            _raise(exc)


@router.post("/video-generation/{intent_id}/execute")
def execute_video_intent(intent_id: int, req: VideoExecuteRequest):
    with Session() as session:
        try:
            return execute_video_generation(session, intent_id=intent_id, provider_id=req.provider_id, model_profile_id=req.model_profile_id)
        except VideoGenerationError as exc:
            session.rollback()
            _raise(exc)


@router.get("/video-generation/{intent_id}")
def get_video_generation(intent_id: int):
    with Session() as session:
        try:
            return get_video_generation_status(session, intent_id=intent_id)
        except VideoGenerationError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/video-production", status_code=201)
def produce_shot_video(shot_id: int, req: ShotVideoProductionRequest):
    """Reconcile current authorities then dispatch the existing video runtime."""
    with Session() as session:
        try:
            return execute_shot_video_production(session, shot_id=shot_id, provider_id=req.provider_id, model_profile_id=req.model_profile_id)
        except ShotVideoProductionError as exc:
            session.rollback()
            _raise_shot(exc)
        except VideoGenerationError as exc:
            session.rollback()
            _raise(exc)


@router.get("/shots/{shot_id}/video-production")
def get_shot_video(shot_id: int):
    with Session() as session:
        try:
            return get_shot_video_production(session, shot_id=shot_id)
        except ShotVideoProductionError as exc:
            _raise_shot(exc)


@router.post("/shots/{shot_id}/video-production/reconcile", status_code=201)
def reconcile_shot_video(shot_id: int, req: ShotVideoProductionRequest):
    """Create or reuse one deterministic VideoGenerationIntent without dispatch."""
    with Session() as session:
        try:
            result = reconcile_video_intent(session, shot_id=shot_id, provider_id=req.provider_id, model_profile_id=req.model_profile_id)
            session.commit()
            return {"intent": result["intent"], "source_fingerprint": result["source"]["source_fingerprint"], "idempotent": result["idempotent"], "human_review_required": True}
        except ShotVideoProductionError as exc:
            session.rollback()
            _raise_shot(exc)


__all__ = ["router", "ShotVideoProductionRequest"]
