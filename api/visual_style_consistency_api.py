"""Visual style consistency runtime API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.visual_style_consistency import (
    VisualStyleConsistencyError,
    add_style_reference_asset,
    bind_episode_style,
    bind_shot_style,
    create_visual_style_profile,
    inject_style_constraints,
    list_style_references,
    serialize_visual_style_profile,
    validate_shot_style_consistency,
)
from models import Session


router = APIRouter(tags=["visual-style-consistency-runtime"])


class VisualStyleProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    book_id: int = Field(gt=0, validation_alias=AliasChoices("book_id", "bookId"))
    name: str = Field(min_length=1)
    description: str = ""
    camera_profile: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("camera_profile", "cameraProfile"))
    lighting_profile: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("lighting_profile", "lightingProfile"))
    color_profile: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("color_profile", "colorProfile"))
    composition_profile: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("composition_profile", "compositionProfile"))


class StyleReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    asset_id: str = Field(min_length=1, validation_alias=AliasChoices("asset_id", "assetId"))
    reference_type: str = Field(default="mood", validation_alias=AliasChoices("reference_type", "referenceType"))
    priority: int = Field(default=0, ge=0)
    visual_reference_asset_id: int | None = Field(default=None, validation_alias=AliasChoices("visual_reference_asset_id", "visualReferenceAssetId"))
    asset_version_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_version_id", "assetVersionId"))
    constraint_snapshot: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("constraint_snapshot", "constraintSnapshot"))


class StyleBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    style_id: int | str = Field(validation_alias=AliasChoices("style_id", "styleId"))
    reference_asset_ids: list[int | str] = Field(default_factory=list, validation_alias=AliasChoices("reference_asset_ids", "referenceAssetIds"))
    style_rules: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("style_rules", "styleRules"))
    constraint_snapshot: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("constraint_snapshot", "constraintSnapshot"))
    asset_authority_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_authority_id", "assetAuthorityId"))
    asset_version_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_version_id", "assetVersionId"))


class StylePromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    original_prompt: str = Field(min_length=1, validation_alias=AliasChoices("original_prompt", "originalPrompt"))


def _raise(exc: VisualStyleConsistencyError) -> None:
    status = 404 if exc.code in {"STYLE_PROFILE_NOT_FOUND", "SHOT_NOT_FOUND", "STYLE_REFERENCE_ASSET_NOT_FOUND"} else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


@router.post("/styles", status_code=201)
def create_style(req: VisualStyleProfileRequest):
    with Session() as session:
        try:
            result = create_visual_style_profile(session, book_id=req.book_id, name=req.name, description=req.description, camera_profile=req.camera_profile, lighting_profile=req.lighting_profile, color_profile=req.color_profile, composition_profile=req.composition_profile)
            session.commit()
            return result
        except VisualStyleConsistencyError as exc:
            session.rollback()
            _raise(exc)


@router.get("/styles/{style_id}")
def get_style(style_id: str):
    with Session() as session:
        try:
            return serialize_visual_style_profile(session, style_id)
        except VisualStyleConsistencyError as exc:
            _raise(exc)


@router.post("/styles/{style_id}/references", status_code=201)
def add_reference(style_id: str, req: StyleReferenceRequest):
    with Session() as session:
        try:
            result = add_style_reference_asset(session, style_id=style_id, asset_id=req.asset_id, reference_type=req.reference_type, priority=req.priority, visual_reference_asset_id=req.visual_reference_asset_id, asset_version_id=req.asset_version_id, constraint_snapshot=req.constraint_snapshot)
            session.commit()
            return result
        except VisualStyleConsistencyError as exc:
            session.rollback()
            _raise(exc)


@router.get("/styles/{style_id}/references")
def get_style_references(style_id: str):
    with Session() as session:
        try:
            return {"style_id": style_id, "references": list_style_references(session, style_id)}
        except VisualStyleConsistencyError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/style", status_code=201)
def bind_style(shot_id: int, req: StyleBindingRequest):
    with Session() as session:
        try:
            result = bind_shot_style(session, shot_id=shot_id, style_id=req.style_id, reference_asset_ids=req.reference_asset_ids, style_rules=req.style_rules, constraint_snapshot=req.constraint_snapshot, asset_authority_id=req.asset_authority_id, asset_version_id=req.asset_version_id)
            session.commit()
            return result
        except VisualStyleConsistencyError as exc:
            session.rollback()
            _raise(exc)


@router.post("/episodes/{book_id}/{episode}/style", status_code=201)
def bind_default_style(book_id: int, episode: int, req: StyleBindingRequest):
    with Session() as session:
        try:
            result = bind_episode_style(session, book_id=book_id, episode=episode, style_id=req.style_id, reference_asset_ids=req.reference_asset_ids, style_rules=req.style_rules, constraint_snapshot=req.constraint_snapshot, asset_authority_id=req.asset_authority_id, asset_version_id=req.asset_version_id)
            session.commit()
            return result
        except VisualStyleConsistencyError as exc:
            session.rollback()
            _raise(exc)


@router.get("/shots/{shot_id}/style/validation")
def validate_style(shot_id: int):
    with Session() as session:
        try:
            return validate_shot_style_consistency(session, shot_id=shot_id)
        except VisualStyleConsistencyError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/style/prompt")
def inject_style_prompt(shot_id: int, req: StylePromptRequest):
    with Session() as session:
        try:
            return inject_style_constraints(session, shot_id=shot_id, original_prompt=req.original_prompt)
        except VisualStyleConsistencyError as exc:
            _raise(exc)


__all__ = ["router"]
