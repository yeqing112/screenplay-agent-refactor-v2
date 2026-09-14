"""Structured Edit Strategy V2 and sequence-level diagnostics."""

from __future__ import annotations

import copy
from typing import Any, Iterable


EDIT_STRATEGY_SCHEMA_VERSION = "director_edit_strategy_v2"
EDIT_ISSUES = (
    "EDIT_STRATEGY_MISSING",
    "UNMOTIVATED_CUT",
    "UNNECESSARY_CUT",
    "REACTION_CUT_TOO_EARLY",
    "REACTION_CUT_TOO_LATE",
    "RHYTHM_FLATLINE",
    "SCENE_BUTTON_MISSING",
    "OVER_CUTTING",
    "UNDER_CUTTING",
)
_KEYS = {
    "schema_version", "cut_reason", "hold_before_cut_seconds", "hold_after_reveal_seconds",
    "reaction_timing", "cut_on_action", "cut_on_reaction", "information_cut", "rhythm_change", "scene_button", "duration_seconds",
}


class EditStrategyError(ValueError):
    code = "EDIT_STRATEGY_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, *, path: str, allow_none: bool = True) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
        raise EditStrategyError("value must be a non-negative number", path=path)
    return float(value)


def normalize_edit_strategy(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise EditStrategyError("edit strategy must be an object")
    unknown = sorted(set(raw) - _KEYS)
    if unknown:
        raise EditStrategyError(f"edit strategy contains forbidden fields: {', '.join(unknown)}", code="EDIT_STRATEGY_FIELD_FORBIDDEN")
    cut_reason = _text(raw.get("cut_reason"))
    if not cut_reason:
        raise EditStrategyError("cut_reason is required", code="EDIT_STRATEGY_MISSING", path="cut_reason")
    reaction_timing = raw.get("reaction_timing", "")
    if isinstance(reaction_timing, (int, float)) and not isinstance(reaction_timing, bool):
        reaction_timing = float(reaction_timing)
    elif reaction_timing is None:
        reaction_timing = ""
    else:
        reaction_timing = _text(reaction_timing)
    for key in ("information_cut", "rhythm_change"):
        value = raw.get(key, "")
        if isinstance(value, bool):
            continue
        if value is not None and not isinstance(value, str):
            raise EditStrategyError(f"{key} must be a non-empty string or boolean", path=key)
    scene_button = raw.get("scene_button", "")
    if isinstance(scene_button, bool):
        scene_button = "" if not scene_button else "present"
    else:
        scene_button = _text(scene_button)
    normalized = {
        "schema_version": EDIT_STRATEGY_SCHEMA_VERSION,
        "cut_reason": cut_reason,
        "duration_seconds": _number(raw.get("duration_seconds"), path="duration_seconds"),
        "hold_before_cut_seconds": _number(raw.get("hold_before_cut_seconds"), path="hold_before_cut_seconds"),
        "hold_after_reveal_seconds": _number(raw.get("hold_after_reveal_seconds"), path="hold_after_reveal_seconds"),
        "reaction_timing": reaction_timing,
        "cut_on_action": bool(raw.get("cut_on_action", False)),
        "cut_on_reaction": bool(raw.get("cut_on_reaction", False)),
        "information_cut": raw.get("information_cut", ""),
        "rhythm_change": raw.get("rhythm_change", ""),
        "scene_button": scene_button,
    }
    return normalized


def validate_edit_strategy(raw: Any) -> dict[str, Any]:
    try:
        value = normalize_edit_strategy(raw)
    except EditStrategyError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "strategy": None}
    return {"status": "valid", "errors": [], "strategy": value}


def _issue(code: str, message: str, *, shot_id: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {"code": code, "issue_code": code, "severity": "warning", "blocking": False, "message": message}
    if shot_id:
        value["shot_id"] = shot_id
    if details:
        value["details"] = copy.deepcopy(details)
    return value


def _duration(shot: dict[str, Any]) -> float | None:
    value = _dict(shot.get("edit")).get("duration_seconds", shot.get("duration_hint_seconds"))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        return None
    return float(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_edit_strategy(
    shots: Iterable[dict[str, Any]], *, scene_duration_seconds: float | None = None, scene_button_required: bool = False,
) -> dict[str, Any]:
    """Return non-blocking edit quality findings and coverage metrics."""

    items = [item for item in shots if isinstance(item, dict)]
    issues: list[dict[str, Any]] = []
    valid_count = 0
    durations: list[float] = []
    for index, shot in enumerate(items):
        sid = str(shot.get("plan_shot_id") or f"S{index + 1:02d}")
        edit = _dict(shot.get("edit"))
        try:
            strategy = normalize_edit_strategy(edit)
        except EditStrategyError:
            issues.append(_issue("EDIT_STRATEGY_MISSING", "镜头缺少结构化 cut_reason", shot_id=sid))
            strategy = None
        if strategy:
            valid_count += 1
            reason = strategy["cut_reason"].lower()
            if reason in {"coverage", "time", "default", "generic", ""}:
                issues.append(_issue("UNMOTIVATED_CUT", "cut_reason 过于泛化，无法解释剪辑动机", shot_id=sid))
            timing = strategy.get("reaction_timing")
            if timing in {"before", "too_early", "early"}:
                issues.append(_issue("REACTION_CUT_TOO_EARLY", "反应完成前切出", shot_id=sid))
            elif timing in {"after", "too_late", "late"}:
                issues.append(_issue("REACTION_CUT_TOO_LATE", "反应窗口已经流失后才切出", shot_id=sid))
        duration = _duration(shot)
        if duration is not None:
            durations.append(duration)
    if len(durations) > 1 and len(set(round(value, 3) for value in durations)) == 1:
        issues.append(_issue("RHYTHM_FLATLINE", "所有镜头时长相同，未显示节奏变化", details={"duration_seconds": durations[0], "shot_count": len(durations)}))
    if scene_button_required and items:
        last = _dict(items[-1].get("edit"))
        if not _text(last.get("scene_button")):
            issues.append(_issue("SCENE_BUTTON_MISSING", "场景要求收束但末镜没有 scene_button", shot_id=str(items[-1].get("plan_shot_id") or f"S{len(items):02d}")))
    if scene_duration_seconds is not None and isinstance(scene_duration_seconds, (int, float)) and float(scene_duration_seconds) > 0 and len(items) > 1:
        cuts = len(items) - 1
        rate = cuts / float(scene_duration_seconds)
        if rate > 1.5:
            issues.append(_issue("OVER_CUTTING", "单位时间切换次数超过受控阈值", details={"cut_rate": round(rate, 4), "threshold": 1.5}))
        elif rate < 0.05 and float(scene_duration_seconds) >= 20:
            issues.append(_issue("UNDER_CUTTING", "长场景缺少足够的剪辑节奏变化", details={"cut_rate": round(rate, 4), "threshold": 0.05}))
    return {
        "schema_version": EDIT_STRATEGY_SCHEMA_VERSION,
        "issues": issues,
        "valid_shot_count": valid_count,
        "shot_count": len(items),
        "coverage": round(valid_count / len(items), 4) if items else None,
        "blocking": False,
    }


__all__ = ["EDIT_STRATEGY_SCHEMA_VERSION", "EDIT_ISSUES", "EditStrategyError", "normalize_edit_strategy", "validate_edit_strategy", "evaluate_edit_strategy"]
