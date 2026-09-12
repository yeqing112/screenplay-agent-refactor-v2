from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import AliasChoices, BaseModel, Field

from core.director_benchmark import score_runtime
from models import DirectorBenchmarkRun, DirectorTreatment, SceneBlocking, Script, Session, ShotPlan

router = APIRouter(prefix="/api/books", tags=["director-benchmark"])


class BenchmarkRunRequest(BaseModel):
    sample_label: str = Field(default="", validation_alias=AliasChoices("sample_label", "sampleLabel"))
    model_id: str = Field(default="deterministic", validation_alias=AliasChoices("model_id", "modelId"))


def _json(value: str | None, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _payload(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    return {"id": row.id, "status": row.status, "beat_map": _json(getattr(row, "beat_map", "[]"), []), "unknowns": _json(getattr(row, "unknowns", "[]"), []), "shots": _json(getattr(row, "shots", "[]"), [])}


@router.get("/{book_id}/episodes/{episode}/director-benchmark")
def run_director_benchmark(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        script_row = session.query(Script).filter_by(book_id=book_id, episode=episode).order_by(Script.id.desc()).first()
        treatments = session.query(DirectorTreatment).filter_by(book_id=book_id, episode=episode).order_by(DirectorTreatment.scene_name, DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).all()
        blockings = session.query(SceneBlocking).filter_by(book_id=book_id, episode=episode).order_by(SceneBlocking.scene_name, SceneBlocking.revision.desc(), SceneBlocking.id.desc()).all()
        plans = session.query(ShotPlan).filter_by(book_id=book_id, episode=episode).order_by(ShotPlan.scene_name, ShotPlan.revision.desc(), ShotPlan.id.desc()).all()

    # Benchmark every declared scene independently. Selecting one latest row
    # for an episode can otherwise hide an unapproved or missing scene.
    script = _json(script_row.content, {}) if script_row else {}
    declared_scenes = script.get("scenes") if isinstance(script, dict) else []
    if not isinstance(declared_scenes, list):
        declared_scenes = []
    declared_names = [str(item.get("name") or "未命名场景").strip() for item in declared_scenes if isinstance(item, dict)]
    scene_names = list(dict.fromkeys(declared_names + [row.scene_name for row in treatments + blockings + plans if row.scene_name]))
    if not scene_names:
        scene_names = [""]

    def latest_by_scene(rows: list[Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for row in rows:
            result.setdefault(str(row.scene_name or ""), row)
        return result

    treatment_by_scene = latest_by_scene(treatments)
    blocking_by_scene = latest_by_scene(blockings)
    plan_by_scene = latest_by_scene(plans)
    scene_reports = []
    for scene_name in scene_names:
        scene_report = score_runtime(
            treatment=_payload(treatment_by_scene.get(scene_name)),
            blocking=_payload(blocking_by_scene.get(scene_name)),
            shot_plan=_payload(plan_by_scene.get(scene_name)),
        )
        scene_reports.append({"scene_name": scene_name or "未命名场景", "report": scene_report})

    checks: list[dict[str, Any]] = []
    for scene in scene_reports:
        for check in scene["report"].get("checks", []):
            checks.append({
                **check,
                "key": f"{scene['scene_name']}::{check.get('key')}",
                "label": f"{scene['scene_name']}：{check.get('label')}",
            })
    passed = sum(1 for check in checks if check.get("passed"))
    report = {
        "score": round((passed / len(checks)) * 100, 2) if checks else 0,
        "passed": passed,
        "total": len(checks),
        "status": "pass" if checks and passed == len(checks) else "needs_work",
        "checks": checks,
        "scene_count": len(scene_reports),
        "scene_reports": scene_reports,
    }
    return {"book_id": book_id, "episode": episode, "report": report, "mutated": False}


@router.post("/{book_id}/episodes/{episode}/director-benchmark/runs")
def persist_director_benchmark(book_id: int, episode: int, req: BenchmarkRunRequest) -> dict[str, Any]:
    current = run_director_benchmark(book_id, episode)
    with Session() as session:
        row = DirectorBenchmarkRun(book_id=book_id, episode=episode, sample_label=req.sample_label.strip(), model_id=req.model_id.strip() or "deterministic", report=json.dumps(current["report"], ensure_ascii=False))
        session.add(row); session.commit(); session.refresh(row)
        return {"run_id": row.id, "book_id": book_id, "episode": episode, "sample_label": row.sample_label, "model_id": row.model_id, "report": current["report"], "mutated": True}


@router.get("/{book_id}/episodes/{episode}/director-benchmark/runs")
def list_director_benchmark_runs(book_id: int, episode: int) -> dict[str, Any]:
    with Session() as session:
        rows = session.query(DirectorBenchmarkRun).filter_by(book_id=book_id, episode=episode).order_by(DirectorBenchmarkRun.id.desc()).all()
    return {"items": [{"run_id": row.id, "sample_label": row.sample_label, "model_id": row.model_id, "report": _json(row.report, {}), "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows]}


@router.get("/{book_id}/episodes/{episode}/director-benchmark/summary")
def summarize_director_benchmark_runs(book_id: int, episode: int) -> dict[str, Any]:
    """Aggregate persisted deterministic/gray reports without re-running them."""
    with Session() as session:
        rows = (
            session.query(DirectorBenchmarkRun)
            .filter_by(book_id=book_id, episode=episode)
            .order_by(DirectorBenchmarkRun.id.desc())
            .all()
        )
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        model_id = str(row.model_id or "deterministic")
        report = _json(row.report, {})
        if not isinstance(report, dict):
            report = {}
        bucket = groups.setdefault(model_id, {"model_id": model_id, "run_count": 0, "pass_count": 0, "needs_work_count": 0, "score_sum": 0.0, "scored_count": 0, "last_run_at": None})
        bucket["run_count"] += 1
        status = str(report.get("status") or "")
        if status == "pass":
            bucket["pass_count"] += 1
        elif status == "needs_work":
            bucket["needs_work_count"] += 1
        score = report.get("score")
        if isinstance(score, (int, float)):
            bucket["score_sum"] += float(score)
            bucket["scored_count"] += 1
        if bucket["last_run_at"] is None and row.created_at:
            bucket["last_run_at"] = row.created_at.isoformat()
    items = []
    for bucket in groups.values():
        scored_count = int(bucket.pop("scored_count"))
        score_sum = float(bucket.pop("score_sum"))
        bucket["average_score"] = round(score_sum / scored_count, 2) if scored_count else None
        bucket["pass_rate"] = round(bucket["pass_count"] / bucket["run_count"], 4) if bucket["run_count"] else None
        items.append(bucket)
    items.sort(key=lambda item: str(item.get("model_id") or ""))
    return {"book_id": book_id, "episode": episode, "run_count": len(rows), "models": items}
