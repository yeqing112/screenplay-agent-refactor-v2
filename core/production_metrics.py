"""Read-only production observability metrics over existing runtime records.

The service deliberately creates no metric tables and does not copy runtime
facts.  Every response is computed from ProductionBatch, GenerationExecution,
Model Registry execution fields, and the existing media authority records.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from core.production_batch import ProductionBatchError, get_production_batch
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    MediaPromotionRecord,
    ProductionBatch,
    ProductionBatchItem,
)


METRICS_SCHEMA_VERSION = "production_observability_runtime_v1"
_SUCCESS_STATUSES = frozenset({"SUCCESS", "SUCCEEDED", "COMPLETED"})
_FAILED_STATUSES = frozenset({"FAILED", "FAILURE", "ERROR"})
_RUNNING_BATCH_STATUSES = frozenset({"RUNNING"})
_PENDING_BATCH_STATUSES = frozenset({"CREATED", "QUEUED"})
_COMPLETED_ITEM_STATUSES = frozenset({"SUCCEEDED", "COMPLETED"})
_FAILED_ITEM_STATUSES = frozenset({"FAILED"})
_RUNNING_ITEM_STATUSES = frozenset({"RUNNING"})
_PENDING_ITEM_STATUSES = frozenset({"CREATED", "QUEUED", "RETRYING"})


def _status(value: Any) -> str:
    return str(value or "").strip().upper()


def _provider_name(value: Any) -> str:
    return str(value or "").strip() or "unknown"


def _duration_ms(row: GenerationExecutionRecord) -> float | None:
    """Return a completed execution duration from persisted timestamps."""
    started = row.submitted_at or row.created_at
    completed = row.completed_at
    if started is None or completed is None:
        return None
    try:
        return max((completed - started).total_seconds() * 1000.0, 0.0)
    except (AttributeError, TypeError):
        return None


def _average(values: Iterable[float]) -> float:
    values = list(values)
    return round(sum(values) / len(values), 2) if values else 0.0


class ProductionMetricsService:
    """Aggregate current production facts without introducing a second store."""

    def __init__(self, session: Any):
        self.session = session

    def _batch(self, batch_id: str | int) -> ProductionBatch:
        try:
            return get_production_batch(self.session, batch_id)
        except ProductionBatchError:
            raise

    def _batches(self, batch_id: str | int | None = None) -> list[ProductionBatch]:
        if batch_id is None:
            return self.session.query(ProductionBatch).order_by(ProductionBatch.id.asc()).all()
        return [self._batch(batch_id)]

    def _items(self, batch_id: str | int | None = None) -> list[ProductionBatchItem]:
        query = self.session.query(ProductionBatchItem)
        if batch_id is not None:
            batch = self._batch(batch_id)
            query = query.filter(ProductionBatchItem.batch_id == int(batch.id))
        return query.order_by(ProductionBatchItem.id.asc()).all()

    def _executions(self, batch_id: str | int | None = None) -> list[GenerationExecutionRecord]:
        if batch_id is None:
            return self.session.query(GenerationExecutionRecord).order_by(GenerationExecutionRecord.id.asc()).all()
        execution_ids = [item.execution_id for item in self._items(batch_id)]
        if not execution_ids:
            return []
        return (
            self.session.query(GenerationExecutionRecord)
            .filter(GenerationExecutionRecord.execution_id.in_(execution_ids))
            .order_by(GenerationExecutionRecord.id.asc())
            .all()
        )

    def batch_metrics(self, batch_id: str | int | None = None) -> dict[str, int]:
        """Return batch/item state counts for one batch or the whole runtime."""
        batches = self._batches(batch_id)
        if batch_id is not None:
            items = self._items(batch_id)
            statuses = [_status(item.status) for item in items]
            return {
                "total": len(items),
                "completed": sum(item_status in _COMPLETED_ITEM_STATUSES for item_status in statuses),
                "failed": sum(item_status in _FAILED_ITEM_STATUSES for item_status in statuses),
                "running": sum(item_status in _RUNNING_ITEM_STATUSES for item_status in statuses),
                "pending": sum(item_status in _PENDING_ITEM_STATUSES for item_status in statuses),
            }

        statuses = [_status(batch.status) for batch in batches]
        return {
            "total": len(batches),
            "completed": sum(batch_status == "COMPLETED" for batch_status in statuses),
            "failed": sum(batch_status == "FAILED" for batch_status in statuses),
            "running": sum(batch_status in _RUNNING_BATCH_STATUSES for batch_status in statuses),
            "pending": sum(batch_status in _PENDING_BATCH_STATUSES for batch_status in statuses),
        }

    def execution_metrics(self, batch_id: str | int | None = None) -> dict[str, int | float]:
        rows = self._executions(batch_id)
        statuses = [_status(row.execution_status) for row in rows]
        durations = [duration for row in rows if (duration := _duration_ms(row)) is not None]
        return {
            "success_count": sum(status in _SUCCESS_STATUSES for status in statuses),
            "failed_count": sum(status in _FAILED_STATUSES for status in statuses),
            "average_duration": _average(durations),
            "average_duration_ms": _average(durations),
            "retry_count": sum(int(row.retry_count or 0) for row in rows),
            "total": len(rows),
        }

    def provider_metrics(self, batch_id: str | int | None = None) -> list[dict[str, int | float | str]]:
        grouped: dict[str, list[GenerationExecutionRecord]] = defaultdict(list)
        for row in self._executions(batch_id):
            grouped[_provider_name(row.provider)].append(row)

        result: list[dict[str, int | float | str]] = []
        for provider in sorted(grouped):
            rows = grouped[provider]
            statuses = [_status(row.execution_status) for row in rows]
            success_count = sum(status in _SUCCESS_STATUSES for status in statuses)
            failure_count = sum(status in _FAILED_STATUSES for status in statuses)
            latencies = [float(row.latency_ms) for row in rows if row.latency_ms is not None]
            request_count = len(rows)
            result.append(
                {
                    "provider_name": provider,
                    "request_count": request_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "success_rate": round(success_count / request_count, 4) if request_count else 0.0,
                    "failure_rate": round(failure_count / request_count, 4) if request_count else 0.0,
                    "average_latency": _average(latencies),
                    "average_latency_ms": _average(latencies),
                }
            )
        return result

    def asset_metrics(self, batch_id: str | int | None = None) -> dict[str, int | float]:
        candidate_query = self.session.query(MediaCandidateRecord)
        promotion_query = self.session.query(MediaPromotionRecord)
        if batch_id is not None:
            execution_ids = [item.execution_id for item in self._items(batch_id)]
            if not execution_ids:
                return {
                    "candidate_count": 0,
                    "approved_count": 0,
                    "rejected_count": 0,
                    "promotion_rate": 0.0,
                }
            candidate_query = candidate_query.filter(MediaCandidateRecord.execution_id.in_(execution_ids))
            promotion_query = promotion_query.filter(MediaPromotionRecord.execution_id.in_(execution_ids))

        candidates = candidate_query.all()
        promotions = promotion_query.all()
        approved_count = sum(_status(row.review_status) == "APPROVED" or _status(row.decision) == "APPROVE" for row in promotions)
        rejected_count = sum(_status(row.review_status) == "REJECTED" or _status(row.decision) == "REJECT" for row in promotions)
        candidate_count = len(candidates)
        return {
            "candidate_count": candidate_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "promotion_rate": round(approved_count / candidate_count, 4) if candidate_count else 0.0,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": METRICS_SCHEMA_VERSION,
            "batch_metrics": self.batch_metrics(),
            "execution_metrics": self.execution_metrics(),
            "provider_metrics": self.provider_metrics(),
            "asset_metrics": self.asset_metrics(),
        }

    def batch_dashboard(self, batch_id: str | int) -> dict[str, Any]:
        batch = self._batch(batch_id)
        return {
            "schema_version": METRICS_SCHEMA_VERSION,
            "batch": {
                "id": int(batch.id),
                "batch_id": batch.batch_key,
                "project_id": int(batch.project_id),
                "episode_id": int(batch.episode_id),
                "episode_number": int(batch.episode_number),
                "task_id": batch.task_id,
                "status": batch.status,
            },
            "batch_metrics": self.batch_metrics(batch.batch_key),
            "execution_metrics": self.execution_metrics(batch.batch_key),
            "provider_metrics": self.provider_metrics(batch.batch_key),
            "asset_metrics": self.asset_metrics(batch.batch_key),
        }


def production_metrics_summary(session: Any) -> dict[str, Any]:
    return ProductionMetricsService(session).summary()


def production_batch_dashboard(session: Any, batch_id: str | int) -> dict[str, Any]:
    return ProductionMetricsService(session).batch_dashboard(batch_id)


__all__ = [
    "METRICS_SCHEMA_VERSION",
    "ProductionMetricsService",
    "production_metrics_summary",
    "production_batch_dashboard",
]
