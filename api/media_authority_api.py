"""Phase G2 deterministic validation, promotion, and exact resolver routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.media_authority import (
    MediaAuthorityError,
    promote_media_candidate,
    resolve_current_official_media_for_shot,
    validate_media_candidate,
)
from models import Session


router = APIRouter(prefix="/api/media-authority", tags=["media-authority"])


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    validation_id: str = Field(min_length=1)
    confirmation: bool | str


def _raise(exc: MediaAuthorityError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


def _record(row) -> dict:
    return {
        "validation_id": row.validation_id,
        "candidate_id": row.candidate_id,
        "execution_id": row.execution_id,
        "candidate_fingerprint": row.candidate_fingerprint,
        "technical_validation_fingerprint": row.technical_validation_fingerprint,
        "authority_snapshot_fingerprint": row.authority_snapshot_fingerprint,
        "status": row.status,
    }


@router.post("/candidates/{candidate_id}/validate")
def validate_candidate(candidate_id: str):
    with Session() as session:
        try:
            result = validate_media_candidate(session, candidate_id)
        except MediaAuthorityError as exc:
            _raise(exc)
        return {**result, "validation": _record(result["validation"])}


@router.post("/promote")
def promote_candidate(req: PromotionRequest):
    with Session() as session:
        try:
            result = promote_media_candidate(session, req.candidate_id, req.validation_id, confirmation=req.confirmation)
        except MediaAuthorityError as exc:
            _raise(exc)
        return {
            "official_media_version_id": result["version"].official_media_version_id,
            "authority_id": result["authority"].authority_id,
            "pointer_id": result["pointer"].id,
            "reused": result["reused"],
            "provider_calls": 0,
            "llm_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
        }


@router.get("/books/{book_id}/episodes/{episode}/shots/{storyboard_shot_id}/roles/{media_role}")
def resolve_official_media(book_id: int, episode: int, storyboard_shot_id: int, media_role: str):
    with Session() as session:
        try:
            result = resolve_current_official_media_for_shot(session, book_id=book_id, episode=episode, storyboard_shot_id=storyboard_shot_id, media_role=media_role)
        except MediaAuthorityError as exc:
            _raise(exc)
        return {
            "official_media_version_id": result["version"].official_media_version_id,
            "authority_id": result["authority"].authority_id,
            "candidate_id": result["candidate"].candidate_id,
            "validation_id": result["validation"].validation_id,
            "storage_identity": result["version"].storage_identity,
            "binding_status": result["binding_status"],
            "provider_calls": 0,
            "llm_calls": 0,
            "image_calls": 0,
            "video_calls": 0,
        }
