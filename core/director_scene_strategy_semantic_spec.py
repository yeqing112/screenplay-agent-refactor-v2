"""Single source of truth for Director Quality V3 Phase 1.1.

The semantic spec is intentionally provider-neutral.  Prompt contracts,
validators, format-repair packets and the deterministic compiler consume the
same definitions instead of maintaining subtly different nested shapes.
"""
from __future__ import annotations

import re
from typing import Any


SEMANTIC_SPEC_VERSION = "director_scene_strategy_semantic_spec_v1"
IR_SCHEMA_VERSION = "director_scene_strategy_ir_v1"
CANONICAL_SCHEMA_VERSION = "director_scene_strategy_v2"
COMPILER_VERSION = "director_scene_strategy_ir_compiler_v1"

POWER_CENTER_TYPES = (
    "CHARACTER", "SHARED", "RELATIONSHIP", "INFORMATION", "OBJECT",
    "ENVIRONMENT", "NONE",
)

IR_TOP_LEVEL_FIELDS = (
    "scene_id", "schema_version", "dramatic_objective", "scene_question",
    "strategy_summary", "visual_thesis", "scene_phases", "spatial_expression",
    "prop_visual_strategy", "shot_architecture_guidance", "must_preserve",
    "must_avoid", "creative_risks",
)

PHASE_FIELDS = (
    "phase_id", "beat_ids", "dramatic_function", "audience_state", "emotion",
    "power", "performance", "edit", "visual", "information",
)

AUDIENCE_FIELDS = ("knows", "suspects", "withholds", "question_shift")
EMOTION_FIELDS = ("state", "trigger", "transition_reason", "intensity_hint")
POWER_FIELDS = ("center_type", "center_ref", "description", "shift")
PERFORMANCE_FIELDS = ("character_id", "objective", "tactic", "visible_behavior", "turning_point")
EDIT_FIELDS = ("tempo", "hold_logic", "cut_logic", "transition_motivation")
VISUAL_FIELDS = ("visual_grammar", "camera_rule", "composition_rule", "movement_condition")
INFORMATION_FIELDS = ("reveal", "hint", "withhold", "source_refs")

FORBIDDEN_IR_FIELDS = frozenset({
    "strategy_fingerprint", "creative_core_fingerprint", "dq_score", "cv_score",
    "quality_score", "shots", "shot_ids", "plan_shot_id", "duration_ladder",
    "patches", "canonical_patch_path", "repair", "shot_plan", "shotplan",
})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_beat_alias_table(beat_ids: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Build aliases solely from the authoritative beat sequence.

    Aliases are accepted only when one alias maps to exactly one canonical ID.
    No scene-specific hand-written mappings are allowed.
    """
    canonical = [_text(item) for item in beat_ids if _text(item)]
    candidates: dict[str, set[str]] = {}
    for beat_id in canonical:
        raw = beat_id
        compact = raw.replace("_", "").replace("-", "").replace(" ", "")
        aliases = {raw, raw.lower(), raw.upper()}
        match = re.fullmatch(r"[Bb](\d+)", compact)
        if match:
            n = int(match.group(1))
            aliases.update({str(n), f"B{n}", f"b{n}", f"B{n:02d}", f"b{n:02d}", f"{n:02d}"})
        elif compact.isdigit():
            n = int(compact)
            aliases.update({str(n), f"B{n}", f"b{n}", f"B{n:02d}", f"b{n:02d}", f"{n:02d}"})
        for alias in aliases:
            candidates.setdefault(alias, set()).add(raw)
    aliases_out = {}
    ambiguous = []
    for alias in sorted(candidates):
        values = sorted(candidates[alias])
        aliases_out[alias] = values[0] if len(values) == 1 else None
        if len(values) > 1:
            ambiguous.append(alias)
    return {
        "canonical_beat_ids": canonical,
        "aliases": aliases_out,
        "ambiguous_aliases": ambiguous,
        "normalization_policy": "accept only one-to-one aliases; reject ambiguous aliases",
    }


def normalize_beat_id(value: Any, alias_table: dict[str, Any]) -> str | None:
    alias = _text(value)
    if not alias:
        return None
    canonical = _dict(alias_table.get("aliases")).get(alias)
    if canonical is None:
        return None
    return _text(canonical)


def semantic_spec() -> dict[str, Any]:
    """Return the JSON-serializable SSOT document."""
    return {
        "schema_version": SEMANTIC_SPEC_VERSION,
        "model_ir_schema_version": IR_SCHEMA_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "top_level_fields": list(IR_TOP_LEVEL_FIELDS),
        "phase_fields": list(PHASE_FIELDS),
        "nested_fields": {
            "audience_state": list(AUDIENCE_FIELDS), "emotion": list(EMOTION_FIELDS),
            "power": list(POWER_FIELDS), "performance": list(PERFORMANCE_FIELDS),
            "edit": list(EDIT_FIELDS), "visual": list(VISUAL_FIELDS),
            "information": list(INFORMATION_FIELDS),
        },
        "phase_constraints": {"minimum": 2, "maximum": 6, "recommended_minimum": 3, "recommended_maximum": 5, "beat_assignment": "exactly_once"},
        "power_center_types": list(POWER_CENTER_TYPES),
        "forbidden_model_fields": sorted(FORBIDDEN_IR_FIELDS),
        "na_rules": {
            "prop_visual_strategy": "N/A when no authoritative prop exists",
            "power": "center_type NONE and center_ref null when unsupported",
            "object_power": "center_ref may be null when no canonical prop ID exists; description must cite source evidence",
        },
        "authority_rules": {
            "source_facts": ["scene identity", "beats", "dialogue", "chronology", "character identity", "asset identity"],
            "treatment_intent": ["dramatic objective", "tone", "intent"],
            "blocking_facts": ["spatial truth", "entry/exit", "screen direction", "continuity"],
            "creative_decision": ["phases", "audience state", "emotion", "power", "performance", "edit", "visual"],
        },
    }


def build_provider_skeleton(*, scene_id: str, beat_ids: list[str], character_ids: list[str], fact_ids: list[str] | None = None) -> dict[str, Any]:
    """Build the minimal provider-facing typed skeleton from the SSOT."""
    alias_table = build_beat_alias_table(beat_ids)
    phase = {
        "phase_id": "P01", "beat_ids": [beat_ids[0]] if beat_ids else [],
        "dramatic_function": "", "audience_state": {key: [] for key in AUDIENCE_FIELDS},
        "emotion": {"state": "", "trigger": "", "transition_reason": "", "intensity_hint": None},
        "power": {"center_type": "NONE", "center_ref": None, "description": "", "shift": ""},
        "performance": [{"character_id": character_ids[0] if character_ids else "", "objective": "", "tactic": "", "visible_behavior": "", "turning_point": False}],
        "edit": {key: "" for key in EDIT_FIELDS},
        "visual": {key: "" for key in VISUAL_FIELDS},
        "information": {"reveal": [], "hint": [], "withhold": [], "source_refs": list(fact_ids or [])},
    }
    return {
        "schema_version": IR_SCHEMA_VERSION, "scene_id": _text(scene_id),
        "allowed_beat_ids": [_text(item) for item in beat_ids],
        "beat_alias_table": alias_table, "allowed_character_ids": sorted({_text(item) for item in character_ids if _text(item)}),
        "allowed_fact_ids": sorted({_text(item) for item in (fact_ids or []) if _text(item)}),
        "phase_constraints": {"min": 2, "max": 6, "recommended": "3-5", "beat_assignment": "exactly_once"},
        "field_shapes": semantic_spec()["nested_fields"],
        "power_center_types": list(POWER_CENTER_TYPES), "na_rules": semantic_spec()["na_rules"],
        "minimal_skeleton": {key: [] if key in {"spatial_expression", "prop_visual_strategy", "must_preserve", "must_avoid", "creative_risks"} else ("" if key not in {"scene_phases"} else [phase]) for key in IR_TOP_LEVEL_FIELDS},
    }


__all__ = [
    "SEMANTIC_SPEC_VERSION", "IR_SCHEMA_VERSION", "CANONICAL_SCHEMA_VERSION", "COMPILER_VERSION",
    "POWER_CENTER_TYPES", "IR_TOP_LEVEL_FIELDS", "PHASE_FIELDS", "FORBIDDEN_IR_FIELDS",
    "semantic_spec", "build_beat_alias_table", "normalize_beat_id", "build_provider_skeleton",
]
