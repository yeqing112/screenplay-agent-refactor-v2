"""Keyframe Authoring Runtime API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.keyframe_authoring import (
    KeyframeAuthoringError,
    bind_keyframe_asset,
    create_keyframe_prompt_version,
    create_keyframe_sequence,
    get_keyframe_sequence,
    inject_keyframe_constraints,
    update_keyframe,
    validate_keyframe_sequence,
)
from models import Session


router = APIRouter(tags=["keyframe-authoring-runtime"])


class KeyframeSequenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    duration: float = Field(gt=0)
    frame_plan: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("frame_plan", "framePlan"))
    frames: list[dict[str, Any]] = Field(min_length=2)


class KeyframeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: str | None = None
    frame_type: str | None = Field(default=None, validation_alias=AliasChoices("frame_type", "frameType"))
    time: float | None = None
    time_seconds: float | None = Field(default=None, validation_alias=AliasChoices("time_seconds", "timeSeconds"))
    description: str | None = None
    camera_state: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("camera_state", "cameraState"))
    character_state: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("character_state", "characterState"))
    scene_state: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("scene_state", "sceneState"))
    emotion_state: dict[str, Any] | None = Field(default=None, validation_alias=AliasChoices("emotion_state", "emotionState"))
    camera_motion: str | None = Field(default=None, validation_alias=AliasChoices("camera_motion", "cameraMotion"))
    character_motion: str | None = Field(default=None, validation_alias=AliasChoices("character_motion", "characterMotion"))
    environment_motion: str | None = Field(default=None, validation_alias=AliasChoices("environment_motion", "environmentMotion"))
    emotion_transition: str | None = Field(default=None, validation_alias=AliasChoices("emotion_transition", "emotionTransition"))


class KeyframePromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    original_prompt: str = Field(min_length=1, validation_alias=AliasChoices("original_prompt", "originalPrompt"))
    prompt_id: str | None = Field(default=None, validation_alias=AliasChoices("prompt_id", "promptId"))
    prompt_structure: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("prompt_structure", "promptStructure"))


class KeyframeAssetBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    asset_type: str = Field(validation_alias=AliasChoices("asset_type", "assetType"))
    authority_id: str = Field(validation_alias=AliasChoices("authority_id", "authorityId"))
    version_id: str = Field(validation_alias=AliasChoices("version_id", "versionId"))
    is_primary: bool = Field(default=False, validation_alias=AliasChoices("is_primary", "isPrimary"))


def _raise(exc: KeyframeAuthoringError) -> None:
    status = 404 if exc.code in {"SHOT_NOT_FOUND", "KEYFRAME_SEQUENCE_NOT_FOUND", "KEYFRAME_NOT_FOUND"} else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


@router.get("/shots/{shot_id}/keyframes")
def get_keyframes(shot_id: int):
    with Session() as session:
        try:
            return get_keyframe_sequence(session, shot_id=shot_id)
        except KeyframeAuthoringError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/keyframes", status_code=201)
def create_keyframes(shot_id: int, req: KeyframeSequenceCreateRequest):
    with Session() as session:
        try:
            result = create_keyframe_sequence(session, shot_id=shot_id, duration=req.duration, frame_plan=req.frame_plan, frames=req.frames)
            session.commit()
            return result
        except KeyframeAuthoringError as exc:
            session.rollback()
            _raise(exc)


@router.put("/keyframes/{keyframe_id}")
def patch_keyframe(keyframe_id: int, req: KeyframeUpdateRequest):
    with Session() as session:
        try:
            values = {key: value for key, value in req.model_dump(by_alias=False).items() if value is not None}
            result = update_keyframe(session, keyframe_id=keyframe_id, values=values)
            session.commit()
            return result
        except KeyframeAuthoringError as exc:
            session.rollback()
            _raise(exc)


@router.get("/shots/{shot_id}/keyframes/validation")
def validate_keyframes(shot_id: int):
    with Session() as session:
        try:
            return validate_keyframe_sequence(session, shot_id=shot_id)
        except KeyframeAuthoringError as exc:
            _raise(exc)


@router.post("/keyframes/{keyframe_id}/prompt")
def keyframe_prompt(keyframe_id: int, req: KeyframePromptRequest):
    with Session() as session:
        try:
            if req.prompt_id:
                result = create_keyframe_prompt_version(session, keyframe_id=keyframe_id, prompt_id=req.prompt_id, original_prompt=req.original_prompt, prompt_structure=req.prompt_structure)
                session.commit()
                return result
            return inject_keyframe_constraints(session, keyframe_id=keyframe_id, original_prompt=req.original_prompt)
        except KeyframeAuthoringError as exc:
            session.rollback()
            _raise(exc)


@router.post("/keyframes/{keyframe_id}/assets", status_code=201)
def keyframe_asset(keyframe_id: int, req: KeyframeAssetBindingRequest):
    with Session() as session:
        try:
            result = bind_keyframe_asset(session, keyframe_id=keyframe_id, asset_type=req.asset_type, authority_id=req.authority_id, version_id=req.version_id, is_primary=req.is_primary)
            session.commit()
            return result
        except KeyframeAuthoringError as exc:
            session.rollback()
            _raise(exc)


__all__ = ["router"]
