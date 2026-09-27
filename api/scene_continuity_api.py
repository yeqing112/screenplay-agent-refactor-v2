"""Scene Continuity Runtime API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.scene_continuity import (
    SceneContinuityError,
    add_scene_reference_asset,
    bind_shot_scene,
    create_scene_identity,
    get_scene_identity,
    inject_scene_constraints,
    list_scene_references,
    serialize_scene_identity,
    validate_scene_continuity,
)
from models import Session


router = APIRouter(tags=["scene-continuity-runtime"])


class SceneIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    book_id: int = Field(gt=0, validation_alias=AliasChoices("book_id", "bookId"))
    name: str = Field(min_length=1)
    scene_id: str = Field(default="", validation_alias=AliasChoices("scene_id", "sceneId"))
    description: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    environment_profile: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("environment_profile", "environmentProfile"))


class SceneReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    asset_id: str = Field(min_length=1, validation_alias=AliasChoices("asset_id", "assetId"))
    reference_type: str = Field(default="overview", validation_alias=AliasChoices("reference_type", "referenceType"))
    priority: int = Field(default=0, ge=0)
    visual_reference_asset_id: int | None = Field(default=None, validation_alias=AliasChoices("visual_reference_asset_id", "visualReferenceAssetId"))
    asset_version_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_version_id", "assetVersionId"))
    constraint_snapshot: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("constraint_snapshot", "constraintSnapshot"))


class ShotSceneBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scene_id: int | str = Field(validation_alias=AliasChoices("scene_id", "sceneId"))
    reference_asset_ids: list[int | str] = Field(default_factory=list, validation_alias=AliasChoices("reference_asset_ids", "referenceAssetIds"))
    environment_rules: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("environment_rules", "environmentRules"))
    constraint_snapshot: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("constraint_snapshot", "constraintSnapshot"))
    asset_authority_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_authority_id", "assetAuthorityId"))
    asset_version_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_version_id", "assetVersionId"))


class ScenePromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    original_prompt: str = Field(min_length=1, validation_alias=AliasChoices("original_prompt", "originalPrompt"))


def _raise(exc: SceneContinuityError) -> None:
    status = 404 if exc.code in {"SCENE_IDENTITY_NOT_FOUND", "SHOT_NOT_FOUND", "SCENE_REFERENCE_ASSET_NOT_FOUND"} else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


@router.post("/scenes", status_code=201)
def create_scene(req: SceneIdentityRequest):
    with Session() as session:
        try:
            result = create_scene_identity(session, book_id=req.book_id, name=req.name, scene_id=req.scene_id, description=req.description, attributes=req.attributes, environment_profile=req.environment_profile)
            session.commit()
            return result
        except SceneContinuityError as exc:
            session.rollback(); _raise(exc)


@router.get("/scenes/{scene_id}")
def get_scene(scene_id: str):
    with Session() as session:
        try:
            return serialize_scene_identity(session, scene_id)
        except SceneContinuityError as exc:
            _raise(exc)


@router.post("/scenes/{scene_id}/references", status_code=201)
def add_reference(scene_id: str, req: SceneReferenceRequest):
    with Session() as session:
        try:
            result = add_scene_reference_asset(session, scene_id=scene_id, asset_id=req.asset_id, reference_type=req.reference_type, priority=req.priority, visual_reference_asset_id=req.visual_reference_asset_id, asset_version_id=req.asset_version_id, constraint_snapshot=req.constraint_snapshot)
            session.commit(); return result
        except SceneContinuityError as exc:
            session.rollback(); _raise(exc)


@router.get("/scenes/{scene_id}/references")
def get_scene_references(scene_id: str):
    with Session() as session:
        try:
            return {"scene_id": scene_id, "references": list_scene_references(session, scene_id)}
        except SceneContinuityError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/scene", status_code=201)
def bind_scene(shot_id: int, req: ShotSceneBindingRequest):
    with Session() as session:
        try:
            result = bind_shot_scene(session, shot_id=shot_id, scene_id=req.scene_id, reference_asset_ids=req.reference_asset_ids, environment_rules=req.environment_rules, constraint_snapshot=req.constraint_snapshot, asset_authority_id=req.asset_authority_id, asset_version_id=req.asset_version_id)
            session.commit(); return result
        except SceneContinuityError as exc:
            session.rollback(); _raise(exc)


@router.get("/shots/{shot_id}/scene/validation")
def validate_scene(shot_id: int):
    with Session() as session:
        try:
            return validate_scene_continuity(session, shot_id=shot_id)
        except SceneContinuityError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/scene/prompt")
def inject_scene_prompt(shot_id: int, req: ScenePromptRequest):
    with Session() as session:
        try:
            return inject_scene_constraints(session, shot_id=shot_id, original_prompt=req.original_prompt)
        except SceneContinuityError as exc:
            _raise(exc)


__all__ = ["router"]
