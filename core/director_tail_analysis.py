"""Distribution and long-tail analysis for Director/Creative Value scores."""

from __future__ import annotations

import copy
import math
from typing import Any, Iterable


TAIL_ANALYSIS_SCHEMA_VERSION = "director_quality_tail_analysis_v1"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _score(record: dict[str, Any], key: str) -> float | None:
    value: Any = record.get(key)
    if value is None and key == "director_quality_score":
        quality = record.get("quality")
        if isinstance(quality, dict):
            value = quality.get("director_quality_score")
            if value is None:
                value = (quality.get("overall_director_quality") or {}).get("after_repair") if isinstance(quality.get("overall_director_quality"), dict) else None
    if value is None and key == "creative_value_score":
        value = (record.get("creative_value") or {}).get("score") if isinstance(record.get("creative_value"), dict) else None
    return _number(value)


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, math.ceil(float(percentile) * len(values)) - 1))
    return values[index]


def build_tail_analysis(records: Iterable[dict[str, Any]], *, score_key: str = "director_quality_score") -> dict[str, Any]:
    """Build deterministic distribution statistics and preserve bottom records."""

    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        value = _score(record, score_key)
        if value is None:
            continue
        scene_id = str(record.get("scene_id") or record.get("id") or record.get("scene", {}).get("scene_id") or f"record-{index}")
        rows.append({"scene_id": scene_id, "score": value, "record": copy.deepcopy(record)})
    rows.sort(key=lambda item: (float(item["score"]), item["scene_id"]))
    values = [float(item["score"]) for item in rows]
    buckets = {
        "<60": sum(value < 60 for value in values),
        "60-69": sum(60 <= value < 70 for value in values),
        "70-79": sum(70 <= value < 80 for value in values),
        "80-89": sum(80 <= value < 90 for value in values),
        ">=90": sum(value >= 90 for value in values),
    }
    bottom_count = min(len(rows), max(1, math.ceil(len(rows) * 0.2))) if rows else 0
    stats = {
        "count": len(values),
        "min": min(values) if values else None,
        "p10": _nearest_rank(values, 0.10),
        "p25": _nearest_rank(values, 0.25),
        "median": _nearest_rank(values, 0.50),
        "p75": _nearest_rank(values, 0.75),
        "p90": _nearest_rank(values, 0.90),
        "max": max(values) if values else None,
    }
    return {
        "schema_version": TAIL_ANALYSIS_SCHEMA_VERSION,
        "score_key": score_key,
        "statistics": stats,
        "buckets": buckets,
        "bottom_3_scenes": copy.deepcopy(rows[:3]),
        "bottom_20_percent": copy.deepcopy(rows[:bottom_count]),
    }


__all__ = ["TAIL_ANALYSIS_SCHEMA_VERSION", "build_tail_analysis"]
