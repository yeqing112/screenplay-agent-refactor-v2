"""Diagnostics for gratuitous directing and shot inflation."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


OVER_DIRECTING_ISSUES = (
    "GRATUITOUS_CAMERA_MOVEMENT",
    "UNNECESSARY_REACTION_SHOT",
    "UNNECESSARY_INSERT",
    "SHOT_INFLATION",
    "OVER_CUTTING",
    "EMOTION_OVEREXPLAINED",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def detect_over_directing(
    shots: Iterable[dict[str, Any]], *, opportunities: Iterable[dict[str, Any]] = (), baseline_shot_count: int | None = None, allowed_auxiliary_count: int | None = None,
) -> dict[str, Any]:
    """Return non-blocking over-directing findings with controlled rates."""

    items = [item for item in shots if isinstance(item, dict)]
    opportunity_types = {_text(item.get("type")) for item in opportunities if isinstance(item, dict) and item.get("eligible") is True}
    issues: list[dict[str, Any]] = []
    auxiliary_count = 0
    for index, shot in enumerate(items):
        sid = _text(shot.get("plan_shot_id")) or f"S{index + 1:02d}"
        auxiliary_type = _text(shot.get("auxiliary_type")).lower()
        if auxiliary_type:
            auxiliary_count += 1
        camera = _dict(shot.get("camera"))
        movement = _text(camera.get("movement")).lower()
        reason = _text(shot.get("why_this_shot")) or _text(shot.get("dramatic_function"))
        if movement and movement not in {"static", "none", "固定"} and not reason:
            issues.append({"code": "GRATUITOUS_CAMERA_MOVEMENT", "issue_code": "GRATUITOUS_CAMERA_MOVEMENT", "shot_id": sid, "blocking": False, "message": "运镜没有导演动机证据"})
        if auxiliary_type == "reaction" and "OPP_REACTION" not in opportunity_types and "OPP_EMOTION_TURN" not in opportunity_types:
            issues.append({"code": "UNNECESSARY_REACTION_SHOT", "issue_code": "UNNECESSARY_REACTION_SHOT", "shot_id": sid, "blocking": False, "message": "没有 reaction/emotion opportunity 支撑辅助反应镜头"})
        if auxiliary_type == "insert" and "OPP_PROP_EMPHASIS" not in opportunity_types and "OPP_VISUAL_REVEAL" not in opportunity_types:
            issues.append({"code": "UNNECESSARY_INSERT", "issue_code": "UNNECESSARY_INSERT", "shot_id": sid, "blocking": False, "message": "没有道具或视觉揭示机会支撑 insert"})
        emotion = _dict(shot.get("emotion"))
        if isinstance(emotion.get("intensity"), (int, float)) and float(emotion["intensity"]) >= 8 and _text(emotion.get("start")) == _text(emotion.get("end")):
            issues.append({"code": "EMOTION_OVEREXPLAINED", "issue_code": "EMOTION_OVEREXPLAINED", "shot_id": sid, "blocking": False, "message": "高强度情绪没有状态变化证据"})
    if baseline_shot_count is not None and allowed_auxiliary_count is not None and auxiliary_count > int(allowed_auxiliary_count):
        issues.append({"code": "SHOT_INFLATION", "issue_code": "SHOT_INFLATION", "blocking": False, "message": "辅助镜头数量超过受控上限", "details": {"baseline_shot_count": int(baseline_shot_count), "auxiliary_shot_count": auxiliary_count, "allowed_auxiliary_count": int(allowed_auxiliary_count)}})
    counts = Counter(item["code"] for item in issues)
    return {"schema_version": "director_over_directing_v1", "issues": issues, "issue_counts": dict(counts), "shot_count": len(items), "auxiliary_shot_count": auxiliary_count, "over_directing_rate": round(len(issues) / len(items), 4) if items else None, "shot_inflation_rate": round(max(0, auxiliary_count - int(allowed_auxiliary_count or auxiliary_count)) / max(1, int(baseline_shot_count or len(items))), 4) if baseline_shot_count is not None else None, "blocking": False}


__all__ = ["OVER_DIRECTING_ISSUES", "detect_over_directing"]
