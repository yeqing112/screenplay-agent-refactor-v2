"""Bounded local repairs for Director Quality findings.

Only creative ShotPlan fields may be changed here.  The wrapper deliberately
rejects structural/factual paths and records an existing ``RepairAttempt``
row when a database context is explicitly supplied.
"""
from __future__ import annotations

import copy
from typing import Any

from core.director_creative_planner import CREATIVE_SHOT_FIELDS
from core.local_repair import apply_local_repair
from core.repair_ledger import record_repair_attempt
from core.director_quality_validator import validate_director_quality
from core.qualification_loop import qualify_candidate


def _path_field(path: str) -> str:
    parts = [part for part in str(path or "").split("/") if part]
    return parts[2] if len(parts) >= 3 and parts[0] == "shots" else (parts[0] if parts else "")


def _assert_creative_patch(issue: dict[str, Any]) -> None:
    layer = str(issue.get("target_layer") or "DIRECTOR_CREATIVE").strip().upper()
    if layer != "DIRECTOR_CREATIVE":
        raise ValueError("director local repair must target DIRECTOR_CREATIVE")
    patch = issue.get("patch") if isinstance(issue.get("patch"), list) else []
    for operation in patch:
        if not isinstance(operation, dict):
            raise ValueError("director repair patch operation must be an object")
        field = _path_field(operation.get("path"))
        if field not in CREATIVE_SHOT_FIELDS:
            raise ValueError(f"director repair cannot modify structural field: {field}")


def apply_director_local_repair(
    candidate: dict[str, Any],
    issue: dict[str, Any],
    *,
    session: Any | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply an explicit creative patch and optionally persist its ledger row."""
    _assert_creative_patch(issue)
    repair = apply_local_repair(candidate, {**issue, "target_layer": "DIRECTOR_CREATIVE"})
    # Always expose the layer even when the caller omitted it.  This makes
    # replay and audit unambiguous.
    repair["target_layer"] = "DIRECTOR_CREATIVE"
    if session is not None or context is not None:
        record_repair_attempt(
            repair=repair,
            issue={**issue, "target_layer": "DIRECTOR_CREATIVE"},
            context=context or {},
            session=session,
        )
    return repair


def build_director_repair_options(candidate: dict[str, Any], issues: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Create reviewable, bounded repair options; never applies them."""
    shots = candidate.get("shots") if isinstance(candidate, dict) and isinstance(candidate.get("shots"), list) else []
    by_id = {str(item.get("plan_shot_id")): i for i, item in enumerate(shots) if isinstance(item, dict)}
    options: list[dict[str, Any]] = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or issue.get("issue_code") or "")
        sid = str(issue.get("shot_id") or issue.get("target_id") or "")
        index = by_id.get(sid)
        patch: list[dict[str, Any]] = []
        operation = "review"
        if code == "UNMOTIVATED_SHOT" and index is not None:
            patch = [{"op": "add", "path": f"/shots/{index}/why_this_shot", "value": "为当前节拍提供必要的视觉信息或反应"}]
            operation = "add_shot_motivation"
        elif code == "CAMERA_REPETITION" and index is not None:
            patch = [{"op": "replace", "path": f"/shots/{index}/camera/shot_size", "value": "MCU"}]
            operation = "change_shot_scale"
        elif code == "EMOTIONAL_FLATLINE" and shots:
            index = len(shots) - 1
            current = shots[index] if isinstance(shots[index], dict) else {}
            emotion = current.get("emotion") if isinstance(current.get("emotion"), dict) else {}
            value = emotion.get("intensity") if isinstance(emotion.get("intensity"), (int, float)) else 5
            patch = [{"op": "add", "path": f"/shots/{index}/emotion/intensity", "value": min(10, float(value) + 1)}]
            operation = "escalate_emotional_intensity"
        elif code == "REDUNDANT_SHOT" and index is not None:
            patch = [{"op": "add", "path": f"/shots/{index}/why_this_shot", "value": "承接上一镜并明确新的反应或信息焦点"}]
            operation = "motivate_or_merge_redundant_shot"
        elif code == "POWER_SHIFT_NOT_VISUALIZED" and index is not None:
            patch = [{"op": "replace", "path": f"/shots/{index}/camera/angle", "value": "low_angle"}]
            operation = "visualize_power_shift"
        options.append({
            "issue_code": code,
            "target_layer": "DIRECTOR_CREATIVE",
            "target_id": sid,
            "operation": operation,
            "patch": patch,
            "requires_confirmation": bool(patch),
        })
    return options


def qualify_director_candidate(
    candidate: dict[str, Any],
    *,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    max_attempts: int = 2,
    repair_recorder: Any | None = None,
    repair_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the existing bounded qualification loop at DIRECTOR_CREATIVE.

    The validator remains deterministic.  A repair is applied only when its
    explicit option contains a patch; unavailable findings stay
    ``needs_review`` instead of being fabricated away.
    """
    def validator(current: dict[str, Any]) -> list[dict[str, Any]]:
        issues = validate_director_quality(current, treatment=treatment, blocking=blocking)
        options = build_director_repair_options(current, issues)
        by_key = {(item.get("issue_code"), item.get("target_id")): item for item in options}
        enriched = []
        for issue in issues:
            option = by_key.get((issue.get("code"), issue.get("target_id") or issue.get("shot_id")))
            enriched.append({**issue, "target_layer": "DIRECTOR_CREATIVE", "patch": (option or {}).get("patch", [])})
        return enriched

    return qualify_candidate(
        candidate,
        [validator],
        max_attempts=max_attempts,
        repair_recorder=repair_recorder,
        repair_context=repair_context,
    )


__all__ = ["apply_director_local_repair", "build_director_repair_options", "qualify_director_candidate"]
