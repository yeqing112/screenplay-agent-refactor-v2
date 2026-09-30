"""Provider-free Retry/Regenerate business intent API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.generation_attempt_lineage import (
    GenerationAttemptLineageError,
    GenerationAttemptLineageService,
    serialize_attempt_lineage,
)
from models import Session


router = APIRouter(prefix="/generation/attempt-intents", tags=["generation-attempt-lineage"])


class CreateGenerationAttemptIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    operation_kind: str = Field(validation_alias=AliasChoices("operation_kind", "operationKind"))
    operation_idempotency_key: str = Field(min_length=1, validation_alias=AliasChoices("operation_idempotency_key", "operationIdempotencyKey"))
    source_execution_id: str | None = Field(default=None, validation_alias=AliasChoices("source_execution_id", "sourceExecutionId"))
    source_official_media_version_id: str | None = Field(default=None, validation_alias=AliasChoices("source_official_media_version_id", "sourceOfficialMediaVersionId"))
    reason: str = Field(default="", max_length=2000)
    book_id: int | None = Field(default=None, validation_alias=AliasChoices("book_id", "bookId"))
    episode: int | None = None
    storyboard_shot_id: int | None = Field(default=None, validation_alias=AliasChoices("storyboard_shot_id", "storyboardShotId"))
    target_media: str | None = Field(default=None, validation_alias=AliasChoices("target_media", "targetMedia"))


def _raise(exc: GenerationAttemptLineageError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message, "provider_calls": 0, "execution_created": False, "media_generated": False}) from exc


@router.post("", status_code=201)
def create_attempt_intent(req: CreateGenerationAttemptIntentRequest):
    with Session() as session:
        service = GenerationAttemptLineageService(session)
        try:
            kind = str(req.operation_kind or "").strip().upper()
            if kind == "RETRY":
                if not req.source_execution_id or req.source_official_media_version_id:
                    raise GenerationAttemptLineageError("Retry requires source_execution_id only", code="GENERATION_ATTEMPT_SOURCE_NOT_FOUND")
                row = service.create_retry_intent(source_execution_id=req.source_execution_id, operation_idempotency_key=req.operation_idempotency_key, reason=req.reason, book_id=req.book_id, episode=req.episode, storyboard_shot_id=req.storyboard_shot_id, target_media=req.target_media)
            elif kind == "REGENERATE":
                if not req.source_official_media_version_id or req.source_execution_id:
                    raise GenerationAttemptLineageError("Regenerate requires source_official_media_version_id only", code="GENERATION_ATTEMPT_SOURCE_NOT_FOUND")
                row = service.create_regenerate_intent(source_official_media_version_id=req.source_official_media_version_id, operation_idempotency_key=req.operation_idempotency_key, reason=req.reason, book_id=req.book_id, episode=req.episode, storyboard_shot_id=req.storyboard_shot_id, target_media=req.target_media)
            else:
                raise GenerationAttemptLineageError("operation_kind must be RETRY or REGENERATE", code="GENERATION_ATTEMPT_SOURCE_NOT_FOUND")
            session.commit()
            return serialize_attempt_lineage(row, include_confirmation=True, service=service)
        except GenerationAttemptLineageError as exc:
            session.rollback()
            _raise(exc)


@router.get("/{attempt_lineage_id}")
def get_attempt_intent(attempt_lineage_id: str):
    with Session() as session:
        try:
            row = GenerationAttemptLineageService(session).get_intent(attempt_lineage_id)
            return serialize_attempt_lineage(row)
        except GenerationAttemptLineageError as exc:
            _raise(exc)


__all__ = ["router", "CreateGenerationAttemptIntentRequest"]
