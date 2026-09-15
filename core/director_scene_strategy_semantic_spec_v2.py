"""Semantic SSOT for Director Quality V3 Phase 1.3.

The v2 provider IR is intentionally shape-tolerant while the canonical v3
representation is strict.  Source references, rather than natural-language
matching, are the only authority for factual grounding.
"""
from __future__ import annotations

import copy
import re
from typing import Any

SEMANTIC_SPEC_VERSION = "director_scene_strategy_semantic_spec_v2"
IR_SCHEMA_VERSION = "director_scene_strategy_ir_v2"
CANONICAL_SCHEMA_VERSION = "director_scene_strategy_v3"
COMPILER_VERSION = "director_scene_strategy_ir_compiler_v2"

POWER_CENTER_TYPES = ("CHARACTER", "SHARED", "RELATIONSHIP", "INFORMATION", "OBJECT", "ENVIRONMENT", "NONE")
TOP_LEVEL_FIELDS = ("schema_version", "scene_id", "dramatic_objective", "scene_question", "strategy_summary", "visual_thesis", "scene_phases", "spatial_expression", "prop_visual_strategy", "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks")
PHASE_FIELDS = ("phase_id", "beat_ids", "dramatic_function", "audience_state", "emotion", "power", "performance", "edit", "visual", "information")
FLEXIBLE_LIST_FIELDS = ("spatial_expression", "prop_visual_strategy", "shot_architecture_guidance", "must_preserve", "must_avoid", "creative_risks")
INFORMATION_FIELDS = ("reveal_refs", "hint_refs", "withhold_refs", "audience_suspicions", "director_inferences")
EPISTEMIC_TYPES = ("SOURCE_FACT", "DIRECTOR_INFERENCE", "AUDIENCE_SUSPICION", "TREATMENT_INTENT", "BLOCKING_FACT", "DIRECTOR_CREATIVE_DECISION")
FORBIDDEN_MODEL_FIELDS = frozenset({"strategy_fingerprint", "creative_core_fingerprint", "dq_score", "cv_score", "quality_score", "shots", "shot_ids", "plan_shot_id", "duration_ladder", "patches", "repair", "shot_plan", "shotplan", "source_fact", "source_facts", "fact_claim"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_beat_alias_table(beat_ids: list[str] | tuple[str, ...]) -> dict[str, Any]:
    canonical = [_text(x) for x in beat_ids if _text(x)]
    candidates: dict[str, set[str]] = {}
    for beat in canonical:
        compact = beat.replace("_", "").replace("-", "").replace(" ", "")
        aliases = {beat, beat.lower(), beat.upper()}
        match = re.fullmatch(r"[Bb]?(\d+)", compact)
        if match:
            n = int(match.group(1)); aliases.update({str(n), f"B{n}", f"b{n}", f"B{n:02d}", f"b{n:02d}", f"{n:02d}", f"beat:{n}"})
        for alias in aliases:
            candidates.setdefault(alias, set()).add(beat)
    aliases: dict[str, str | None] = {}; ambiguous: list[str] = []
    for alias, values in sorted(candidates.items()):
        aliases[alias] = next(iter(values)) if len(values) == 1 else None
        if len(values) > 1: ambiguous.append(alias)
    return {"canonical_beat_ids": canonical, "aliases": aliases, "ambiguous_aliases": ambiguous, "normalization_policy": "one-to-one aliases only"}


def normalize_beat_id(value: Any, alias_table: dict[str, Any]) -> str | None:
    raw = _text(value)
    if raw.startswith("beat:"):
        raw = raw[5:]
    return _text(_dict(alias_table.get("aliases")).get(raw)) or None


def build_source_ref_contract(*, beat_ids: list[str], fact_ids: list[str] | None = None, character_ids: list[str] | None = None, prop_ids: list[str] | None = None, location_ids: list[str] | None = None) -> dict[str, Any]:
    beats = [_text(x) for x in beat_ids if _text(x)]
    values = {"beat": beats, "fact": [_text(x) for x in (fact_ids or []) if _text(x)], "character": [_text(x) for x in (character_ids or []) if _text(x)], "prop": [_text(x) for x in (prop_ids or []) if _text(x)], "location": [_text(x) for x in (location_ids or []) if _text(x)]}
    refs = [f"{kind}:{item}" for kind, ids in values.items() for item in ids]
    return {"schema_version": "director_source_ref_contract_v2", "allowed_ids": values, "allowed_source_refs": refs, "syntax": "<type>:<authoritative_id>", "beat_alias_table": build_beat_alias_table(beats), "types": ["beat", "fact", "prop", "character", "location"]}


def semantic_spec() -> dict[str, Any]:
    return {"schema_version": SEMANTIC_SPEC_VERSION, "model_ir_schema_version": IR_SCHEMA_VERSION, "canonical_schema_version": CANONICAL_SCHEMA_VERSION, "compiler_version": COMPILER_VERSION, "top_level_fields": list(TOP_LEVEL_FIELDS), "phase_fields": list(PHASE_FIELDS), "flexible_list_fields": list(FLEXIBLE_LIST_FIELDS), "information_fields": list(INFORMATION_FIELDS), "epistemic_types": list(EPISTEMIC_TYPES), "power_center_types": list(POWER_CENTER_TYPES), "forbidden_model_fields": sorted(FORBIDDEN_MODEL_FIELDS), "phase_constraints": {"minimum": 2, "maximum": 6, "recommended": "3-5", "beat_assignment": "exactly_once"}, "information_policy": {"reference_first": True, "reveal_refs": "source refs visible by this phase", "hint_refs": "already available evidence only", "withhold_refs": "future evidence allowed", "audience_suspicions": "interpretive claims with support_refs", "director_inferences": "directing interpretations with support_refs and purpose"}, "epistemic_boundary": {"SOURCE_FACT": "authoritative upstream only", "DIRECTOR_INFERENCE": "director interpretation, never a fact", "AUDIENCE_SUSPICION": "audience hypothesis, never a fact", "TREATMENT_INTENT": "approved intent", "BLOCKING_FACT": "approved spatial truth", "DIRECTOR_CREATIVE_DECISION": "staging decision"}, "na_rules": {"prop_visual_strategy": "N/A or null normalizes to [] when no prop evidence exists", "source_refs": "never invent IDs"}}


def build_provider_skeleton(*, scene_id: str, beat_ids: list[str], character_ids: list[str], fact_ids: list[str] | None = None, prop_ids: list[str] | None = None, location_ids: list[str] | None = None, runtime_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    from core.director_scene_strategy import canonicalize_allowed_characters
    source_refs = _dict(runtime_contract).get("source_ref_contract") if isinstance(runtime_contract, dict) else None
    if not isinstance(source_refs, dict):
        source_refs = build_source_ref_contract(beat_ids=beat_ids, fact_ids=fact_ids, character_ids=character_ids, prop_ids=prop_ids, location_ids=location_ids)
    source_contract = _dict(runtime_contract)
    beat_source = (source_contract.get("beat_ids") or beat_ids) if isinstance(runtime_contract, dict) else beat_ids
    character_source = (source_contract.get("character_ids") or character_ids) if isinstance(runtime_contract, dict) else character_ids
    beat_ids = [_text(x) for x in beat_source]
    character_ids = [_text(x) for x in character_source]
    phase = {"phase_id": "P01", "beat_ids": [], "dramatic_function": "", "audience_state": {"knows": [], "suspects": [], "withholds": [], "question_shift": ""}, "emotion": {"state": "", "trigger": "", "transition_reason": "", "intensity_hint": None}, "power": {"center_type": "NONE", "center_ref": None, "description": "", "shift": ""}, "performance": [{"character_id": character_ids[0] if character_ids else "", "objective": "", "tactic": "", "visible_behavior": "", "turning_point": False}], "edit": {"tempo": "", "hold_logic": "", "cut_logic": "", "transition_motivation": ""}, "visual": {"visual_grammar": "", "camera_rule": "", "composition_rule": "", "movement_condition": ""}, "information": {key: [] for key in INFORMATION_FIELDS}}
    allowed_characters = canonicalize_allowed_characters(_dict(runtime_contract).get("allowed_characters"), book_id=_dict(runtime_contract).get("book_id")) if isinstance(runtime_contract, dict) else []
    return {"schema_version": IR_SCHEMA_VERSION, "scene_id": _text(scene_id), "allowed_beat_ids": [_text(x) for x in beat_ids], "allowed_character_ids": sorted({_text(x) for x in character_ids if _text(x)}), "allowed_characters": allowed_characters, "source_ref_contract": source_refs, "allowed_source_refs": source_refs["allowed_source_refs"], "phase_constraints": {"min": 2, "max": 6, "recommended": "3-5", "beat_assignment": "exactly_once"}, "flexible_shape_policy": {field: ["string", "string[]", "null"] for field in FLEXIBLE_LIST_FIELDS}, "information_schema": {key: "source_ref[]" if key.endswith("_refs") else "claim[]" for key in INFORMATION_FIELDS}, "epistemic_rules": semantic_spec()["epistemic_boundary"], "minimal_skeleton": {**{key: "" for key in TOP_LEVEL_FIELDS if key not in FLEXIBLE_LIST_FIELDS + ("scene_phases",)}, **{field: [] for field in FLEXIBLE_LIST_FIELDS}, "scene_phases": [phase]}}


__all__ = ["SEMANTIC_SPEC_VERSION", "IR_SCHEMA_VERSION", "CANONICAL_SCHEMA_VERSION", "COMPILER_VERSION", "TOP_LEVEL_FIELDS", "PHASE_FIELDS", "FLEXIBLE_LIST_FIELDS", "INFORMATION_FIELDS", "POWER_CENTER_TYPES", "FORBIDDEN_MODEL_FIELDS", "semantic_spec", "build_source_ref_contract", "build_beat_alias_table", "normalize_beat_id", "build_provider_skeleton"]
