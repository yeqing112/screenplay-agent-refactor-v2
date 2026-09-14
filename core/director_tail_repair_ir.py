"""Typed semantic repair protocol for Director Quality V2.4.1.

The model describes an intended creative decision.  It never supplies JSON
Patch paths or production facts; those are resolved by the deterministic
compiler.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

REPAIR_IR_SCHEMA_VERSION = "director_tail_repair_ir_v1"
REPAIR_TYPES = {"edit", "emotion", "information", "performance", "camera"}
DIRECTOR_TARGET_DIMENSIONS = {"DRAMATIC_CLARITY", "SHOT_MOTIVATION", "EMOTIONAL_PROGRESSION", "VISUAL_STORYTELLING", "SPATIAL_CLARITY", "PERFORMANCE_DIRECTION", "EDIT_RHYTHM", "INFORMATION_STRATEGY", "POWER_DYNAMICS", "SHOT_DIVERSITY"}

ALLOWED_FIELDS: dict[str, dict[str, set[str]]] = {
    "edit": {"edit": {"duration_seconds", "cut_reason", "hold_after_action_seconds", "hold_before_cut_seconds", "hold_after_reveal_seconds", "rhythm_change", "reaction_timing"}},
    "emotion": {"emotion": {"intensity", "start", "end", "arc_position", "valence", "shift"}, "performance_emphasis": {"text"}},
    "information": {"information_strategy": {"reveals", "withholds", "audience_focus", "reveal_order", "withhold_until", "audience_should_notice", "audience_should_not_yet_know"}},
    "performance": {"performance_direction": {"character_id", "objective", "visible_behavior", "reaction_behavior", "subtext", "emphasis"}},
    "camera": {"camera": {"shot_size", "angle", "movement", "speed", "camera_side"}, "composition": {"frame_relationship", "dominant_subject", "visual_emphasis", "foreground", "background", "depth", "screen_position", "blocking_focus"}},
}

ROOT_CAUSE_TYPES: dict[str, set[str]] = {
    "WEAK_EDIT_STRATEGY": {"edit"},
    "WEAK_EMOTION_ARC": {"emotion", "performance"},
    "WEAK_INFORMATION_STRATEGY": {"information"},
    "PERFORMANCE_DIRECTION_WEAK": {"performance"},
    "CAMERA_LANGUAGE_GENERIC": {"camera"},
    "OVER_DIRECTING": {"camera", "edit", "emotion", "performance"},
    "UNDER_DIRECTING": {"camera", "edit", "emotion", "performance"},
}

_TOP_LEVEL = {"schema_version", "repair_type", "root_cause", "target_dimensions", "shot_decisions", "reasoning_summary", "ir_fingerprint"}
_SHOT_KEYS = {"plan_shot_id", "edit", "emotion", "performance_emphasis", "information_strategy", "performance_direction", "camera", "composition", "reason"}


class RepairIRSchemaError(ValueError):
    code = "DIRECTOR_REPAIR_IR_INVALID"
    def __init__(self, message: str, *, path: str = "", code: str | None = None):
        super().__init__(message); self.path = path; self.code = code or self.code


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def ir_fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _validate_value(group: str, field: str, value: Any, path: str) -> None:
    if group == "edit" and field in {"cut_reason", "rhythm_change", "reaction_timing"} and (not isinstance(value, str) or not value.strip()):
        raise RepairIRSchemaError("edit text field must be non-empty", path=path)
    if group == "edit" and field.startswith("hold_"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
            raise RepairIRSchemaError("edit hold value must be non-negative", path=path)
    if group == "edit" and field == "duration_seconds":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
            raise RepairIRSchemaError("duration_seconds must be positive", path=path)
    if group == "emotion" and field == "intensity":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 10:
            raise RepairIRSchemaError("emotion.intensity must be between 0 and 10", path=path)
    if group == "performance_direction" and field in {"character_id", "objective", "visible_behavior"} and (not isinstance(value, str) or not value.strip()):
        raise RepairIRSchemaError("performance required text must be non-empty", path=path)


def validate_repair_ir(raw: Any, *, known_plan_shot_ids: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RepairIRSchemaError("Repair IR must be an object")
    extra = sorted(set(raw) - _TOP_LEVEL)
    if extra:
        raise RepairIRSchemaError(f"Repair IR contains forbidden fields: {', '.join(extra)}")
    if _text(raw.get("schema_version")) != REPAIR_IR_SCHEMA_VERSION:
        raise RepairIRSchemaError("unsupported Repair IR schema version", path="schema_version")
    repair_type = _text(raw.get("repair_type"))
    if repair_type not in REPAIR_TYPES:
        raise RepairIRSchemaError("repair_type must be one of edit/emotion/information/performance/camera", path="repair_type")
    root = _text(raw.get("root_cause"))
    if not root:
        raise RepairIRSchemaError("root_cause is required", path="root_cause")
    if root and root in ROOT_CAUSE_TYPES and repair_type not in ROOT_CAUSE_TYPES[root]:
        raise RepairIRSchemaError("repair_type is incompatible with root_cause", path="repair_type", code="REPAIR_TYPE_ROOT_CAUSE_MISMATCH")
    targets = raw.get("target_dimensions")
    if not isinstance(targets, list) or not targets or any(not isinstance(item, str) or not item.strip() for item in targets):
        raise RepairIRSchemaError("target_dimensions must be a non-empty list of strings", path="target_dimensions")
    unknown_targets = sorted({str(item).strip().upper() for item in targets} - DIRECTOR_TARGET_DIMENSIONS)
    if unknown_targets:
        raise RepairIRSchemaError(f"target_dimensions contains unsupported values: {', '.join(unknown_targets)}", path="target_dimensions")
    decisions = raw.get("shot_decisions")
    if not isinstance(decisions, list) or not decisions:
        raise RepairIRSchemaError("shot_decisions must be a non-empty list", path="shot_decisions")
    known = known_plan_shot_ids or set()
    groups = ALLOWED_FIELDS[repair_type]
    normalized: dict[str, Any] = {"schema_version": REPAIR_IR_SCHEMA_VERSION, "repair_type": repair_type, "root_cause": root, "target_dimensions": [str(x).strip() for x in targets], "shot_decisions": []}
    for index, item in enumerate(decisions):
        path = f"shot_decisions[{index}]"
        if not isinstance(item, dict):
            raise RepairIRSchemaError("shot decision must be an object", path=path)
        extra_shot = sorted(set(item) - _SHOT_KEYS)
        if extra_shot:
            raise RepairIRSchemaError(f"shot decision contains forbidden fields: {', '.join(extra_shot)}", path=path)
        sid = _text(item.get("plan_shot_id"))
        if not sid or (known and sid not in known):
            raise RepairIRSchemaError("unknown plan_shot_id", path=f"{path}.plan_shot_id", code="UNKNOWN_PLAN_SHOT_ID")
        out: dict[str, Any] = {"plan_shot_id": sid}
        semantic_count = 0
        for group, fields in groups.items():
            if group not in item:
                continue
            semantic_count += 1
            value = item[group]
            if group == "performance_direction":
                if not isinstance(value, list) or not value:
                    raise RepairIRSchemaError("performance_direction must be a non-empty list", path=f"{path}.{group}")
                values = []
                for pidx, person in enumerate(value):
                    if not isinstance(person, dict):
                        raise RepairIRSchemaError("performance direction item must be an object", path=f"{path}.{group}[{pidx}]")
                    unknown = sorted(set(person) - fields)
                    if unknown:
                        raise RepairIRSchemaError(f"performance direction contains forbidden fields: {', '.join(unknown)}", path=f"{path}.{group}[{pidx}]")
                    person_out = copy.deepcopy(person)
                    for key, val in person_out.items(): _validate_value(group, key, val, f"{path}.{group}[{pidx}].{key}")
                    values.append(person_out)
                out[group] = values
            elif group == "performance_emphasis":
                if not isinstance(value, str) or not value.strip():
                    raise RepairIRSchemaError("performance_emphasis must be non-empty text", path=f"{path}.{group}")
                out[group] = value.strip()
            else:
                if not isinstance(value, dict) or not value:
                    raise RepairIRSchemaError(f"{group} must be a non-empty object", path=f"{path}.{group}")
                unknown = sorted(set(value) - fields)
                if unknown:
                    raise RepairIRSchemaError(f"{group} contains forbidden fields: {', '.join(unknown)}", path=f"{path}.{group}")
                group_out = copy.deepcopy(value)
                for key, val in group_out.items(): _validate_value(group, key, val, f"{path}.{group}.{key}")
                out[group] = group_out
        if semantic_count == 0:
            raise RepairIRSchemaError("shot decision has no semantic decision", path=path)
        if "reason" in item:
            if not isinstance(item["reason"], str) or not item["reason"].strip():
                raise RepairIRSchemaError("reason must be non-empty text", path=f"{path}.reason")
            out["reason"] = item["reason"].strip()
        normalized["shot_decisions"].append(out)
    if _text(raw.get("reasoning_summary")):
        normalized["reasoning_summary"] = _text(raw.get("reasoning_summary"))
    computed = ir_fingerprint(normalized)
    supplied = _text(raw.get("ir_fingerprint"))
    if supplied and supplied != computed:
        raise RepairIRSchemaError("ir_fingerprint does not match normalized Repair IR", path="ir_fingerprint")
    normalized["ir_fingerprint"] = computed
    return normalized


parse_repair_ir = validate_repair_ir

__all__ = ["REPAIR_IR_SCHEMA_VERSION", "REPAIR_TYPES", "DIRECTOR_TARGET_DIMENSIONS", "ALLOWED_FIELDS", "ROOT_CAUSE_TYPES", "RepairIRSchemaError", "validate_repair_ir", "parse_repair_ir", "ir_fingerprint"]
