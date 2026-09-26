"""Read-only production observability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.production_batch import ProductionBatchError
from core.production_metrics import ProductionMetricsService
from models import Session


router = APIRouter(prefix="/production/metrics", tags=["production-observability"])


def _raise(exc: ProductionBatchError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.get("/batches/{batch_id}")
def batch_dashboard(batch_id: str):
    with Session() as session:
        try:
            return ProductionMetricsService(session).batch_dashboard(batch_id)
        except ProductionBatchError as exc:
            _raise(exc)


@router.get("/summary")
def runtime_summary():
    with Session() as session:
        return ProductionMetricsService(session).summary()


__all__ = ["router", "batch_dashboard", "runtime_summary"]
