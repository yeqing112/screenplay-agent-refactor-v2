"""Sequential production image batch orchestration over existing runtimes.

The batch service owns only batch state, ordering, retry bookkeeping, and
TaskRun persistence.  GenerationExecutionService remains the execution state
authority; GenerationOrchestrator remains the provider boundary; Media
Authority remains the validation/review/promotion boundary.
"""

from __future__ import annotations

from datetime import datetime
import json
import uuid
from collections.abc import Callable
from typing import Any

from core.generation_execution_service import GenerationExecutionError, GenerationExecutionService
from core.generation_orchestrator import GenerationOrchestrator, GenerationOrchestratorError
from core.media_authority import MediaAuthorityError
from models import (
    EpisodeOutline,
    GenerationExecutionRecord,
    PromptIRPointer,
    ProductionBatch,
    ProductionBatchItem,
    Session,
    StoryboardShot,
    TaskRun,
)


BATCH_STATUSES = frozenset({"CREATED", "QUEUED", "RUNNING", "COMPLETED", "FAILED"})
BATCH_ITEM_STATUSES = frozenset({"CREATED", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "RETRYING", "SKIPPED"})
BATCH_TASK_KIND = "production_batch"


class ProductionBatchError(ValueError):
    """Stable API-safe batch error."""

    status_code = 409

    def __init__(self, message: str, *, code: str = "PRODUCTION_BATCH_INVALID", status_code: int = 409, diagnostics: Any = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.diagnostics = diagnostics if diagnostics is not None else []

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _positive(value: Any, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ProductionBatchError(f"{field} must be a positive integer", code="PRODUCTION_BATCH_INPUT_INVALID", status_code=400) from exc
    if result <= 0:
        raise ProductionBatchError(f"{field} must be a positive integer", code="PRODUCTION_BATCH_INPUT_INVALID", status_code=400)
    return result


def _resolve_episode_number(session: Any, *, project_id: int, episode_id: int) -> int:
    outline = session.query(EpisodeOutline).filter_by(id=episode_id, book_id=project_id).one_or_none()
    if outline is not None:
        return _positive(outline.episode, "episode")
    # Existing production APIs use the numeric episode scope directly.  Keep
    # that form valid when an EpisodeOutline row is not materialized yet.
    return episode_id


def _resolve_prompt_pointer(session: Any, *, project_id: int, episode_number: int, shot: StoryboardShot) -> PromptIRPointer | None:
    pointer = (
        session.query(PromptIRPointer)
        .filter_by(book_id=project_id, episode=episode_number, storyboard_shot_id=int(shot.id), target_media="IMAGE")
        .order_by(PromptIRPointer.id.desc())
        .first()
    )
    if pointer is None and int(getattr(shot, "shot_id", 0) or 0) != int(shot.id):
        pointer = (
            session.query(PromptIRPointer)
            .filter_by(book_id=project_id, episode=episode_number, storyboard_shot_id=int(shot.shot_id), target_media="IMAGE")
            .order_by(PromptIRPointer.id.desc())
            .first()
        )
    return pointer


def _task_payload(batch: ProductionBatch, items: list[ProductionBatchItem]) -> dict[str, Any]:
    return {
        "schema_version": "production_batch_runtime_v1",
        "batch_id": batch.batch_key,
        "project_id": int(batch.project_id),
        "episode_id": int(batch.episode_id),
        "episode_number": int(batch.episode_number),
        "status": batch.status,
        "total_tasks": int(batch.total_tasks or 0),
        "completed_tasks": int(batch.completed_tasks or 0),
        "failed_tasks": int(batch.failed_tasks or 0),
        "items": [
            {
                "item_id": item.id,
                "shot_id": item.shot_id,
                "execution_id": item.execution_id,
                "status": item.status,
                "priority": item.priority,
                "retry_count": item.retry_count,
                "candidate_id": item.candidate_id,
                "promotion_id": item.promotion_id,
                "error": item.error,
            }
            for item in items
        ],
    }


def _task_row(session: Any, batch: ProductionBatch) -> TaskRun | None:
    return session.query(TaskRun).filter_by(task_id=batch.task_id).one_or_none()


def _sync_task(session: Any, batch: ProductionBatch, items: list[ProductionBatchItem], *, status: str | None = None, error: str | None = None) -> None:
    row = _task_row(session, batch)
    if row is None:
        return
    now = datetime.utcnow()
    if status is not None:
        row.status = status
    row.progress = int(round((int(batch.completed_tasks or 0) / max(int(batch.total_tasks or 1), 1)) * 100))
    row.payload = json.dumps(_task_payload(batch, items), ensure_ascii=False, sort_keys=True)
    if error is not None:
        row.error = str(error)
    row.updated_at = now
    if row.status in {"completed", "failed"}:
        row.finished_at = batch.completed_at or now


def _serialize_item(item: ProductionBatchItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "shot_id": item.shot_id,
        "execution_id": item.execution_id,
        "status": item.status,
        "priority": item.priority,
        "retry_count": item.retry_count,
        "candidate_id": item.candidate_id,
        "promotion_id": item.promotion_id,
        "error": item.error,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


def serialize_production_batch(session: Any, batch: ProductionBatch) -> dict[str, Any]:
    items = (
        session.query(ProductionBatchItem)
        .filter_by(batch_id=batch.id)
        .order_by(ProductionBatchItem.priority.desc(), ProductionBatchItem.id.asc())
        .all()
    )
    task = _task_row(session, batch)
    return {
        "id": batch.id,
        "batch_id": batch.batch_key,
        "project_id": batch.project_id,
        "episode_id": batch.episode_id,
        "episode_number": batch.episode_number,
        "task_id": batch.task_id,
        "status": batch.status,
        "total_tasks": batch.total_tasks,
        "completed_tasks": batch.completed_tasks,
        "failed_tasks": batch.failed_tasks,
        "error": batch.error,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "task_run": {
            "task_id": task.task_id,
            "task_kind": task.task_kind,
            "status": task.status,
            "progress": task.progress,
            "error": task.error,
        } if task is not None else None,
        "items": [_serialize_item(item) for item in items],
    }


def _get_batch(session: Any, batch_id: str | int) -> ProductionBatch:
    text = str(batch_id or "").strip()
    row = session.query(ProductionBatch).filter_by(batch_key=text).one_or_none()
    if row is None and text.isdigit():
        row = session.query(ProductionBatch).filter_by(id=int(text)).one_or_none()
    if row is None:
        raise ProductionBatchError("Production batch does not exist.", code="PRODUCTION_BATCH_NOT_FOUND", status_code=404)
    return row


def create_production_batch(
    session: Any,
    *,
    project_id: Any,
    episode_id: Any,
    model_profile_id: str,
    priority: int = 0,
) -> ProductionBatch:
    project = _positive(project_id, "project_id")
    episode_input = _positive(episode_id, "episode_id")
    profile = str(model_profile_id or "").strip()
    if not profile:
        raise ProductionBatchError("model_profile_id is required.", code="PRODUCTION_BATCH_MODEL_PROFILE_REQUIRED", status_code=400)
    episode_number = _resolve_episode_number(session, project_id=project, episode_id=episode_input)
    shots = (
        session.query(StoryboardShot)
        .filter_by(book_id=project, episode=episode_number)
        .order_by(StoryboardShot.shot_id.asc(), StoryboardShot.id.asc())
        .all()
    )
    if not shots:
        raise ProductionBatchError("Episode has no storyboard shots.", code="PRODUCTION_BATCH_NO_SHOTS", status_code=404)
    missing = []
    pointers: list[tuple[StoryboardShot, PromptIRPointer]] = []
    for shot in shots:
        pointer = _resolve_prompt_pointer(session, project_id=project, episode_number=episode_number, shot=shot)
        if pointer is None:
            missing.append(int(shot.id))
            continue
        if str(pointer.target_media or "").upper() != "IMAGE":
            missing.append(int(shot.id))
            continue
        pointers.append((shot, pointer))
    if missing:
        raise ProductionBatchError(
            "Every batch shot requires a current IMAGE PromptIR pointer.",
            code="PRODUCTION_BATCH_PROMPT_POINTER_MISSING",
            diagnostics={"shot_ids": missing},
        )

    batch_key = "pbat-" + uuid.uuid4().hex
    task_id = "task-" + batch_key
    now = datetime.utcnow()
    batch = ProductionBatch(
        batch_key=batch_key,
        project_id=project,
        episode_id=episode_input,
        episode_number=episode_number,
        task_id=task_id,
        status="CREATED",
        total_tasks=len(pointers),
        completed_tasks=0,
        failed_tasks=0,
        created_at=now,
    )
    session.add(batch)
    session.flush()
    task = TaskRun(
        task_id=task_id,
        task_kind=BATCH_TASK_KIND,
        status="queued",
        progress=0,
        book_id=project,
        episode=episode_number,
        payload="{}",
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    service = GenerationExecutionService(session)
    for index, (shot, pointer) in enumerate(pointers):
        execution = service.create_execution(
            shot_id=int(shot.id),
            prompt_pointer_id=int(pointer.id),
            prompt_version_id=int(pointer.prompt_ir_version_id),
            model_profile_id=profile,
        )
        item = ProductionBatchItem(
            batch_id=int(batch.id),
            shot_id=int(shot.id),
            execution_id=execution.execution_id,
            status="CREATED",
            priority=int(priority) - index,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
    session.flush()
    items = session.query(ProductionBatchItem).filter_by(batch_id=batch.id).all()
    _sync_task(session, batch, items, status="queued")
    return batch


def _default_runner(session: Any, execution_id: str) -> GenerationExecutionRecord:
    return GenerationOrchestrator(session).run(execution_id)


def _fail_execution(session: Any, execution_id: str, message: str) -> None:
    service = GenerationExecutionService(session)
    row = service.get_execution(execution_id)
    if row.execution_status in {"CREATED", "QUEUED", "RUNNING", "PROVIDER_CALLED", "RETRYING"}:
        try:
            if row.execution_status == "CREATED":
                service.transition(execution_id, "QUEUED")
            if service.get_execution(execution_id).execution_status == "QUEUED":
                service.transition(execution_id, "RUNNING")
            if service.get_execution(execution_id).execution_status in {"RUNNING", "PROVIDER_CALLED"}:
                service.transition(execution_id, "FAILED", error_message=message)
        except GenerationExecutionError:
            pass


def run_production_batch(
    session: Any,
    batch_id: str | int,
    *,
    retry_failed: bool = False,
    max_retries: int = 1,
    runner: Callable[[Any, str], GenerationExecutionRecord] | None = None,
) -> ProductionBatch:
    batch = _get_batch(session, batch_id)
    retry_limit = max(int(max_retries), 0)
    if batch.status == "COMPLETED":
        raise ProductionBatchError("Completed production batch cannot be run again.", code="PRODUCTION_BATCH_ALREADY_COMPLETED")
    if batch.status == "FAILED" and not retry_failed:
        raise ProductionBatchError("Failed batch requires retry_failed=true for recovery.", code="PRODUCTION_BATCH_RETRY_REQUIRED")
    items = (
        session.query(ProductionBatchItem)
        .filter_by(batch_id=batch.id)
        .order_by(ProductionBatchItem.priority.desc(), ProductionBatchItem.id.asc())
        .all()
    )
    if not items:
        raise ProductionBatchError("Production batch has no items.", code="PRODUCTION_BATCH_NO_ITEMS")
    if batch.status == "FAILED":
        for item in items:
            if item.status == "FAILED" and int(item.retry_count or 0) < retry_limit:
                # Keep the increment at the execution retry boundary below.
                # This leaves the item eligible for the same retry pass and
                # keeps the batch item count aligned with the durable
                # GenerationExecutionRecord retry_count.
                item.status = "RETRYING"
                item.error = ""
                item.updated_at = datetime.utcnow()
    batch.status = "QUEUED"
    batch.error = ""
    _sync_task(session, batch, items, status="queued")
    batch.status = "RUNNING"
    _sync_task(session, batch, items, status="running")
    execute = runner or _default_runner
    for item in items:
        if item.status in {"SUCCEEDED", "SKIPPED"}:
            continue
        if item.status == "FAILED":
            continue
        item.status = "QUEUED"
        item.updated_at = datetime.utcnow()
        try:
            execution = GenerationExecutionService(session).get_execution(item.execution_id)
            if execution.execution_status == "FAILED":
                if int(item.retry_count or 0) >= retry_limit:
                    item.status = "FAILED"
                    continue
                item.retry_count = int(item.retry_count or 0) + 1
                GenerationExecutionService(session).transition(item.execution_id, "RETRYING")
                execution = GenerationExecutionService(session).get_execution(item.execution_id)
            result = execute(session, item.execution_id)
            if str(result.execution_status or "").upper() != "SUCCESS":
                raise ProductionBatchError("Generation execution did not reach SUCCESS.", code="PRODUCTION_BATCH_EXECUTION_FAILED")
            item.status = "SUCCEEDED"
            item.candidate_id = str(result.candidate_id or "") or None
            # Candidate validation creates the existing review gate.  It never
            # auto-approves or replaces an OfficialMediaPointer.
            if item.candidate_id:
                from core.media_authority import validate_media_candidate

                validation = validate_media_candidate(session, item.candidate_id)
                promotion = validation.get("promotion")
                item.promotion_id = getattr(promotion, "promotion_id", None) if promotion is not None else None
            item.completed_at = datetime.utcnow()
            item.updated_at = item.completed_at
        except (ProductionBatchError, GenerationOrchestratorError, GenerationExecutionError, MediaAuthorityError, Exception) as exc:
            message = str(getattr(exc, "message", exc))
            _fail_execution(session, item.execution_id, message)
            item.status = "FAILED"
            item.error = message[:4000]
            item.updated_at = datetime.utcnow()
    batch.completed_tasks = sum(1 for item in items if item.status == "SUCCEEDED")
    batch.failed_tasks = sum(1 for item in items if item.status == "FAILED")
    pending = sum(1 for item in items if item.status in {"CREATED", "QUEUED", "RUNNING", "RETRYING"})
    if batch.failed_tasks and not pending:
        batch.status = "FAILED"
        batch.error = next((item.error for item in items if item.status == "FAILED" and item.error), "One or more batch items failed.")
        batch.completed_at = datetime.utcnow()
        _sync_task(session, batch, items, status="failed", error=batch.error)
    elif batch.completed_tasks == batch.total_tasks:
        batch.status = "COMPLETED"
        batch.completed_at = datetime.utcnow()
        _sync_task(session, batch, items, status="completed")
    else:
        batch.status = "RUNNING"
        _sync_task(session, batch, items, status="running")
    session.flush()
    return batch


def get_production_batch(session: Any, batch_id: str | int) -> ProductionBatch:
    return _get_batch(session, batch_id)


__all__ = [
    "BATCH_STATUSES",
    "BATCH_ITEM_STATUSES",
    "BATCH_TASK_KIND",
    "ProductionBatchError",
    "create_production_batch",
    "run_production_batch",
    "get_production_batch",
    "serialize_production_batch",
]
