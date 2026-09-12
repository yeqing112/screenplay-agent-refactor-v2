"""Canonical metric schema for production pilot reports.

The previous report used ``human_intervention_rate`` for two different
quantities.  These helpers keep approval-gate events separate from manual
edits and expose repair yield per responsibility layer.
"""
from __future__ import annotations

from typing import Any


REPAIR_LAYERS = ("script_ir", "treatment", "scene_blocking", "shot_plan", "prompt_ir")


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def build_pilot_metrics(*, approval_gate_event_count: int = 0, approval_gate_total: int = 0, manual_shot_edit_count: int = 0, shot_count: int = 0, manual_scene_edit_count: int = 0, scene_count: int = 0, repair_yield: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """Return a collision-free aggregate metrics object."""
    yield_input = repair_yield if isinstance(repair_yield, dict) else {}
    normalized_yield: dict[str, Any] = {"overall_repair_yield": yield_input.get("overall_repair_yield")}
    for layer in REPAIR_LAYERS:
        key = f"{layer}_repair_yield"
        normalized_yield[key] = yield_input.get(key)
    result = {
        "approval_gate_event_count": int(approval_gate_event_count),
        "approval_gate_rate": _rate(int(approval_gate_event_count), int(approval_gate_total)),
        "manual_shot_edit_count": int(manual_shot_edit_count),
        "manual_shot_edit_rate": _rate(int(manual_shot_edit_count), int(shot_count)),
        "manual_scene_edit_count": int(manual_scene_edit_count),
        "manual_scene_edit_rate": _rate(int(manual_scene_edit_count), int(scene_count)),
        "repair_yield": normalized_yield,
    }
    # Preserve non-conflicting caller metrics while preventing the old
    # ambiguous key from being reintroduced.
    for key, value in extra.items():
        if key not in result and key != "human_intervention_rate":
            result[key] = value
    return result

def add_pipeline_completion(metrics: dict[str, Any], *, approved_scenes: int, total_scenes: int, completed_episodes: int, total_episodes: int) -> dict[str, Any]:
    """Attach scene/episode completion KPIs without changing source data."""
    result = dict(metrics)
    result["scene_pipeline_completion_rate"] = _rate(int(approved_scenes), int(total_scenes))
    result["episode_pipeline_completion_rate"] = _rate(int(completed_episodes), int(total_episodes))
    result["scene_pipeline_completion"] = {"approved": int(approved_scenes), "total": int(total_scenes)}
    result["episode_pipeline_completion"] = {"completed": int(completed_episodes), "total": int(total_episodes)}
    return result
