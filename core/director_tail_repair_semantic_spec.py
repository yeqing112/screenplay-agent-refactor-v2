"""Semantic Spec SSOT for Director Tail Repair IR.

The spec is intentionally small (not a JSON-Schema implementation).  Every
consumer-facing contract and the authoritative validator derive from this
module so nested constraints cannot silently drift.
"""
from __future__ import annotations

import copy
import json
from typing import Any

SEMANTIC_SPEC_VERSION = "director_tail_repair_semantic_spec_v1"


def _field(type_name: Any, **kwargs: Any) -> dict[str, Any]:
    value = {"type": type_name}
    value.update(kwargs)
    return value


_TEXT = _field("string", min_length=1)
_TEXT_NULLABLE = _field("string", min_length=1, nullable=True)
_NUMBER = _field("number")
_NON_NEGATIVE = _field("number", minimum=0)


REPAIR_TYPE_SPECS: dict[str, dict[str, Any]] = {
    "edit": {
        "groups": {
            "edit": {
                "type": "object",
                "required": False,
                "fields": {
                    "duration_seconds": _field("number", minimum=0, minimum_exclusive=True),
                    "cut_reason": copy.deepcopy(_TEXT),
                    "hold_after_action_seconds": copy.deepcopy(_NON_NEGATIVE),
                    "hold_before_cut_seconds": copy.deepcopy(_NON_NEGATIVE),
                    "hold_after_reveal_seconds": copy.deepcopy(_NON_NEGATIVE),
                    "rhythm_change": copy.deepcopy(_TEXT),
                    "reaction_timing": copy.deepcopy(_TEXT),
                },
            }
        }
    },
    "emotion": {
        "groups": {
            "emotion": {
                "type": "object",
                "required": False,
                "fields": {
                    "intensity": _field("number", minimum=0, maximum=10),
                    "start": copy.deepcopy(_TEXT_NULLABLE),
                    "end": copy.deepcopy(_TEXT_NULLABLE),
                    "arc_position": copy.deepcopy(_TEXT_NULLABLE),
                    "valence": copy.deepcopy(_TEXT_NULLABLE),
                    "shift": copy.deepcopy(_TEXT_NULLABLE),
                },
            },
            "performance_emphasis": _field("string", min_length=1),
        }
    },
    "information": {
        "groups": {
            "information_strategy": {
                "type": "object",
                "required": False,
                "fields": {
                    "reveals": _field("array", min_items=1, item_type="string", item_min_length=1),
                    "withholds": _field("array", min_items=1, item_type="string", item_min_length=1),
                    "audience_focus": _field("string_or_array", min_length=1, min_items=1, item_type="string", item_min_length=1),
                    "reveal_order": _field("array", min_items=1, item_type="string", item_min_length=1),
                    "withhold_until": _field("string_or_array", min_length=1, min_items=1, item_type="string", item_min_length=1),
                    "audience_should_notice": _field("string_or_array", min_length=1, min_items=1, item_type="string", item_min_length=1),
                    "audience_should_not_yet_know": _field("string_or_array", min_length=1, min_items=1, item_type="string", item_min_length=1),
                },
            }
        }
    },
    "performance": {
        "groups": {
            "performance_direction": {
                "type": "array",
                "min_items": 1,
                "items": {
                    "type": "object",
                    "item_required_fields": ["character_id", "objective", "visible_behavior"],
                    "item_allowed_fields": ["character_id", "objective", "visible_behavior", "reaction_behavior", "subtext", "emphasis"],
                    "fields": {
                        "character_id": copy.deepcopy(_TEXT),
                        "objective": copy.deepcopy(_TEXT),
                        "visible_behavior": copy.deepcopy(_TEXT),
                        "reaction_behavior": copy.deepcopy(_TEXT_NULLABLE),
                        "subtext": copy.deepcopy(_TEXT_NULLABLE),
                        "emphasis": copy.deepcopy(_TEXT_NULLABLE),
                    },
                },
            }
        }
    },
    "camera": {
        "groups": {
            "camera": {
                "type": "object",
                "required": False,
                "fields": {key: copy.deepcopy(_TEXT) for key in ("shot_size", "angle", "movement", "speed", "camera_side")},
            },
            "composition": {
                "type": "object",
                "required": False,
                "fields": {key: copy.deepcopy(_TEXT) for key in ("frame_relationship", "dominant_subject", "visual_emphasis", "foreground", "background", "depth", "screen_position", "blocking_focus")},
            },
        }
    },
}


def get_semantic_spec() -> dict[str, Any]:
    return {"version": SEMANTIC_SPEC_VERSION, "repair_types": copy.deepcopy(REPAIR_TYPE_SPECS)}


def get_repair_type_spec(repair_type: str) -> dict[str, Any]:
    return copy.deepcopy(REPAIR_TYPE_SPECS.get(str(repair_type), {"groups": {}}))


def minimal_valid_skeleton(repair_type: str, *, plan_shot_placeholder: str = "<allowed plan_shot_id>", character_placeholder: str = "<existing character_id>") -> dict[str, Any]:
    """Return a typed shape example; placeholders are never production facts."""
    base: dict[str, Any] = {"schema_version": "director_tail_repair_ir_v1", "repair_type": repair_type, "root_cause": "<compatible root_cause>", "target_dimensions": ["<target dimension>"], "shot_decisions": [{"plan_shot_id": plan_shot_placeholder}]}
    decision = base["shot_decisions"][0]
    if repair_type == "edit": decision["edit"] = {"cut_reason": "<non-empty>"}
    elif repair_type == "emotion": decision["emotion"] = {"intensity": 5}
    elif repair_type == "information": decision["information_strategy"] = {"audience_focus": "<non-empty>"}
    elif repair_type == "performance": decision["performance_direction"] = [{"character_id": character_placeholder, "objective": "<non-empty>", "visible_behavior": "<non-empty>"}]
    elif repair_type == "camera": decision["camera"] = {"shot_size": "<non-empty>"}
    return base


def typed_constraints_for(repair_type: str) -> dict[str, Any]:
    return {"semantic_spec_version": SEMANTIC_SPEC_VERSION, "repair_type": repair_type, **get_repair_type_spec(repair_type)}


def render_constraints(repair_type: str | None = None) -> str:
    """Deterministic human-readable constraints for a provider system prompt."""
    types = [repair_type] if repair_type else sorted(REPAIR_TYPE_SPECS)
    lines = [f"semantic_spec_version: {SEMANTIC_SPEC_VERSION}"]
    for kind in types:
        spec = REPAIR_TYPE_SPECS.get(kind)
        if not spec: continue
        lines.append(f"{kind}:")
        if kind == "emotion":
            lines.append("- emotion.intensity must be a number in range 0..10")
        for group, group_spec in spec["groups"].items():
            if group_spec.get("type") == "array":
                lines.append(f"- {group} must be a non-empty array (minItems={group_spec.get('min_items')})")
                item = group_spec.get("items", {})
                lines.append(f"- every item must be object with required fields: {', '.join(item.get('item_required_fields', []))}")
                lines.append(f"- item allowed fields: {', '.join(item.get('item_allowed_fields', []))}")
            else:
                lines.append(f"- {group} is an object; allowed fields: {', '.join(sorted(group_spec.get('fields', {})))}")
            for field, field_spec in sorted(group_spec.get("fields", {}).items()):
                bits = [f"type={field_spec.get('type')}"]
                if "minimum" in field_spec: bits.append(f"minimum={field_spec['minimum']}{' (exclusive)' if field_spec.get('minimum_exclusive') else ''}")
                if "maximum" in field_spec: bits.append(f"maximum={field_spec['maximum']}")
                if "min_length" in field_spec: bits.append(f"minLength={field_spec['min_length']}")
                if "min_items" in field_spec: bits.append(f"minItems={field_spec['min_items']}")
                lines.append(f"- {group}.{field}: " + ", ".join(bits))
    return "\n".join(lines)


def spec_json() -> str:
    return json.dumps(get_semantic_spec(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = ["SEMANTIC_SPEC_VERSION", "REPAIR_TYPE_SPECS", "get_semantic_spec", "get_repair_type_spec", "typed_constraints_for", "minimal_valid_skeleton", "render_constraints", "spec_json"]
