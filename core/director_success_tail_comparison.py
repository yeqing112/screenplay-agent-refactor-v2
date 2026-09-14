"""Generic Success-vs-Tail contrast analysis for Director Quality V2.4."""

from __future__ import annotations

import copy
from collections import Counter
from statistics import mean
from typing import Any, Iterable


SUCCESS_TAIL_COMPARISON_SCHEMA_VERSION = "director-quality-v2-4-success-tail-comparison-v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _score(record: dict[str, Any]) -> float | None:
    for value in (record.get("director_quality_score"), _dict(record.get("quality")).get("director_quality_score"), _dict(record.get("quality")).get("score")):
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _distribution(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    counts = Counter()
    for row in rows:
        for item in _list(row.get("opportunities")):
            if isinstance(item, dict):
                value = _text(item.get(key))
                if value:
                    counts[value] += 1
        value_map = _dict(row.get("opportunity_type_distribution"))
        for value, count in value_map.items():
            if isinstance(count, (int, float)) and not isinstance(count, bool):
                counts[_text(value)] += int(count)
    total = sum(counts.values())
    return {"counts": dict(sorted(counts.items())), "total": total, "rates": {key: round(value / total, 4) for key, value in sorted(counts.items())} if total else {}}


def _metric_value(row: dict[str, Any], name: str) -> float | None:
    coverage = _dict(row.get("eligible_coverage")) or _dict(row.get("coverage"))
    telemetry = _dict(row.get("telemetry"))
    quality = _dict(row.get("quality"))
    sources = {
        "eligible_ratio": row.get("eligible_ratio", _dict(row.get("opportunity_value")).get("eligible_opportunity_count")),
        "act_ratio": row.get("act_ratio"),
        "valid_skip_ratio": row.get("valid_skip_rate", _dict(row.get("opportunity_value")).get("valid_skip_rate")),
        "patch_count": row.get("patch_count", _dict(row.get("partial_acceptance")).get("accepted_patch_count")),
        "contract_failure": row.get("contract_failure_count", _dict(row.get("validation")).get("rejected_patch_count")),
        "scene_length": row.get("scene_length", row.get("duration_seconds")),
        "beat_count": row.get("beat_count"),
        "shot_count": row.get("shot_count"),
        "auxiliary_proposal_count": row.get("auxiliary_proposal_count", _dict(row.get("validation")).get("auxiliary_shot_count")),
        "prompt_tokens": row.get("prompt_tokens", telemetry.get("prompt_tokens")),
        "completion_tokens": row.get("completion_tokens", telemetry.get("completion_tokens")),
        "latency_ms": row.get("latency_ms", telemetry.get("latency_ms")),
        "edit_strategy_completeness": coverage.get("edit_strategy", coverage.get("edit_strategy_coverage")),
        "emotion_strategy_completeness": coverage.get("emotion_arc", coverage.get("emotion_arc_coverage")),
        "information_strategy_completeness": coverage.get("information_strategy", coverage.get("information_strategy_coverage")),
        "performance_direction": coverage.get("performance_direction", coverage.get("performance_direction_coverage")),
    }
    if name.startswith("dimension:"):
        return _number(_dict(quality.get("dimensions")).get(name.split(":", 1)[1]))
    return _number(sources.get(name))


COMPARISON_METRICS = (
    "eligible_ratio", "act_ratio", "valid_skip_ratio", "patch_count", "contract_failure",
    "edit_strategy_completeness", "emotion_strategy_completeness", "information_strategy_completeness",
    "performance_direction", "prompt_tokens", "completion_tokens", "latency_ms", "scene_length",
    "beat_count", "shot_count", "auxiliary_proposal_count",
)


def compare_success_tail(
    records: Iterable[dict[str, Any]],
    *,
    success_threshold: float = 90.0,
    tail_threshold: float = 60.0,
) -> dict[str, Any]:
    rows = [item for item in records if isinstance(item, dict) and _score(item) is not None]
    success = [item for item in rows if float(_score(item) or 0) >= float(success_threshold)]
    tail = [item for item in rows if float(_score(item) or 0) < float(tail_threshold)]
    metrics: dict[str, Any] = {}
    for name in COMPARISON_METRICS:
        success_values = [value for row in success if (value := _metric_value(row, name)) is not None]
        tail_values = [value for row in tail if (value := _metric_value(row, name)) is not None]
        success_mean = _mean(success_values)
        tail_mean = _mean(tail_values)
        metrics[name] = {"success_mean": success_mean, "tail_mean": tail_mean, "delta_success_minus_tail": round(success_mean - tail_mean, 4) if success_mean is not None and tail_mean is not None else None, "success_n": len(success_values), "tail_n": len(tail_values)}
    dimensions = sorted({dimension for row in rows for dimension in _dict(_dict(row.get("quality")).get("dimensions"))})
    for dimension in dimensions:
        name = f"dimension:{dimension}"
        success_values = [value for row in success if (value := _metric_value(row, name)) is not None]
        tail_values = [value for row in tail if (value := _metric_value(row, name)) is not None]
        metrics[name] = {"success_mean": _mean(success_values), "tail_mean": _mean(tail_values), "delta_success_minus_tail": round(_mean(success_values) - _mean(tail_values), 4) if success_values and tail_values else None, "success_n": len(success_values), "tail_n": len(tail_values)}
    patterns: list[dict[str, Any]] = []
    for name, metric in metrics.items():
        delta = metric.get("delta_success_minus_tail")
        if isinstance(delta, (int, float)) and abs(float(delta)) >= 0.2:
            direction = "higher_in_success" if delta > 0 else "lower_in_success"
            patterns.append({"pattern": direction, "metric": name, "delta": delta, "evidence": "success/tail group mean contrast"})
    return {
        "schema_version": SUCCESS_TAIL_COMPARISON_SCHEMA_VERSION,
        "status": "ready" if success and tail else "needs_information",
        "thresholds": {"success": float(success_threshold), "tail": float(tail_threshold)},
        "success_count": len(success),
        "tail_count": len(tail),
        "excluded_count": len(rows) - len(success) - len(tail),
        "success_scene_ids": [_text(item.get("scene_id") or item.get("id")) for item in success],
        "tail_scene_ids": [_text(item.get("scene_id") or item.get("id")) for item in tail],
        "opportunity_type_distribution": {"success": _distribution(success, "type"), "tail": _distribution(tail, "type")},
        "metrics": metrics,
        "generalized_success_patterns": patterns,
    }


build_success_tail_comparison = compare_success_tail


__all__ = ["SUCCESS_TAIL_COMPARISON_SCHEMA_VERSION", "COMPARISON_METRICS", "compare_success_tail", "build_success_tail_comparison"]
