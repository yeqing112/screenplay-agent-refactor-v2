"""Evidence-first root-cause classification for low-scoring scenes."""

from __future__ import annotations

import copy
from typing import Any, Iterable


ROOT_CAUSES = (
    "MISSING_OPPORTUNITY_DETECTION",
    "WEAK_EDIT_STRATEGY",
    "WEAK_EMOTION_ARC",
    "WEAK_INFORMATION_STRATEGY",
    "LOW_USEFUL_ACCEPTANCE",
    "OVER_DIRECTING",
    "UNDER_DIRECTING",
    "PATCH_QUALITY_WEAK",
    "AUXILIARY_SHOT_OVERUSE",
    "PERFORMANCE_DIRECTION_WEAK",
    "CAMERA_LANGUAGE_GENERIC",
    "UNKNOWN_ROOT_CAUSE",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def classify_tail_root_cause(record: dict[str, Any], *, quality_threshold: float = 70.0) -> dict[str, Any]:
    """Return one primary cause and all evidence-backed candidate causes."""

    coverage = _dict(record.get("coverage"))
    trace = _dict(record.get("quality_trace"))
    trace_summary = _dict(trace.get("summary"))
    validation = _dict(record.get("validation"))
    pipeline = _dict(record.get("pipeline_diagnostics"))
    quality = _number(record.get("director_quality_score"))
    if quality is None:
        quality = _number(_dict(record.get("quality")).get("director_quality_score"))
    causes: list[tuple[str, str]] = []
    if int(trace.get("unknown_root_cause_count") or 0) > 0 or int(trace_summary.get("UNKNOWN") or 0) > 0:
        causes.append(("UNKNOWN_ROOT_CAUSE", "quality trace contains UNKNOWN root cause"))
    if not record.get("opportunities") and not record.get("opportunity_count") and int(trace_summary.get("STRATEGY_MISSING") or 0) > 0:
        causes.append(("MISSING_OPPORTUNITY_DETECTION", "no opportunity evidence reached the scene trace"))
    if _number(coverage.get("edit_strategy_coverage")) is not None and float(coverage["edit_strategy_coverage"]) < 0.8:
        causes.append(("WEAK_EDIT_STRATEGY", "eligible edit strategy coverage is below 0.8"))
    if _number(coverage.get("emotion_arc_coverage")) is not None and float(coverage["emotion_arc_coverage"]) < 0.85:
        causes.append(("WEAK_EMOTION_ARC", "eligible emotion arc coverage is below 0.85"))
    if _number(coverage.get("information_strategy_coverage")) is not None and float(coverage["information_strategy_coverage"]) < 0.85:
        causes.append(("WEAK_INFORMATION_STRATEGY", "eligible information strategy coverage is below 0.85"))
    if _number(coverage.get("useful_creative_acceptance_rate")) is not None and float(coverage["useful_creative_acceptance_rate"]) < 0.75:
        causes.append(("LOW_USEFUL_ACCEPTANCE", "useful creative acceptance is below 0.75"))
    issue_codes = {str(item.get("code") or item.get("issue_code") or "") for item in (_list(validation.get("quality_issues")) + _list(record.get("quality_issues")))}
    issue_codes.update(str(item.get("code") or item.get("issue_code") or "") for item in _list(record.get("issues")))
    if {"OVER_CUTTING", "GRATUITOUS_CAMERA_MOVEMENT", "UNNECESSARY_REACTION_SHOT", "UNNECESSARY_INSERT", "EMOTION_OVEREXPLAINED"} & issue_codes:
        causes.append(("OVER_DIRECTING", "quality diagnostics contain an over-directing issue"))
    if {"UNDER_CUTTING", "RHYTHM_FLATLINE", "EDIT_STRATEGY_MISSING", "EMOTIONAL_FLATLINE"} & issue_codes:
        causes.append(("UNDER_DIRECTING", "quality diagnostics show flat or missing directing choices"))
    if int(validation.get("rejected_patch_count") or 0) > 0 or int(pipeline.get("failed_repairs") or 0) > 0:
        causes.append(("PATCH_QUALITY_WEAK", "patch rejection or failed repair evidence is present"))
    if int(validation.get("auxiliary_shot_count") or 0) > int(validation.get("baseline_shot_count") or 0) * 2 and int(validation.get("baseline_shot_count") or 0) > 0:
        causes.append(("AUXILIARY_SHOT_OVERUSE", "auxiliary shots exceed twice the baseline count"))
    if _number(coverage.get("performance_direction_coverage")) is not None and float(coverage["performance_direction_coverage"]) < 0.85:
        causes.append(("PERFORMANCE_DIRECTION_WEAK", "performance direction coverage is below 0.85"))
    if _number(coverage.get("shot_diversity_index")) is not None and float(coverage["shot_diversity_index"]) < 0.3:
        causes.append(("CAMERA_LANGUAGE_GENERIC", "shot diversity index indicates generic camera language"))
    if quality is not None and quality >= quality_threshold and not causes:
        return {"root_cause": "UNKNOWN_ROOT_CAUSE", "candidate_causes": [], "evidence": ["no tail cause applicable above quality threshold"]}
    primary = causes[0][0] if causes else "UNKNOWN_ROOT_CAUSE"
    return {"root_cause": primary, "candidate_causes": [item[0] for item in causes], "evidence": [item[1] for item in causes] or ["no structured evidence matched"]}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def classify_tail_root_causes(records: Iterable[dict[str, Any]], *, quality_threshold: float = 70.0) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    counts = {cause: 0 for cause in ROOT_CAUSES}
    for record in records:
        if not isinstance(record, dict):
            continue
        result = classify_tail_root_cause(record, quality_threshold=quality_threshold)
        scene_id = str(record.get("scene_id") or record.get("id") or record.get("scene", {}).get("scene_id") or "")
        row = {"scene_id": scene_id, **result}
        rows.append(row)
        counts[result["root_cause"]] = counts.get(result["root_cause"], 0) + 1
    return {"schema_version": "director_quality_tail_root_cause_v1", "records": rows, "counts": {key: value for key, value in counts.items() if value}}


__all__ = ["ROOT_CAUSES", "classify_tail_root_cause", "classify_tail_root_causes"]
