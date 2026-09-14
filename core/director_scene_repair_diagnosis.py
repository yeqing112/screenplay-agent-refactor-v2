"""Deterministic Scene Repair Diagnosis and opportunity map."""
from __future__ import annotations

from typing import Any, Iterable

from core.director_quality_validator import DIRECTOR_DIMENSIONS, DIRECTOR_WEIGHTS, score_director_quality
from core.director_scene_repair_scope import SCENE_ALLOWED_DIMENSIONS


def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []
def _text(value: Any) -> str: return str(value or "").strip()
def _shot_id(shot: dict[str, Any], index: int) -> str: return _text(shot.get("plan_shot_id") or shot.get("shot_id")) or f"S{index + 1:02d}"


def diagnose_scene_repair(*, candidate: dict[str, Any], treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, opportunities: Iterable[dict[str, Any]] = (), quality: dict[str, Any] | None = None, quality_issues: Iterable[dict[str, Any]] = (), creative_value: dict[str, Any] | None = None) -> dict[str, Any]:
    shots = [item for item in _list(candidate.get("shots")) if isinstance(item, dict)]
    score = quality if isinstance(quality, dict) and isinstance(quality.get("dimensions"), dict) else score_director_quality(candidate, treatment=treatment, blocking=blocking)
    dimensions = {name: float(_dict(score.get("dimensions")).get(name, 0.0)) for name in DIRECTOR_DIMENSIONS}
    weak = [name for name in SCENE_ALLOWED_DIMENSIONS if dimensions.get(name, 0.0) < 8.0]
    selected = sorted(weak, key=lambda name: (-(8.0 - dimensions.get(name, 0.0)) * DIRECTOR_WEIGHTS[name], -DIRECTOR_WEIGHTS[name], name))[:5]
    issue_codes = {_text(item.get("code") or item.get("issue_code")) for item in quality_issues if isinstance(item, dict)}
    issue_codes.update(_text(item.get("code") or item.get("issue_code")) for item in score.get("issues", []) if isinstance(item, dict))
    patterns: list[str] = []
    mapping = {"CAMERA_REPETITION": "camera_repetition", "EMOTIONAL_FLATLINE": "flat_emotional_line", "REDUNDANT_SHOT": "weak_composition_progression", "POWER_SHIFT_NOT_VISUALIZED": "unvisualized_power_shift", "UNMOTIVATED_SHOT": "weak_shot_motivation"}
    patterns.extend(mapping[code] for code in sorted(issue_codes) if code in mapping)
    if not any(_dict(shot.get("information_strategy")) for shot in shots): patterns.append("missing_information_strategy")
    if not any(_list(shot.get("performance_direction")) for shot in shots): patterns.append("weak_performance_coverage")
    if len({_text(_dict(shot.get("edit")).get("duration_seconds")) for shot in shots}) <= 1 and len(shots) > 1: patterns.append("uniform_edit_rhythm")
    camera_signatures = {
        (
            _text(_dict(shot.get("camera")).get("shot_size")),
            _text(_dict(shot.get("camera")).get("angle")),
            _text(_dict(shot.get("camera")).get("movement")),
        )
        for shot in shots
    }
    if len(shots) > 1 and len(camera_signatures) <= 1: patterns.append("poor_visual_escalation")
    if len(shots) > 1 and not any(_dict(shot.get("composition")) for shot in shots): patterns.append("weak_composition_progression")
    patterns = list(dict.fromkeys(patterns))
    budget = min(len(shots), 8, max(0, int(len(shots) * 0.7 + 0.9999))) if shots else 0
    affected = [_shot_id(shot, index) for index, shot in enumerate(shots[:budget])]
    excluded = [name for name in SCENE_ALLOWED_DIMENSIONS if name not in selected]
    potential = round(sum((10.0 - dimensions.get(name, 0.0)) / 10.0 * DIRECTOR_WEIGHTS[name] for name in selected), 4)
    return {"schema_version": "director_scene_repair_diagnosis_v1", "scene_id": _text(candidate.get("scene_id")), "weak_dimensions": weak, "dimension_scores": dimensions, "dimension_weights": DIRECTOR_WEIGHTS.copy(), "repairable_dimensions": list(SCENE_ALLOWED_DIMENSIONS), "selected_dimensions": selected, "excluded_dimensions": excluded, "affected_shots": affected, "affected_shot_ratio": round(len(affected) / len(shots), 4) if shots else 0.0, "cross_shot_patterns": patterns, "known_constraints": {"facts_frozen": True, "topology_frozen": True, "continuity_frozen": True}, "current_scorer_blockers": sorted(issue_codes), "potential_value_contribution": potential, "creative_value_evidence": {"status": "CV_CEILING_NOT_MEASURABLE" if creative_value is not None else "not_supplied"}}


__all__ = ["diagnose_scene_repair"]
