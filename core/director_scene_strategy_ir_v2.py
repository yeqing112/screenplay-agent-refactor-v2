"""Reference-grounded validator for Director Strategy IR V2."""
from __future__ import annotations

from typing import Any

from core.director_scene_strategy_ir_normalizer import normalize_strategy_ir_v2, normalize_source_ref
from core.director_scene_strategy_semantic_spec_v2 import PHASE_FIELDS, POWER_CENTER_TYPES, TOP_LEVEL_FIELDS, INFORMATION_FIELDS


def _text(value: Any) -> str: return str(value or "").strip()
def _dict(value: Any) -> dict[str, Any]: return value if isinstance(value, dict) else {}
def _list(value: Any) -> list[Any]: return value if isinstance(value, list) else []


def _error(code: str, path: str, **extra: Any) -> dict[str, Any]: return {"code": code, "path": path, **extra}


def _ref_parts(ref: str) -> tuple[str, str]:
    kind, _, ident = _text(ref).partition(":")
    return kind, ident


CANONICAL_BLOCKER_CODES = frozenset({
    "IR_NOT_OBJECT", "IR_SCHEMA_VERSION_INVALID", "IR_REQUIRED_FIELD_MISSING", "UNKNOWN_IR_FIELD",
    "UNKNOWN_INFORMATION_FIELD", "NESTED_FIELD_SHAPE_INVALID", "PHASE_NOT_OBJECT", "PHASE_FIELD_MISSING",
    "PHASE_COUNT_OUT_OF_RANGE", "PHASE_ID_INVALID", "PHASE_BEATS_EMPTY", "BEAT_ASSIGNED_MULTIPLE_TIMES",
    "BEAT_COVERAGE_GAP", "UNKNOWN_BEAT_REFERENCE", "UNKNOWN_SOURCE_REFERENCE", "UNKNOWN_CHARACTER_REFERENCE",
    "SCENE_ID_MISMATCH", "INVALID_POWER_CENTER", "INVALID_POWER_CONTROLLER", "INVALID_POWER_REFERENCE",
    "PERFORMANCE_ROW_INVALID", "PERFORMANCE_FIELD_MISSING", "NESTED_FIELD_MISSING", "EPISTEMIC_CLAIM_INVALID",
    "STRATEGY_LAYER_LEAKAGE", "FACT_AUTHORITY_VIOLATION", "INFERENCE_PROMOTED_TO_FACT", "MODEL_CREATED_SOURCE_FACT",
    "CHARACTER_IDENTITY_BINDING_DRIFT", "AMBIGUOUS_IDENTITY_BINDING",
})


def _beat_index(contract: dict[str, Any], beat_id: str) -> int:
    try: return list(contract.get("beat_ids") or []).index(beat_id)
    except ValueError: return -1


def validate_strategy_ir_v2(raw: Any, *, contract: dict[str, Any]) -> dict[str, Any]:
    normalized_result = normalize_strategy_ir_v2(raw, contract=contract)
    errors = list(normalized_result.get("errors") or [])
    ir = normalized_result.get("ir")
    if not isinstance(ir, dict): return {"valid": False, "ir": None, "canonical_status":"CANONICAL_INVALID", "approval_blockers":[], "errors": errors or [_error("IR_NOT_OBJECT", "$")]}
    if _text(ir.get("schema_version")) != "director_scene_strategy_ir_v2": errors.append(_error("IR_SCHEMA_VERSION_INVALID", "schema_version"))
    if _text(ir.get("scene_id")) != _text(contract.get("scene_id")): errors.append(_error("SCENE_ID_MISMATCH", "scene_id"))
    for field in TOP_LEVEL_FIELDS:
        if field not in ir: errors.append(_error("IR_REQUIRED_FIELD_MISSING", field))
    phases = _list(ir.get("scene_phases"))
    if not 2 <= len(phases) <= 6: errors.append(_error("PHASE_COUNT_OUT_OF_RANGE", "scene_phases", actual=len(phases)))
    known_chars = set(_text(x) for x in _list(contract.get("character_ids")) if _text(x))
    seen: list[str] = []
    for pi, phase in enumerate(phases):
        path = f"scene_phases[{pi}]"
        if not isinstance(phase, dict): continue
        missing = [key for key in PHASE_FIELDS if key not in phase]
        if missing: errors.append(_error("PHASE_FIELD_MISSING", path, missing=missing))
        pid = _text(phase.get("phase_id"))
        if not pid: errors.append(_error("PHASE_ID_INVALID", f"{path}.phase_id"))
        beats = _list(phase.get("beat_ids")); seen.extend(_text(x) for x in beats if _text(x))
        if not beats: errors.append(_error("PHASE_BEATS_EMPTY", f"{path}.beat_ids"))
        audience = _dict(phase.get("audience_state"))
        for key in ("knows", "suspects", "withholds"):
            if not isinstance(audience.get(key), list): errors.append(_error("NESTED_FIELD_SHAPE_INVALID", f"{path}.audience_state.{key}"))
        if not _text(audience.get("question_shift")): errors.append(_error("NESTED_FIELD_MISSING", f"{path}.audience_state.question_shift"))
        emotion = _dict(phase.get("emotion"))
        for key in ("state", "trigger", "transition_reason"):
            if not _text(emotion.get(key)): errors.append(_error("NESTED_FIELD_MISSING", f"{path}.emotion.{key}"))
        power = _dict(phase.get("power")); center = _text(power.get("center_type")).upper()
        if center not in POWER_CENTER_TYPES: errors.append(_error("INVALID_POWER_CENTER", f"{path}.power.center_type"))
        if center == "CHARACTER" and _text(power.get("center_ref")) not in known_chars: errors.append(_error("INVALID_POWER_CONTROLLER", f"{path}.power.center_ref"))
        if center != "NONE" and not _text(power.get("description")): errors.append(_error("NESTED_FIELD_MISSING", f"{path}.power.description"))
        perf = phase.get("performance")
        if not isinstance(perf, list): errors.append(_error("NESTED_FIELD_SHAPE_INVALID", f"{path}.performance"))
        else:
            for i, row in enumerate(perf):
                if not isinstance(row, dict): errors.append(_error("PERFORMANCE_ROW_INVALID", f"{path}.performance[{i}]")); continue
                if _text(row.get("character_id")) not in known_chars: errors.append(_error("UNKNOWN_CHARACTER_REFERENCE", f"{path}.performance[{i}].character_id"))
                for key in ("objective", "tactic", "visible_behavior"): 
                    if not _text(row.get(key)): errors.append(_error("PERFORMANCE_FIELD_MISSING", f"{path}.performance[{i}].{key}"))
        for group, keys in (("edit", ("tempo", "hold_logic", "cut_logic", "transition_motivation")), ("visual", ("visual_grammar", "camera_rule", "composition_rule", "movement_condition"))):
            obj = _dict(phase.get(group))
            for key in keys:
                if not _text(obj.get(key)): errors.append(_error("NESTED_FIELD_MISSING", f"{path}.{group}.{key}"))
        info = _dict(phase.get("information"))
        for key in INFORMATION_FIELDS:
            if key not in info: errors.append(_error("NESTED_FIELD_MISSING", f"{path}.information.{key}"))
        current_last = max((_beat_index(contract, beat) for beat in beats), default=-1)
        for key in ("reveal_refs", "hint_refs", "withhold_refs"):
            for ri, ref in enumerate(_list(info.get(key))):
                kind, ident = _ref_parts(ref); idx = _beat_index(contract, ident) if kind == "beat" else -1
                if kind == "beat" and idx < 0: errors.append(_error("UNKNOWN_SOURCE_REFERENCE", f"{path}.information.{key}[{ri}]", reference=ref))
                if key == "reveal_refs" and idx > current_last: errors.append(_error("FUTURE_REVEAL", f"{path}.information.{key}[{ri}]", reference=ref))
                if key == "hint_refs" and idx > current_last: errors.append(_error("FUTURE_HINT_EVIDENCE", f"{path}.information.{key}[{ri}]", reference=ref))
        for key in ("audience_suspicions", "director_inferences"):
            for ri, claim in enumerate(_list(info.get(key))):
                if not isinstance(claim, dict): errors.append(_error("EPISTEMIC_CLAIM_INVALID", f"{path}.information.{key}[{ri}]")); continue
                refs = _list(claim.get("support_refs"))
                if not _text(claim.get("claim")) or not refs: errors.append(_error("UNSUPPORTED_INFERENCE", f"{path}.information.{key}[{ri}]"))
                for ref in refs:
                    normalized_ref, ref_error = normalize_source_ref(ref, contract=contract)
                    if ref_error: errors.append(_error("UNKNOWN_SOURCE_REFERENCE", f"{path}.information.{key}[{ri}].support_refs", reference=ref)); continue
                    kind, ident = _ref_parts(normalized_ref or "")
                    if kind == "beat" and _beat_index(contract, ident) > current_last: errors.append(_error("FUTURE_SUPPORT_EVIDENCE", f"{path}.information.{key}[{ri}].support_refs", reference=ref))
    known_beats = [_text(x) for x in _list(contract.get("beat_ids")) if _text(x)]
    if len(seen) != len(set(seen)): errors.append(_error("BEAT_ASSIGNED_MULTIPLE_TIMES", "scene_phases"))
    if set(seen) != set(known_beats): errors.append(_error("BEAT_COVERAGE_GAP", "scene_phases", missing=sorted(set(known_beats) - set(seen))))
    canonical_errors = [error for error in errors if _text(error.get("code")) in CANONICAL_BLOCKER_CODES]
    approval_blockers = [error for error in errors if error not in canonical_errors]
    if not canonical_errors: return {"valid": True, "ir": ir, "canonical_status":"CANONICAL_VALID", "approval_blockers":approval_blockers, "errors": errors}
    return {"valid": False, "ir": None, "canonical_status":"CANONICAL_INVALID", "approval_blockers":approval_blockers, "errors": errors}


__all__ = ["validate_strategy_ir_v2", "CANONICAL_BLOCKER_CODES"]
