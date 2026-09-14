"""Bounded, root-cause-scoped Tail Repair for creative candidates."""

from __future__ import annotations

import copy
from typing import Any

from core.director_creative_planner import fingerprint
from core.director_tail_root_cause import ROOT_CAUSES


TAIL_REPAIR_SCHEMA_VERSION = "director_quality_tail_repair_v1"
MAX_ATTEMPTS_PER_ROOT_CAUSE = 2
REPAIR_SCOPES = {
    "MISSING_OPPORTUNITY_DETECTION": {"opportunities", "performance_direction", "edit", "emotion", "information_strategy"},
    "WEAK_EDIT_STRATEGY": {"edit"},
    "WEAK_EMOTION_ARC": {"emotion", "performance_direction"},
    "WEAK_INFORMATION_STRATEGY": {"information_strategy"},
    "LOW_USEFUL_ACCEPTANCE": {"opportunities", "edit", "emotion", "information_strategy", "performance_direction"},
    "OVER_DIRECTING": {"camera", "composition", "edit", "emotion", "performance_direction"},
    "UNDER_DIRECTING": {"camera", "composition", "edit", "emotion", "performance_direction"},
    "PATCH_QUALITY_WEAK": {"camera", "composition", "edit", "emotion", "information_strategy", "performance_direction"},
    "AUXILIARY_SHOT_OVERUSE": {"shots"},
    "PERFORMANCE_DIRECTION_WEAK": {"performance_direction"},
    "CAMERA_LANGUAGE_GENERIC": {"camera", "composition"},
    "UNKNOWN_ROOT_CAUSE": set(),
}


class TailRepairError(ValueError):
    code = "TAIL_REPAIR_INVALID"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _repair_triggered(record: dict[str, Any]) -> bool:
    quality = _number(record.get("director_quality_score"))
    if quality is None:
        quality = _number(_dict(record.get("quality")).get("director_quality_score"))
    creative = _number(record.get("creative_value_score"))
    if creative is None:
        creative = _number(_dict(record.get("creative_value")).get("score"))
    if quality is not None and quality < 70:
        return True
    if creative is not None and creative < 70:
        return True
    coverage = _dict(record.get("coverage"))
    thresholds = {"edit_strategy_coverage": 0.8, "emotion_arc_coverage": 0.85, "information_strategy_coverage": 0.85}
    return any(_number(coverage.get(key)) is not None and float(coverage[key]) < threshold for key, threshold in thresholds.items())


def build_tail_repair_plan(record: dict[str, Any], *, root_causes: list[str] | None = None) -> dict[str, Any]:
    """Create a repair plan without mutating the candidate."""

    selected = root_causes or [_dict(record).get("root_cause") or _dict(record).get("tail_root_cause") or "UNKNOWN_ROOT_CAUSE"]
    selected = [str(item) for item in selected if str(item) in ROOT_CAUSES]
    selected = list(dict.fromkeys(selected)) or ["UNKNOWN_ROOT_CAUSE"]
    triggered = _repair_triggered(record)
    scopes = {cause: sorted(REPAIR_SCOPES.get(cause, set())) for cause in selected}
    return {
        "schema_version": TAIL_REPAIR_SCHEMA_VERSION,
        "triggered": triggered,
        "reason": "quality/tail threshold reached" if triggered else "threshold not reached",
        "root_causes": selected,
        "scopes": scopes,
        "max_attempts_per_root_cause": MAX_ATTEMPTS_PER_ROOT_CAUSE,
        "attempts": {cause: 0 for cause in selected},
    }


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in str(path).replace("/", ".").split(".") if part]
    if not parts:
        raise TailRepairError("repair path is outside creative field scope")
    if parts[0] == "shots":
        if len(parts) < 3 or not parts[1].isdigit():
            raise TailRepairError("shot repair path requires a numeric shot index")
        index = int(parts[1])
        shots = target.get("shots")
        if not isinstance(shots, list) or index >= len(shots) or not isinstance(shots[index], dict):
            raise TailRepairError("shot repair index is invalid")
        current: Any = shots[index]
        parts = parts[2:]
    elif parts[0] in {"edit", "emotion", "information_strategy", "performance_direction", "camera", "composition"}:
        current = target
    else:
        raise TailRepairError("repair path is outside creative field scope")
    for part in parts[:-1]:
        if not isinstance(current, dict):
            raise TailRepairError("repair path traverses a non-object")
        current = current.setdefault(part, {})
    if not isinstance(current, dict):
        raise TailRepairError("repair path parent is not an object")
    current[parts[-1]] = copy.deepcopy(value)


def apply_tail_repair(candidate: dict[str, Any], repair_plan: dict[str, Any], *, root_cause: str, attempt_number: int, patch: dict[str, Any]) -> dict[str, Any]:
    """Apply one root-cause-scoped patch and return an auditable diff."""

    if not repair_plan.get("triggered"):
        raise TailRepairError("tail repair plan is not triggered")
    if root_cause not in repair_plan.get("root_causes", []):
        raise TailRepairError("root cause is not present in repair plan")
    if attempt_number < 1 or attempt_number > MAX_ATTEMPTS_PER_ROOT_CAUSE:
        raise TailRepairError("tail repair attempt exceeds per-root-cause budget")
    allowed = set(REPAIR_SCOPES.get(root_cause, set()))
    if not isinstance(patch, dict) or not patch:
        raise TailRepairError("repair patch must be a non-empty object")
    for path in patch:
        parts = [part for part in str(path).replace("/", ".").split(".") if part]
        root = parts[2] if parts and parts[0] == "shots" and len(parts) >= 3 else (parts[0] if parts else "")
        if root not in allowed:
            raise TailRepairError(f"repair path {path} is outside root-cause scope")
    before = fingerprint(candidate)
    updated = copy.deepcopy(candidate)
    for path, value in patch.items():
        _set_path(updated, path, value)
    after = fingerprint(updated)
    return {"schema_version": TAIL_REPAIR_SCHEMA_VERSION, "root_cause": root_cause, "attempt_number": attempt_number, "changed": before != after, "before_fingerprint": before, "after_fingerprint": after, "candidate": updated, "patch": copy.deepcopy(patch)}


__all__ = ["TAIL_REPAIR_SCHEMA_VERSION", "MAX_ATTEMPTS_PER_ROOT_CAUSE", "REPAIR_SCOPES", "TailRepairError", "build_tail_repair_plan", "apply_tail_repair"]
