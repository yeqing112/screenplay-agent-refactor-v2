"""Structured Emotion Arc V2 and performance-support diagnostics."""

from __future__ import annotations

import copy
from typing import Any, Iterable


EMOTION_ARC_SCHEMA_VERSION = "director_emotion_arc_v2"
EMOTION_PHASES = ("rise", "fall", "plateau", "spike", "release")
EMOTION_ISSUES = (
    "EMOTION_ARC_MISSING",
    "EMOTIONAL_FLATLINE",
    "EMOTION_JUMP_UNMOTIVATED",
    "EMOTION_PEAK_UNVISUALIZED",
    "REACTION_WITHOUT_PERFORMANCE_SUPPORT",
    "PERFORMANCE_DIRECTION_MISMATCH",
)


class EmotionArcError(ValueError):
    code = "EMOTION_ARC_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_emotion_arc(raw: Any) -> list[dict[str, Any]]:
    """Normalize a beat-bound arc; no beat or state is invented."""

    if isinstance(raw, dict):
        if "scene_emotion_arc" in raw:
            raw = raw["scene_emotion_arc"]
        elif "emotion_curve" in raw:
            raw = raw["emotion_curve"]
    if not isinstance(raw, list) or not raw:
        raise EmotionArcError("scene_emotion_arc must be a non-empty list", code="EMOTION_ARC_MISSING", path="scene_emotion_arc")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous: float | None = None
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise EmotionArcError("emotion arc item must be an object", path=f"scene_emotion_arc[{index}]")
        unknown = sorted(set(item) - {"beat_id", "character_id", "state", "intensity", "phase"})
        if unknown:
            raise EmotionArcError(f"emotion arc item contains forbidden fields: {', '.join(unknown)}", path=f"scene_emotion_arc[{index}]")
        beat_id = _text(item.get("beat_id"))
        state = _text(item.get("state"))
        if not beat_id or not state:
            raise EmotionArcError("beat_id and state are required", path=f"scene_emotion_arc[{index}]")
        if beat_id in seen:
            raise EmotionArcError("beat_id must be unique in emotion arc", path=f"scene_emotion_arc[{index}].beat_id")
        seen.add(beat_id)
        intensity = item.get("intensity")
        if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or not 0 <= float(intensity) <= 10:
            raise EmotionArcError("intensity must be between 0 and 10", path=f"scene_emotion_arc[{index}].intensity")
        value = float(intensity)
        phase = _text(item.get("phase")).lower()
        if not phase and previous is not None:
            delta = value - previous
            phase = "spike" if abs(delta) >= 4 else ("rise" if delta > 0.25 else ("fall" if delta < -0.25 else "plateau"))
        if phase and phase not in EMOTION_PHASES:
            raise EmotionArcError("phase must be rise, fall, plateau, spike, or release", path=f"scene_emotion_arc[{index}].phase")
        normalized = {"beat_id": beat_id, "state": state, "intensity": value}
        character_id = _text(item.get("character_id"))
        if character_id:
            normalized["character_id"] = character_id
        if phase:
            normalized["phase"] = phase
        result.append(normalized)
        previous = value
    return result


def validate_emotion_arc(raw: Any) -> dict[str, Any]:
    try:
        value = normalize_emotion_arc(raw)
    except EmotionArcError as exc:
        return {"status": "invalid", "errors": [{"code": exc.code, "path": exc.path, "message": str(exc)}], "scene_emotion_arc": None}
    return {"status": "valid", "errors": [], "scene_emotion_arc": value}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _issue(code: str, message: str, *, beat_id: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {"code": code, "issue_code": code, "severity": "warning", "blocking": False, "message": message}
    if beat_id:
        value["beat_id"] = beat_id
    if details:
        value["details"] = copy.deepcopy(details)
    return value


def evaluate_emotion_arc(
    scene_emotion_arc: Any, *, shots: Iterable[dict[str, Any]] = (), beat_map: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Validate arc shape and its visible support in the candidate shots."""

    try:
        arc = normalize_emotion_arc(scene_emotion_arc)
    except EmotionArcError as exc:
        return {"schema_version": EMOTION_ARC_SCHEMA_VERSION, "issues": [_issue(exc.code, str(exc))], "coverage": None, "blocking": False}
    items = [item for item in shots if isinstance(item, dict)]
    beat_types = {_text(item.get("beat_id")): _text(item.get("type")).lower() for item in beat_map if isinstance(item, dict) and _text(item.get("beat_id"))}
    by_beat = {_text(item.get("beat_id")): item for item in items if _text(item.get("beat_id"))}
    issues: list[dict[str, Any]] = []
    values = [float(item["intensity"]) for item in arc]
    if len(values) > 1 and len(set(values)) == 1:
        issues.append(_issue("EMOTIONAL_FLATLINE", "情绪曲线所有 beat 强度相同", details={"intensity": values[0]}))
    for previous, current in zip(arc, arc[1:]):
        delta = float(current["intensity"]) - float(previous["intensity"])
        if abs(delta) >= 4 and beat_types.get(current["beat_id"]) not in {"reveal", "decision", "power_shift", "turn", "emotional_peak"}:
            issues.append(_issue("EMOTION_JUMP_UNMOTIVATED", "情绪强度发生大幅跳变但没有转折证据", beat_id=current["beat_id"], details={"delta": delta}))
    peak = max(values)
    peak_ids = {item["beat_id"] for item in arc if float(item["intensity"]) == peak and peak >= 8}
    for beat_id in peak_ids:
        shot = by_beat.get(beat_id, {})
        performance = shot.get("performance_direction")
        if not isinstance(performance, list) or not any(isinstance(entry, dict) and _text(entry.get("visible_behavior")) for entry in performance):
            issues.append(_issue("EMOTION_PEAK_UNVISUALIZED", "情绪峰值没有可观察的表演支撑", beat_id=beat_id))
    aligned = 0
    for entry in arc:
        shot = by_beat.get(entry["beat_id"], {})
        shot_emotion = _dict(shot.get("emotion"))
        intensity = shot_emotion.get("intensity")
        if isinstance(intensity, (int, float)) and abs(float(intensity) - float(entry["intensity"])) <= 1:
            aligned += 1
        if beat_types.get(entry["beat_id"]) == "reaction":
            performance = shot.get("performance_direction")
            if not isinstance(performance, list) or not any(isinstance(item, dict) and _text(item.get("visible_behavior")) for item in performance):
                issues.append(_issue("REACTION_WITHOUT_PERFORMANCE_SUPPORT", "reaction beat 没有 visible_behavior", beat_id=entry["beat_id"]))
        if isinstance(intensity, (int, float)) and abs(float(intensity) - float(entry["intensity"])) > 2:
            issues.append(_issue("PERFORMANCE_DIRECTION_MISMATCH", "镜头情绪强度与场景曲线不一致", beat_id=entry["beat_id"], details={"arc_intensity": entry["intensity"], "shot_intensity": intensity}))
    return {
        "schema_version": EMOTION_ARC_SCHEMA_VERSION,
        "issues": issues,
        "coverage": round(aligned / len(arc), 4) if arc else None,
        "arc_count": len(arc),
        "peak_intensity": peak,
        "blocking": False,
    }


__all__ = ["EMOTION_ARC_SCHEMA_VERSION", "EMOTION_PHASES", "EMOTION_ISSUES", "EmotionArcError", "normalize_emotion_arc", "validate_emotion_arc", "evaluate_emotion_arc"]
