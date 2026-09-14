"""Provider-neutral aggregation for the Director Quality V2.3 benchmark.

This module consumes already-recorded artifacts only.  It never imports a
provider client and never mutates production, storyboard, media, or storage
state.  The real MiMo runners are responsible for producing one normalized
sample per ``run_id``/``variant``/``scene_id``; this module supplies the
variance and gate calculations used by the final report.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Iterable


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

COVERAGE_METRICS = (
    "performance_direction_coverage",
    "edit_strategy_coverage",
    "emotion_arc_coverage",
    "information_strategy_coverage",
    "useful_creative_acceptance_rate",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _stats(values: Iterable[float]) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"mean": None, "median": None, "stddev": None, "p25": None, "p75": None}
    return {
        "mean": round(statistics.fmean(ordered), 4),
        "median": round(statistics.median(ordered), 4),
        "stddev": round(statistics.stdev(ordered), 4) if len(ordered) > 1 else 0.0,
        "p25": round(statistics.quantiles(ordered, n=4, method="inclusive")[0], 4) if len(ordered) > 1 else round(ordered[0], 4),
        "p75": round(statistics.quantiles(ordered, n=4, method="inclusive")[2], 4) if len(ordered) > 1 else round(ordered[0], 4),
    }


def _quality_score(record: dict[str, Any]) -> float | None:
    for candidate in (
        record.get("director_quality"),
        _dict(record.get("score")).get("director_quality_score"),
        _dict(_dict(record.get("quality")).get("scorer_direct")).get("director_quality_score"),
        _dict(_dict(record.get("quality")).get("scores")).get("after_repair"),
    ):
        value = _number(candidate)
        if value is not None:
            return value
    return None


def normalize_sample(
    record: dict[str, Any],
    *,
    variant: str,
    run_id: int | str,
    scene_id: str | None = None,
) -> dict[str, Any]:
    """Normalize a runner scene record into the V2.3 sample contract."""

    quality = _dict(record.get("quality"))
    score = _dict(record.get("score"))
    scorer = _dict(quality.get("scorer_direct"))
    dimensions = _dict(record.get("dimensions")) or _dict(scorer.get("dimensions")) or _dict(quality.get("dimensions"))
    coverage = _dict(record.get("coverage")) or _dict(quality.get("v23_coverage"))
    metadata = _dict(record.get("scene"))
    safe_id = _text(scene_id) or _text(metadata.get("scene_id")) or _text(record.get("scene_id"))
    if not safe_id:
        raise ValueError("V2.3 benchmark sample requires scene_id")
    normalized_dimensions = {name: _number(dimensions.get(name)) for name in DIRECTOR_DIMENSIONS}
    normalized_coverage = {name: _number(coverage.get(name)) for name in COVERAGE_METRICS}
    side_effects = _dict(record.get("side_effects"))
    telemetry = _dict(record.get("telemetry"))
    return {
        "scene_id": safe_id,
        "run_id": str(run_id),
        "variant": _text(variant).upper() or "B",
        "director_quality": _quality_score(record),
        "dimensions": normalized_dimensions,
        "coverage": normalized_coverage,
        "contract_pass": bool(record.get("contract_pass", record.get("status") in {"accepted", "success", "succeeded"})),
        "fact_override_accepted": int(record.get("fact_override_accepted") or 0),
        "fallback_count": int(record.get("fallback_count") or len(_list(record.get("fallbacks")))),
        "planner_calls": int(record.get("planner_calls") or 0),
        "repair_calls": int(record.get("repair_calls") or record.get("repair_attempts_count") or 0),
        "tokens": int(record.get("tokens") or telemetry.get("total_tokens") or 0),
        "cached_tokens": int(record.get("cached_tokens") or telemetry.get("total_cached_tokens") or 0),
        "latency_ms": float(record.get("latency_ms") or telemetry.get("avg_latency_ms") or 0),
        "side_effects": {
            str(key): int(value or 0)
            for key, value in side_effects.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        },
    }


def samples_from_offline_benchmark(payload: dict[str, Any], *, run_id: int | str = 1) -> list[dict[str, Any]]:
    """Extract normalized A/B samples from the deterministic V2.3 artifact."""

    samples: list[dict[str, Any]] = []
    for item in _list(payload.get("samples")):
        if not isinstance(item, dict):
            continue
        metadata = _dict(item.get("scene"))
        scene_id = _text(metadata.get("scene_id"))
        for key, variant in (("variant_a", "A"), ("variant_b", "B")):
            entry = _dict(item.get(key))
            if not entry:
                continue
            record = {
                "scene": metadata,
                "score": entry.get("score"),
                "coverage": entry.get("coverage"),
                "contract_pass": item.get("contract_pass", False),
                "side_effects": item.get("side_effects"),
            }
            samples.append(normalize_sample(record, variant=variant, run_id=run_id, scene_id=scene_id))
    return samples


def samples_from_smoke_pilot(payload: dict[str, Any], *, variant: str = "B", run_id: int | str = 1) -> list[dict[str, Any]]:
    """Extract normalized samples from a real MiMo smoke-pilot artifact."""

    return [
        normalize_sample(item, variant=variant, run_id=run_id)
        for item in _list(payload.get("scenes"))
        if isinstance(item, dict)
    ]


def _coverage_stats(samples: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    return {
        metric: _stats(
            value
            for sample in samples
            if (value := _number(_dict(sample.get("coverage")).get(metric))) is not None
        )
        for metric in COVERAGE_METRICS
    }


def aggregate_variance(samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate independent A/B samples and compute the variance gate."""

    rows = [dict(sample) for sample in samples if isinstance(sample, dict)]
    variants = sorted({_text(row.get("variant")).upper() for row in rows if _text(row.get("variant"))})
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[_text(row.get("variant")).upper()].append(row)
    quality = {
        variant: _stats(
            value
            for row in variant_rows
            if (value := _number(row.get("director_quality"))) is not None
        )
        for variant, variant_rows in sorted(by_variant.items())
    }
    coverage = {
        variant: _coverage_stats(variant_rows)
        for variant, variant_rows in sorted(by_variant.items())
    }
    paired: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        paired[(str(row.get("run_id")), _text(row.get("scene_id")))][_text(row.get("variant")).upper()] = row
    paired_deltas = []
    per_scene: dict[str, list[float]] = defaultdict(list)
    for (run_id, scene_id), pair in paired.items():
        a = _number(_dict(pair.get("A")).get("director_quality"))
        b = _number(_dict(pair.get("B")).get("director_quality"))
        if a is None or b is None:
            continue
        delta = round(b - a, 4)
        paired_deltas.append(delta)
        per_scene[scene_id].append(delta)

    run_pairs: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        score = _number(row.get("director_quality"))
        if score is not None:
            run_pairs[str(row.get("run_id"))][_text(row.get("variant")).upper()].append(score)
    run_comparisons = []
    for run_id, pair in sorted(run_pairs.items()):
        if not pair.get("A") or not pair.get("B"):
            continue
        a_mean = statistics.fmean(pair["A"])
        b_mean = statistics.fmean(pair["B"])
        run_comparisons.append({"run_id": run_id, "variant_a_mean": round(a_mean, 4), "variant_b_mean": round(b_mean, 4), "delta": round(b_mean - a_mean, 4), "improved": b_mean > a_mean, "degraded": b_mean < a_mean})

    side_effect_totals: dict[str, int] = defaultdict(int)
    totals = {"planner_calls": 0, "repair_calls": 0, "tokens": 0, "cached_tokens": 0, "latency_ms": 0.0, "fact_override_accepted": 0, "fallback_count": 0}
    for row in rows:
        for key in totals:
            value = row.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] += value
        for key, value in _dict(row.get("side_effects")).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                side_effect_totals[str(key)] += int(value)
    contract_pass = sum(1 for row in rows if bool(row.get("contract_pass")))
    scene_ids = sorted({_text(row.get("scene_id")) for row in rows if _text(row.get("scene_id"))})
    run_ids = sorted({str(row.get("run_id")) for row in rows})
    return {
        "sample_count": len(rows),
        "variants": variants,
        "scene_count": len(scene_ids),
        "independent_run_count": len(run_ids),
        "quality": quality,
        "coverage": coverage,
        "paired_delta": _stats(paired_deltas),
        "per_scene_paired_delta": {scene_id: _stats(values) for scene_id, values in sorted(per_scene.items())},
        "run_comparisons": run_comparisons,
        "improved_run_count": sum(1 for item in run_comparisons if item["improved"]),
        "degraded_run_count": sum(1 for item in run_comparisons if item["degraded"]),
        "variance": {variant: {"score": quality.get(variant), "run_mean": _stats([item[f"variant_{variant.lower()}_mean"] for item in run_comparisons if f"variant_{variant.lower()}_mean" in item])} for variant in variants},
        "safety": {
            "final_contract_pass_rate": round(contract_pass / len(rows), 4) if rows else None,
            "fact_override_accepted": int(totals["fact_override_accepted"]),
            "side_effects": dict(sorted(side_effect_totals.items())),
        },
        "cost": {
            "planner_calls": int(totals["planner_calls"]),
            "repair_calls": int(totals["repair_calls"]),
            "tokens": int(totals["tokens"]),
            "cached_tokens": int(totals["cached_tokens"]),
            "latency_ms": round(float(totals["latency_ms"]), 2),
            "cache_hit_rate": round(float(totals["cached_tokens"]) / float(totals["tokens"]), 4) if totals["tokens"] else None,
        },
    }


__all__ = [
    "DIRECTOR_DIMENSIONS",
    "COVERAGE_METRICS",
    "normalize_sample",
    "samples_from_offline_benchmark",
    "samples_from_smoke_pilot",
    "aggregate_variance",
]
