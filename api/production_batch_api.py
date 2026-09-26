"""Production image batch orchestration API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.production_batch import (
    ProductionBatchError,
    create_production_batch,
    get_production_batch,
    run_production_batch,
    serialize_production_batch,
)
from models import Session


router = APIRouter(prefix="/production", tags=["production-batch-runtime"])


class CreateProductionBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    project_id: int = Field(gt=0, validation_alias=AliasChoices("project_id", "projectId"))
    episode_id: int = Field(gt=0, validation_alias=AliasChoices("episode_id", "episodeId"))
    model_profile_id: str = Field(min_length=1, validation_alias=AliasChoices("model_profile_id", "modelProfileId"))
    priority: int = 0


class RunProductionBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    retry_failed: bool = Field(default=False, validation_alias=AliasChoices("retry_failed", "retryFailed"))
    max_retries: int = Field(default=1, ge=0, le=3, validation_alias=AliasChoices("max_retries", "maxRetries"))


def _raise(exc: ProductionBatchError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/batches", status_code=201)
def create_batch(req: CreateProductionBatchRequest):
    """Create one image execution per current episode shot."""
    with Session() as session:
        try:
            batch = create_production_batch(
                session,
                project_id=req.project_id,
                episode_id=req.episode_id,
                model_profile_id=req.model_profile_id,
                priority=req.priority,
            )
            session.commit()
            return serialize_production_batch(session, batch)
        except ProductionBatchError as exc:
            session.rollback()
            _raise(exc)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str):
    with Session() as session:
        try:
            return serialize_production_batch(session, get_production_batch(session, batch_id))
        except ProductionBatchError as exc:
            _raise(exc)


@router.post("/batches/{batch_id}/run")
def run_batch(batch_id: str, req: RunProductionBatchRequest | None = None):
    """Run batch items sequentially through the existing execution runtime."""
    with Session() as session:
        request = req or RunProductionBatchRequest()
        try:
            batch = run_production_batch(
                session,
                batch_id,
                retry_failed=request.retry_failed,
                max_retries=request.max_retries,
            )
            session.commit()
            return serialize_production_batch(session, batch)
        except ProductionBatchError as exc:
            session.commit()
            _raise(exc)
        except Exception:
            # GenerationOrchestrator persists its own failure transition; do
            # not discard that durable TaskRun/Execution evidence on response
            # serialization or provider boundary errors.
            session.commit()
            raise


__all__ = ["router", "CreateProductionBatchRequest", "RunProductionBatchRequest"]
