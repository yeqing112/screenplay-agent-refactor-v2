"""Provider-free Generation Execution Foundation API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.generation_execution_service import (
    GenerationExecutionError,
    GenerationExecutionService,
    serialize_generation_execution,
)
from models import Session


router = APIRouter(prefix="/generation", tags=["generation-execution-foundation"])


class CreateGenerationExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    shot_id: int = Field(gt=0, validation_alias=AliasChoices("shot_id", "shotId"))
    prompt_pointer_id: int = Field(gt=0, validation_alias=AliasChoices("prompt_pointer_id", "promptPointerId"))
    prompt_version_id: int = Field(gt=0, validation_alias=AliasChoices("prompt_version_id", "promptVersionId"))
    model_profile_id: str = Field(min_length=1, validation_alias=AliasChoices("model_profile_id", "modelProfileId"))


def _raise(exc: GenerationExecutionError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


def _create(req: CreateGenerationExecutionRequest):
    with Session() as session:
        try:
            row = GenerationExecutionService(session).create_execution(
                shot_id=req.shot_id,
                prompt_pointer_id=req.prompt_pointer_id,
                prompt_version_id=req.prompt_version_id,
                model_profile_id=req.model_profile_id,
            )
            session.commit()
            return {
                "execution_id": row.execution_id,
                "status": row.execution_status,
            }
        except GenerationExecutionError as exc:
            session.rollback()
            _raise(exc)


@router.post("/executions", status_code=201)
def create_execution(req: CreateGenerationExecutionRequest):
    """Create a durable foundation record without calling a provider."""
    return _create(req)


@router.get("/executions/{execution_id}")
def get_execution(execution_id: str):
    with Session() as session:
        try:
            row = GenerationExecutionService(session).get_execution(execution_id)
            return serialize_generation_execution(row)
        except GenerationExecutionError as exc:
            _raise(exc)


__all__ = ["router", "CreateGenerationExecutionRequest"]
