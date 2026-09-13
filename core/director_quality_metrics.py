"""Contract reliability and ten-dimension Director Quality metrics."""

from __future__ import annotations

import copy
from typing import Any

from core.director_quality_validator import DIRECTOR_DIMENSIONS, score_director_quality


def _rate(numerator: int, denominator: int) -> float | None:
    return round(float(numerator) / float(denominator), 4) if denominator else None


def build_director_quality_v22_metrics(
    *,
    stage_counts: dict[str, int] | None = None,
    repair_cost: dict[str, Any] | None = None,
    creative_patch_count: int = 0,
    retained_creative_patch_count: int = 0,
    fallback_free_scene_count: int = 0,
    scene_count: int = 0,
    creative_recoverable_patch_count: int | None = None,
    creative_recovered_patch_count: int = 0,
    safe_fallback_count: int | None = None,
    avoidable_fallback_count: int | None = None,
) -> dict[str, Any]:
    """Build the staged stability/repair-cost metrics required by V2.2.

    Counts are supplied by the runner; this helper performs no quality-rule
    relaxation and returns ``None`` rates when a denominator is unavailable.
    """

    counts = {str(key): int(value or 0) for key, value in (stage_counts or {}).items()}
    stages = {
        "raw_parse_pass": counts.get("raw_parse_pass", 0),
        "normalized_parse_pass": counts.get("normalized_parse_pass", 0),
        "first_pass_schema_pass": counts.get("first_pass_schema_pass", 0),
        "first_pass_contract_pass": counts.get("first_pass_contract_pass", 0),
        "post_normalization_contract_pass": counts.get("post_normalization_contract_pass", 0),
        "post_deterministic_repair_pass": counts.get("post_deterministic_repair_pass", 0),
        "post_llm_repair_pass": counts.get("post_llm_repair_pass", 0),
        "final_contract_pass": counts.get("final_contract_pass", 0),
    }
    denominator = counts.get("total_scenes", scene_count)
    stage_metrics = {
        key: {"count": value, "total": denominator, "rate": _rate(value, denominator)}
        for key, value in stages.items()
    }
    costs = {
        "normalization_events": 0,
        "deterministic_repair_events": 0,
        "llm_repair_calls": 0,
        "llm_repair_calls_per_scene": None,
        "llm_repair_calls_per_failed_patch": None,
        "average_repair_attempts": None,
        "repair_token_cost": 0,
        "repair_latency_ms": 0,
        "fallback_after_repair_count": 0,
    }
    if isinstance(repair_cost, dict):
        costs.update(copy.deepcopy(repair_cost))
    if costs.get("llm_repair_calls_per_scene") is None:
        costs["llm_repair_calls_per_scene"] = _rate(int(costs.get("llm_repair_calls") or 0), denominator)
    result = {
        "stages": stage_metrics,
        "stage_counts": stages | {"total_scenes": denominator},
        "repair_cost": costs,
        "fallback_patch_count": int(counts.get("fallback_patch_count", 0)),
        "fallback_patch_rate": _rate(int(counts.get("fallback_patch_count", 0)), int(counts.get("evaluated_patch_count", 0))),
        "creative_retention_rate": _rate(int(retained_creative_patch_count), int(creative_patch_count)),
        "full_creative_scene_success_rate": _rate(int(fallback_free_scene_count), int(scene_count)),
    }
    if creative_recoverable_patch_count is not None:
        recoverable = int(creative_recoverable_patch_count)
        recovered = int(creative_recovered_patch_count or 0)
        result["creative_recovery_rate"] = _rate(recovered, recoverable)
        result["creative_loss_rate"] = _rate(max(recoverable - recovered, 0), int(creative_patch_count))
    else:
        result["creative_recovery_rate"] = None
        result["creative_loss_rate"] = None
    if safe_fallback_count is not None or avoidable_fallback_count is not None:
        safe = int(safe_fallback_count or 0)
        avoidable = int(avoidable_fallback_count or 0)
        result["fallback_classification"] = {
            "safe_required_fallback_count": safe,
            "avoidable_technical_fallback_count": avoidable,
            "safe_required_fallback_rate": _rate(safe, int(counts.get("fallback_patch_count", 0))),
            "avoidable_technical_fallback_rate": _rate(avoidable, int(counts.get("fallback_patch_count", 0))),
        }
    else:
        result["fallback_classification"] = None
    successful_repairs = int(costs.get("successful_repairs") or 0)
    failed_repairs = int(costs.get("failed_repairs") or 0)
    total_repairs = successful_repairs + failed_repairs
    costs.setdefault("successful_repairs", successful_repairs)
    costs.setdefault("failed_repairs", failed_repairs)
    costs["repair_success_rate"] = _rate(successful_repairs, total_repairs)
    costs.setdefault("creative_patches_saved_by_llm_repair", successful_repairs)
    costs.setdefault("fallbacks_prevented_by_repair", successful_repairs)
    costs["tokens_per_successful_repair"] = _rate(int(costs.get("repair_token_cost") or 0), successful_repairs)
    costs["latency_per_successful_repair_ms"] = _rate(int(costs.get("repair_latency_ms") or 0), successful_repairs)
    return result


def _score(plan: dict[str, Any] | None, *, treatment: dict[str, Any] | None, blocking: dict[str, Any] | None) -> dict[str, Any]:
    return score_director_quality(plan if isinstance(plan, dict) else {}, treatment=treatment, blocking=blocking)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _shots(plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [item for item in _list((plan or {}).get("shots")) if isinstance(item, dict)]


def _key_shot(shot: dict[str, Any], treatment: dict[str, Any] | None = None) -> bool:
    """Deterministically identify shots where performance guidance matters."""

    beat_id = _text(shot.get("beat_id"))
    for beat in _list((treatment or {}).get("beat_map")):
        if isinstance(beat, dict) and _text(beat.get("beat_id")) == beat_id:
            if _text(beat.get("type")).lower() in {"reaction", "reveal", "decision", "power_shift", "dialogue_turn", "emotional_peak", "turn"}:
                return True
    text = " ".join(_text(shot.get(key)).lower() for key in ("purpose", "dramatic_function", "why_this_shot"))
    return any(token in text for token in ("reaction", "reveal", "power", "decision", "反应", "揭示", "权力", "决策", "转折"))


def _valid_performance(shot: dict[str, Any]) -> bool:
    value = shot.get("performance_direction")
    return isinstance(value, list) and any(isinstance(item, dict) and _text(item.get("objective")) and _text(item.get("visible_behavior")) for item in value)


def _valid_edit(shot: dict[str, Any]) -> bool:
    edit = _dict(shot.get("edit"))
    duration = edit.get("duration_seconds", shot.get("duration_hint_seconds"))
    return bool(_text(edit.get("cut_reason"))) and isinstance(duration, (int, float)) and not isinstance(duration, bool) and float(duration) > 0


def _valid_emotion(shot: dict[str, Any]) -> bool:
    value = _dict(shot.get("emotion")).get("intensity")
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= float(value) <= 10


def _valid_information(shot: dict[str, Any]) -> bool:
    info = _dict(shot.get("information_strategy"))
    return any(bool(info.get(key)) for key in ("reveals", "withholds", "audience_focus"))


def build_director_quality_v23_coverage_metrics(
    *,
    candidate: dict[str, Any] | None,
    strategy: dict[str, Any] | None = None,
    treatment: dict[str, Any] | None = None,
    proposed_patch_document: dict[str, Any] | None = None,
    accepted_patch_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute V2.3 coverage without changing the ten-dimension scorer."""

    shots = _shots(candidate)
    key_shots = [shot for shot in shots if _key_shot(shot, treatment)]
    performance_denominator = len(key_shots)
    performance_numerator = sum(1 for shot in key_shots if _valid_performance(shot))
    # A single shot still has an edit decision (where it enters/leaves the
    # scene); coverage is therefore measurable without requiring a neighbor.
    edit_denominator = len(shots)
    edit_numerator = sum(1 for shot in shots if _valid_edit(shot)) if edit_denominator else 0
    strategy_obj = strategy if isinstance(strategy, dict) else {}
    emotion_entries = [item for item in _list(strategy_obj.get("emotion_curve")) if isinstance(item, dict) and _text(item.get("beat_id"))]
    info_entries = [item for item in _list(strategy_obj.get("information_plan")) if isinstance(item, dict) and _text(item.get("beat_id"))]
    shot_by_beat = {_text(shot.get("beat_id")): shot for shot in shots if _text(shot.get("beat_id"))}
    emotion_denominator = len(emotion_entries) or (len(shots) if strategy_obj else 0)
    info_denominator = len(info_entries) or (len(shots) if strategy_obj else 0)
    emotion_numerator = sum(1 for item in emotion_entries if _valid_emotion(shot_by_beat.get(_text(item.get("beat_id")), {})))
    info_numerator = sum(1 for item in info_entries if _valid_information(shot_by_beat.get(_text(item.get("beat_id")), {})))

    proposed = [item for item in _list((proposed_patch_document or {}).get("patches")) if isinstance(item, dict)]
    accepted = [item for item in _list((accepted_patch_document or {}).get("patches")) if isinstance(item, dict)]
    accepted_ids = {_text(item.get("plan_shot_id")) for item in accepted if _text(item.get("plan_shot_id"))}
    useful = 0
    for patch in proposed:
        sid = _text(patch.get("plan_shot_id"))
        if sid not in accepted_ids:
            continue
        changes = _dict(patch.get("changes"))
        roots = {_text(path).replace("/", ".").split(".")[0] for path in changes}
        shot = next((item for item in shots if _text(item.get("plan_shot_id")) == sid), {})
        contributes = (("performance_direction" in roots and _valid_performance(shot)) or ("edit" in roots and _valid_edit(shot)) or ("emotion" in roots and _valid_emotion(shot)) or ("information_strategy" in roots and _valid_information(shot)))
        if contributes:
            useful += 1
    return {
        "performance_direction_coverage": _rate(performance_numerator, performance_denominator),
        "edit_strategy_coverage": _rate(edit_numerator, edit_denominator),
        "emotion_arc_coverage": _rate(emotion_numerator, emotion_denominator),
        "information_strategy_coverage": _rate(info_numerator, info_denominator),
        "useful_creative_acceptance_rate": _rate(useful, len(proposed)),
        "performance_direction_key_shot_count": performance_denominator,
        "edit_strategy_required_shot_count": edit_denominator,
        "emotion_curve_entry_count": emotion_denominator,
        "information_plan_entry_count": info_denominator,
        "useful_creative_patch_count": useful,
        "evaluable_creative_patch_count": len(proposed),
    }


def build_director_quality_metrics(
    *,
    baseline: dict[str, Any],
    first_candidate: dict[str, Any] | None = None,
    final_candidate: dict[str, Any] | None = None,
    treatment: dict[str, Any] | None = None,
    blocking: dict[str, Any] | None = None,
    contract_reliability: dict[str, Any] | None = None,
    partial_acceptance: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
    v22_stage_counts: dict[str, int] | None = None,
    v22_repair_cost: dict[str, Any] | None = None,
    creative_patch_count: int = 0,
    retained_creative_patch_count: int = 0,
    fallback_free_scene_count: int = 0,
    scene_count: int = 0,
    creative_recoverable_patch_count: int | None = None,
    creative_recovered_patch_count: int = 0,
    safe_fallback_count: int | None = None,
    avoidable_fallback_count: int | None = None,
    strategy: dict[str, Any] | None = None,
    proposed_patch_document: dict[str, Any] | None = None,
    accepted_patch_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record Baseline / Before Repair / After Repair separately.

    Missing candidates intentionally fall back to baseline while preserving a
    stage marker, so reports never mistake an absent planner output for a
    successful creative call.
    """

    first = first_candidate if isinstance(first_candidate, dict) else baseline
    final = final_candidate if isinstance(final_candidate, dict) else first
    scored = {
        "baseline": _score(baseline, treatment=treatment, blocking=blocking),
        "before_repair": _score(first, treatment=treatment, blocking=blocking),
        "after_repair": _score(final, treatment=treatment, blocking=blocking),
    }
    dimensions = {
        stage: {name: float(scored[stage]["dimensions"].get(name, 0.0)) for name in DIRECTOR_DIMENSIONS}
        for stage in scored
    }
    overall = {stage: float(scored[stage]["director_quality_score"]) for stage in scored}
    reliability = {
        "schema_pass": None,
        "patch_path_pass": None,
        "fact_override_count": 0,
        "fact_override_attempt_count": 0,
        "forbidden_field_attempt": False,
        "forbidden_field_attempt_count": 0,
        "schema_rejection_count": 0,
        "schema_rejections": [],
        "auxiliary_binding_pass": None,
        "parse_success": None,
        "repair_success": None,
        "scene_planner_success": None,
    }
    if isinstance(contract_reliability, dict):
        reliability.update(copy.deepcopy(contract_reliability))
    schema_rejections = [item for item in (reliability.get("schema_rejections") or []) if isinstance(item, dict)]
    reliability["schema_rejections"] = schema_rejections
    reliability["schema_rejection_count"] = len(schema_rejections)
    reliability["forbidden_field_attempt_count"] = int(reliability.get("forbidden_field_attempt_count") or sum(
        1
        for item in schema_rejections
        if str(item.get("code") or item.get("issue_code") or "") in {
            "DIRECTOR_FACT_OVERRIDE",
            "DIRECTOR_PATCH_FIELD_FORBIDDEN",
            "DIRECTOR_PATCH_PATH_FORBIDDEN",
        }
    ))
    reliability["forbidden_field_attempt"] = bool(reliability.get("forbidden_field_attempt")) or reliability["forbidden_field_attempt_count"] > 0
    reliability["fact_override_attempt_count"] = int(reliability.get("fact_override_attempt_count") or sum(
        1 for item in schema_rejections if str(item.get("code") or item.get("issue_code") or "") == "DIRECTOR_FACT_OVERRIDE"
    ))
    partial = {
        "accepted_patch_count": 0,
        "rejected_patch_count": 0,
        "repaired_patch_count": 0,
        "fallback_patch_count": 0,
    }
    if isinstance(partial_acceptance, dict):
        partial.update({key: int(value or 0) for key, value in partial_acceptance.items() if key in partial})
    result = {
        "director_dimensions": list(DIRECTOR_DIMENSIONS),
        "scores": {
            "baseline": scored["baseline"],
            "before_repair": scored["before_repair"],
            "after_repair": scored["after_repair"],
        },
        "dimensions": dimensions,
        "overall_director_quality": overall,
        "director_quality_delta": round(overall["after_repair"] - overall["baseline"], 2),
        "contract_reliability": reliability,
        "partial_acceptance": partial,
        "v23_coverage": build_director_quality_v23_coverage_metrics(
            candidate=final,
            strategy=strategy,
            treatment=treatment,
            proposed_patch_document=proposed_patch_document,
            accepted_patch_document=accepted_patch_document,
        ),
    }
    if isinstance(telemetry, dict):
        result["telemetry"] = copy.deepcopy(telemetry)
    if any(value is not None for value in (v22_stage_counts, v22_repair_cost)) or creative_patch_count or retained_creative_patch_count or fallback_free_scene_count or scene_count:
        result["v22"] = build_director_quality_v22_metrics(
            stage_counts=v22_stage_counts,
            repair_cost=v22_repair_cost,
            creative_patch_count=creative_patch_count,
            retained_creative_patch_count=retained_creative_patch_count,
            fallback_free_scene_count=fallback_free_scene_count,
            scene_count=scene_count,
            creative_recoverable_patch_count=creative_recoverable_patch_count,
            creative_recovered_patch_count=creative_recovered_patch_count,
            safe_fallback_count=safe_fallback_count,
            avoidable_fallback_count=avoidable_fallback_count,
        )
    return result


record_director_quality_metrics = build_director_quality_metrics
build_quality_metrics = build_director_quality_metrics


__all__ = ["build_director_quality_metrics", "record_director_quality_metrics", "build_quality_metrics", "build_director_quality_v22_metrics", "build_director_quality_v23_coverage_metrics"]
