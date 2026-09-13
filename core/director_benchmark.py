"""Director Runtime benchmark scoring.

Structural readiness and creative-director quality are deliberately reported
as separate values.  Existing callers can continue to use ``score`` for the
structural gate while new consumers read ``director_quality_score`` and the
ten dimension breakdown.
"""
from __future__ import annotations

from typing import Any

from core.director_quality_validator import score_director_quality


def score_runtime(*, treatment: dict[str, Any] | None, blocking: dict[str, Any] | None, shot_plan: dict[str, Any] | None) -> dict[str, Any]:
    treatment = treatment or {}
    blocking = blocking or {}
    shot_plan = shot_plan or {}
    checks: list[dict[str, Any]] = []

    def check(key: str, label: str, passed: bool, detail: str) -> None:
        checks.append({"key": key, "label": label, "passed": bool(passed), "detail": detail})

    check("treatment_approved", "导演方案已批准", treatment.get("status") == "approved", "需要 approved DirectorTreatment")
    check("treatment_beats", "导演节拍完整", bool(treatment.get("beat_map")), "Beat Map 不能为空")
    check("blocking_approved", "空间调度已批准", blocking.get("status") == "approved", "需要 approved SceneBlocking")
    check("blocking_unknowns", "空间信息无未决项", not bool(blocking.get("unknowns")), "SceneBlocking unknowns 必须为空")
    check("shot_plan_approved", "ShotPlan 已批准", shot_plan.get("status") == "approved", "需要 approved ShotPlan")
    shots = shot_plan.get("shots") if isinstance(shot_plan.get("shots"), list) else []
    executable = bool(shots) and all(isinstance(item, dict) and isinstance(item.get("camera"), dict) and item.get("duration_hint_seconds", 0) > 0 for item in shots)
    check("shot_plan_executable", "ShotPlan 可执行", executable, "每个计划镜头必须有 camera 和正时长")
    passed = sum(1 for item in checks if item["passed"])
    structural_score = round((passed / len(checks)) * 100, 2) if checks else 0
    structural_status = "pass" if checks and passed == len(checks) else "needs_work"
    creative = score_director_quality(shot_plan, treatment=treatment, blocking=blocking)
    # ``score`` and ``status`` remain backwards-compatible structural
    # aliases.  Never merge the values: a creative warning must not weaken a
    # structural gate and a structural failure must not be hidden by a high
    # creative score.
    return {
        "score": structural_score,
        "structural_score": structural_score,
        "structural_status": structural_status,
        "passed": passed,
        "total": len(checks),
        "status": structural_status,
        "checks": checks,
        "director_quality_score": creative["director_quality_score"],
        "director_quality_rating": creative["rating"],
        "director_quality": creative,
        "quality_issues": creative["issues"],
    }


def compare_director_plans(
    *,
    baseline: dict[str, Any],
    planner: dict[str, Any],
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare two plans sharing the same structural evidence.

    This helper is intentionally blind-review friendly: callers can relabel
    the returned ``version_a``/``version_b`` values before presenting them to
    a reviewer.  It does not infer human preference.
    """
    baseline_quality = score_director_quality(baseline, treatment=treatment, blocking=blocking)
    planner_quality = score_director_quality(planner, treatment=treatment, blocking=blocking)
    baseline_ids = [str(item.get("plan_shot_id") or "") for item in baseline.get("shots", []) if isinstance(item, dict)]
    planner_ids = [str(item.get("plan_shot_id") or "") for item in planner.get("shots", []) if isinstance(item, dict)]
    return {
        "version_a": {"label": "Version A", "role": "baseline", "director_quality": baseline_quality},
        "version_b": {"label": "Version B", "role": "planner", "director_quality": planner_quality},
        "delta": round(planner_quality["director_quality_score"] - baseline_quality["director_quality_score"], 2),
        "structural_evidence_shared": baseline_ids == planner_ids[: len(baseline_ids)] and baseline.get("scene_name") == planner.get("scene_name"),
        "baseline_shot_count": len(baseline_ids),
        "planner_shot_count": len(planner_ids),
        "blind_review": {"preferred_version": None, "reviewer": None, "reason": None},
    }
