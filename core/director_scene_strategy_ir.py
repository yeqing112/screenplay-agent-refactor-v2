"""Validation boundary for the provider-facing, phase-centric Strategy IR."""
from __future__ import annotations

import copy
from typing import Any

from core.director_scene_strategy_semantic_spec import (
    AUDIENCE_FIELDS,
    EMOTION_FIELDS,
    FORBIDDEN_IR_FIELDS,
    INFORMATION_FIELDS,
    IR_SCHEMA_VERSION,
    PHASE_FIELDS,
    POWER_CENTER_TYPES,
    PERFORMANCE_FIELDS,
    normalize_beat_id,
    IR_TOP_LEVEL_FIELDS,
)


class StrategyIRError(ValueError):
    code = "DIRECTOR_SCENE_STRATEGY_IR_INVALID"

    def __init__(self, message: str, *, code: str | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code or self.code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _error(code: str, path: str, message: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"code": code, "path": path, "message": message or code, **extra}


def validate_strategy_ir(raw: Any, *, contract: dict[str, Any]) -> dict[str, Any]:
    """Return normalized IR or evidence-rich errors; never invents content."""
    errors: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return {"valid": False, "ir": None, "errors": [_error("IR_NOT_OBJECT", "$")]}
    forbidden = sorted(set(raw) & set(FORBIDDEN_IR_FIELDS))
    if forbidden:
        errors.append(_error("FORBIDDEN_IR_FIELD", "$", forbidden_fields=forbidden))
    unknown = sorted(set(raw) - set(IR_TOP_LEVEL_FIELDS) - set(FORBIDDEN_IR_FIELDS))
    if unknown:
        errors.append(_error("UNKNOWN_IR_FIELD", "$", unknown_fields=unknown))
    if _text(raw.get("schema_version")) != IR_SCHEMA_VERSION:
        errors.append(_error("IR_SCHEMA_VERSION_INVALID", "schema_version", expected=IR_SCHEMA_VERSION))
    expected_scene = _text(_dict(contract).get("scene_id"))
    if expected_scene and _text(raw.get("scene_id")) != expected_scene:
        errors.append(_error("SCENE_ID_MISMATCH", "scene_id", expected=expected_scene))
    for field in IR_TOP_LEVEL_FIELDS:
        if field not in raw:
            errors.append(_error("IR_REQUIRED_FIELD_MISSING", field))
    for field in ("dramatic_objective", "scene_question", "strategy_summary", "visual_thesis"):
        if not _text(raw.get(field)):
            errors.append(_error("IR_REQUIRED_FIELD_MISSING", field))
    for field in ("spatial_expression", "prop_visual_strategy", "must_preserve", "must_avoid", "creative_risks"):
        if not isinstance(raw.get(field), list):
            errors.append(_error("NESTED_FIELD_SHAPE_INVALID", field, expected="array"))
    if not isinstance(raw.get("shot_architecture_guidance"), dict):
        errors.append(_error("NESTED_FIELD_SHAPE_INVALID", "shot_architecture_guidance", expected="object"))
    phases = _list(raw.get("scene_phases"))
    if len(phases) < 2 or len(phases) > 6:
        errors.append(_error("PHASE_COUNT_OUT_OF_RANGE", "scene_phases", expected="2..6", actual=len(phases)))
    beat_ids = [_text(item) for item in _list(_dict(contract).get("beat_ids")) if _text(item)]
    known_beats = set(beat_ids)
    alias_table = _dict(contract).get("beat_alias_table") or {"aliases": {item: item for item in beat_ids}}
    seen_beats: list[str] = []
    phase_ids: set[str] = set()
    known_chars = set(_text(item) for item in _list(_dict(contract).get("character_ids")) if _text(item))
    known_facts = set(_text(item) for item in _list(_dict(contract).get("fact_ids")) if _text(item))
    source_events_by_beat = {
        _text(beat_id): _text(_dict(row).get("event"))
        for beat_id, row in _dict(contract).get("beats", {}).items() if _text(_dict(row).get("event"))
    }
    source_events = set(source_events_by_beat.values())
    beat_order = {beat: idx for idx, beat in enumerate(beat_ids)}
    for i, phase in enumerate(phases):
        path = f"scene_phases[{i}]"
        if not isinstance(phase, dict):
            errors.append(_error("PHASE_NOT_OBJECT", path)); continue
        missing = [key for key in PHASE_FIELDS if key not in phase]
        if missing:
            errors.append(_error("PHASE_FIELD_MISSING", path, missing=missing))
        phase_id = _text(phase.get("phase_id"))
        if not phase_id or phase_id in phase_ids:
            errors.append(_error("PHASE_ID_INVALID", f"{path}.phase_id"))
        phase_ids.add(phase_id)
        refs = _list(phase.get("beat_ids"))
        if not refs:
            errors.append(_error("PHASE_BEATS_EMPTY", f"{path}.beat_ids"))
        for j, ref in enumerate(refs):
            canonical = normalize_beat_id(ref, alias_table)
            if _text(ref) in _dict(alias_table.get("aliases")) and canonical is None:
                errors.append(_error("AMBIGUOUS_BEAT_ALIAS", f"{path}.beat_ids[{j}]", beat_id=_text(ref)))
            elif canonical is None or canonical not in known_beats:
                errors.append(_error("UNKNOWN_BEAT_REFERENCE", f"{path}.beat_ids[{j}]", beat_id=_text(ref)))
            else:
                seen_beats.append(canonical)
        audience = _dict(phase.get("audience_state"))
        for key in ("knows", "suspects", "withholds"):
            if key not in audience or not isinstance(audience.get(key), list):
                errors.append(_error("NESTED_FIELD_SHAPE_INVALID", f"{path}.audience_state.{key}", expected="array"))
        if "question_shift" not in audience or not _text(audience.get("question_shift")):
            errors.append(_error("NESTED_FIELD_MISSING", f"{path}.audience_state.question_shift"))
        emotion = _dict(phase.get("emotion"))
        for key in EMOTION_FIELDS[:3]:
            if not _text(emotion.get(key)):
                errors.append(_error("NESTED_FIELD_MISSING", f"{path}.emotion.{key}"))
        power = _dict(phase.get("power"))
        center = _text(power.get("center_type")).upper()
        if center not in POWER_CENTER_TYPES:
            errors.append(_error("INVALID_POWER_CENTER", f"{path}.power.center_type", allowed=list(POWER_CENTER_TYPES)))
        ref = _text(power.get("center_ref"))
        if center == "CHARACTER" and ref not in known_chars:
            errors.append(_error("INVALID_POWER_CONTROLLER", f"{path}.power.center_ref", character_id=ref))
        if center == "OBJECT" and ref and ref not in known_facts and ref not in set(_text(x) for x in _list(_dict(contract).get("prop_ids"))):
            errors.append(_error("UNKNOWN_POWER_OBJECT_REFERENCE", f"{path}.power.center_ref", reference=ref))
        if center != "NONE" and not _text(power.get("description")):
            errors.append(_error("NESTED_FIELD_MISSING", f"{path}.power.description"))
        performance = phase.get("performance")
        if not isinstance(performance, list):
            errors.append(_error("NESTED_FIELD_SHAPE_INVALID", f"{path}.performance", expected="array"))
        else:
            for j, row in enumerate(performance):
                if not isinstance(row, dict):
                    errors.append(_error("PERFORMANCE_ROW_INVALID", f"{path}.performance[{j}]")); continue
                char = _text(row.get("character_id"))
                if char not in known_chars:
                    errors.append(_error("UNKNOWN_CHARACTER_REFERENCE", f"{path}.performance[{j}].character_id", character_id=char))
                for key in PERFORMANCE_FIELDS[1:4]:
                    if not _text(row.get(key)):
                        errors.append(_error("PERFORMANCE_FIELD_MISSING", f"{path}.performance[{j}].{key}"))
        for group, required in (("edit", ("tempo", "hold_logic", "cut_logic", "transition_motivation")), ("visual", ("visual_grammar", "camera_rule", "composition_rule", "movement_condition"))):
            value = _dict(phase.get(group))
            for key in required:
                if not _text(value.get(key)):
                    errors.append(_error("NESTED_FIELD_MISSING", f"{path}.{group}.{key}"))
        info = _dict(phase.get("information"))
        for key in INFORMATION_FIELDS:
            if key not in info or not isinstance(info.get(key), list):
                errors.append(_error("NESTED_FIELD_SHAPE_INVALID", f"{path}.information.{key}", expected="array"))
        for fact_id in _list(info.get("source_refs")):
            if known_facts and _text(fact_id) not in known_facts:
                errors.append(_error("UNKNOWN_SOURCE_FACT_REFERENCE", f"{path}.information.source_refs", fact_id=_text(fact_id)))
        reveal = {_text(value) for value in _list(info.get("reveal")) if _text(value)}
        if source_events and not reveal.issubset(source_events):
            errors.append(_error("FACT_INVENTION", f"{path}.information.reveal", values=sorted(reveal - source_events)))
        if reveal:
            current_max = max((beat_order.get(normalize_beat_id(ref, alias_table), -1) for ref in refs), default=-1)
            future = [event for event in reveal if event in source_events and beat_order.get(next((b for b, e in source_events_by_beat.items() if e == event), ""), -1) > current_max]
            if future:
                errors.append(_error("FUTURE_REVEAL", f"{path}.information.reveal", values=sorted(future)))
    duplicates = sorted({beat for beat in seen_beats if seen_beats.count(beat) > 1})
    missing_beats = sorted(known_beats - set(seen_beats))
    if duplicates:
        errors.append(_error("BEAT_ASSIGNED_MULTIPLE_TIMES", "scene_phases", beat_ids=duplicates))
    if missing_beats:
        errors.append(_error("BEAT_COVERAGE_GAP", "scene_phases", beat_ids=missing_beats))
    if not duplicates and not missing_beats and seen_beats != beat_ids:
        errors.append(_error("BEAT_CHRONOLOGY_INVALID", "scene_phases", expected=beat_ids, actual=seen_beats))
    if errors:
        return {"valid": False, "ir": None, "errors": errors}
    normalized = copy.deepcopy(raw)
    for phase in normalized["scene_phases"]:
        phase["beat_ids"] = [normalize_beat_id(ref, alias_table) for ref in phase["beat_ids"]]
        phase["power"]["center_type"] = _text(phase["power"].get("center_type")).upper()
        phase["power"]["center_ref"] = _text(phase["power"].get("center_ref")) or None
    return {"valid": True, "ir": normalized, "errors": []}


__all__ = ["StrategyIRError", "validate_strategy_ir"]
