"""Typed semantic Repair IR validation.

Validation is fail-closed and collect-all. Nested constraints derive from the
Repair IR Semantic Spec SSOT; the legacy exception API remains compatible.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.director_tail_repair_semantic_spec import REPAIR_TYPE_SPECS

REPAIR_IR_SCHEMA_VERSION = "director_tail_repair_ir_v1"
REPAIR_TYPES = set(REPAIR_TYPE_SPECS)
DIRECTOR_TARGET_DIMENSIONS = {"DRAMATIC_CLARITY", "SHOT_MOTIVATION", "EMOTIONAL_PROGRESSION", "VISUAL_STORYTELLING", "SPATIAL_CLARITY", "PERFORMANCE_DIRECTION", "EDIT_RHYTHM", "INFORMATION_STRATEGY", "POWER_DYNAMICS", "SHOT_DIVERSITY"}
ALLOWED_FIELDS = {kind: {group: set(spec.get("fields", {})) if spec.get("type") != "array" else set(spec.get("items", {}).get("fields", {})) for group, spec in body["groups"].items()} for kind, body in REPAIR_TYPE_SPECS.items()}
ROOT_CAUSE_TYPES = {
    "WEAK_EDIT_STRATEGY": {"edit"}, "WEAK_EMOTION_ARC": {"emotion", "performance"},
    "WEAK_INFORMATION_STRATEGY": {"information"}, "PERFORMANCE_DIRECTION_WEAK": {"performance"},
    "CAMERA_LANGUAGE_GENERIC": {"camera"}, "OVER_DIRECTING": {"camera", "edit", "emotion", "performance"},
    "UNDER_DIRECTING": {"camera", "edit", "emotion", "performance"},
}
_TOP_LEVEL = {"schema_version", "repair_type", "root_cause", "target_dimensions", "shot_decisions", "reasoning_summary", "ir_fingerprint"}
_SHOT_KEYS = {"plan_shot_id", "edit", "emotion", "performance_emphasis", "information_strategy", "performance_direction", "camera", "composition", "reason"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def ir_fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _actual_summary(value: Any) -> Any:
    if isinstance(value, str): return value[:120]
    if isinstance(value, (int, float, bool)) or value is None: return value
    if isinstance(value, list): return {"length": len(value), "sample_types": [type(x).__name__ for x in value[:3]]}
    if isinstance(value, dict): return {"keys": sorted(str(k) for k in value.keys())[:20], "key_count": len(value)}
    return str(value)[:120]


class RepairIRSchemaError(ValueError):
    code = "DIRECTOR_REPAIR_IR_INVALID"

    def __init__(self, message: str, *, path: str = "", code: str | None = None, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.path = path
        self.code = code or self.code
        self.errors = list(errors or [])


def _error(errors: list[dict[str, Any]], *, path: str, code: str, message: str, expected: Any = None, actual: Any = None) -> None:
    row = {"path": path, "code": code, "message": message, "expected": expected, "actual_type": type(actual).__name__}
    if actual is not None: row["actual_value_summary"] = _actual_summary(actual)
    errors.append(row)


def _validate_typed(value: Any, spec: dict[str, Any], path: str, errors: list[dict[str, Any]]) -> None:
    if value is None and spec.get("nullable"): return
    kind = spec.get("type")
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _error(errors, path=path, code="INVALID_TYPE", message=f"{path} must be a number", expected="number", actual=value); return
        n = float(value)
        if "minimum" in spec and (n < float(spec["minimum"]) or (spec.get("minimum_exclusive") and n == float(spec["minimum"]))): _error(errors, path=path, code="VALUE_OUT_OF_RANGE", message=f"{path} is below minimum", expected={"minimum": spec["minimum"], "exclusive": bool(spec.get("minimum_exclusive"))}, actual=value)
        if "maximum" in spec and n > float(spec["maximum"]): _error(errors, path=path, code="VALUE_OUT_OF_RANGE", message=f"{path} is above maximum", expected={"maximum": spec["maximum"]}, actual=value)
    elif kind == "string":
        if not isinstance(value, str): _error(errors, path=path, code="INVALID_TYPE", message=f"{path} must be a string", expected="string", actual=value); return
        if spec.get("min_length") and len(value.strip()) < int(spec["min_length"]): _error(errors, path=path, code="EMPTY_STRING", message=f"{path} must be non-empty", expected={"minLength": spec["min_length"]}, actual=value)
    elif kind == "array":
        if not isinstance(value, list): _error(errors, path=path, code="INVALID_TYPE", message=f"{path} must be an array", expected="array", actual=value); return
        if len(value) < int(spec.get("min_items", 0)): _error(errors, path=path, code="EMPTY_ARRAY", message=f"{path} must contain at least {spec['min_items']} item(s)", expected={"minItems": spec["min_items"]}, actual=value)
        if "max_items" in spec and len(value) > int(spec["max_items"]): _error(errors, path=path, code="VALUE_OUT_OF_RANGE", message=f"{path} contains too many items", expected={"maxItems": spec["max_items"]}, actual=value)
        if spec.get("item_type") == "string":
            for index, item in enumerate(value):
                if not isinstance(item, str) or len(item.strip()) < int(spec.get("item_min_length", 0)): _error(errors, path=f"{path}[{index}]", code="EMPTY_STRING", message=f"{path}[{index}] must be non-empty string", expected="non-empty string", actual=item)
    elif kind == "string_or_array":
        if isinstance(value, str):
            if spec.get("min_length") and len(value.strip()) < int(spec["min_length"]): _error(errors, path=path, code="EMPTY_STRING", message=f"{path} must be non-empty", expected={"minLength": spec["min_length"]}, actual=value)
        elif isinstance(value, list):
            if len(value) < int(spec.get("min_items", 0)): _error(errors, path=path, code="EMPTY_ARRAY", message=f"{path} must contain at least {spec['min_items']} item(s)", expected={"minItems": spec["min_items"]}, actual=value)
        else: _error(errors, path=path, code="INVALID_TYPE", message=f"{path} must be string or array", expected="string|array", actual=value)


def validate_repair_ir_diagnostics(raw: Any, *, known_plan_shot_ids: set[str] | None = None, allowed_character_ids: set[str] | None = None) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        _error(errors, path="", code="INVALID_TYPE", message="Repair IR must be an object", expected="object", actual=raw)
        return {"valid": False, "errors": errors, "normalized": None}
    for key in sorted(set(raw) - _TOP_LEVEL): _error(errors, path=key, code="FORBIDDEN_FIELD", message=f"forbidden top-level field: {key}", expected=sorted(_TOP_LEVEL), actual=raw.get(key))
    if _text(raw.get("schema_version")) != REPAIR_IR_SCHEMA_VERSION: _error(errors, path="schema_version", code="INVALID_TYPE", message="unsupported Repair IR schema version", expected=REPAIR_IR_SCHEMA_VERSION, actual=raw.get("schema_version"))
    repair_type = _text(raw.get("repair_type"))
    if repair_type not in REPAIR_TYPES: _error(errors, path="repair_type", code="INVALID_ENUM", message="repair_type is unsupported", expected=sorted(REPAIR_TYPES), actual=repair_type)
    root = _text(raw.get("root_cause"))
    if not root: _error(errors, path="root_cause", code="REQUIRED_FIELD_MISSING", message="root_cause is required", expected="non-empty string", actual=raw.get("root_cause"))
    if root in ROOT_CAUSE_TYPES and repair_type and repair_type not in ROOT_CAUSE_TYPES[root]: _error(errors, path="repair_type", code="ROOT_CAUSE_TYPE_MISMATCH", message="repair_type is incompatible with root_cause", expected=sorted(ROOT_CAUSE_TYPES[root]), actual=repair_type)
    targets = raw.get("target_dimensions")
    if not isinstance(targets, list) or not targets:
        _error(errors, path="target_dimensions", code="EMPTY_ARRAY", message="target_dimensions must be a non-empty list", expected="non-empty array", actual=targets); targets = []
    else:
        for idx, target in enumerate(targets):
            if not isinstance(target, str) or not target.strip(): _error(errors, path=f"target_dimensions[{idx}]", code="EMPTY_STRING", message="target dimension must be non-empty string", expected="non-empty string", actual=target)
        for item in sorted({str(x).strip().upper() for x in targets if isinstance(x, str)} - DIRECTOR_TARGET_DIMENSIONS): _error(errors, path="target_dimensions", code="INVALID_ENUM", message=f"unsupported target dimension: {item}", expected=sorted(DIRECTOR_TARGET_DIMENSIONS), actual=item)
    decisions = raw.get("shot_decisions")
    if not isinstance(decisions, list) or not decisions:
        _error(errors, path="shot_decisions", code="EMPTY_ARRAY", message="shot_decisions must be a non-empty list", expected="non-empty array", actual=decisions); decisions = []
    known = known_plan_shot_ids or set(); groups = ALLOWED_FIELDS.get(repair_type, {})
    normalized = {"schema_version": REPAIR_IR_SCHEMA_VERSION, "repair_type": repair_type, "root_cause": root, "target_dimensions": [str(x).strip() for x in targets], "shot_decisions": []}
    for index, item in enumerate(decisions):
        path = f"shot_decisions[{index}]"
        if not isinstance(item, dict): _error(errors, path=path, code="INVALID_TYPE", message="shot decision must be an object", expected="object", actual=item); continue
        for key in sorted(set(item) - _SHOT_KEYS): _error(errors, path=f"{path}.{key}", code="FORBIDDEN_FIELD", message=f"forbidden shot decision field: {key}", expected=sorted(_SHOT_KEYS), actual=item.get(key))
        sid = _text(item.get("plan_shot_id"))
        if not sid: _error(errors, path=f"{path}.plan_shot_id", code="REQUIRED_FIELD_MISSING", message="plan_shot_id is required", expected="non-empty string", actual=item.get("plan_shot_id"))
        elif known and sid not in known: _error(errors, path=f"{path}.plan_shot_id", code="UNKNOWN_PLAN_SHOT_ID", message="unknown plan_shot_id", expected=sorted(known), actual=sid)
        out = {"plan_shot_id": sid}; semantic_count = 0
        for group, allowed in groups.items():
            if group not in item: continue
            semantic_count += 1; value = item[group]; spec = REPAIR_TYPE_SPECS[repair_type]["groups"][group]; group_path = f"{path}.{group}"
            if spec.get("type") == "array":
                _validate_typed(value, spec, group_path, errors)
                if isinstance(value, list):
                    item_spec = spec.get("items", {})
                    for pidx, person in enumerate(value):
                        person_path = f"{group_path}[{pidx}]"
                        if not isinstance(person, dict): _error(errors, path=person_path, code="INVALID_TYPE", message="performance direction item must be object", expected="object", actual=person); continue
                        for key in sorted(set(person) - set(item_spec.get("item_allowed_fields", []))): _error(errors, path=f"{person_path}.{key}", code="FORBIDDEN_FIELD", message=f"performance direction contains forbidden field: {key}", expected=item_spec.get("item_allowed_fields", []), actual=person.get(key))
                        for required in item_spec.get("item_required_fields", []):
                            if required not in person: _error(errors, path=f"{person_path}.{required}", code="REQUIRED_FIELD_MISSING", message=f"required child field missing: {required}", expected="non-empty string", actual=None)
                        for key, field_spec in item_spec.get("fields", {}).items():
                            if key in person: _validate_typed(person[key], field_spec, f"{person_path}.{key}", errors)
                        if allowed_character_ids and isinstance(person.get("character_id"), str) and person["character_id"].strip() not in allowed_character_ids: _error(errors, path=f"{person_path}.character_id", code="UNKNOWN_CHARACTER_ID", message="character_id is not in allowed_character_ids", expected=sorted(allowed_character_ids), actual=person.get("character_id"))
                out[group] = copy.deepcopy(value)
            elif group == "performance_emphasis":
                _validate_typed(value, spec, group_path, errors); out[group] = value.strip() if isinstance(value, str) else value
            else:
                if not isinstance(value, dict) or not value: _error(errors, path=group_path, code="REQUIRED_FIELD_MISSING", message=f"{group} must be a non-empty object", expected="non-empty object", actual=value); continue
                for key in sorted(set(value) - allowed): _error(errors, path=f"{group_path}.{key}", code="FORBIDDEN_FIELD", message=f"{group} contains forbidden field: {key}", expected=sorted(allowed), actual=value.get(key))
                for key, field_spec in spec.get("fields", {}).items():
                    if key in value: _validate_typed(value[key], field_spec, f"{group_path}.{key}", errors)
                out[group] = copy.deepcopy(value)
        if semantic_count == 0: _error(errors, path=path, code="NO_SEMANTIC_DECISION", message="shot decision has no semantic decision", expected=f"one of {sorted(groups)}", actual=item)
        if "reason" in item:
            if not isinstance(item["reason"], str) or not item["reason"].strip(): _error(errors, path=f"{path}.reason", code="EMPTY_STRING", message="reason must be non-empty text", expected="non-empty string", actual=item["reason"])
            else: out["reason"] = item["reason"].strip()
        normalized["shot_decisions"].append(out)
    if _text(raw.get("reasoning_summary")): normalized["reasoning_summary"] = _text(raw.get("reasoning_summary"))
    computed = ir_fingerprint(normalized); supplied = _text(raw.get("ir_fingerprint"))
    if supplied and supplied != computed: _error(errors, path="ir_fingerprint", code="INVALID_TYPE", message="ir_fingerprint does not match normalized Repair IR", expected=computed, actual=supplied)
    normalized["ir_fingerprint"] = computed
    return {"valid": not errors, "errors": errors, "normalized": normalized if not errors else None}


def validate_repair_ir(raw: Any, *, known_plan_shot_ids: set[str] | None = None, allowed_character_ids: set[str] | None = None) -> dict[str, Any]:
    result = validate_repair_ir_diagnostics(raw, known_plan_shot_ids=known_plan_shot_ids, allowed_character_ids=allowed_character_ids)
    if not result["valid"]:
        first = result["errors"][0] if result["errors"] else {}
        raise RepairIRSchemaError("; ".join(str(item.get("message")) for item in result["errors"]) or "Repair IR invalid", path=str(first.get("path", "")), code=str(first.get("code", "DIRECTOR_REPAIR_IR_INVALID")), errors=result["errors"])
    return result["normalized"]


parse_repair_ir = validate_repair_ir

__all__ = ["REPAIR_IR_SCHEMA_VERSION", "REPAIR_TYPES", "DIRECTOR_TARGET_DIMENSIONS", "ALLOWED_FIELDS", "ROOT_CAUSE_TYPES", "RepairIRSchemaError", "validate_repair_ir", "validate_repair_ir_diagnostics", "parse_repair_ir", "ir_fingerprint"]
