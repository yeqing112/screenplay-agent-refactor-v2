"""Character consistency runtime API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.character_consistency import (
    CharacterConsistencyError,
    add_character_reference_asset,
    bind_shot_character,
    create_character_identity,
    inject_character_constraints,
    list_character_references,
    serialize_character_identity,
    validate_shot_character_consistency,
)
from models import Session


router = APIRouter(tags=["character-consistency-runtime"])


class CharacterIdentityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    book_id: int = Field(gt=0, validation_alias=AliasChoices("book_id", "bookId"))
    name: str = Field(min_length=1)
    description: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    appearance_profile: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("appearance_profile", "appearanceProfile"))


class CharacterReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    asset_id: str = Field(min_length=1, validation_alias=AliasChoices("asset_id", "assetId"))
    reference_type: str = Field(default="portrait", validation_alias=AliasChoices("reference_type", "referenceType"))
    priority: int = Field(default=0, ge=0)
    visual_reference_asset_id: int | None = Field(default=None, validation_alias=AliasChoices("visual_reference_asset_id", "visualReferenceAssetId"))
    asset_version_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_version_id", "assetVersionId"))
    constraint_snapshot: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("constraint_snapshot", "constraintSnapshot"))


class ShotCharacterBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    character_id: int = Field(gt=0, validation_alias=AliasChoices("character_id", "characterId"))
    role: str = "supporting"
    reference_asset_ids: list[int | str] = Field(default_factory=list, validation_alias=AliasChoices("reference_asset_ids", "referenceAssetIds"))
    appearance_rules: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("appearance_rules", "appearanceRules"))
    constraint_snapshot: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("constraint_snapshot", "constraintSnapshot"))
    asset_authority_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_authority_id", "assetAuthorityId"))
    asset_version_id: str | None = Field(default=None, validation_alias=AliasChoices("asset_version_id", "assetVersionId"))


class CharacterPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    original_prompt: str = Field(min_length=1, validation_alias=AliasChoices("original_prompt", "originalPrompt"))


def _raise(exc: CharacterConsistencyError) -> None:
    status = 404 if exc.code in {"CHARACTER_IDENTITY_NOT_FOUND", "SHOT_NOT_FOUND", "CHARACTER_REFERENCE_ASSET_NOT_FOUND"} else exc.status_code
    raise HTTPException(status_code=status, detail=exc.to_dict()) from exc


@router.post("/characters", status_code=201)
def create_character(req: CharacterIdentityRequest):
    with Session() as session:
        try:
            result = create_character_identity(session, book_id=req.book_id, name=req.name, description=req.description, attributes=req.attributes, appearance_profile=req.appearance_profile)
            session.commit()
            return result
        except CharacterConsistencyError as exc:
            session.rollback()
            _raise(exc)


@router.get("/characters/{character_id}")
def get_character(character_id: int):
    with Session() as session:
        try:
            return serialize_character_identity(session, character_id)
        except CharacterConsistencyError as exc:
            _raise(exc)


@router.post("/characters/{character_id}/references", status_code=201)
def add_reference(character_id: int, req: CharacterReferenceRequest):
    with Session() as session:
        try:
            result = add_character_reference_asset(session, character_id=character_id, asset_id=req.asset_id, reference_type=req.reference_type, priority=req.priority, visual_reference_asset_id=req.visual_reference_asset_id, asset_version_id=req.asset_version_id, constraint_snapshot=req.constraint_snapshot)
            session.commit()
            return result
        except CharacterConsistencyError as exc:
            session.rollback()
            _raise(exc)


@router.get("/characters/{character_id}/references")
def get_character_references(character_id: int):
    with Session() as session:
        try:
            return {"character_id": character_id, "references": list_character_references(session, character_id)}
        except CharacterConsistencyError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/characters", status_code=201)
def bind_character(shot_id: int, req: ShotCharacterBindingRequest):
    with Session() as session:
        try:
            result = bind_shot_character(session, shot_id=shot_id, character_id=req.character_id, role=req.role, reference_asset_ids=req.reference_asset_ids, appearance_rules=req.appearance_rules, constraint_snapshot=req.constraint_snapshot, asset_authority_id=req.asset_authority_id, asset_version_id=req.asset_version_id)
            session.commit()
            return result
        except CharacterConsistencyError as exc:
            session.rollback()
            _raise(exc)


@router.get("/shots/{shot_id}/characters/validation")
def validate_shot_characters(shot_id: int):
    with Session() as session:
        try:
            return validate_shot_character_consistency(session, shot_id=shot_id)
        except CharacterConsistencyError as exc:
            _raise(exc)


@router.post("/shots/{shot_id}/characters/prompt")
def inject_shot_character_prompt(shot_id: int, req: CharacterPromptRequest):
    with Session() as session:
        try:
            return inject_character_constraints(session, shot_id=shot_id, original_prompt=req.original_prompt)
        except CharacterConsistencyError as exc:
            _raise(exc)


__all__ = ["router"]
