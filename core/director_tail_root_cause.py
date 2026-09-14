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

ROOT_CAUSE_RANKER_V2_SCHEMA_VERSION = "director_quality_tail_root_cause_ranker_v2"
ROOT_CAUSE_PRIORITY_WEIGHTS = {"high": 1.0, "medium": 0.7, "low": 0.4}
ROOT_CAUSE_EXPECTED_IMPACT = {
    "WEAK_EDIT_STRATEGY": 1.0,
    "WEAK_EMOTION_ARC": 1.0,
    "WEAK_INFORMATION_STRATEGY": 1.0,
    "PERFORMANCE_DIRECTION_WEAK": 0.9,
    "CAMERA_LANGUAGE_GENERIC": 0.7,
    "LOW_USEFUL_ACCEPTANCE": 0.8,
    "PATCH_QUALITY_WEAK": 0.8,
    "OVER_DIRECTING": 0.7,
    "UNDER_DIRECTING": 0.7,
    "AUXILIARY_SHOT_OVERUSE": 0.5,
    "MISSING_OPPORTUNITY_DETECTION": 0.6,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _eligible_coverage_value(record: dict[str, Any], dimension: str, legacy_key: str) -> float | None:
    """Prefer opportunity-level eligible coverage over legacy field coverage."""

    eligible = _dict(record.get("eligible_coverage"))
    value = _number(eligible.get(dimension))
    if value is not None:
        return value
    return _number(_dict(record.get("coverage")).get(legacy_key))


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
    edit_coverage = _eligible_coverage_value(record, "edit_strategy", "edit_strategy_coverage")
    emotion_coverage = _eligible_coverage_value(record, "emotion_arc", "emotion_arc_coverage")
    information_coverage = _eligible_coverage_value(record, "information_strategy", "information_strategy_coverage")
    if edit_coverage is not None and edit_coverage < 0.8:
        causes.append(("WEAK_EDIT_STRATEGY", "eligible edit strategy coverage is below 0.8"))
    if emotion_coverage is not None and emotion_coverage < 0.85:
        causes.append(("WEAK_EMOTION_ARC", "eligible emotion arc coverage is below 0.85"))
    if information_coverage is not None and information_coverage < 0.85:
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


def _priority_for_cause(record: dict[str, Any], cause: str) -> float:
    priorities = _dict(record.get("opportunity_priority_weights"))
    raw = priorities.get(cause) or priorities.get(cause.lower())
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return max(0.0, float(raw))
    return ROOT_CAUSE_PRIORITY_WEIGHTS.get(str(record.get("priority") or "medium").lower(), 0.7)


def _affected_weight(record: dict[str, Any], cause: str) -> float:
    values = _dict(record.get("affected_opportunity_counts"))
    count = values.get(cause) or values.get(cause.lower())
    if isinstance(count, (int, float)) and not isinstance(count, bool):
        return max(0.0, min(1.0, float(count) / max(1.0, float(record.get("eligible_opportunity_count") or 1))))
    return 1.0


def _severity_deficit(record: dict[str, Any], cause: str, *, quality_threshold: float) -> float:
    coverage = _dict(record.get("eligible_coverage")) or _dict(record.get("coverage"))
    thresholds = {
        "WEAK_EDIT_STRATEGY": (coverage.get("edit_strategy", coverage.get("edit_strategy_coverage")), 0.8),
        "WEAK_EMOTION_ARC": (coverage.get("emotion_arc", coverage.get("emotion_arc_coverage")), 0.85),
        "WEAK_INFORMATION_STRATEGY": (coverage.get("information_strategy", coverage.get("information_strategy_coverage")), 0.85),
        "PERFORMANCE_DIRECTION_WEAK": (coverage.get("performance_direction", coverage.get("performance_direction_coverage")), 0.85),
        "CAMERA_LANGUAGE_GENERIC": (coverage.get("shot_diversity_index"), 0.3),
        "LOW_USEFUL_ACCEPTANCE": (coverage.get("useful_creative_acceptance_rate"), 0.75),
    }
    actual, threshold = thresholds.get(cause, (None, None))
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) and threshold:
        return max(0.0, min(1.0, (float(threshold) - float(actual)) / float(threshold)))
    quality = _number(record.get("director_quality_score"))
    if quality is None:
        quality = _number(_dict(record.get("quality")).get("director_quality_score"))
    if quality is not None:
        return max(0.0, min(1.0, (quality_threshold - quality) / quality_threshold))
    return 0.0


def rank_tail_root_causes_v2(record: dict[str, Any], *, quality_threshold: float = 70.0) -> dict[str, Any]:
    """Rank evidence-backed causes by deterministic severity, not code order."""

    source = record if isinstance(record, dict) else {}
    quality = _number(source.get("director_quality_score"))
    if quality is None:
        quality = _number(_dict(source.get("quality")).get("director_quality_score"))
    classified = classify_tail_root_cause(source, quality_threshold=quality_threshold)
    candidates = [str(item) for item in classified.get("candidate_causes") or [] if str(item) in ROOT_CAUSES and str(item) != "UNKNOWN_ROOT_CAUSE"]
    # A scene outside tail thresholds is explicitly not applicable; it must
    # never acquire UNKNOWN_ROOT_CAUSE merely because no repair is needed.
    if (quality is not None and quality >= quality_threshold and not candidates) and not _repair_signal_present(source):
        return {
            "schema_version": ROOT_CAUSE_RANKER_V2_SCHEMA_VERSION,
            "root_cause": "NOT_APPLICABLE",
            "ranked_root_causes": [],
            "candidate_causes": [],
            "evidence": ["scene does not satisfy tail-repair thresholds"],
        }
    ranked: list[dict[str, Any]] = []
    for cause in candidates:
        deficit = _severity_deficit(source, cause, quality_threshold=quality_threshold)
        score = deficit * _priority_for_cause(source, cause) * _affected_weight(source, cause) * ROOT_CAUSE_EXPECTED_IMPACT.get(cause, 0.5)
        ranked.append({"code": cause, "score": round(score, 6), "normalized_deficit": round(deficit, 6), "priority_weight": _priority_for_cause(source, cause), "affected_opportunity_weight": _affected_weight(source, cause), "expected_quality_impact": ROOT_CAUSE_EXPECTED_IMPACT.get(cause, 0.5)})
    ranked.sort(key=lambda item: (-float(item["score"]), str(item["code"])))
    if not ranked:
        return {
            "schema_version": ROOT_CAUSE_RANKER_V2_SCHEMA_VERSION,
            "root_cause": "UNKNOWN_ROOT_CAUSE",
            "ranked_root_causes": [],
            "candidate_causes": [],
            "evidence": ["tail thresholds are met but no structured cause explains the deficit"],
        }
    return {
        "schema_version": ROOT_CAUSE_RANKER_V2_SCHEMA_VERSION,
        "root_cause": ranked[0]["code"],
        "ranked_root_causes": ranked,
        "candidate_causes": [item["code"] for item in ranked],
        "evidence": list(classified.get("evidence") or []),
    }


def _repair_signal_present(record: dict[str, Any]) -> bool:
    quality = _number(record.get("director_quality_score"))
    if quality is not None and quality < 70:
        return True
    coverage = _dict(record.get("eligible_coverage")) or _dict(record.get("coverage"))
    return any(isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) < threshold for value, threshold in ((coverage.get("edit_strategy", coverage.get("edit_strategy_coverage")), 0.8), (coverage.get("emotion_arc", coverage.get("emotion_arc_coverage")), 0.85), (coverage.get("information_strategy", coverage.get("information_strategy_coverage")), 0.85)))


rank_root_causes_v2 = rank_tail_root_causes_v2


__all__ = ["ROOT_CAUSES", "ROOT_CAUSE_RANKER_V2_SCHEMA_VERSION", "ROOT_CAUSE_PRIORITY_WEIGHTS", "classify_tail_root_cause", "classify_tail_root_causes", "rank_tail_root_causes_v2", "rank_root_causes_v2"]
