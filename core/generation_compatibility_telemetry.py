"""Provider-free evidence for the legacy storyboard generation bridge.

This is intentionally process-local diagnostic telemetry.  It records response
shape only; it never sends data to a SaaS telemetry service and never changes
generation behavior.
"""
from __future__ import annotations

from threading import Lock
from typing import Any, Mapping

_LOCK = Lock()
_COUNTERS = {
    "canonical_execution_response_count": 0,
    "canonical_candidate_response_count": 0,
    "task_id_only_fallback_count": 0,
    "mixed_execution_task_id_response_count": 0,
    "response_count": 0,
}


def record_generation_compatibility_response(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    has_execution = isinstance(data.get("execution"), Mapping)
    has_candidate = isinstance(data.get("candidate"), Mapping)
    has_task_id = bool(str(data.get("task_id") or "").strip())
    with _LOCK:
        _COUNTERS["response_count"] += 1
        if has_execution:
            _COUNTERS["canonical_execution_response_count"] += 1
        if has_candidate:
            _COUNTERS["canonical_candidate_response_count"] += 1
        if has_task_id and has_execution:
            _COUNTERS["mixed_execution_task_id_response_count"] += 1
        elif has_task_id:
            _COUNTERS["task_id_only_fallback_count"] += 1
        return dict(_COUNTERS)


def generation_compatibility_telemetry_snapshot() -> dict[str, Any]:
    with _LOCK:
        return {"schema_version": "generation_compatibility_telemetry_v1", **_COUNTERS, "provider_calls": 0, "llm_calls": 0}


def reset_generation_compatibility_telemetry() -> None:
    with _LOCK:
        for key in _COUNTERS:
            _COUNTERS[key] = 0


__all__ = ["record_generation_compatibility_response", "generation_compatibility_telemetry_snapshot", "reset_generation_compatibility_telemetry"]
