"""Evidence trace for Director Quality signal chains.

The quality scorer is intentionally deterministic and side-effect free.  This
module adds provenance around that scorer without changing its weights or
rules.  It accepts stage snapshots supplied by callers (strategy, provider
output, accepted patch and final candidate) and reports where a dimension's
signal disappeared or failed to qualify.

The trace is diagnostic data only.  It never repairs a candidate, infers a
creative value, or relaxes the Director Contract.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Iterable

from core.director_quality_validator import DIRECTOR_DIMENSIONS, score_director_quality


MISSING_STAGES = (
    "STRATEGY_MISSING",
    "PLANNER_NOT_OUTPUT",
    "PATCH_REJECTED",
    "PATCH_FALLBACK",
    "FIELD_DROPPED",
    "SCORER_PATH_MISMATCH",
    "SCORER_RULE_FAILURE",
    "MODEL_QUALITY_LOW",
    "NOT_APPLICABLE",
    "UNKNOWN",
)

_DIMENSION_FIELDS: dict[str, tuple[str, ...]] = {
    "DRAMATIC_CLARITY": ("purpose",),
    "SHOT_MOTIVATION": ("why_this_shot", "purpose", "dramatic_function"),
    "EMOTIONAL_PROGRESSION": ("emotion.intensity",),
    "VISUAL_STORYTELLING": ("purpose", "composition", "information_strategy"),
    "SPATIAL_CLARITY": ("continuity_contract", "camera.camera_side", "composition.frame_relationship"),
    "PERFORMANCE_DIRECTION": ("performance_direction",),
    "EDIT_RHYTHM": ("edit.cut_reason", "edit.duration_seconds", "duration_hint_seconds"),
    "INFORMATION_STRATEGY": ("information_strategy.reveals", "information_strategy.withholds", "information_strategy.audience_focus"),
    "POWER_DYNAMICS": ("treatment.beat_map", "camera", "composition.frame_relationship"),
    "SHOT_DIVERSITY": ("camera",),
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _shot_id(shot: dict[str, Any], index: int = 0) -> str:
    return _text(shot.get("plan_shot_id") or shot.get("shot_id")) or f"S{index + 1:02d}"


def _shots(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("shots")
    return [item for item in _list(value) if isinstance(item, dict)]


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _has_value(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _field_present(shot: dict[str, Any], dimension: str) -> bool:
    return any(_has_value(_get_path(shot, field)) for field in _DIMENSION_FIELDS.get(dimension, ()))


def _performance_scorer_value(value: Any) -> bool:
    """Mirror the scorer's accepted shape without scoring or coercion."""

    return isinstance(value, list) and any(
        isinstance(item, dict)
        and _text(item.get("objective"))
        and _text(item.get("visible_behavior"))
        for item in value
    )


def _emotion_scorer_value(shot: dict[str, Any]) -> bool:
    value = _dict(shot.get("emotion")).get("intensity")
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _edit_scorer_value(shot: dict[str, Any]) -> bool:
    return bool(_text(_dict(shot.get("edit")).get("cut_reason")) and (
        isinstance(_dict(shot.get("edit")).get("duration_seconds"), (int, float))
        or isinstance(shot.get("duration_hint_seconds"), (int, float))
    ))


def _info_scorer_value(shot: dict[str, Any]) -> bool:
    info = _dict(shot.get("information_strategy"))
    return any(_has_value(info.get(key)) for key in ("reveals", "withholds", "audience_focus"))


def scorer_field_present(dimension: str, shot: dict[str, Any] | None) -> bool:
    """Return whether *shot* has a value in the shape read by the scorer."""

    shot = shot if isinstance(shot, dict) else {}
    if dimension == "PERFORMANCE_DIRECTION":
        return _performance_scorer_value(shot.get("performance_direction"))
    if dimension == "EMOTIONAL_PROGRESSION":
        return _emotion_scorer_value(shot)
    if dimension == "EDIT_RHYTHM":
        return _edit_scorer_value(shot)
    if dimension == "INFORMATION_STRATEGY":
        return _info_scorer_value(shot)
    return _field_present(shot, dimension)


def _stage_snapshot_has(snapshot: Any, shot_id: str, dimension: str) -> bool:
    """Check a stage snapshot in either complete-plan or shot-list form."""

    for index, shot in enumerate(_shots(snapshot)):
        if _shot_id(shot, index) != shot_id:
            continue
        return _field_present(shot, dimension)
    if isinstance(snapshot, dict):
        # A patch document may carry dotted changes rather than complete shots.
        for patch in _list(snapshot.get("patches")):
            if not isinstance(patch, dict) or _text(patch.get("plan_shot_id")) != shot_id:
                continue
            changes = patch.get("changes") if isinstance(patch.get("changes"), dict) else {}
            prefixes = _DIMENSION_FIELDS.get(dimension, ())
            return any(any(_text(path).replace("/", ".").endswith(prefix) or prefix in _text(path).replace("/", ".") for prefix in prefixes) for path in changes)
    return False


def _rejected_for_shot(value: Any, shot_id: str) -> bool:
    if not isinstance(value, dict):
        return False
    for item in _list(value.get("rejected_patches")) + _list(value.get("rejected")):
        if isinstance(item, dict) and _text(item.get("plan_shot_id") or item.get("target_id")) == shot_id:
            return True
    return False


def _strategy_signal(strategy: Any, shot: dict[str, Any], dimension: str) -> bool:
    strategy = _dict(strategy)
    beat_id = _text(shot.get("beat_id"))
    if not beat_id:
        return False
    if dimension == "PERFORMANCE_DIRECTION":
        return any(isinstance(item, dict) and _text(item.get("beat_id")) == beat_id for item in _list(strategy.get("performance_arc")))
    if dimension == "EDIT_RHYTHM":
        return any(isinstance(item, dict) and _text(item.get("beat_id")) == beat_id for item in _list(strategy.get("rhythm_curve")))
    if dimension == "EMOTIONAL_PROGRESSION":
        curve = strategy.get("emotion_curve") or strategy.get("emotional_curve")
        return any(isinstance(item, dict) and _text(item.get("beat_id")) == beat_id for item in _list(curve))
    if dimension == "INFORMATION_STRATEGY":
        return any(isinstance(item, dict) and _text(item.get("beat_id")) == beat_id for item in _list(strategy.get("information_plan"))) or bool(_dict(strategy.get("information_strategy")))
    return False


def classify_missing_stage(
    *,
    dimension: str,
    strategy_present: bool,
    planner_output_present: bool,
    patch_accepted: bool,
    patch_rejected: bool,
    patch_fallback: bool,
    final_candidate_field_present: bool,
    scorer_field_present: bool,
    dimension_score: float | int | None,
    applicable: bool = True,
) -> str:
    """Classify the first observable break in a quality signal chain."""

    if not applicable:
        return "NOT_APPLICABLE"
    if patch_fallback:
        return "PATCH_FALLBACK"
    if patch_rejected:
        return "PATCH_REJECTED"
    # If a value reached the candidate but is not in the shape read by the
    # scorer, report the concrete terminal mismatch first.  This remains more
    # actionable than masking it with an absent optional strategy snapshot
    # (which is common in V2.2 historical artifacts).
    if final_candidate_field_present and not scorer_field_present:
        return "SCORER_PATH_MISMATCH"
    if not strategy_present and dimension in {"PERFORMANCE_DIRECTION", "EDIT_RHYTHM", "EMOTIONAL_PROGRESSION", "INFORMATION_STRATEGY"}:
        return "STRATEGY_MISSING"
    if not planner_output_present and not patch_accepted and not final_candidate_field_present:
        return "PLANNER_NOT_OUTPUT"
    if patch_accepted and not final_candidate_field_present:
        return "FIELD_DROPPED"
    if scorer_field_present and dimension_score is not None and float(dimension_score) <= 0:
        return "SCORER_RULE_FAILURE"
    if scorer_field_present and dimension_score is not None and float(dimension_score) < 5:
        return "MODEL_QUALITY_LOW"
    if scorer_field_present and dimension_score is not None and float(dimension_score) >= 5:
        # No missing stage: use the existing taxonomy's explicit non-applicable
        # bucket instead of counting a healthy signal as an unknown root cause.
        return "NOT_APPLICABLE"
    if final_candidate_field_present:
        return "UNKNOWN"
    return "UNKNOWN"


def trace_quality_signals(
    *,
    scene_id: str = "",
    strategy: dict[str, Any] | None = None,
    planner_output: dict[str, Any] | list[dict[str, Any]] | None = None,
    accepted_patch: dict[str, Any] | None = None,
    final_candidate: dict[str, Any] | None = None,
    scorer_input: dict[str, Any] | None = None,
    dimension_scores: dict[str, float] | None = None,
    patch_fallback_shot_ids: Iterable[str] | None = None,
    patch_rejected_shot_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build shot × dimension provenance records for one scene.

    The function is deliberately tolerant of absent historical snapshots so
    old artifacts can be traced without migration.  Missing evidence is
    classified explicitly rather than silently treated as a model failure.
    """

    candidate = final_candidate if isinstance(final_candidate, dict) else {}
    score_input = scorer_input if isinstance(scorer_input, dict) else candidate
    shots = _shots(score_input) or _shots(candidate) or _shots(planner_output) or _shots(accepted_patch)
    fallback_ids = {_text(item) for item in (patch_fallback_shot_ids or []) if _text(item)}
    rejected_ids = {_text(item) for item in (patch_rejected_shot_ids or []) if _text(item)}
    if isinstance(accepted_patch, dict):
        rejected_ids.update(_text(item.get("plan_shot_id")) for item in _list(accepted_patch.get("rejected_patches")) if isinstance(item, dict) and _text(item.get("plan_shot_id")))
    scores = dimension_scores or {}
    records: list[dict[str, Any]] = []
    for index, shot in enumerate(shots):
        sid = _shot_id(shot, index)
        for dimension in DIRECTOR_DIMENSIONS:
            strategy_present = _strategy_signal(strategy, shot, dimension)
            planner_present = _stage_snapshot_has(planner_output, sid, dimension)
            accepted_present = _stage_snapshot_has(accepted_patch, sid, dimension)
            final_present = _field_present(next((item for item in _shots(candidate) if _shot_id(item) == sid), shot), dimension)
            scorer_shot = next((item for item in _shots(score_input) if _shot_id(item) == sid), shot)
            scorer_present = scorer_field_present(dimension, scorer_shot)
            raw_value = _get_path(scorer_shot, _DIMENSION_FIELDS.get(dimension, ("",))[0])
            score = scores.get(dimension)
            if score is None:
                try:
                    score = score_director_quality(score_input).get("dimensions", {}).get(dimension)
                except Exception:
                    score = None
            applicable = _field_present(shot, dimension) or strategy_present or planner_present or accepted_present or final_present
            accepted = accepted_present or (isinstance(accepted_patch, dict) and not _rejected_for_shot(accepted_patch, sid) and planner_present)
            missing_stage = classify_missing_stage(
                dimension=dimension,
                strategy_present=strategy_present,
                planner_output_present=planner_present,
                patch_accepted=bool(accepted),
                patch_rejected=sid in rejected_ids or _rejected_for_shot(accepted_patch, sid),
                patch_fallback=sid in fallback_ids,
                final_candidate_field_present=final_present,
                scorer_field_present=scorer_present,
                dimension_score=score,
                applicable=applicable,
            )
            records.append({
                "scene_id": scene_id,
                "plan_shot_id": sid,
                "dimension": dimension,
                "strategy_evidence": strategy_present,
                "planner_output_present": planner_present,
                "patch_accepted": bool(accepted),
                "patch_fallback": sid in fallback_ids,
                "patch_rejected": sid in rejected_ids or _rejected_for_shot(accepted_patch, sid),
                "final_candidate_field_present": final_present,
                "scorer_field_present": scorer_present,
                "scorer_raw_value": copy.deepcopy(raw_value),
                "dimension_score": score,
                "score_reason": "canonical scorer path present" if scorer_present else "canonical scorer path absent or shape mismatch",
                "missing_stage": missing_stage,
            })
    summary = Counter(record["missing_stage"] for record in records)
    return {
        "schema_version": "director_quality_trace_v1",
        "scene_id": scene_id,
        "records": records,
        "summary": {key: int(summary.get(key, 0)) for key in MISSING_STAGES},
        "unknown_root_cause_count": int(summary.get("UNKNOWN", 0)),
    }


def build_quality_trace(**kwargs: Any) -> dict[str, Any]:
    """Friendly alias used by benchmark and integration callers."""

    return trace_quality_signals(**kwargs)


def trace_director_quality(**kwargs: Any) -> dict[str, Any]:
    return trace_quality_signals(**kwargs)


__all__ = [
    "MISSING_STAGES",
    "scorer_field_present",
    "classify_missing_stage",
    "trace_quality_signals",
    "build_quality_trace",
    "trace_director_quality",
]
