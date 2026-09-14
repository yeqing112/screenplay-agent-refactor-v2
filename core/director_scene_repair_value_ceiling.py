"""Provider-free bounded Scene Repair reachability."""
from __future__ import annotations

import copy
from typing import Any, Iterable

from core.director_patch_validator import compile_and_validate_creative_patches
from core.director_quality_validator import score_director_quality
from core.director_scene_repair_contract import build_scene_repair_contract
from core.director_scene_repair_diagnosis import diagnose_scene_repair
from core.director_scene_repair_ir_compiler import compile_scene_repair_ir
from core.director_scene_repair_scope import SCENE_ALLOWED_DIMENSIONS


def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []
def _text(value: Any) -> str: return str(value or "").strip()


def _event(shot: dict[str, Any]) -> str: return _text(shot.get("event") or shot.get("purpose") or shot.get("dramatic_function") or "the beat")
def _subject(shot: dict[str, Any]) -> str: return _text(_dict(shot.get("composition")).get("dominant_subject") or (_list(shot.get("participants"))[0] if _list(shot.get("participants")) else "subject"))


def _decision(shot: dict[str, Any], index: int, selected: set[str]) -> dict[str, Any]:
    sid = _text(shot.get("plan_shot_id"))
    event = _event(shot)
    out: dict[str, Any] = {"plan_shot_id": sid, "reason": f"scene-level progression for {event}"}
    if "EDIT_RHYTHM" in selected:
        out["edit"] = {"cut_reason": f"cut on completion of {event}", "duration_seconds": (2.0, 2.5, 3.0, 3.5, 4.0)[index % 5], "rhythm_change": "beat-linked variation"}
    if "EMOTIONAL_PROGRESSION" in selected:
        intensity = (2.0, 5.0, 8.0, 6.0, 4.0)[index % 5]
        out["emotion"] = {"intensity": intensity, "start": f"phase_{index + 1}_start", "end": f"phase_{index + 1}_end", "arc_position": f"scene_phase_{index + 1}"}
    if "PERFORMANCE_DIRECTION" in selected:
        out["performance_direction"] = [{"character_id": _text(char), "objective": f"pursue the objective in {event}", "visible_behavior": f"make {event} visible through controlled action"} for char in _list(shot.get("participants")) if _text(char)]
    if "INFORMATION_STRATEGY" in selected:
        out["information_strategy"] = {"reveals": [event], "withholds": [f"what follows beat {index + 1}"], "audience_focus": _subject(shot)}
    if "SHOT_MOTIVATION" in selected or "DRAMATIC_CLARITY" in selected:
        out["why_this_shot"] = f"show {event} so the audience can follow the scene turn"
        out["purpose"] = _text(shot.get("purpose")) or "action"
    # A motivated shot may require a deliberate camera choice even when the
    # diagnosis did not spend a separate diversity/storytelling dimension.
    # Keep this within the selected dimension budget while ensuring the IR
    # carries an auditable camera decision for every shot-motivation repair.
    if "VISUAL_STORYTELLING" in selected or "SHOT_DIVERSITY" in selected or "SHOT_MOTIVATION" in selected:
        palette = (("WS", "eye_level", "static", "slow", "left"), ("MS", "eye_level", "push_in", "slow", "right"), ("CU", "low", "static", "moderate", "center"))
        out["camera"] = dict(zip(("shot_size", "angle", "movement", "speed", "camera_side"), palette[index % len(palette)]))
        out["composition"] = {"dominant_subject": _subject(shot), "frame_relationship": "subject-to-space progression", "visual_emphasis": event}
        out.setdefault("why_this_shot", f"use a coherent visual change to show {event}")
    if "POWER_DYNAMICS" in selected:
        out["composition"] = {**_dict(out.get("composition")), "frame_relationship": "power contrast"}
    return out


def build_scene_repair_ir(*, candidate: dict[str, Any], diagnosis: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    selected = set(diagnosis.get("selected_dimensions") or []) & set(SCENE_ALLOWED_DIMENSIONS)
    allowed = set(contract.get("allowed_shot_ids") or [])
    shots = [shot for shot in _list(candidate.get("shots")) if isinstance(shot, dict) and _text(shot.get("plan_shot_id")) in allowed]
    return {"schema_version": "director_scene_repair_ir_v1", "scene_id": _text(candidate.get("scene_id")), "strategy_summary": "bounded multi-dimensional scene repair", "target_dimensions": sorted(selected), "scene_level_intent": "improve cross-shot progression while preserving approved facts and topology", "shot_decisions": [_decision(shot, index, selected) for index, shot in enumerate(shots)]}


def execute_bounded_scene_repair(*, candidate: dict[str, Any], treatment: dict[str, Any] | None = None, blocking: dict[str, Any] | None = None, base_contract: dict[str, Any] | None = None, quality: dict[str, Any] | None = None, quality_issues: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    diagnosis = diagnose_scene_repair(candidate=candidate, treatment=treatment, blocking=blocking, quality=quality, quality_issues=quality_issues)
    contract = build_scene_repair_contract(candidate=candidate, base_contract=base_contract, scene_id=_text(candidate.get("scene_id")), allowed_dimensions=diagnosis.get("selected_dimensions"), affected_shot_ids=diagnosis.get("affected_shots"))
    ir = build_scene_repair_ir(candidate=candidate, diagnosis=diagnosis, contract=contract)
    compiled = compile_scene_repair_ir(ir, contract=contract)
    validation = compile_and_validate_creative_patches(candidate, compiled["patch_document"], contract, treatment=treatment, blocking=blocking)
    return {"schema_version": "director-quality-v2-4-5a-bounded-scene-repair-v1", "diagnosis": diagnosis, "contract": contract, "ir": ir, "compiled": compiled, "validation": validation, "candidate": _dict(_dict(validation.get("compilation")).get("candidate")), "provider_calls": 0}


__all__ = ["build_scene_repair_ir", "execute_bounded_scene_repair"]
