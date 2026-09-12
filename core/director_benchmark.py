"""Deterministic Director Runtime benchmark scoring."""
from __future__ import annotations

from typing import Any


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
    return {"score": round((passed / len(checks)) * 100, 2) if checks else 0, "passed": passed, "total": len(checks), "status": "pass" if passed == len(checks) else "needs_work", "checks": checks}
