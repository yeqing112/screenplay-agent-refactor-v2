"""Shot Direction Runtime API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.shot_direction import (
    ShotDirectionError,
    create_shot_direction,
    get_shot_direction,
    inject_shot_direction,
    update_shot_direction,
    validate_shot_direction,
)
from models import Session


router = APIRouter(tags=["shot-direction-runtime"])


class ShotDirectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    shot_type: str = Field(min_length=1, validation_alias=AliasChoices("shot_type", "shotType"))
    camera_profile: dict[str, Any] = Field(validation_alias=AliasChoices("camera_profile", "cameraProfile"))
    movement_profile: dict[str, Any] = Field(validation_alias=AliasChoices("movement_profile", "movementProfile"))
    composition_profile: dict[str, Any] = Field(validation_alias=AliasChoices("composition_profile", "compositionProfile"))
    performance_profile: dict[str, Any] = Field(validation_alias=AliasChoices("performance_profile", "performanceProfile"))
    emotion_profile: dict[str, Any] = Field(validation_alias=AliasChoices("emotion_profile", "emotionProfile"))


class ShotDirectionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    shot_type: str | None = Field(default=None, validation_alias=AliasChoices("shot_type", "shotType"))
    camera_profile: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("camera_profile", "cameraProfile"))
    movement_profile: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("movement_profile", "movementProfile"))
    composition_profile: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("composition_profile", "compositionProfile"))
    performance_profile: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("performance_profile", "performanceProfile"))
    emotion_profile: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("emotion_profile", "emotionProfile"))


class ShotDirectionPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    original_prompt: str = Field(min_length=1, validation_alias=AliasChoices("original_prompt", "originalPrompt"))


def _raise(exc: ShotDirectionError) -> None:
    status = 404 if exc.code in {"SHOT_NOT_FOUND", "SHOT_DIRECTION_NOT_FOUND"} else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


@router.get("/shots/{shot_id}/direction")
def get_direction(shot_id: int):
    with Session() as session:
        try:
            return get_shot_direction(session, shot_id=shot_id)
        except ShotDirectionError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/direction", status_code=201)
def create_direction(shot_id: int, req: ShotDirectionCreateRequest):
    with Session() as session:
        try:
            result = create_shot_direction(session, shot_id=shot_id, shot_type=req.shot_type, camera_profile=req.camera_profile, movement_profile=req.movement_profile, composition_profile=req.composition_profile, performance_profile=req.performance_profile, emotion_profile=req.emotion_profile)
            session.commit()
            return result
        except ShotDirectionError as exc:
            session.rollback()
            _raise(exc)


@router.put("/shots/{shot_id}/direction")
def update_direction(shot_id: int, req: ShotDirectionUpdateRequest):
    with Session() as session:
        try:
            result = update_shot_direction(session, shot_id=shot_id, shot_type=req.shot_type, camera_profile=req.camera_profile, movement_profile=req.movement_profile, composition_profile=req.composition_profile, performance_profile=req.performance_profile, emotion_profile=req.emotion_profile)
            session.commit()
            return result
        except ShotDirectionError as exc:
            session.rollback()
            _raise(exc)


@router.get("/shots/{shot_id}/direction/validation")
def validate_direction(shot_id: int):
    with Session() as session:
        try:
            return validate_shot_direction(session, shot_id=shot_id)
        except ShotDirectionError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/direction/prompt")
def inject_direction_prompt(shot_id: int, req: ShotDirectionPromptRequest):
    with Session() as session:
        try:
            return inject_shot_direction(session, shot_id=shot_id, original_prompt=req.original_prompt)
        except ShotDirectionError as exc:
            _raise(exc)


__all__ = ["router"]
