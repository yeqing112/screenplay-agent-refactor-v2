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


def _raise(exc: VideoGenerationError) -> None:
    status = 404 if exc.code in {"SHOT_NOT_FOUND", "VIDEO_INTENT_NOT_FOUND"} else exc.status_code
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
            return execute_video_generation(session, intent_id=intent_id, provider_id=req.provider_id)
        except VideoGenerationError as exc:
            session.rollback()
            _raise(exc)


__all__ = ["router"]
