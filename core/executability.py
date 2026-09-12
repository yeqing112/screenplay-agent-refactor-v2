"""ShotPlan-level executability preflight and deterministic repair options."""
from __future__ import annotations

import json
from typing import Any

from core.shot_executability import validate_shot_executability


def _state_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "").strip()


def preflight_shot_plan(shots: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Validate every ShotPlan V2 item before it can become approved."""
    results: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for item in shots or []:
        if not isinstance(item, dict):
            blocking.append({"code": "SHOT_OBJECT_INVALID", "message": "ShotPlan item must be an object."})
            continue
        camera = item.get("camera") if isinstance(item.get("camera"), dict) else {}
        result = validate_shot_executability(
            duration=item.get("duration_hint_seconds") or item.get("duration_seconds"),
            action_process=str(item.get("event") or ""),
            action_beats=item.get("action_beats") if isinstance(item.get("action_beats"), list) else [],
            camera_movement=str(camera.get("movement") or "static"),
            start_state=_state_text(item.get("entry_state")),
            end_state=_state_text(item.get("exit_state")),
        )
        result = {"plan_shot_id": item.get("plan_shot_id"), **result}
        results.append(result)
        for finding in result.get("findings", []):
            (blocking if finding.get("severity") == "blocked" else warnings).append({"plan_shot_id": item.get("plan_shot_id"), **finding})
    return {"status": "blocked" if blocking else "warning" if warnings else "pass", "shots": results, "blocking_issues": blocking, "warnings": warnings, "repair_options": [suggestion for result in results for suggestion in result.get("suggestions", [])]}


def build_executability_repair_plan(preflight: dict[str, Any], *, max_attempts: int = 2) -> dict[str, Any]:
    options = []
    for issue in preflight.get("blocking_issues", []) if isinstance(preflight, dict) else []:
        code = str(issue.get("code") or "")
        target = str(issue.get("plan_shot_id") or "")
        if code == "action_overloaded":
            options.append({"issue_code": code, "target_layer": "SHOT_PLAN", "target_id": target, "operation": "split_shot", "patch": [], "reason": "动作超出当前时长预算，需在 ShotPlan 层拆镜。"})
        elif code == "missing_core_action":
            options.append({"issue_code": code, "target_layer": "SHOT_PLAN", "target_id": target, "operation": "request_missing_information", "patch": [], "reason": "缺少核心动作，不能用 Prompt 文本掩盖。"})
    return {"max_attempts": max(1, int(max_attempts)), "operations": options}

