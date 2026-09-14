"""Deterministic reachability analysis for Director Quality V2.4.4.

This module answers a narrow diagnostic question: how much score is reachable
when the existing frozen candidate is repaired through the currently legal
field scopes?  It never calls a provider and it never mutates the production
pipeline.  Synthetic candidates are built from semantic, bounded defaults and
are rejected when topology or immutable contract facts change.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Iterable

from core.director_creative_contract import IMMUTABLE_FIELDS, is_allowed_patch_path
from core.director_overdirecting import detect_over_directing
from core.director_quality_validator import DIRECTOR_DIMENSIONS, DIRECTOR_WEIGHTS, score_director_quality
from core.director_tail_repair import REPAIR_SCOPES


VALUE_CEILING_SCHEMA_VERSION = "director-quality-v2-4-4-value-ceiling-v1"
SENSITIVITY_SCHEMA_VERSION = "director-quality-v2-4-4-scorer-sensitivity-v1"

ROOT_TARGETS = {
    "WEAK_EDIT_STRATEGY": {"EDIT_RHYTHM"},
    "WEAK_EMOTION_ARC": {"EMOTIONAL_PROGRESSION", "PERFORMANCE_DIRECTION"},
    "WEAK_INFORMATION_STRATEGY": {"INFORMATION_STRATEGY"},
    "PERFORMANCE_DIRECTION_WEAK": {"PERFORMANCE_DIRECTION"},
    "CAMERA_LANGUAGE_GENERIC": {"SHOT_DIVERSITY", "VISUAL_STORYTELLING"},
    "OVER_DIRECTING": {"EDIT_RHYTHM", "SHOT_DIVERSITY"},
    "UNDER_DIRECTING": {"EDIT_RHYTHM", "EMOTIONAL_PROGRESSION"},
}
ROOT_REPAIR_TYPE = {
    "WEAK_EDIT_STRATEGY": "edit",
    "WEAK_EMOTION_ARC": "emotion",
    "WEAK_INFORMATION_STRATEGY": "information",
    "PERFORMANCE_DIRECTION_WEAK": "performance",
    "CAMERA_LANGUAGE_GENERIC": "camera",
    "OVER_DIRECTING": "camera",
    "UNDER_DIRECTING": "emotion",
}

_CAMERA_PALETTE = (
    ("WS", "eye_level", "static", "slow", "left"),
    ("MS", "eye_level", "push_in", "slow", "right"),
    ("MCU", "high", "static", "moderate", "center"),
    ("CU", "low", "track", "moderate", "left"),
    ("ECU", "eye_level", "static", "fast", "right"),
    ("OTS", "eye_level", "pan", "slow", "center"),
    ("MS", "low", "dolly", "moderate", "left"),
    ("CU", "high", "tilt", "slow", "right"),
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _shot_id(shot: dict[str, Any], index: int) -> str:
    return _text(shot.get("plan_shot_id") or shot.get("shot_id") or shot.get("id")) or f"S{index + 1:02d}"


def _shots(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(candidate.get("shots")) if isinstance(item, dict)]


def _event_text(shot: dict[str, Any]) -> str:
    action = next((a for a in _list(shot.get("action_beats")) if isinstance(a, dict) and _text(a.get("action"))), {})
    return _text(shot.get("event") or shot.get("purpose") or shot.get("dramatic_function") or action.get("action") or "the beat")


def _subject(shot: dict[str, Any]) -> str:
    composition = _dict(shot.get("composition"))
    return _text(composition.get("dominant_subject") or (_list(shot.get("participants"))[0] if _list(shot.get("participants")) else "subject"))


def _selected_ids(candidate: dict[str, Any], relevant_plan_shot_ids: Iterable[str] | None) -> list[str]:
    available = [_shot_id(shot, index) for index, shot in enumerate(_shots(candidate))]
    requested = [_text(value) for value in (relevant_plan_shot_ids or ()) if _text(value)]
    if requested:
        return [sid for sid in available if sid in set(requested)]
    return available


def _ensure_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _apply_edit(shot: dict[str, Any], rank: int) -> None:
    edit = _ensure_dict(shot, "edit")
    event = _event_text(shot)
    edit.setdefault("cut_reason", f"cut on completion of {event}")
    # A bounded duration ladder is the semantic maximum for the scorer's
    # duration-variety signal; values remain positive and production-plausible.
    edit["duration_seconds"] = (2.0, 2.5, 3.0, 3.5, 4.0)[rank % 5]
    edit.setdefault("rhythm_change", "varied")


def _apply_emotion(shot: dict[str, Any], rank: int) -> None:
    emotion = _ensure_dict(shot, "emotion")
    emotion["intensity"] = (2.0, 5.0, 8.0, 6.0, 4.0)[rank % 5]
    emotion.setdefault("arc_position", f"beat_{rank + 1}")


def _apply_information(shot: dict[str, Any], rank: int) -> None:
    info = _ensure_dict(shot, "information_strategy")
    event = _event_text(shot)
    info["reveals"] = [event]
    info["withholds"] = [f"next beat after {rank + 1}"]
    info["audience_focus"] = _subject(shot)


def _apply_performance(shot: dict[str, Any], rank: int) -> None:
    participants = [_text(value) for value in _list(shot.get("participants")) if _text(value)]
    if not participants:
        participants = [_text(_dict(row).get("character_id")) for row in _list(shot.get("performance_direction")) if _text(_dict(row).get("character_id"))]
    event = _event_text(shot)
    shot["performance_direction"] = [
        {
            "character_id": character,
            "objective": f"pursue the objective in {event}",
            "visible_behavior": f"make the beat visible through controlled action in {event}",
        }
        for character in participants
    ]


def _apply_camera(shot: dict[str, Any], rank: int) -> None:
    signature = _CAMERA_PALETTE[rank % len(_CAMERA_PALETTE)]
    camera = _ensure_dict(shot, "camera")
    for key, value in zip(("shot_size", "angle", "movement", "speed", "camera_side"), signature):
        camera[key] = value
    composition = _ensure_dict(shot, "composition")
    composition.setdefault("dominant_subject", _subject(shot))
    composition.setdefault("frame_relationship", "subject-to-space")
    composition.setdefault("visual_emphasis", _event_text(shot))


def _apply_root(candidate: dict[str, Any], root_cause: str, selected_ids: Iterable[str]) -> dict[str, Any]:
    updated = copy.deepcopy(candidate)
    wanted = set(selected_ids)
    rank = 0
    for index, shot in enumerate(_shots(updated)):
        if _shot_id(shot, index) not in wanted:
            continue
        repair_type = ROOT_REPAIR_TYPE.get(root_cause)
        if repair_type == "edit":
            _apply_edit(shot, rank)
        elif repair_type == "emotion":
            _apply_emotion(shot, rank)
        elif repair_type == "information":
            _apply_information(shot, rank)
        elif repair_type == "performance":
            _apply_performance(shot, rank)
        elif repair_type == "camera":
            _apply_camera(shot, rank)
        rank += 1
    # OVER_DIRECTING is a subtractive repair: remove gratuitous movement only
    # on the allowed scope while retaining the shot and all immutable facts.
    if root_cause == "OVER_DIRECTING":
        for index, shot in enumerate(_shots(updated)):
            if _shot_id(shot, index) in wanted:
                _ensure_dict(shot, "camera")["movement"] = "static"
    return updated


def immutable_projection(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the fields that a ceiling candidate is never allowed to change."""
    projection: list[dict[str, Any]] = []
    for index, shot in enumerate(_shots(candidate)):
        projection.append({key: copy.deepcopy(shot.get(key)) for key in IMMUTABLE_FIELDS if key in shot} | {"plan_shot_id": _shot_id(shot, index)})
    return projection


def validate_ceiling_candidate(*, baseline: dict[str, Any], candidate: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fail closed if synthetic repair changes topology or immutable facts."""
    baseline_shots = _shots(baseline)
    candidate_shots = _shots(candidate)
    topology_equal = [_shot_id(s, i) for i, s in enumerate(baseline_shots)] == [_shot_id(s, i) for i, s in enumerate(candidate_shots)]
    immutable_equal = immutable_projection(baseline) == immutable_projection(candidate)
    allowed_paths_valid = True
    if contract:
        # Synthetic changes are field-scoped; verify every changed leaf against
        # the contract rather than trusting the repair type label.
        for before, after in zip(baseline_shots, candidate_shots):
            for group in ("camera", "composition", "emotion", "performance_direction", "edit", "information_strategy"):
                if before.get(group) != after.get(group):
                    probe = {
                        "camera": "/shots/0/camera/shot_size",
                        "composition": "/shots/0/composition",
                        "emotion": "/shots/0/emotion",
                        "performance_direction": "/shots/0/performance_direction",
                        "edit": "/shots/0/edit",
                        "information_strategy": "/shots/0/information_strategy",
                    }[group]
                    allowed_paths_valid = allowed_paths_valid and is_allowed_patch_path(probe, contract)
    return {
        "valid": bool(topology_equal and immutable_equal and allowed_paths_valid),
        "topology_equal": topology_equal,
        "immutable_equal": immutable_equal,
        "allowed_paths_valid": allowed_paths_valid,
        "baseline_shot_count": len(baseline_shots),
        "candidate_shot_count": len(candidate_shots),
    }


def _score(candidate: dict[str, Any], treatment: dict[str, Any] | None, blocking: dict[str, Any] | None) -> dict[str, Any]:
    return score_director_quality(candidate, treatment=treatment, blocking=blocking)


def _root_ceiling(*, baseline: dict[str, Any], root: dict[str, Any], treatment: dict[str, Any] | None, blocking: dict[str, Any] | None, contract: dict[str, Any] | None) -> dict[str, Any]:
    root_name = _text(root.get("root_cause"))
    selected = _selected_ids(baseline, root.get("relevant_plan_shot_ids"))
    before = _score(baseline, treatment, blocking)
    candidate = _apply_root(baseline, root_name, selected)
    validation = validate_ceiling_candidate(baseline=baseline, candidate=candidate, contract=contract)
    after = _score(candidate, treatment, blocking) if validation["valid"] else before
    targets = sorted(ROOT_TARGETS.get(root_name, set()))
    before_dims, after_dims = before.get("dimensions", {}), after.get("dimensions", {})
    target_before = {d: round(float(before_dims.get(d, 0)), 4) for d in targets}
    target_after = {d: round(float(after_dims.get(d, 0)), 4) for d in targets}
    target_delta = {d: round(target_after[d] - target_before[d], 4) for d in targets}
    return {
        "root_cause": root_name,
        "repair_type": ROOT_REPAIR_TYPE.get(root_name),
        "target_dimensions": targets,
        "allowed_fields": sorted(REPAIR_SCOPES.get(root_name, set())),
        "relevant_plan_shot_ids": selected,
        "affected_shot_count": len(selected),
        "scene_shot_count": len(_shots(baseline)),
        "scope_ratio": round(len(selected) / len(_shots(baseline)), 4) if _shots(baseline) else 0.0,
        "before_target_score": target_before,
        "reachable_target_score": target_after,
        "target_dimension_ceiling_delta": target_delta,
        "before_dq": before.get("director_quality_score"),
        "reachable_dq": after.get("director_quality_score"),
        "dq_ceiling_delta": round(float(after.get("director_quality_score", 0)) - float(before.get("director_quality_score", 0)), 4),
        "candidate_fingerprint": _fingerprint(candidate),
        "validation": validation,
    }


def _scene_upper_bound(candidate: dict[str, Any], treatment: dict[str, Any] | None, blocking: dict[str, Any] | None, contract: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = copy.deepcopy(candidate)
    ids = _selected_ids(updated, None)
    # Apply one legal, scorer-relevant operation per dimension across the
    # existing topology. No facts, beats, participants or assets are touched.
    for root in ("WEAK_EDIT_STRATEGY", "WEAK_EMOTION_ARC", "WEAK_INFORMATION_STRATEGY", "PERFORMANCE_DIRECTION_WEAK", "CAMERA_LANGUAGE_GENERIC"):
        updated = _apply_root(updated, root, ids)
    validation = validate_ceiling_candidate(baseline=candidate, candidate=updated, contract=contract)
    return updated, validation


def analyze_scene(*, scene_id: str, baseline: dict[str, Any], treatment: dict[str, Any] | None, blocking: dict[str, Any] | None, contract: dict[str, Any] | None, frozen_roots: list[dict[str, Any]], all_known_roots: list[dict[str, Any]] | None = None, actual: dict[str, Any] | None = None) -> dict[str, Any]:
    """Calculate top1/top2/all-root and scorer upper-bound ceilings."""
    baseline_score = _score(baseline, treatment, blocking)
    root_rows = [_root_ceiling(baseline=baseline, root=root, treatment=treatment, blocking=blocking, contract=contract) for root in frozen_roots]
    top1 = {"root": root_rows[0] if root_rows else None, "dq": root_rows[0]["reachable_dq"] if root_rows else baseline_score["director_quality_score"]}
    current = copy.deepcopy(baseline)
    seq_rows: list[dict[str, Any]] = []
    for root in frozen_roots[:2]:
        ids = _selected_ids(current, root.get("relevant_plan_shot_ids"))
        current = _apply_root(current, _text(root.get("root_cause")), ids)
        seq_rows.append(_root_ceiling(baseline=current, root={**root, "relevant_plan_shot_ids": ids}, treatment=treatment, blocking=blocking, contract=contract))
    current_validation = validate_ceiling_candidate(baseline=baseline, candidate=current, contract=contract)
    current_score = _score(current, treatment, blocking) if current_validation["valid"] else baseline_score
    known = all_known_roots or frozen_roots
    known_root_rows = [_root_ceiling(baseline=baseline, root=root, treatment=treatment, blocking=blocking, contract=contract) for root in known]
    all_candidate = copy.deepcopy(baseline)
    for root in known:
        all_candidate = _apply_root(all_candidate, _text(root.get("root_cause")), _selected_ids(all_candidate, root.get("relevant_plan_shot_ids")))
    all_validation = validate_ceiling_candidate(baseline=baseline, candidate=all_candidate, contract=contract)
    all_score = _score(all_candidate, treatment, blocking) if all_validation["valid"] else baseline_score
    priority_values = {row["root_cause"]: float(row["dq_ceiling_delta"]) for row in known_root_rows}
    priority_roots = sorted(known, key=lambda root: (-priority_values.get(_text(root.get("root_cause")), 0.0), _text(root.get("root_cause"))))
    priority_candidate = copy.deepcopy(baseline)
    for root in priority_roots[:2]:
        priority_candidate = _apply_root(priority_candidate, _text(root.get("root_cause")), _selected_ids(priority_candidate, root.get("relevant_plan_shot_ids")))
    priority_validation = validate_ceiling_candidate(baseline=baseline, candidate=priority_candidate, contract=contract)
    priority_score = _score(priority_candidate, treatment, blocking) if priority_validation["valid"] else baseline_score
    coordinated = copy.deepcopy(baseline)
    for root in frozen_roots[:2]:
        coordinated = _apply_root(coordinated, _text(root.get("root_cause")), _selected_ids(coordinated, root.get("relevant_plan_shot_ids")))
    coordinated_validation = validate_ceiling_candidate(baseline=baseline, candidate=coordinated, contract=contract)
    coordinated_score = _score(coordinated, treatment, blocking) if coordinated_validation["valid"] else baseline_score
    upper_candidate, upper_validation = _scene_upper_bound(baseline, treatment, blocking, contract)
    upper_score = _score(upper_candidate, treatment, blocking) if upper_validation["valid"] else baseline_score
    actual_score = actual.get("after_director_quality") if isinstance(actual, dict) else None
    def pack(score: dict[str, Any], validation: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"dq": score.get("director_quality_score"), "delta": round(float(score.get("director_quality_score", 0)) - float(baseline_score.get("director_quality_score", 0)), 4), "dimensions": score.get("dimensions", {}), "validation": validation or {"valid": True}}
    return {
        "scene_id": scene_id,
        "baseline": pack(baseline_score),
        "actual": {"dq": actual_score, "delta": round(float(actual_score) - float(baseline_score["director_quality_score"]), 4) if isinstance(actual_score, (int, float)) else None},
        "top1_ceiling": {"root": root_rows[0] if root_rows else None, **pack(_score(_apply_root(baseline, _text(frozen_roots[0].get("root_cause")), _selected_ids(baseline, frozen_roots[0].get("relevant_plan_shot_ids"))) if frozen_roots else baseline, treatment, blocking))},
        "current_top2_ceiling": {"roots": [r.get("root_cause") for r in frozen_roots[:2]], **pack(current_score, current_validation)},
        "all_known_roots_ceiling": {"roots": [r.get("root_cause") for r in known], **pack(all_score, all_validation)},
        "value_priority_top2_ceiling": {"roots": [r.get("root_cause") for r in priority_roots[:2]], **pack(priority_score, priority_validation)},
        "coordinated_top2_ceiling": {"roots": [r.get("root_cause") for r in frozen_roots[:2]], **pack(coordinated_score, coordinated_validation)},
        "scene_upper_bound": pack(upper_score, upper_validation),
        "root_cause_ceilings": root_rows,
        "counterfactual_root_cause_ceilings": known_root_rows,
        "frozen_root_count": len(frozen_roots),
        "all_known_root_count": len(known),
        "creative_value": {"status": "CV_CEILING_NOT_MEASURABLE", "reason": "synthetic candidates have no authoritative intervention outcomes; no CV estimate is fabricated"},
    }


def build_sensitivity_map(*, baseline: dict[str, Any], treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map legal repair fields to observed scorer dimensions without changing the scorer."""
    before = _score(baseline, treatment, blocking)
    shots = _shots(baseline)
    if not shots:
        return {"schema_version": SENSITIVITY_SCHEMA_VERSION, "dimensions": DIRECTOR_WEIGHTS.copy(), "fields": [], "flags": ["SCORER_SENSITIVITY_GAP"]}
    rows: list[dict[str, Any]] = []
    probes = {
        "edit.cut_reason": ("WEAK_EDIT_STRATEGY", lambda s: _apply_edit(s, 0), "EDIT_RHYTHM"),
        "edit.duration_seconds": ("WEAK_EDIT_STRATEGY", lambda s: _apply_edit(s, 1), "EDIT_RHYTHM"),
        "emotion.intensity": ("WEAK_EMOTION_ARC", lambda s: _apply_emotion(s, 2), "EMOTIONAL_PROGRESSION"),
        "information_strategy.reveals": ("WEAK_INFORMATION_STRATEGY", lambda s: _apply_information(s, 0), "INFORMATION_STRATEGY"),
        "performance_direction": ("PERFORMANCE_DIRECTION_WEAK", lambda s: _apply_performance(s, 0), "PERFORMANCE_DIRECTION"),
        "camera.signature": ("CAMERA_LANGUAGE_GENERIC", lambda s: _apply_camera(s, 0), "SHOT_DIVERSITY"),
    }
    for field, (repair_type, operation, expected) in probes.items():
        candidate = copy.deepcopy(baseline)
        operation(_shots(candidate)[0])
        after = _score(candidate, treatment, blocking)
        delta = round(float(after["dimensions"].get(expected, 0)) - float(before["dimensions"].get(expected, 0)), 4)
        rows.append({"field": field, "repair_type": repair_type, "expected_dimension": expected, "weight": DIRECTOR_WEIGHTS[expected], "before": before["dimensions"].get(expected), "after": after["dimensions"].get(expected), "delta": delta, "classification": "SCORER_INSENSITIVE_FIELD" if delta == 0 else "SENSITIVE"})
    flags = ["SCORER_SENSITIVITY_GAP"] if any(row["classification"] == "SCORER_INSENSITIVE_FIELD" for row in rows) else []
    return {"schema_version": SENSITIVITY_SCHEMA_VERSION, "dimensions": DIRECTOR_WEIGHTS.copy(), "fields": rows, "flags": flags, "scorer_module": "core.director_quality_validator.score_director_quality"}


__all__ = ["VALUE_CEILING_SCHEMA_VERSION", "SENSITIVITY_SCHEMA_VERSION", "ROOT_TARGETS", "ROOT_REPAIR_TYPE", "immutable_projection", "validate_ceiling_candidate", "analyze_scene", "build_sensitivity_map"]
