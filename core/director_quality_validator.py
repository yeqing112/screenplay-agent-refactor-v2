"""Deterministic Director Quality Benchmark V2 validators.

Structural executability remains owned by ``core.executability``.  The
diagnostics here are creative-quality findings: they reduce the director
score but do not weaken or replace production gates.  Every issue carries the
``DIRECTOR_CREATIVE`` responsibility layer so Local Repair can keep repairs
out of facts, script, blocking, and prompt text.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


DIRECTOR_DIMENSIONS = (
    "DRAMATIC_CLARITY",
    "SHOT_MOTIVATION",
    "EMOTIONAL_PROGRESSION",
    "VISUAL_STORYTELLING",
    "SPATIAL_CLARITY",
    "PERFORMANCE_DIRECTION",
    "EDIT_RHYTHM",
    "INFORMATION_STRATEGY",
    "POWER_DYNAMICS",
    "SHOT_DIVERSITY",
)
DIRECTOR_WEIGHTS = {
    "DRAMATIC_CLARITY": 15,
    "SHOT_MOTIVATION": 15,
    "EMOTIONAL_PROGRESSION": 12,
    "VISUAL_STORYTELLING": 12,
    "SPATIAL_CLARITY": 10,
    "PERFORMANCE_DIRECTION": 10,
    "EDIT_RHYTHM": 8,
    "INFORMATION_STRATEGY": 8,
    "POWER_DYNAMICS": 5,
    "SHOT_DIVERSITY": 5,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _shots(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [item for item in ((plan or {}).get("shots") or []) if isinstance(item, dict)]


def _issue(code: str, message: str, *, shot_id: str = "", severity: str = "warning", details: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "code": code,
        "issue_code": code,
        "target_layer": "DIRECTOR_CREATIVE",
        "target_id": shot_id,
        "shot_id": shot_id,
        "severity": severity,
        "blocking": False,
        "message": message,
    }
    if isinstance(details, dict) and details:
        result["details"] = details
    return result


def _camera_signature(shot: dict[str, Any]) -> tuple[str, str, str, str, str]:
    camera = _dict(shot.get("camera"))
    return tuple(_text(camera.get(key)) for key in ("shot_size", "angle", "movement", "speed", "camera_side"))


def _subject(shot: dict[str, Any]) -> str:
    composition = _dict(shot.get("composition"))
    return _text(composition.get("dominant_subject") or ((shot.get("participants") or [""])[0] if isinstance(shot.get("participants"), list) else ""))


def _motivation(shot: dict[str, Any]) -> bool:
    if _text(shot.get("why_this_shot")):
        return True
    return bool(_text(shot.get("purpose")) and _text(shot.get("dramatic_function")) and _text(shot.get("purpose")).lower() != "coverage")


def validate_director_quality(plan: dict[str, Any] | None, *, treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return creative-quality diagnostics without mutating ``plan``."""
    shots = _shots(plan)
    issues: list[dict[str, Any]] = []
    # Missing motivation is a quality error, not a structural production
    # blocker; it is intentionally repairable at DIRECTOR_CREATIVE only.
    for index, shot in enumerate(shots):
        sid = _text(shot.get("plan_shot_id") or shot.get("shot_id") or f"S{index + 1:02d}")
        if not _motivation(shot):
            issues.append(_issue("UNMOTIVATED_SHOT", f"{sid} cannot answer why the cut is needed", shot_id=sid, severity="error"))
    # Consecutive identical camera choices are only a quality deduction.  An
    # explicit continuity/establish reason exempts the run from the warning.
    run_start = 0
    while run_start < len(shots):
        signature = _camera_signature(shots[run_start])
        run_end = run_start + 1
        while run_end < len(shots) and _camera_signature(shots[run_end]) == signature:
            run_end += 1
        if run_end - run_start >= 4:
            reasons = " ".join(_text(shots[i].get("why_this_shot")) for i in range(run_start, run_end)).lower()
            if not any(token in reasons for token in ("continuity", "maintain", "establish", "保持", "建立")):
                issues.append(_issue("CAMERA_REPETITION", f"{run_end - run_start} consecutive shots repeat the same camera signature", shot_id=_text(shots[run_start].get("plan_shot_id")), details={"run_length": run_end - run_start, "signature": signature}))
        run_start = run_end
    # Adjacent redundancy: identical visual grammar and no new beat/info or
    # emotion.  Never delete it here; Local Repair decides merge/replace.
    for left, right in zip(shots, shots[1:]):
        left_id = _text(left.get("plan_shot_id")); right_id = _text(right.get("plan_shot_id"))
        left_comp, right_comp = _dict(left.get("composition")), _dict(right.get("composition"))
        same_visual = _camera_signature(left) == _camera_signature(right) and _subject(left) == _subject(right) and left_comp == right_comp
        same_purpose = _text(left.get("purpose")) == _text(right.get("purpose"))
        no_new_info = _dict(left.get("information_strategy")) == _dict(right.get("information_strategy"))
        no_emotion = _dict(left.get("emotion")) == _dict(right.get("emotion"))
        if same_visual and same_purpose and no_new_info and no_emotion:
            issues.append(_issue("REDUNDANT_SHOT", f"{left_id} and {right_id} repeat the same visual and dramatic function", shot_id=right_id, details={"previous_shot_id": left_id}))
    # A flat emotional line is meaningful only when there are at least two
    # shots. Missing intensity is treated as unknown, not as a fabricated 0.
    intensities = []
    for shot in shots:
        value = _dict(shot.get("emotion")).get("intensity")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            intensities.append(float(value))
    if len(shots) >= 2 and len(intensities) >= 2 and len(set(intensities)) == 1:
        issues.append(_issue("EMOTIONAL_FLATLINE", "all scored shots have the same emotional intensity"))
    treatment_beats = (treatment or {}).get("beat_map") if isinstance((treatment or {}).get("beat_map"), list) else []
    has_power_shift = any(_text(item.get("type")).lower() in {"decision", "power_shift"} or "power" in _text(item.get("dramatic_function")).lower() for item in treatment_beats if isinstance(item, dict))
    if has_power_shift and len(shots) >= 2:
        signatures = {_camera_signature(shot) for shot in shots}
        compositions = {_text(_dict(shot.get("composition")).get("frame_relationship")) for shot in shots}
        if len(signatures) == 1 and len(compositions) <= 1:
            issues.append(_issue("POWER_SHIFT_NOT_VISUALIZED", "treatment declares a power shift but framing never changes"))
    return issues


def _clamp(value: float) -> float:
    return max(0.0, min(10.0, round(value, 2)))


def _dimension_scores(plan: dict[str, Any], *, treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, issues: list[dict[str, Any]] | None = None) -> dict[str, float]:
    shots = _shots(plan)
    if not shots:
        return {name: 0.0 for name in DIRECTOR_DIMENSIONS}
    issues = issues if issues is not None else validate_director_quality(plan, treatment=treatment, blocking=blocking)
    code_counts = Counter(item.get("code") for item in issues)
    motivations = sum(1 for shot in shots if _motivation(shot)) / len(shots)
    purposes = [_text(shot.get("purpose")).lower() for shot in shots]
    coverage = sum(1 for purpose in purposes if purpose in {"", "coverage"}) / len(shots)
    visual = sum(1 for shot in shots if _text(shot.get("purpose")).lower() not in {"", "coverage"} or _dict(shot.get("composition")) or _dict(shot.get("information_strategy"))) / len(shots)
    performance = sum(1 for shot in shots if any(_text(item.get("objective")) and _text(item.get("visible_behavior")) for item in (shot.get("performance_direction") or []) if isinstance(item, dict))) / len(shots)
    spatial = sum(1 for shot in shots if _dict(shot.get("continuity_contract")) and (_text(_dict(shot.get("camera")).get("camera_side")) or _text(_dict(shot.get("composition")).get("frame_relationship")))) / len(shots)
    info = sum(1 for shot in shots if any(_text(_dict(shot.get("information_strategy")).get(key)) or _dict(shot.get("information_strategy")).get(key) for key in ("reveals", "withholds", "audience_focus"))) / len(shots)
    durations = [_dict(shot.get("edit")).get("duration_seconds", shot.get("duration_hint_seconds")) for shot in shots]
    duration_values = [float(value) for value in durations if isinstance(value, (int, float)) and value > 0]
    duration_variety = min(1.0, len(set(round(value, 2) for value in duration_values)) / max(2, len(duration_values))) if duration_values else 0
    rhythm = sum(1 for shot in shots if _text(_dict(shot.get("edit")).get("cut_reason"))) / len(shots)
    rhythm = min(1.0, (rhythm + duration_variety) / 2)
    signatures = [_camera_signature(shot) for shot in shots]
    diversity = min(1.0, len(set(signatures)) / len(signatures))
    repetition_penalty = min(1.0, code_counts.get("CAMERA_REPETITION", 0) / max(1, len(shots)))
    diversity = max(0.0, diversity - repetition_penalty * 0.5)
    intensities = [_dict(shot.get("emotion")).get("intensity") for shot in shots]
    numeric = [float(value) for value in intensities if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if len(numeric) < 2:
        emotional = 4.0 if len(numeric) == 0 else 6.0
    else:
        spread = max(numeric) - min(numeric)
        direction_changes = sum(1 for a, b in zip(numeric, numeric[1:]) if a != b)
        emotional = _clamp(4.0 + min(4.0, spread / 2) + min(2.0, direction_changes / max(1, len(numeric) - 1)))
    power = 8.0
    treatment_beats = (treatment or {}).get("beat_map") if isinstance((treatment or {}).get("beat_map"), list) else []
    if any(isinstance(item, dict) and _text(item.get("type")).lower() in {"decision", "power_shift"} for item in treatment_beats):
        power = 3.0 if code_counts.get("POWER_SHIFT_NOT_VISUALIZED") else 8.0
    scores = {
        "DRAMATIC_CLARITY": _clamp(10.0 * (1.0 - coverage) + 6.0 * coverage),
        "SHOT_MOTIVATION": _clamp(10.0 * motivations),
        "EMOTIONAL_PROGRESSION": emotional if not code_counts.get("EMOTIONAL_FLATLINE") else 3.0,
        "VISUAL_STORYTELLING": _clamp(10.0 * visual),
        "SPATIAL_CLARITY": _clamp(10.0 * spatial) if blocking is not None else 7.0,
        "PERFORMANCE_DIRECTION": _clamp(10.0 * performance),
        "EDIT_RHYTHM": _clamp(10.0 * rhythm),
        "INFORMATION_STRATEGY": _clamp(10.0 * info),
        "POWER_DYNAMICS": power,
        "SHOT_DIVERSITY": _clamp(10.0 * diversity),
    }
    return scores


def score_director_quality(plan: dict[str, Any] | None, *, treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score the ten creative dimensions independently from structural pass."""
    safe_plan = plan if isinstance(plan, dict) else {}
    issues = validate_director_quality(safe_plan, treatment=treatment, blocking=blocking)
    dimensions = _dimension_scores(safe_plan, treatment=treatment, blocking=blocking, issues=issues)
    weighted = sum(dimensions[key] / 10.0 * DIRECTOR_WEIGHTS[key] for key in DIRECTOR_DIMENSIONS)
    score = round(weighted, 2)
    rating = "Excellent" if score >= 90 else "Strong" if score >= 80 else "Usable" if score >= 70 else "Weak" if score >= 60 else "Needs Redesign"
    shots = _shots(safe_plan)
    return {
        "director_quality_score": score,
        "rating": rating,
        "dimensions": dimensions,
        "weights": DIRECTOR_WEIGHTS.copy(),
        "issues": issues,
        "metrics": {
            "motivated_shot_rate": round(sum(1 for shot in shots if _motivation(shot)) / len(shots), 4) if shots else 0.0,
            "camera_repetition_rate": round(sum(1 for item in issues if item.get("code") == "CAMERA_REPETITION") / len(shots), 4) if shots else 0.0,
            "redundant_shot_rate": round(sum(1 for item in issues if item.get("code") == "REDUNDANT_SHOT") / len(shots), 4) if shots else 0.0,
            "visual_storytelling_rate": round(sum(1 for shot in shots if _text(shot.get("purpose")).lower() not in {"", "coverage"}) / len(shots), 4) if shots else 0.0,
            "emotional_progression_score": dimensions["EMOTIONAL_PROGRESSION"],
            "shot_diversity_index": round(len({_camera_signature(shot) for shot in shots}) / len(shots), 4) if shots else 0.0,
        },
    }


def validate_shot_plan_quality(plan: dict[str, Any] | None, *, treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Alias used by the ShotPlan and benchmark layers."""
    return validate_director_quality(plan, treatment=treatment, blocking=blocking)


__all__ = ["DIRECTOR_DIMENSIONS", "DIRECTOR_WEIGHTS", "validate_director_quality", "validate_shot_plan_quality", "score_director_quality"]
