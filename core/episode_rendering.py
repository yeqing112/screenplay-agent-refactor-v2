"""Episode-level rendering orchestration over the existing batch runtime."""

from __future__ import annotations

from datetime import datetime
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from core.production_batch import (
    ProductionBatchError,
    create_production_batch,
    get_production_batch,
    run_production_batch,
    serialize_production_batch,
)
from models import EpisodeOutline, EpisodeRenderItem, EpisodeRenderPlan, ProductionBatchItem, Session, StoryboardShot


RENDER_PLAN_STATUSES = frozenset({"DRAFT", "PREPARING", "GENERATING", "REVIEWING", "COMPLETED", "FAILED"})
RENDER_ITEM_STATUSES = frozenset({"PENDING", "QUEUED", "RUNNING", "COMPLETED", "FAILED", "SKIPPED"})
RENDER_STRATEGIES = frozenset({"SEQUENTIAL", "DEPENDENCY_AWARE"})


class EpisodeRenderingError(ValueError):
    status_code = 409

    def __init__(self, message: str, *, code: str = "EPISODE_RENDERING_INVALID", status_code: int = 409, diagnostics: Any = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.diagnostics = diagnostics if diagnostics is not None else []

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "diagnostics": self.diagnostics}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _dependency_list(value: Any) -> list[int]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise EpisodeRenderingError("dependency must be a JSON array", code="EPISODE_RENDER_DEPENDENCY_INVALID", status_code=400) from exc
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
        raise EpisodeRenderingError("dependency must be an array of shot ids", code="EPISODE_RENDER_DEPENDENCY_INVALID", status_code=400)
    result: list[int] = []
    for raw in value:
        try:
            shot_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise EpisodeRenderingError("dependency contains a non-integer shot id", code="EPISODE_RENDER_DEPENDENCY_INVALID", status_code=400) from exc
        if shot_id <= 0 or shot_id in result:
            raise EpisodeRenderingError("dependency contains an invalid or duplicate shot id", code="EPISODE_RENDER_DEPENDENCY_INVALID", status_code=400)
        result.append(shot_id)
    return result


def _episode_context(session: Any, episode_id: int) -> tuple[EpisodeOutline, list[StoryboardShot]]:
    outline = session.query(EpisodeOutline).filter_by(id=int(episode_id)).one_or_none()
    if outline is None:
        raise EpisodeRenderingError("Episode does not exist.", code="EPISODE_RENDER_EPISODE_NOT_FOUND", status_code=404)
    shots = (
        session.query(StoryboardShot)
        .filter_by(book_id=int(outline.book_id), episode=int(outline.episode))
        .order_by(StoryboardShot.shot_id.asc(), StoryboardShot.id.asc())
        .all()
    )
    if not shots:
        raise EpisodeRenderingError("Episode has no storyboard shots.", code="EPISODE_RENDER_NO_SHOTS", status_code=404)
    return outline, shots


def _validate_items(shots: list[StoryboardShot], item_specs: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    shot_by_id = {int(shot.id): shot for shot in shots}
    if item_specs is None:
        specs = [
            {"shot_id": int(shot.id), "order": index, "dependency": ([int(shots[index - 1].id)] if index else [])}
            for index, shot in enumerate(shots)
        ]
    else:
        specs = [dict(item) for item in item_specs]
    if len(specs) != len(shots):
        raise EpisodeRenderingError("Render plan must include every episode shot exactly once.", code="EPISODE_RENDER_SHOT_SET_INVALID", status_code=400, diagnostics={"expected": len(shots), "received": len(specs)})
    normalized: list[dict[str, Any]] = []
    seen_shots: set[int] = set()
    seen_orders: set[int] = set()
    for raw in specs:
        try:
            shot_id = int(raw.get("shot_id", raw.get("shotId")))
            order = int(raw.get("order", raw.get("order_index", raw.get("orderIndex"))))
        except (TypeError, ValueError) as exc:
            raise EpisodeRenderingError("Each render item requires integer shot_id and order.", code="EPISODE_RENDER_ITEM_INVALID", status_code=400) from exc
        if shot_id not in shot_by_id:
            raise EpisodeRenderingError("Render item references a shot outside the episode.", code="EPISODE_RENDER_SHOT_INVALID", status_code=400, diagnostics={"shot_id": shot_id})
        if shot_id in seen_shots or order in seen_orders or order < 0:
            raise EpisodeRenderingError("Render item shot and order values must be unique and nonnegative.", code="EPISODE_RENDER_ORDER_INVALID", status_code=400)
        seen_shots.add(shot_id)
        seen_orders.add(order)
        normalized.append({"shot_id": shot_id, "order": order, "dependency": _dependency_list(raw.get("dependency", raw.get("dependencies")))})
    expected_shots = set(shot_by_id)
    if seen_shots != expected_shots or seen_orders != set(range(len(shots))):
        raise EpisodeRenderingError("Render item set must cover all shots with contiguous order values starting at zero.", code="EPISODE_RENDER_ORDER_INVALID", status_code=400)
    by_shot = {item["shot_id"]: item for item in normalized}
    for item in normalized:
        for dependency in item["dependency"]:
            if dependency not in by_shot:
                raise EpisodeRenderingError("Dependency references a shot outside the render plan.", code="EPISODE_RENDER_DEPENDENCY_INVALID", status_code=400, diagnostics={"shot_id": item["shot_id"], "dependency": dependency})
            if dependency == item["shot_id"]:
                raise EpisodeRenderingError("A render item cannot depend on itself.", code="EPISODE_RENDER_DEPENDENCY_CYCLE", status_code=400, diagnostics={"shot_id": item["shot_id"]})
    graph = {item["shot_id"]: item["dependency"] for item in normalized}
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(node: int) -> None:
        if node in visiting:
            raise EpisodeRenderingError("Render plan dependency graph contains a cycle.", code="EPISODE_RENDER_DEPENDENCY_CYCLE", status_code=400, diagnostics={"shot_id": node})
        if node in visited:
            return
        visiting.add(node)
        for parent in graph[node]:
            visit(parent)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    for item in normalized:
        for dependency in item["dependency"]:
            if by_shot[dependency]["order"] >= item["order"]:
                raise EpisodeRenderingError("Dependencies must precede their dependent shot.", code="EPISODE_RENDER_ORDER_INVALID", status_code=400, diagnostics={"shot_id": item["shot_id"], "dependency": dependency})
    return sorted(normalized, key=lambda item: item["order"])


def _get_plan(session: Any, plan_id: int | str | None = None, *, episode_id: int | None = None) -> EpisodeRenderPlan:
    query = session.query(EpisodeRenderPlan)
    if plan_id is not None:
        try:
            row = query.filter_by(id=int(plan_id)).one_or_none()
        except (TypeError, ValueError):
            row = None
    elif episode_id is not None:
        row = query.filter_by(episode_id=int(episode_id)).order_by(EpisodeRenderPlan.id.desc()).first()
    else:
        row = None
    if row is None:
        raise EpisodeRenderingError("Episode render plan does not exist.", code="EPISODE_RENDER_PLAN_NOT_FOUND", status_code=404)
    return row


def _items(session: Any, plan: EpisodeRenderPlan) -> list[EpisodeRenderItem]:
    return session.query(EpisodeRenderItem).filter_by(render_plan_id=plan.id).order_by(EpisodeRenderItem.order_index.asc()).all()


def _serialize_item(item: EpisodeRenderItem) -> dict[str, Any]:
    try:
        dependencies = json.loads(item.dependency or "[]")
    except json.JSONDecodeError:
        dependencies = []
    return {
        "id": item.id,
        "episode_id": item.episode_id,
        "shot_id": item.shot_id,
        "order": item.order_index,
        "dependency": dependencies,
        "status": item.status,
        "production_batch_item_id": item.production_batch_item_id,
        "error": item.error,
    }


def serialize_episode_render_plan(session: Any, plan: EpisodeRenderPlan) -> dict[str, Any]:
    items = _items(session, plan)
    batch = get_production_batch(session, plan.production_batch_id) if plan.production_batch_id else None
    return {
        "id": plan.id,
        "episode_id": plan.episode_id,
        "project_id": plan.project_id,
        "episode_number": plan.episode_number,
        "status": plan.status,
        "render_strategy": plan.render_strategy,
        "production_batch_id": plan.production_batch_id,
        "error": plan.error,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
        "items": [_serialize_item(item) for item in items],
        "production_batch": serialize_production_batch(session, batch) if batch is not None else None,
    }


def create_episode_render_plan(session: Any, *, episode_id: int, render_strategy: str = "SEQUENTIAL", items: Sequence[Mapping[str, Any]] | None = None) -> EpisodeRenderPlan:
    strategy = str(render_strategy or "SEQUENTIAL").strip().upper()
    if strategy not in RENDER_STRATEGIES:
        raise EpisodeRenderingError("render_strategy is unsupported.", code="EPISODE_RENDER_STRATEGY_INVALID", status_code=400, diagnostics={"allowed": sorted(RENDER_STRATEGIES)})
    outline, shots = _episode_context(session, int(episode_id))
    normalized = _validate_items(shots, items)
    now = datetime.utcnow()
    plan = EpisodeRenderPlan(
        episode_id=int(outline.id),
        project_id=int(outline.book_id),
        episode_number=int(outline.episode),
        status="DRAFT",
        render_strategy=strategy,
        created_at=now,
        updated_at=now,
    )
    session.add(plan)
    session.flush()
    for item in normalized:
        session.add(EpisodeRenderItem(
            render_plan_id=int(plan.id),
            episode_id=int(outline.id),
            shot_id=int(item["shot_id"]),
            order_index=int(item["order"]),
            dependency=_json(item["dependency"]),
            status="PENDING",
            created_at=now,
            updated_at=now,
        ))
    session.flush()
    return plan


def get_episode_render_plan(session: Any, *, episode_id: int, plan_id: int | str | None = None) -> EpisodeRenderPlan:
    plan = _get_plan(session, plan_id, episode_id=episode_id)
    if int(plan.episode_id) != int(episode_id):
        raise EpisodeRenderingError("Render plan does not belong to the requested episode.", code="EPISODE_RENDER_PLAN_EPISODE_MISMATCH", status_code=409)
    return plan


def _prepare(session: Any, plan: EpisodeRenderPlan, *, model_profile_id: str) -> EpisodeRenderPlan:
    if plan.production_batch_id:
        return plan
    if plan.status not in {"DRAFT", "PREPARING", "FAILED"}:
        raise EpisodeRenderingError("Render plan cannot be prepared in its current state.", code="EPISODE_RENDER_STATE_INVALID", status_code=409, diagnostics={"status": plan.status})
    plan.status = "PREPARING"
    plan.error = ""
    plan.updated_at = datetime.utcnow()
    try:
        batch = create_production_batch(
            session,
            project_id=int(plan.project_id),
            episode_id=int(plan.episode_id),
            model_profile_id=model_profile_id,
        )
    except ProductionBatchError as exc:
        plan.status = "FAILED"
        plan.error = exc.message[:4000]
        plan.updated_at = datetime.utcnow()
        raise EpisodeRenderingError(exc.message, code=exc.code, status_code=exc.status_code, diagnostics=exc.diagnostics) from exc
    plan.production_batch_id = int(batch.id)
    batch_items = {int(item.shot_id): item for item in session.query(ProductionBatchItem).filter_by(batch_id=batch.id).all()}
    for render_item in _items(session, plan):
        batch_item = batch_items.get(int(render_item.shot_id))
        if batch_item is None:
            raise EpisodeRenderingError("Production batch is missing a render-plan shot.", code="EPISODE_RENDER_BATCH_SHOT_MISSING", diagnostics={"shot_id": render_item.shot_id})
        batch_item.priority = -int(render_item.order_index)
        render_item.production_batch_item_id = int(batch_item.id)
        render_item.status = "QUEUED"
        render_item.updated_at = datetime.utcnow()
    session.flush()
    return plan


def render_episode(
    session: Any,
    *,
    episode_id: int,
    model_profile_id: str = "shapi-image",
    plan_id: int | str | None = None,
    retry_failed: bool = False,
    max_retries: int = 1,
    runner: Callable[[Any, str], Any] | None = None,
) -> EpisodeRenderPlan:
    plan = get_episode_render_plan(session, episode_id=episode_id, plan_id=plan_id)
    if plan.status == "COMPLETED":
        raise EpisodeRenderingError("Completed episode render cannot be run again.", code="EPISODE_RENDER_ALREADY_COMPLETED")
    if plan.status == "FAILED" and not retry_failed:
        raise EpisodeRenderingError("Failed render requires retry_failed=true for recovery.", code="EPISODE_RENDER_RETRY_REQUIRED")
    plan = _prepare(session, plan, model_profile_id=model_profile_id)
    plan.status = "GENERATING"
    plan.updated_at = datetime.utcnow()
    for item in _items(session, plan):
        if item.status not in {"COMPLETED", "SKIPPED"}:
            item.status = "RUNNING"
            item.updated_at = datetime.utcnow()
    session.flush()
    batch = run_production_batch(
        session,
        int(plan.production_batch_id),
        retry_failed=retry_failed,
        max_retries=max_retries,
        runner=runner,
    )
    batch_items = {int(item.id): item for item in session.query(ProductionBatchItem).filter_by(batch_id=batch.id).all()}
    for item in _items(session, plan):
        batch_item = batch_items.get(int(item.production_batch_item_id or 0))
        if batch_item is None:
            continue
        item.status = {"SUCCEEDED": "COMPLETED", "FAILED": "FAILED"}.get(batch_item.status, item.status)
        item.error = batch_item.error or ""
        item.updated_at = datetime.utcnow()
    if batch.status == "FAILED":
        plan.status = "FAILED"
        plan.error = batch.error or "One or more render items failed."
    elif batch.status == "COMPLETED":
        # Generation has completed; review/promotion remains an explicit gate.
        plan.status = "REVIEWING"
        plan.error = ""
    else:
        plan.status = "FAILED"
        plan.error = "Production batch did not reach a terminal state."
    plan.updated_at = datetime.utcnow()
    session.flush()
    return plan


def complete_episode_render_plan(session: Any, *, episode_id: int, plan_id: int | str | None = None, reviewed: bool = False) -> EpisodeRenderPlan:
    plan = get_episode_render_plan(session, episode_id=episode_id, plan_id=plan_id)
    if plan.status != "REVIEWING":
        raise EpisodeRenderingError("Only a render plan in REVIEWING state can be completed.", code="EPISODE_RENDER_REVIEW_REQUIRED", diagnostics={"status": plan.status})
    if not reviewed:
        raise EpisodeRenderingError("Explicit review confirmation is required.", code="EPISODE_RENDER_REVIEW_CONFIRMATION_REQUIRED", status_code=400)
    items = _items(session, plan)
    if any(item.status != "COMPLETED" for item in items):
        raise EpisodeRenderingError("Every render item must complete before episode completion.", code="EPISODE_RENDER_ITEMS_INCOMPLETE", diagnostics={"statuses": {item.shot_id: item.status for item in items}})
    now = datetime.utcnow()
    plan.status = "COMPLETED"
    plan.completed_at = now
    plan.updated_at = now
    session.flush()
    return plan


__all__ = [
    "EpisodeRenderingError",
    "create_episode_render_plan",
    "get_episode_render_plan",
    "serialize_episode_render_plan",
    "render_episode",
    "complete_episode_render_plan",
]
