"""Deterministic, bounded context selection for Director Tail Repair.

The resolver keeps provider input scoped to the selected root cause.  It never
invents beats or shots: every returned id must come from the approved treatment
or structural candidate supplied by the caller.
"""
from __future__ import annotations

import copy
from typing import Any, Iterable


TARGET_DIMENSIONS_BY_ROOT_CAUSE = {
    "WEAK_EDIT_STRATEGY": {"EDIT_RHYTHM"},
    "WEAK_EMOTION_ARC": {"EMOTIONAL_PROGRESSION", "PERFORMANCE_DIRECTION"},
    "WEAK_INFORMATION_STRATEGY": {"INFORMATION_STRATEGY"},
    "PERFORMANCE_DIRECTION_WEAK": {"PERFORMANCE_DIRECTION"},
    "CAMERA_LANGUAGE_GENERIC": {"SHOT_DIVERSITY", "VISUAL_STORYTELLING"},
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _priority(value: Any) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(_text(value).lower(), 3)


def _beat_id(item: dict[str, Any], index: int) -> str:
    return _text(item.get("beat_id") or item.get("id")) or f"B{index + 1:02d}"


def _shot_id(item: dict[str, Any], index: int) -> str:
    return _text(item.get("plan_shot_id") or item.get("shot_id") or item.get("id")) or f"S{index + 1:02d}"


def _beat_map(treatment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    beats = treatment.get("beat_map")
    if not isinstance(beats, list):
        beats = treatment.get("beats")
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(_list(beats)):
        if isinstance(item, dict):
            result.setdefault(_beat_id(item, index), copy.deepcopy(item))
    return result


def _shot_rows(candidate: dict[str, Any]) -> list[tuple[int, str, dict[str, Any]]]:
    result = []
    for index, item in enumerate(_list(candidate.get("shots"))):
        if isinstance(item, dict):
            result.append((index, _shot_id(item, index), copy.deepcopy(item)))
    return result


def _field_present(item: dict[str, Any], *paths: str) -> bool:
    for path in paths:
        current: Any = item
        for part in path.split("."):
            current = _dict(current).get(part)
        if current not in (None, "", [], {}):
            return True
    return False


def _fallback_shot_score(root_cause: str, shot: dict[str, Any], index: int) -> tuple[int, int]:
    """Return a stable score; lower means a stronger repair candidate."""

    if root_cause == "WEAK_EDIT_STRATEGY":
        missing = not _field_present(shot, "edit.cut_reason", "edit.rhythm_change", "edit.reaction_timing")
    elif root_cause == "WEAK_EMOTION_ARC":
        missing = not _field_present(shot, "emotion", "performance_direction")
    elif root_cause == "WEAK_INFORMATION_STRATEGY":
        missing = not _field_present(shot, "information_strategy")
    elif root_cause == "PERFORMANCE_DIRECTION_WEAK":
        missing = not _field_present(shot, "performance_direction")
    elif root_cause == "CAMERA_LANGUAGE_GENERIC":
        missing = not _field_present(shot, "camera", "composition")
    else:
        missing = False
    return (0 if missing else 1, index)


def resolve_tail_repair_context(
    *,
    root_cause: str,
    opportunities: Iterable[dict[str, Any]] = (),
    treatment: dict[str, Any] | None = None,
    structural_candidate: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
    quality_issues: Iterable[Any] = (),
    target_dimensions: Iterable[str] | None = None,
    max_opportunities: int = 5,
    max_beats: int = 3,
    max_shots: int = 4,
) -> dict[str, Any]:
    """Resolve bounded, root-cause-scoped evidence for a provider request."""

    dimensions = {str(value).strip() for value in (target_dimensions or TARGET_DIMENSIONS_BY_ROOT_CAUSE.get(root_cause, set())) if str(value).strip()}
    source_opportunities = [copy.deepcopy(item) for item in opportunities if isinstance(item, dict)]
    selected_opportunities = [
        item for item in source_opportunities
        if bool(item.get("eligible", True))
        and dimensions.intersection({str(value).strip().upper() for value in _list(item.get("recommended_directing_dimensions"))})
    ]
    selected_opportunities.sort(key=lambda item: (_priority(item.get("priority")), _text(item.get("opportunity_id")), _text(item.get("beat_id"))))
    selected_opportunities = selected_opportunities[: max(0, int(max_opportunities))]

    beat_map = _beat_map(_dict(treatment))
    shots = _shot_rows(_dict(structural_candidate))
    shots_by_beat: dict[str, list[tuple[int, str, dict[str, Any]]]] = {}
    for row in shots:
        beat_id = _text(row[2].get("beat_id"))
        if beat_id:
            shots_by_beat.setdefault(beat_id, []).append(row)

    selected_beat_ids: list[str] = []
    for item in selected_opportunities:
        beat_id = _text(item.get("beat_id"))
        if beat_id and beat_id not in selected_beat_ids:
            selected_beat_ids.append(beat_id)
    relevant_beats = [copy.deepcopy(beat_map[beat_id]) for beat_id in selected_beat_ids if beat_id in beat_map][: max(0, int(max_beats))]

    relevant_shots: list[dict[str, Any]] = []
    seen_shots: set[str] = set()
    for beat_id in selected_beat_ids:
        for _, shot_id, shot in shots_by_beat.get(beat_id, []):
            if shot_id not in seen_shots:
                relevant_shots.append(shot)
                seen_shots.add(shot_id)
            if len(relevant_shots) >= max(0, int(max_shots)):
                break
        if len(relevant_shots) >= max(0, int(max_shots)):
            break

    fallback_reason = ""
    if not relevant_shots:
        ranked = sorted(shots, key=lambda row: _fallback_shot_score(root_cause, row[2], row[0]))
        relevant_shots = [row[2] for row in ranked[: max(0, min(int(max_shots), 3))]]
        if relevant_shots:
            fallback_reason = f"fallback:{root_cause}:missing_opportunity_shot_binding"

    if not relevant_beats:
        fallback_beat_ids = []
        for shot in relevant_shots:
            beat_id = _text(shot.get("beat_id"))
            if beat_id and beat_id in beat_map and beat_id not in fallback_beat_ids:
                fallback_beat_ids.append(beat_id)
        selected_beat_ids = fallback_beat_ids[: max(0, int(max_beats))]
        relevant_beats = [copy.deepcopy(beat_map[beat_id]) for beat_id in selected_beat_ids]

    allowed_ids = [_shot_id(shot, index) for index, shot in enumerate(relevant_shots)]
    return {
        "root_cause": root_cause,
        "target_dimensions": sorted(dimensions),
        "relevant_opportunities": selected_opportunities,
        "relevant_beats": relevant_beats,
        "relevant_shots": relevant_shots,
        "allowed_plan_shot_ids": allowed_ids,
        "relevant_opportunity_ids": [_text(item.get("opportunity_id")) for item in selected_opportunities if _text(item.get("opportunity_id"))],
        "relevant_beat_ids": selected_beat_ids,
        "relevant_plan_shot_ids": allowed_ids,
        "fallback_reason": fallback_reason,
        "bounded": {"max_opportunities": int(max_opportunities), "max_beats": int(max_beats), "max_shots": int(max_shots)},
    }


__all__ = ["TARGET_DIMENSIONS_BY_ROOT_CAUSE", "resolve_tail_repair_context"]
