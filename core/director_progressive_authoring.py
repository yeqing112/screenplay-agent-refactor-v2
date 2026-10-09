"""Two-stage Director authoring contracts.

Stage A groups immutable source units into a dramatic beat plan.  Stage B adds
performance and audience-facing enrichment to those already validated beats.
The module is deliberately provider-free: it validates and deterministically
merges proposals, but never invents missing creative text.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping

from core.director_source_grounded import DIRECTOR_CREATIVE_AUTHORITY


DIRECTOR_BEAT_PLAN_IR_VERSION = "director_beat_plan_ir_v1"
DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION = "director_creative_enrichment_ir_v1"
DIRECTOR_BEAT_PLAN_IR_V1_SYSTEM_PROMPT = (
    "你是受来源约束的导演结构规划助手。只输出 director_beat_plan_ir_v1 JSON。"
    "只负责把不可变来源单元分组为戏剧 beats，并填写场景目标、戏剧问题、目的、导演目标和信息变化。"
    "不得改写或输出对白、speaker、binding、source_constraints、authority、creative_beat_id、"
    "performance、audience_effect、transition、character_effects、character_directions、"
    "performance_arc、information_strategy、rhythm_strategy、visual_priority、scene_exit_intent、"
    "prohibited_interpretations。仅 string 类型的创意字段需要是完整中文句子并以。！？?!之一结束；"
    "scene_objective、dramatic_question、beats[].purpose、beats[].objective、beats[].information_change 属于文本字段。"
    "beats[].hook 是 boolean 分类标志，不是文本字段，不适用句子完整性要求。"
)

# These ordered tuples are the protocol source of truth.  Sets are exported
# below for backwards-compatible membership checks, while prompt rendering,
# examples, parity checks, and evidence use the stable tuple order.
CANONICAL_TOP_LEVEL_KEYS = (
    "version", "scene_label", "scene_objective", "dramatic_question", "beats",
    "passthrough_refs", "unknowns", "confidence", "note",
)
CANONICAL_BEAT_KEYS = ("refs", "purpose", "objective", "information_change", "hook")
STAGE_A_BEAT_FIELDS = set(CANONICAL_BEAT_KEYS)
STAGE_A_TOP_LEVEL_FIELDS = set(CANONICAL_TOP_LEVEL_KEYS)
STAGE_B_TOP_LEVEL_KEYS = (
    "version", "beat_enrichments", "character_directions", "performance_arc",
    "information_strategy", "rhythm_strategy", "visual_priority",
    "scene_exit_intent", "prohibited_interpretations", "confidence", "note",
)
STAGE_B_ENRICHMENT_KEYS = ("beat_ref", "audience_effect", "performance", "transition", "character_effects")
CHARACTER_DIRECTION_KEYS = ("character_ref", "direction", "objective", "obstacle", "strategy", "performance_notes")
CHARACTER_EFFECT_KEYS = ("character_ref", "effect")
STAGE_B_TOP_LEVEL_FIELDS = set(STAGE_B_TOP_LEVEL_KEYS)
STAGE_B_ENRICHMENT_FIELDS = set(STAGE_B_ENRICHMENT_KEYS)
CHARACTER_DIRECTION_FIELDS = set(CHARACTER_DIRECTION_KEYS)
CHARACTER_EFFECT_FIELDS = set(CHARACTER_EFFECT_KEYS)
INFORMATION_STRATEGY_KEYS = (
    "schema_version", "known_to_audience", "withheld_from_audience", "reveal_plan",
    "reaction_priority", "audience_focus",
)
INFORMATION_REVEAL_KEYS = ("beat_id", "reveals", "withholds", "audience_should_notice", "audience_should_not_yet_know")
RHYTHM_STRATEGY_KEYS = ("opening", "reveal", "escalation", "button")


DIRECTOR_BEAT_PLAN_IR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(STAGE_A_TOP_LEVEL_FIELDS),
    "properties": {
        "version": {"const": DIRECTOR_BEAT_PLAN_IR_VERSION},
        "scene_label": {"type": "string"},
        "scene_objective": {"type": "string"},
        "dramatic_question": {"type": "string"},
        "beats": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": sorted(STAGE_A_BEAT_FIELDS),
            "properties": {
                "refs": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "purpose": {"type": "string"},
                "objective": {"type": "string"},
                "information_change": {"type": "string"},
                "hook": {"type": "boolean"},
            },
        }},
        "passthrough_refs": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array"},
        "confidence": {"type": ["number", "string"]},
        "note": {"type": "string"},
    },
}


DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    # Preserve the protocol's declared order in the formal schema.  The
    # completeness gate and evidence therefore show the same eleven keys the
    # contract documents, while validation remains set-like.
    "required": list(STAGE_B_TOP_LEVEL_KEYS),
    "properties": {
        "version": {"const": DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION},
        "beat_enrichments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": list(STAGE_B_ENRICHMENT_KEYS),
            "properties": {
                "beat_ref": {"type": "string"},
                "audience_effect": {"type": "string"},
                "performance": {"type": "string"},
                "transition": {"type": "string"},
                "character_effects": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": list(CHARACTER_EFFECT_KEYS),
                    "properties": {"character_ref": {"type": "string"}, "effect": {"type": "string"}},
                }},
            },
        }},
        "character_directions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["character_ref", "direction"],
            "properties": {key: {"type": "string"} for key in CHARACTER_DIRECTION_KEYS},
        }},
        "performance_arc": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["phase", "state"],
            "properties": {"phase": {"type": "string"}, "state": {"type": "string"}},
        }},
        "information_strategy": {"type": "object", "additionalProperties": False,
            "required": list(INFORMATION_STRATEGY_KEYS),
            "properties": {
                "schema_version": {"const": "director_information_strategy_v2"},
                "known_to_audience": {"type": "array", "items": {"type": "string"}},
                "withheld_from_audience": {"type": "array", "items": {"type": "string"}},
                "reveal_plan": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": list(INFORMATION_REVEAL_KEYS),
                    "properties": {
                        "beat_id": {"type": "string"}, "reveals": {"type": "array", "items": {"type": "string"}},
                        "withholds": {"type": "array", "items": {"type": "string"}},
                        "audience_should_notice": {"type": "string"}, "audience_should_not_yet_know": {"type": "string"},
                    },
                }},
                "reaction_priority": {"type": "array", "items": {"type": "string"}},
                "audience_focus": {"type": "array", "items": {"type": "string"}},
            },
        },
        "rhythm_strategy": {"type": "object", "additionalProperties": False,
            "required": list(RHYTHM_STRATEGY_KEYS),
            "properties": {key: {"type": "string"} for key in RHYTHM_STRATEGY_KEYS},
        },
        "visual_priority": {"type": "array", "items": {"type": "string"}},
        "scene_exit_intent": {"type": "string"},
        "prohibited_interpretations": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": ["number", "string"]},
        "note": {"type": "string"},
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _schema_check(value: Any, schema: Mapping[str, Any], path: str = "$", errors: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    errors = errors if errors is not None else []
    wanted = schema.get("type")
    if wanted:
        kinds = wanted if isinstance(wanted, list) else [wanted]
        ok = any((kind == "object" and isinstance(value, Mapping)) or (kind == "array" and isinstance(value, list)) or (kind == "string" and isinstance(value, str)) or (kind == "boolean" and isinstance(value, bool)) or (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) for kind in kinds)
        if not ok:
            errors.append({"path": path, "code": "SCHEMA_TYPE_INVALID", "expected": wanted})
            return errors
    if "const" in schema and value != schema["const"]:
        errors.append({"path": path, "code": "SCHEMA_CONST_INVALID", "expected": schema["const"]})
    if isinstance(value, Mapping):
        for field in schema.get("required", []):
            if field not in value:
                errors.append({"path": path, "code": "SCHEMA_REQUIRED_FIELD_MISSING", "field": field})
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for field in value:
                if field not in properties:
                    errors.append({"path": path, "code": "SCHEMA_ADDITIONAL_PROPERTY", "field": field})
        for field, child in properties.items():
            if field in value:
                _schema_check(value[field], child, f"{path}.{field}", errors)
    elif isinstance(value, list) and isinstance(schema.get("items"), Mapping):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append({"path": path, "code": "SCHEMA_MIN_ITEMS"})
        for index, item in enumerate(value):
            _schema_check(item, schema["items"], f"{path}[{index}]", errors)
    return errors


def render_stage_a_schema_contract() -> dict[str, Any]:
    """Render the structural Stage A contract from the formal JSON schema.

    The renderer intentionally contains no new business semantics.  It turns
    the schema's property/required/type/additionalProperties declarations into
    a compact contract that can be embedded in the Provider prompt and stored
    in evidence.  This prevents prompt and validator field lists drifting.
    """
    top = DIRECTOR_BEAT_PLAN_IR_SCHEMA
    beat = top["properties"]["beats"]["items"]
    def type_label(node: Mapping[str, Any]) -> str:
        if "const" in node:
            return f"const:{node['const']}"
        wanted = node.get("type")
        if isinstance(wanted, list):
            return "|".join(str(item) for item in wanted)
        return str(wanted or "unknown")

    field_types = {key: type_label(node) for key, node in top["properties"].items()}
    beat_field_types = {f"beats[].{key}": type_label(node) for key, node in beat["properties"].items()}
    field_types.update(beat_field_types)
    field_types["beats"] = "array<object>"
    field_types["beats[].refs"] = "array<string>"
    return {
        "version": DIRECTOR_BEAT_PLAN_IR_VERSION,
        "top_level_keys": list(top["properties"].keys()),
        "top_level_required": list(top["required"]),
        "top_level_additional_properties": top.get("additionalProperties") is True,
        "beat_keys": list(beat["properties"].keys()),
        "beat_required": list(beat["required"]),
        "beat_additional_properties": beat.get("additionalProperties") is True,
        "field_types": field_types,
        "canonical_key_rules": {
            "byte_for_byte": True,
            "ascii_identifiers_only": True,
            "chinese_allowed_only_in_values": True,
            "additional_properties": False,
        },
    }


def _stage_a_shape_example() -> dict[str, Any]:
    """Build the prompt example from the formal schema key lists."""
    contract = render_stage_a_schema_contract()
    return {
        key: (
            DIRECTOR_BEAT_PLAN_IR_VERSION if key == "version" else
            "string" if key in {"scene_label", "note"} else
            "完整中文句子。" if key in {"scene_objective"} else
            "完整中文疑问句？" if key == "dramatic_question" else
            [{field: (["SAU_..." ] if field == "refs" else True if field == "hook" else "完整中文句子。") for field in contract["beat_keys"]}] if key == "beats" else
            [] if key in {"passthrough_refs", "unknowns"} else
            0.8 if key == "confidence" else
            None
        ) for key in contract["top_level_keys"]
    }


class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object repeats an exact property name."""

    def __init__(self, key: str, stage: str = "BEAT_PLAN"):
        self.key = key
        self.stage = stage
        prefix = "DIRECTOR_CREATIVE_ENRICHMENT" if stage == "CREATIVE_ENRICHMENT" else "DIRECTOR_BEAT_PLAN"
        super().__init__(f"{prefix}_DUPLICATE_JSON_KEY:{key}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(str(key))
        result[key] = value
    return result


def _reject_duplicate_stage_b_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(str(key), "CREATIVE_ENRICHMENT")
        result[key] = value
    return result


def audit_duplicate_json_keys(raw: str) -> dict[str, Any]:
    """Audit raw JSON for exact duplicate object keys without repairing it."""
    try:
        json.loads(str(raw or ""), object_pairs_hook=_reject_duplicate_pairs)
    except DuplicateJSONKeyError as exc:
        return {"status": "FAIL", "duplicate_keys": [exc.key], "error": str(exc)}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "NOT_EVALUATED", "duplicate_keys": [], "error": str(exc)}
    return {"status": "PASS", "duplicate_keys": [], "error": None}


def validate_stage_a_prompt_schema_key_parity(user_prompt: str) -> dict[str, Any]:
    """Compare prompt-declared key sets with the formal schema key sets."""
    contract = render_stage_a_schema_contract()
    found: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for marker, expected in (("CANONICAL_TOP_LEVEL_KEYS=", contract["top_level_keys"]), ("CANONICAL_BEAT_KEYS=", contract["beat_keys"])):
        line = next((item for item in str(user_prompt or "").splitlines() if item.startswith(marker)), "")
        if not line:
            errors.append({"code": "PROMPT_CANONICAL_KEY_BLOCK_MISSING", "marker": marker})
            continue
        try:
            actual = json.loads(line[len(marker):])
        except (TypeError, ValueError, json.JSONDecodeError):
            actual = None
        found[marker.rstrip("=")] = actual
        if not isinstance(actual, list) or set(actual) != set(expected) or len(actual) != len(expected):
            errors.append({"code": "STAGE_A_PROMPT_SCHEMA_KEY_PARITY", "marker": marker, "expected": expected, "actual": actual})
    for phrase in ("byte-for-byte", "do not translate", "Chinese only in values", "never in keys"):
        if phrase not in str(user_prompt or ""):
            errors.append({"code": "PROMPT_CANONICAL_KEY_RULE_MISSING", "phrase": phrase})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "prompt": found, "schema": contract}


def validate_director_beat_plan_ir_schema(value: Any) -> dict[str, Any]:
    errors = _schema_check(value, DIRECTOR_BEAT_PLAN_IR_SCHEMA)
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "version": DIRECTOR_BEAT_PLAN_IR_VERSION}


def parse_director_beat_plan_ir(raw: str) -> dict[str, Any]:
    """Parse Stage A once with no extraction or repair heuristics."""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Director BeatPlan IR is empty")
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except DuplicateJSONKeyError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to parse Director BeatPlan IR: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Director BeatPlan IR is not a JSON object")
    if payload.get("version") != DIRECTOR_BEAT_PLAN_IR_VERSION:
        raise ValueError("Director BeatPlan IR has an invalid version")
    return payload


_INCOMPLETE_TEXT_MARKERS = ("placeholder", "tbd", "todo", "n/a", "待补", "未完成")


def validate_director_beat_plan_text_completeness(value: Any) -> dict[str, Any]:
    """Reject empty, placeholder, or fragmentary Stage A creative text."""
    errors: list[dict[str, Any]] = []
    if not isinstance(value, Mapping):
        return {"status": "FAIL", "errors": [{"code": "DIRECTOR_BEAT_PLAN_TEXT_INCOMPLETE", "path": "$"}]}
    required = [("scene_objective", value.get("scene_objective")), ("dramatic_question", value.get("dramatic_question"))]
    for index, beat in enumerate(value.get("beats", []) if isinstance(value.get("beats"), list) else []):
        if isinstance(beat, Mapping):
            for field in ("purpose", "objective", "information_change"):
                required.append((f"beats[{index}].{field}", beat.get(field)))
    for path, raw in required:
        text = _text(raw)
        lower = text.lower()
        if not text or any(marker in lower for marker in _INCOMPLETE_TEXT_MARKERS):
            errors.append({"code": "DIRECTOR_BEAT_PLAN_TEXT_INCOMPLETE", "path": path, "reason": "empty_or_placeholder"})
            continue
        if not re.search(r"[。！？?!]$", text):
            errors.append({"code": "DIRECTOR_BEAT_PLAN_TEXT_INCOMPLETE", "path": path, "reason": "sentence_punctuation_required"})
        if path == "dramatic_question" and not re.search(r"[？?!]$", text):
            errors.append({"code": "DIRECTOR_BEAT_PLAN_TEXT_INCOMPLETE", "path": path, "reason": "question_punctuation_required"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def validate_director_creative_enrichment_ir_schema(value: Any) -> dict[str, Any]:
    errors = _schema_check(value, DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA)
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "version": DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION}


def _stage_b_schema_projection(schema: Mapping[str, Any]) -> tuple[dict[str, list[str]], dict[str, str], list[str], Any]:
    """Project the formal schema into deterministic prompt contract blocks."""
    required: dict[str, list[str]] = {}
    field_types: dict[str, str] = {}
    additional_paths: list[str] = []

    def type_label(node: Mapping[str, Any]) -> str:
        if "const" in node:
            return f"const:{node['const']}"
        wanted = node.get("type")
        if isinstance(wanted, list):
            return "|".join(str(item) for item in wanted)
        if wanted == "array" and isinstance(node.get("items"), Mapping):
            item_type = node["items"].get("type")
            return "array<object>" if item_type == "object" else "array<string>" if item_type == "string" else "array"
        return str(wanted or "object")

    def shape(node: Mapping[str, Any]) -> Any:
        if "const" in node:
            return node["const"]
        wanted = node.get("type")
        if isinstance(wanted, list):
            return 0 if "number" in wanted else "string"
        if wanted == "object":
            return {key: shape(child) for key, child in (node.get("properties") or {}).items()}
        if wanted == "array":
            items = node.get("items")
            return [shape(items)] if isinstance(items, Mapping) else []
        if wanted == "number":
            return 0
        if wanted == "boolean":
            return False
        return "string"

    def visit(node: Mapping[str, Any], path: str, *, expose_type: bool = False) -> None:
        if expose_type:
            field_types[path] = type_label(node)
        if node.get("type") == "object":
            required[path] = list(node.get("required") or [])
            if node.get("additionalProperties") is False:
                additional_paths.append(path)
            for key, child in (node.get("properties") or {}).items():
                child_path = key if path == "$" else f"{path}.{key}"
                visit(child, child_path, expose_type=True)
        elif node.get("type") == "array" and isinstance(node.get("items"), Mapping):
            visit(node["items"], f"{path}[]")

    visit(schema, "$")
    return required, field_types, additional_paths, shape(schema)


def render_stage_b_schema_contract() -> dict[str, Any]:
    top = DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA
    # The formal schema is the only structural source for prompt blocks.
    # Recompute these projections from the schema object so a future formal
    # schema change cannot silently leave a second prompt contract behind.
    nested_required, field_types, additional_properties_false_paths, shape_example = _stage_b_schema_projection(top)
    return {
        "version": DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION,
        # Required top-level keys are rendered from the formal schema.  Keep
        # this list separate from the Python compatibility tuple so adding a
        # required field cannot leave the prompt checklist stale.
        "top_level_keys": list(top["required"]),
        "top_level_required": list(top["required"]),
        "top_level_additional_properties": bool(top.get("additionalProperties", True)),
        "beat_enrichment_keys": list(STAGE_B_ENRICHMENT_KEYS),
        "character_direction_keys": list(CHARACTER_DIRECTION_KEYS),
        "character_effect_keys": list(CHARACTER_EFFECT_KEYS),
        "information_strategy_keys": list(INFORMATION_STRATEGY_KEYS),
        "information_reveal_keys": list(INFORMATION_REVEAL_KEYS),
        "rhythm_strategy_keys": list(RHYTHM_STRATEGY_KEYS),
        "canonical_key_rules": {"byte_for_byte": True, "ascii_identifiers_only": True, "additional_properties": False},
        "nested_required": nested_required,
        "field_types": field_types,
        "additional_properties_false_paths": additional_properties_false_paths,
        "shape_example": shape_example,
        "shape_decisions": {
            "information_strategy": "director_information_strategy_v2 object",
            "performance_arc": "array<{phase:string,state:string}>",
            "rhythm_strategy": "object<opening,reveal,escalation,button>",
            "visual_priority": "array<string>",
            "prohibited_interpretations": "array<string>",
        },
    }


def validate_stage_b_prompt_schema_key_parity(user_prompt: str) -> dict[str, Any]:
    contract = render_stage_b_schema_contract()
    errors: list[dict[str, Any]] = []
    found: dict[str, Any] = {}
    markers = {
        "CANONICAL_STAGE_B_TOP_LEVEL_KEYS=": contract["top_level_keys"],
        "CANONICAL_STAGE_B_BEAT_ENRICHMENT_KEYS=": contract["beat_enrichment_keys"],
        "CANONICAL_STAGE_B_CHARACTER_DIRECTION_KEYS=": contract["character_direction_keys"],
        "CANONICAL_STAGE_B_CHARACTER_EFFECT_KEYS=": contract["character_effect_keys"],
        "CANONICAL_STAGE_B_INFORMATION_STRATEGY_KEYS=": contract["information_strategy_keys"],
        "CANONICAL_STAGE_B_INFORMATION_REVEAL_KEYS=": contract["information_reveal_keys"],
        "CANONICAL_STAGE_B_RHYTHM_STRATEGY_KEYS=": contract["rhythm_strategy_keys"],
        "STAGE_B_REQUIRED_FIELDS=": contract["nested_required"],
        "STAGE_B_FIELD_TYPES=": contract["field_types"],
    }
    for marker, expected in markers.items():
        line = next((item for item in str(user_prompt or "").splitlines() if item.startswith(marker)), "")
        if not line:
            errors.append({"code": "PROMPT_CANONICAL_KEY_BLOCK_MISSING", "marker": marker})
            continue
        try:
            actual = json.loads(line[len(marker):])
        except (TypeError, ValueError, json.JSONDecodeError):
            actual = None
        found[marker.rstrip("=")] = actual
        if actual != expected:
            errors.append({"code": "STAGE_B_PROMPT_SCHEMA_KEY_PARITY", "marker": marker, "expected": expected, "actual": actual})
    additional_line = next((item for item in str(user_prompt or "").splitlines() if item.startswith("STAGE_B_ADDITIONAL_PROPERTIES=")), "")
    found["STAGE_B_ADDITIONAL_PROPERTIES"] = additional_line[len("STAGE_B_ADDITIONAL_PROPERTIES="):].strip().lower() if additional_line else None
    if found["STAGE_B_ADDITIONAL_PROPERTIES"] != "false":
        errors.append({"code": "STAGE_B_ADDITIONAL_PROPERTIES_NOT_FALSE", "expected": False, "actual": found["STAGE_B_ADDITIONAL_PROPERTIES"]})
    additional_paths_marker = "STAGE_B_ADDITIONAL_PROPERTIES_FALSE_PATHS="
    additional_paths_line = next((item for item in str(user_prompt or "").splitlines() if item.startswith(additional_paths_marker)), "")
    if not additional_paths_line:
        errors.append({"code": "STAGE_B_ADDITIONAL_PROPERTIES_PATHS_MISSING"})
    else:
        try:
            actual_paths = json.loads(additional_paths_line[len(additional_paths_marker):])
        except (TypeError, ValueError, json.JSONDecodeError):
            actual_paths = None
        found["STAGE_B_ADDITIONAL_PROPERTIES_FALSE_PATHS"] = actual_paths
        if actual_paths != contract["additional_properties_false_paths"]:
            errors.append({"code": "STAGE_B_ADDITIONAL_PROPERTIES_PATHS_PARITY", "expected": contract["additional_properties_false_paths"], "actual": actual_paths})
    shape_line = next((item for item in str(user_prompt or "").splitlines() if item.startswith("JSON_SHAPE_EXAMPLE_ONLY=")), "")
    if not shape_line:
        errors.append({"code": "STAGE_B_SHAPE_EXAMPLE_MISSING"})
    else:
        try:
            actual_shape = json.loads(shape_line[len("JSON_SHAPE_EXAMPLE_ONLY="):])
        except (TypeError, ValueError, json.JSONDecodeError):
            actual_shape = None
        found["JSON_SHAPE_EXAMPLE_ONLY"] = actual_shape
        if actual_shape != contract["shape_example"]:
            errors.append({"code": "STAGE_B_SHAPE_EXAMPLE_PARITY", "expected": contract["shape_example"], "actual": actual_shape})
    for phrase in ("byte-for-byte", "do not translate", "Chinese only in values", "never in keys", "Stage A is immutable"):
        if phrase not in str(user_prompt or ""):
            errors.append({"code": "PROMPT_CANONICAL_KEY_RULE_MISSING", "phrase": phrase})
    required_phrase = "exactly one beat_enrichment per validated DBP beat; missing, duplicate, unknown, or invented beat_ref is invalid"
    if required_phrase not in str(user_prompt or ""):
        errors.append({"code": "STAGE_B_BEAT_COVERAGE_CONTRACT_MISSING"})
    final_keys_marker = "FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEYS="
    final_keys_line = next((item for item in str(user_prompt or "").splitlines() if item.startswith(final_keys_marker)), "")
    if not final_keys_line:
        errors.append({"code": "STAGE_B_FINAL_OUTPUT_CHECKLIST_MISSING", "marker": final_keys_marker})
    else:
        try:
            actual_final_keys = json.loads(final_keys_line[len(final_keys_marker):])
        except (TypeError, ValueError, json.JSONDecodeError):
            actual_final_keys = None
        found["FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEYS"] = actual_final_keys
        if actual_final_keys != contract["top_level_required"]:
            errors.append({"code": "STAGE_B_FINAL_OUTPUT_SCHEMA_KEY_PARITY", "expected": contract["top_level_required"], "actual": actual_final_keys})
    final_count_marker = "FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEY_COUNT="
    final_count_line = next((item for item in str(user_prompt or "").splitlines() if item.startswith(final_count_marker)), "")
    if not final_count_line:
        errors.append({"code": "STAGE_B_FINAL_OUTPUT_CHECKLIST_MISSING", "marker": final_count_marker})
    else:
        try:
            actual_final_count = int(final_count_line[len(final_count_marker):].strip())
        except (TypeError, ValueError):
            actual_final_count = None
        found["FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEY_COUNT"] = actual_final_count
        if actual_final_count != len(contract["top_level_required"]):
            errors.append({"code": "STAGE_B_FINAL_OUTPUT_SCHEMA_KEY_COUNT", "expected": len(contract["top_level_required"]), "actual": actual_final_count})
    final_gate_marker = "FINAL_OUTPUT_COMPLETENESS_GATE="
    if not any(item.startswith(final_gate_marker) for item in str(user_prompt or "").splitlines()):
        errors.append({"code": "STAGE_B_FINAL_OUTPUT_COMPLETENESS_GATE_MISSING"})
    for phrase in ("visual_priority", "no unknown top-level key", "output JSON only", "no placeholders", "beat_enrichments exactly once"):
        if phrase not in str(user_prompt or ""):
            errors.append({"code": "STAGE_B_FINAL_OUTPUT_COMPLETENESS_RULE_MISSING", "phrase": phrase})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "prompt": found, "schema": contract, "structural_parity": "PASS" if not errors else "FAIL"}


def parse_director_creative_enrichment_ir(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Director CreativeEnrichment IR is empty")
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_stage_b_pairs)
    except DuplicateJSONKeyError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to parse Director CreativeEnrichment IR: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION:
        raise ValueError("Director CreativeEnrichment IR has an invalid version")
    return payload


def validate_director_creative_enrichment_text_completeness(value: Any) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if not isinstance(value, Mapping):
        return {"status": "FAIL", "errors": [{"code": "DIRECTOR_CREATIVE_ENRICHMENT_TEXT_INCOMPLETE", "path": "$"}]}
    text_paths: list[tuple[str, Any]] = [("scene_exit_intent", value.get("scene_exit_intent")), ("note", value.get("note"))]
    for idx, item in enumerate(value.get("beat_enrichments", []) if isinstance(value.get("beat_enrichments"), list) else []):
        if isinstance(item, Mapping):
            for field in ("audience_effect", "performance", "transition"):
                text_paths.append((f"beat_enrichments[{idx}].{field}", item.get(field)))
            for j, effect in enumerate(item.get("character_effects", []) if isinstance(item.get("character_effects"), list) else []):
                if isinstance(effect, Mapping): text_paths.append((f"beat_enrichments[{idx}].character_effects[{j}].effect", effect.get("effect")))
    for section in ("character_directions", "performance_arc"):
        for idx, item in enumerate(value.get(section, []) if isinstance(value.get(section), list) else []):
            if isinstance(item, Mapping):
                for key, raw in item.items():
                    if key not in {"character_ref", "phase"}: text_paths.append((f"{section}[{idx}].{key}", raw))
    rhythm = value.get("rhythm_strategy")
    if isinstance(rhythm, Mapping):
        text_paths.extend((f"rhythm_strategy.{key}", rhythm.get(key)) for key in RHYTHM_STRATEGY_KEYS)
    for path, raw in text_paths:
        text = _text(raw)
        lower = text.lower()
        if not text or any(marker in lower for marker in _INCOMPLETE_TEXT_MARKERS):
            errors.append({"code": "DIRECTOR_CREATIVE_ENRICHMENT_TEXT_INCOMPLETE", "path": path})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def _source_unit_map(source_units: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {_text(item.get("unit_id")): item for item in source_units if _text(item.get("unit_id"))}


def validate_director_beat_plan_ir(value: Any, *, source_units: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate Stage A without filling missing fields or refs."""

    schema = validate_director_beat_plan_ir_schema(value)
    errors = list(schema["errors"])
    units = _source_unit_map(source_units)
    covered: list[str] = []
    if isinstance(value, Mapping):
        beats = value.get("beats") if isinstance(value.get("beats"), list) else []
        passthrough = value.get("passthrough_refs") if isinstance(value.get("passthrough_refs"), list) else []
        for ordinal, beat in enumerate(beats, 1):
            if not isinstance(beat, Mapping):
                continue
            refs = beat.get("refs") if isinstance(beat.get("refs"), list) else []
            for ref in refs:
                ref_text = _text(ref)
                if ref_text not in units:
                    errors.append({"code": "DIRECTOR_BEAT_PLAN_SOURCE_REF_INVALID", "ordinal": ordinal, "unit_ref": ref_text})
                else:
                    covered.append(ref_text)
        for ref in passthrough:
            ref_text = _text(ref)
            if ref_text not in units:
                errors.append({"code": "DIRECTOR_BEAT_PLAN_SOURCE_REF_INVALID", "unit_ref": ref_text})
            else:
                covered.append(ref_text)
    covered_set = set(covered)
    missing = sorted(set(units) - covered_set)
    duplicates = sorted(ref for ref in covered_set if covered.count(ref) > 1)
    if missing:
        errors.append({"code": "DIRECTOR_BEAT_PLAN_SOURCE_COVERAGE_INCOMPLETE", "missing_unit_refs": missing})
    if duplicates:
        errors.append({"code": "DIRECTOR_BEAT_PLAN_SOURCE_REF_DUPLICATE", "unit_refs": duplicates})
    return {
        "status": "qualified" if not errors else "blocked",
        "errors": errors,
        "version": DIRECTOR_BEAT_PLAN_IR_VERSION,
        "source_unit_count": len(units),
        "covered_source_unit_count": len(covered_set & set(units)),
        "creative_beat_count": len(value.get("beats", [])) if isinstance(value, Mapping) and isinstance(value.get("beats"), list) else 0,
        "local_creative_completion_count": 0,
    }


def materialize_director_beat_plan_ids(value: Mapping[str, Any], *, scene_id: str) -> dict[str, Any]:
    """Assign local DBP ids only after Stage A validation has passed."""

    result = copy.deepcopy(dict(value))
    result["beats"] = [{"beat_ref": f"DBP_{scene_id}_{index:03d}", **copy.deepcopy(beat)} for index, beat in enumerate(value.get("beats", []), 1)]
    result["authoring_stage"] = "AUTHORING_STAGE_A"
    result["proposal_origin"] = "PROVIDER_PROPOSAL"
    result["authority"] = "PROVIDER_PROPOSAL"
    return result


def validate_director_creative_enrichment_ir(value: Any, *, beat_plan: Mapping[str, Any], declared_participants: list[Any] | None = None) -> dict[str, Any]:
    schema = validate_director_creative_enrichment_ir_schema(value)
    errors = list(schema["errors"])
    text_report = validate_director_creative_enrichment_text_completeness(value)
    errors.extend(text_report.get("errors", []))
    beat_ids = [_text(item.get("beat_ref")) for item in beat_plan.get("beats", []) if isinstance(item, Mapping)]
    beat_set = set(beat_ids)
    seen: list[str] = []
    participants: set[str] = set()
    for item in declared_participants or []:
        if isinstance(item, Mapping):
            participants.update(_text(item.get(key)) for key in ("id", "character_id", "name", "character_ref") if _text(item.get(key)))
        elif _text(item):
            participants.add(_text(item))
    if isinstance(value, Mapping):
        if not isinstance(value.get("information_strategy"), Mapping):
            errors.append({"code": "DIRECTOR_ENRICHMENT_INFORMATION_STRATEGY_INVALID"})
        else:
            info = value["information_strategy"]
            reveal_plan = info.get("reveal_plan") if isinstance(info.get("reveal_plan"), list) else []
            reveal_ids: list[str] = []
            for item in reveal_plan:
                if isinstance(item, Mapping):
                    reveal_ids.append(_text(item.get("beat_id")))
                    if _text(item.get("beat_id")) not in beat_set:
                        errors.append({"code": "DIRECTOR_ENRICHMENT_INFORMATION_BEAT_REF_UNKNOWN", "beat_id": _text(item.get("beat_id"))})
            if len(reveal_ids) != len(set(reveal_ids)):
                errors.append({"code": "DIRECTOR_ENRICHMENT_INFORMATION_BEAT_REF_DUPLICATE"})
        if not isinstance(value.get("performance_arc"), list) or not all(isinstance(item, Mapping) for item in value.get("performance_arc", [])):
            errors.append({"code": "DIRECTOR_ENRICHMENT_PERFORMANCE_ARC_INVALID"})
        if not isinstance(value.get("rhythm_strategy"), Mapping):
            errors.append({"code": "DIRECTOR_ENRICHMENT_RHYTHM_STRATEGY_INVALID"})
        for list_field in ("visual_priority", "prohibited_interpretations"):
            if not isinstance(value.get(list_field), list) or not all(isinstance(item, str) and _text(item) for item in value.get(list_field, [])):
                errors.append({"code": "DIRECTOR_ENRICHMENT_TEXT_LIST_INVALID", "field": list_field})
        for enrichment in value.get("beat_enrichments", []) if isinstance(value.get("beat_enrichments"), list) else []:
            if not isinstance(enrichment, Mapping):
                continue
            ref = _text(enrichment.get("beat_ref")); seen.append(ref)
            if ref not in beat_set:
                errors.append({"code": "DIRECTOR_ENRICHMENT_BEAT_REF_UNKNOWN", "beat_ref": ref})
            effects = enrichment.get("character_effects") if isinstance(enrichment.get("character_effects"), list) else []
            for effect in effects:
                if not isinstance(effect, Mapping) or set(effect) != CHARACTER_EFFECT_FIELDS or not _text(effect.get("character_ref")) or not isinstance(effect.get("effect"), str) or not _text(effect.get("effect")):
                    errors.append({"code": "DIRECTOR_ENRICHMENT_CHARACTER_EFFECT_INVALID", "beat_ref": ref})
                elif participants and _text(effect.get("character_ref")) not in participants:
                    errors.append({"code": "DIRECTOR_ENRICHMENT_PARTICIPANT_INVALID", "participant_ref": _text(effect.get("character_ref"))})
        if len(seen) != len(set(seen)):
            errors.append({"code": "DIRECTOR_ENRICHMENT_BEAT_REF_DUPLICATE", "beat_refs": sorted({ref for ref in seen if seen.count(ref) > 1})})
        missing = sorted(beat_set - set(seen))
        if missing:
            errors.append({"code": "DIRECTOR_ENRICHMENT_BEAT_REF_MISSING", "beat_refs": missing})
        for direction in value.get("character_directions", []) if isinstance(value.get("character_directions"), list) else []:
            if not isinstance(direction, Mapping):
                errors.append({"code": "DIRECTOR_ENRICHMENT_CHARACTER_DIRECTION_INVALID"}); continue
            unexpected = sorted(set(direction) - CHARACTER_DIRECTION_FIELDS)
            if unexpected:
                errors.append({"code": "DIRECTOR_ENRICHMENT_CHARACTER_DIRECTION_FIELD_UNEXPECTED", "fields": unexpected})
            ref = _text(direction.get("character_ref"))
            if not ref or (participants and ref not in participants):
                errors.append({"code": "DIRECTOR_ENRICHMENT_PARTICIPANT_INVALID", "participant_ref": ref})
            if not any(isinstance(direction.get(field), str) and _text(direction.get(field)) for field in CHARACTER_DIRECTION_FIELDS - {"character_ref"}):
                errors.append({"code": "DIRECTOR_ENRICHMENT_DIRECTION_SEMANTICS_REQUIRED", "participant_ref": ref})
    return {
        "status": "qualified" if not errors else "blocked",
        "errors": errors,
        "version": DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION,
        "stage_a_beat_count": len(beat_ids),
        "beat_enrichment_count": len(seen),
        "beat_coverage": "PASS" if set(seen) == beat_set and len(seen) == len(set(seen)) else "FAIL",
        "source_mutation_count": 0,
    }


def compile_progressive_director_proposal(*, beat_plan_ir: Mapping[str, Any], enrichment_ir: Mapping[str, Any], baseline_treatment: Mapping[str, Any], source_scene: Mapping[str, Any], materialized_beat_plan: Mapping[str, Any] | None = None, materialized_fingerprint: str = "") -> dict[str, Any]:
    """Merge two validated proposals without creating new creative semantics."""

    source_units = (baseline_treatment.get("source_constraints") or {}).get("source_authoring_units", [])
    stage_a = validate_director_beat_plan_ir(beat_plan_ir, source_units=source_units)
    if stage_a["status"] != "qualified":
        raise ValueError({"code": "DIRECTOR_BEAT_PLAN_IR_INVALID", "report": stage_a})
    expected_materialized = materialize_director_beat_plan_ids(beat_plan_ir, scene_id=_text(source_scene.get("scene_id") or baseline_treatment.get("scene_id")))
    materialized = copy.deepcopy(dict(materialized_beat_plan)) if isinstance(materialized_beat_plan, Mapping) else expected_materialized
    if isinstance(materialized_beat_plan, Mapping) and json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != json.dumps(expected_materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")):
        raise ValueError({"code": "DIRECTOR_STAGE_A_MATERIALIZED_MUTATION"})
    expected_materialized_fp = hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if materialized_fingerprint and expected_materialized_fp != str(materialized_fingerprint):
        raise ValueError({"code": "DIRECTOR_STAGE_A_MATERIALIZED_FINGERPRINT_MISMATCH", "expected": str(materialized_fingerprint), "actual": expected_materialized_fp})
    stage_b = validate_director_creative_enrichment_ir(enrichment_ir, beat_plan=materialized, declared_participants=source_scene.get("participants", []))
    if stage_b["status"] != "qualified":
        raise ValueError({"code": "DIRECTOR_CREATIVE_ENRICHMENT_IR_INVALID", "report": stage_b})
    enrichment_by_ref = {item["beat_ref"]: item for item in enrichment_ir["beat_enrichments"]}
    beats = []
    for ordinal, beat in enumerate(materialized["beats"], 1):
        enrich = enrichment_by_ref[beat["beat_ref"]]
        beats.append({
            "creative_beat_id": f"DCB_{_text(source_scene.get('scene_id') or baseline_treatment.get('scene_id'))}_{ordinal:03d}",
            "authority": DIRECTOR_CREATIVE_AUTHORITY,
            "derived_from_source_unit_refs": list(beat["refs"]),
            "dramatic_purpose": beat["purpose"],
            "director_objective": beat["objective"],
            "information_change": beat["information_change"],
            "audience_effect": enrich["audience_effect"],
            "character_effects": copy.deepcopy(enrich["character_effects"]),
            "performance_intent": enrich["performance"],
            "transition_intent": enrich["transition"],
            "hook_intent": beat["hook"],
        })
    constraints = copy.deepcopy(baseline_treatment.get("source_constraints") or {})
    projection = {
        "status": "PROPOSED", "authority": DIRECTOR_CREATIVE_AUTHORITY,
        "director_scene_label": beat_plan_ir["scene_label"], "director_scene_label_authority": DIRECTOR_CREATIVE_AUTHORITY,
        "scene_objective": beat_plan_ir["scene_objective"], "dramatic_question": beat_plan_ir["dramatic_question"],
        "creative_beats": beats, "explicit_passthrough_unit_refs": list(beat_plan_ir["passthrough_refs"]),
        "character_directions": copy.deepcopy(enrichment_ir["character_directions"]),
        "performance_arc": copy.deepcopy(enrichment_ir["performance_arc"]),
        "information_strategy": copy.deepcopy(enrichment_ir["information_strategy"]),
        "rhythm_strategy": copy.deepcopy(enrichment_ir["rhythm_strategy"]),
        "visual_priority": copy.deepcopy(enrichment_ir["visual_priority"]),
        "scene_exit_intent": enrichment_ir["scene_exit_intent"],
        "prohibited_interpretations": copy.deepcopy(enrichment_ir["prohibited_interpretations"]),
    }
    return {
        "schema_version": "director_treatment_v3", "scene_id": _text(baseline_treatment.get("scene_id") or source_scene.get("scene_id")),
        "scene_name": "", "source_constraints": constraints, "creative_projection": projection,
        "unknowns": copy.deepcopy(beat_plan_ir["unknowns"]), "decision": "ready_for_review",
        "confidence": enrichment_ir["confidence"], "human_confirmation_required": True, "note": enrichment_ir["note"],
        "compiler_report": {"status": "PASS", "local_new_creative_decision_count": 0, "local_direction_semantic_expansion_count": 0, "stage_a": stage_a, "stage_b": stage_b},
    }


def build_stage_a_persistence_patch(*, ir: Mapping[str, Any], fingerprint: str, authorization_id: str, attempt_id: str, materialized_beat_plan: Mapping[str, Any] | None = None, materialized_fingerprint: str = "", provider_provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return model_info-only state; never replaces DecisionPacket.proposal."""

    stage = {"status": "VALIDATED", "ir": copy.deepcopy(dict(ir)), "fingerprint": str(fingerprint), "ir_fingerprint": str(fingerprint), "authorization_id": str(authorization_id), "attempt_id": str(attempt_id), "authoring_stage": "BEAT_PLAN"}
    if materialized_beat_plan is not None:
        stage["materialized_beat_plan"] = copy.deepcopy(dict(materialized_beat_plan))
    if materialized_fingerprint:
        stage["materialized_fingerprint"] = str(materialized_fingerprint)
    if provider_provenance is not None:
        stage["provider_provenance"] = copy.deepcopy(dict(provider_provenance))
    return {"progressive_director_authoring": {"stage_a": stage}}


def build_stage_b_persistence_patch(*, ir: Mapping[str, Any], fingerprint: str, authorization_id: str, attempt_id: str, stage_a_materialized_fingerprint: str, provider_provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    stage = {
        "status": "VALIDATED", "ir": copy.deepcopy(dict(ir)), "fingerprint": str(fingerprint), "ir_fingerprint": str(fingerprint),
        "authorization_id": str(authorization_id), "attempt_id": str(attempt_id), "authoring_stage": "CREATIVE_ENRICHMENT",
        "stage_a_materialized_fingerprint": str(stage_a_materialized_fingerprint),
    }
    if provider_provenance is not None:
        stage["provider_provenance"] = copy.deepcopy(dict(provider_provenance))
    return {"progressive_director_authoring": {"stage_b": stage}}


def is_progressive_stage_validated(stage: Any, *, authoring_stage: str | None = None) -> bool:
    if not isinstance(stage, Mapping):
        return False
    status = _text(stage.get("status"))
    if authoring_stage and _text(stage.get("authoring_stage")).upper() != _text(authoring_stage).upper():
        return False
    if status == "VALIDATED":
        return True
    return status.endswith("_VALIDATED")


def build_director_beat_plan_prompt(*, scene_id: str, source_units: list[Mapping[str, Any]], declared_participants: list[Any] | None = None, explicit_story_constraints: list[Any] | None = None, unknown_source_facts: list[Any] | None = None) -> tuple[str, str]:
    """Build the small Stage A prompt without any Stage B output burden."""

    system = DIRECTOR_BEAT_PLAN_IR_V1_SYSTEM_PROMPT
    minimized_units = []
    for item in source_units:
        if not isinstance(item, Mapping):
            continue
        unit = {"unit_id": _text(item.get("unit_id") or item.get("source_ref")), "source_type": _text(item.get("source_type")), "source_order": item.get("source_order"), "text": _text(item.get("text"))}
        if _text(item.get("source_type")).upper() in {"SOURCE_DIALOGUE", "DIALOGUE"} and _text(item.get("speaker")):
            unit["speaker"] = _text(item.get("speaker"))
        minimized_units.append(unit)
    contract = render_stage_a_schema_contract()
    shape_example = _stage_a_shape_example()
    top_keys = json.dumps(contract["top_level_keys"], ensure_ascii=False, separators=(",", ":"))
    beat_keys = json.dumps(contract["beat_keys"], ensure_ascii=False, separators=(",", ":"))
    user = (
        "DIRECTOR_BEAT_PLAN_IR_V1\n"
        f"SCENE_ID={json.dumps(scene_id, ensure_ascii=False)}\n"
        f"SOURCE_AUTHORING_UNITS={json.dumps(minimized_units, ensure_ascii=False, sort_keys=True)}\n"
        f"DECLARED_PARTICIPANTS={json.dumps(declared_participants or [], ensure_ascii=False, sort_keys=True)}\n"
        f"EXPLICIT_STORY_CONSTRAINTS={json.dumps(explicit_story_constraints or [], ensure_ascii=False, sort_keys=True)}\n"
        f"UNKNOWN_SOURCE_FACTS={json.dumps(unknown_source_facts or [], ensure_ascii=False, sort_keys=True)}\n"
        f"CANONICAL_TOP_LEVEL_KEYS={top_keys}\n"
        f"CANONICAL_BEAT_KEYS={beat_keys}\n"
        "KEY_RULE=Property names must match these strings exactly, byte-for-byte. do not translate; Chinese only in values, never in keys.\n"
        "CANONICAL_JSON_KEY_CONTRACT=JSON property names are protocol tokens, not natural-language text. Every property name MUST be copied byte-for-byte from the canonical key lists. Do NOT translate, localize, paraphrase, abbreviate, rename, mix Chinese with English, change case, add prefixes/suffixes, or create aliases. Only JSON VALUES may contain Chinese natural-language text. JSON KEYS must remain the exact canonical ASCII identifiers.\n"
        "中文键名合同=所有 JSON 键名都是协议标识符，不是自然语言。键名必须逐字符原样复制；禁止翻译、同义词、别名、大小写变化或额外翻译版本。中文只能出现在 value 中，不能出现在 property name 中。\n"
        "REQUIRED_TOP_LEVEL_FIELDS=" + ",".join(contract["top_level_keys"]) + "\n"
        "REQUIRED_BEAT_FIELDS=" + ",".join(contract["beat_keys"]) + "\n"
        "FIELD_TYPES=" + "; ".join(f"{key}:{value}" for key, value in contract["field_types"].items()) + "\n"
        "HOOK_BOOLEAN_CONTRACT=beats[].hook MUST be a JSON boolean literal true or false. NEVER output a string for hook, NEVER write hook text, and NEVER quote true/false. hook=true means this beat carries a clear unresolved question, reversal, suspense, continuation drive, or next-step hook; hook=false means the beat mainly establishes, explains, advances, or transitions without a clear hook. hook is only a classification flag, not hook copy, audience_effect, dramatic_question, information_change, transition, performance, or scene_exit_intent.\n"
        f"JSON_SHAPE_EXAMPLE_ONLY={json.dumps(shape_example, ensure_ascii=False, separators=(',', ':'))}; this example specifies JSON shape and types only; do not copy its semantics.\n"
        "BEAT_PLAN_CONTRACT=只允许上述字段；每个 string 类型文本字段必须是完整中文句子，dramatic_question 以？?!结束；hook 不得是字符串。\n"
        "禁止省略字段、增加字段、补写来源事实；禁止输出 Stage B 字段、对白内容、speaker、binding 或 source_constraints；所有 SAU 必须恰好出现在 beats[].refs 或 passthrough_refs。"
    )
    return system, user


def build_director_creative_enrichment_prompt(*, scene_id: str, beat_plan: Mapping[str, Any], declared_participants: list[Any] | None = None, source_authoring_units: list[Mapping[str, Any]] | None = None, source_authoring_unit_fingerprint: str = "", source_authority_content_fingerprint: str = "", revision_feedback: Mapping[str, Any] | None = None, revision_parent: Mapping[str, Any] | None = None, semantic_review_policy: str = "", semantic_policy_fingerprint: str = "", structural_feedback: Mapping[str, Any] | None = None) -> tuple[str, str]:
    """Build the Stage B prompt over a validated local beat plan."""

    system = "你是受 Stage A 约束的导演表现层助手。只输出 director_creative_enrichment_ir_v1 JSON，不得重排或修改 Stage A。"
    contract = render_stage_b_schema_contract()
    beat_refs = [str(item.get("beat_ref") or "") for item in (beat_plan.get("beats") or []) if isinstance(item, Mapping)]
    minimized_source_units = []
    for item in source_authoring_units or []:
        if not isinstance(item, Mapping):
            continue
        minimized = {"unit_id": _text(item.get("unit_id") or item.get("source_ref")), "source_type": _text(item.get("source_type")), "source_order": item.get("source_order"), "text": _text(item.get("text") or item.get("source_text"))}
        if _text(item.get("speaker")):
            minimized["speaker"] = _text(item.get("speaker"))
        minimized_source_units.append(minimized)
    v2_boundary = ""
    if semantic_review_policy == "director_creative_semantic_review_v2":
        v2_boundary = (
            f"SEMANTIC_REVIEW_POLICY={json.dumps(semantic_review_policy, ensure_ascii=False)}\n"
            f"SEMANTIC_POLICY_FINGERPRINT={json.dumps(semantic_policy_fingerprint or '', ensure_ascii=False)}\n"
            "UNCERTAINTY_PRESERVATION_RULE=If SOURCE_AUTHORING_UNITS says 是否、可能、想不起、无法确认、不确定、未知、未说明 or equivalent unknown, do not turn it into 首次、第一次、从未、一定、就是、确定、确认、明确知道 or 必然.\n"
            "STORY_ACTION_BOUNDARY=Do not invent canonical story actions involving key props, including opening a box, picking up a prop, taking film, or handing over a key, unless the action is explicit in SOURCE_AUTHORING_UNITS.\n"
            "SCENEBLOCKING_BOUNDARY=Stage B must not specify concrete spatial paths, placement, or movement such as walking to a prop, bringing someone to a place, standing at a place, moving to a place, or going behind someone unless it is an explicit source event.\n"
            "PERFORMANCE_ACTION_ALLOWLIST=Low-risk playable actions such as pauses, hesitation, gaze changes, facial changes, breath, tone, speech rate, body tension, and freezing remain allowed.\n"
            "V2_SHOTPLAN_BOUNDARY=Keep shot size, camera, lens, movement, frame, keyframe, shot count, and concrete shot execution out of Stage B.\n"
        )
    user = (
        "DIRECTOR_CREATIVE_ENRICHMENT_IR_V1\n"
        f"SCENE_ID={json.dumps(scene_id, ensure_ascii=False)}\n"
        f"VALIDATED_BEAT_PLAN={json.dumps(beat_plan, ensure_ascii=False, sort_keys=True)}\n"
        f"SOURCE_AUTHORING_UNITS={json.dumps(minimized_source_units, ensure_ascii=False, sort_keys=True)}\n"
        f"SOURCE_AUTHORING_UNIT_FINGERPRINT={json.dumps(source_authoring_unit_fingerprint or '', ensure_ascii=False)}\n"
        f"SOURCE_AUTHORITY_CONTENT_FINGERPRINT={json.dumps(source_authority_content_fingerprint or '', ensure_ascii=False)}\n"
        f"DECLARED_PARTICIPANTS={json.dumps(declared_participants or [], ensure_ascii=False, sort_keys=True)}\n"
        f"REVISION_PARENT={json.dumps(revision_parent or {}, ensure_ascii=False, sort_keys=True)}\n"
        f"REVISION_FEEDBACK={json.dumps(revision_feedback or {}, ensure_ascii=False, sort_keys=True)}\n"
        f"STRUCTURAL_REVISION_FEEDBACK={json.dumps(structural_feedback or {}, ensure_ascii=False, sort_keys=True)}\n"
        f"{v2_boundary}"
        f"CANONICAL_STAGE_B_TOP_LEVEL_KEYS={json.dumps(contract['top_level_keys'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"CANONICAL_STAGE_B_BEAT_ENRICHMENT_KEYS={json.dumps(contract['beat_enrichment_keys'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"CANONICAL_STAGE_B_CHARACTER_DIRECTION_KEYS={json.dumps(contract['character_direction_keys'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"CANONICAL_STAGE_B_CHARACTER_EFFECT_KEYS={json.dumps(contract['character_effect_keys'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"CANONICAL_STAGE_B_INFORMATION_STRATEGY_KEYS={json.dumps(contract['information_strategy_keys'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"CANONICAL_STAGE_B_INFORMATION_REVEAL_KEYS={json.dumps(contract['information_reveal_keys'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"CANONICAL_STAGE_B_RHYTHM_STRATEGY_KEYS={json.dumps(contract['rhythm_strategy_keys'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"STAGE_B_REQUIRED_FIELDS={json.dumps(contract['nested_required'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
        f"STAGE_B_FIELD_TYPES={json.dumps(contract['field_types'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
        "STAGE_B_ADDITIONAL_PROPERTIES=false\n"
        f"STAGE_B_ADDITIONAL_PROPERTIES_FALSE_PATHS={json.dumps(contract['additional_properties_false_paths'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"JSON_SHAPE_EXAMPLE_ONLY={json.dumps(contract['shape_example'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
        f"BEAT_COVERAGE={json.dumps(beat_refs, ensure_ascii=False, separators=(',', ':'))}\n"
        "KEY_RULE=Property names must match these strings exactly, byte-for-byte. do not translate; Chinese only in values, never in keys.\n"
        "Stage A is immutable: refs,purpose,objective,information_change,hook,scene_objective,dramatic_question are read-only and must not be repeated or changed.\n"
        "SOURCE_GROUNDING_RULE=Creative direction may interpret presentation, but must not introduce new story facts, hidden character knowledge, backstory, relationships, motives, past events, sensory facts, or object properties not present in SOURCE_AUTHORING_UNITS or validated Stage A.\n"
        "CHARACTER_KNOWLEDGE_CONTRACT=Do not assert 他知道、他认识、他早就知道、他经历过、他不是第一次、他曾经、他训练过 or equivalent character knowledge/history unless SOURCE_AUTHORING_UNITS explicitly support it. Phrase uncertainty as a playable performance option.\n"
        "EMOTIONAL_FACT_CONTRACT=Do not canonize love, hatred, resentment, guilt, jealousy, attachment, or fear without source support; write playable tension or performance options instead.\n"
        "SENSORY_FACT_CONTRACT=Do not invent smells, tastes, temperatures, textures, sounds, or other sensory facts absent from SOURCE_AUTHORING_UNITS.\n"
        "STAGE_B_SHOTPLAN_BOUNDARY=Do not specify shot size, camera angle, lens, camera movement, frame number, keyframe, shot count, or concrete camera execution. 禁止特写、近景、全景、机位、焦段、推拉摇移、第一帧、最后一帧、镜头编号和具体镜头执行。\n"
        "REVISION_GENERATION_CONTRACT=Generate a fresh CreativeEnrichment IR. Do not patch or paraphrase the rejected response. Do not preserve rejected assumptions. Use source facts and Stage A as authority. 重新生成全新的 CreativeEnrichment IR；禁止修补、改写或沿用被拒绝响应中的假设。REVISION_FEEDBACK is a constraint list, not repair instructions.\n"
        "exactly one beat_enrichment per validated DBP beat; missing, duplicate, unknown, or invented beat_ref is invalid\n"
        "每个 DBP beat_ref 必须恰好有一个 beat_enrichment；character_effects 只能引用 DECLARED_PARTICIPANTS。"
        "information_strategy 必须使用 director_information_strategy_v2 对象；performance_arc 使用 phase/state 对象数组；rhythm_strategy 使用 opening/reveal/escalation/button。"
        f"\nFINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEYS={json.dumps(contract['top_level_required'], ensure_ascii=False, separators=(',', ':'))}\n"
        f"FINAL_OUTPUT_REQUIRED_TOP_LEVEL_KEY_COUNT={len(contract['top_level_required'])}\n"
        "FINAL_OUTPUT_COMPLETENESS_GATE=Before emitting the final response, self-check that the JSON object contains every required top-level key exactly once, contains no unknown top-level key, uses visual_priority as an array<string> (required and never replaced by audience_focus or rhythm_strategy), includes beat_enrichments exactly once per validated beat, information_strategy, rhythm_strategy, performance_arc, prohibited_interpretations, scene_exit_intent, confidence, and note, emits output JSON only, and contains no placeholders, TODO, null, or schema commentary. visual_priority may contain only source-supported visual subjects; never add shots, camera, lens, composition, keyframes, or concrete shot execution.\n"
    )
    return system, user


__all__ = [
    "DIRECTOR_BEAT_PLAN_IR_VERSION", "DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION",
    "DIRECTOR_BEAT_PLAN_IR_SCHEMA", "DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA",
    "validate_director_beat_plan_ir_schema", "validate_director_beat_plan_ir",
    "parse_director_beat_plan_ir", "validate_director_beat_plan_text_completeness", "DIRECTOR_BEAT_PLAN_IR_V1_SYSTEM_PROMPT",
    "materialize_director_beat_plan_ids", "validate_director_creative_enrichment_ir_schema", "parse_director_creative_enrichment_ir",
    "validate_director_creative_enrichment_ir", "validate_director_creative_enrichment_text_completeness", "compile_progressive_director_proposal",
    "build_stage_a_persistence_patch", "build_stage_b_persistence_patch", "is_progressive_stage_validated", "build_director_beat_plan_prompt", "build_director_creative_enrichment_prompt",
    "CANONICAL_TOP_LEVEL_KEYS", "CANONICAL_BEAT_KEYS", "render_stage_a_schema_contract",
    "STAGE_B_TOP_LEVEL_KEYS", "STAGE_B_ENRICHMENT_KEYS", "CHARACTER_DIRECTION_KEYS", "CHARACTER_EFFECT_KEYS", "render_stage_b_schema_contract",
    "validate_stage_a_prompt_schema_key_parity", "validate_stage_b_prompt_schema_key_parity", "audit_duplicate_json_keys", "DuplicateJSONKeyError",
]
