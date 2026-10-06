"""Two-stage Director authoring contracts.

Stage A groups immutable source units into a dramatic beat plan.  Stage B adds
performance and audience-facing enrichment to those already validated beats.
The module is deliberately provider-free: it validates and deterministically
merges proposals, but never invents missing creative text.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from core.director_source_grounded import DIRECTOR_CREATIVE_AUTHORITY


DIRECTOR_BEAT_PLAN_IR_VERSION = "director_beat_plan_ir_v1"
DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION = "director_creative_enrichment_ir_v1"

STAGE_A_BEAT_FIELDS = {"refs", "purpose", "objective", "information_change", "hook"}
STAGE_A_TOP_LEVEL_FIELDS = {
    "version", "scene_label", "scene_objective", "dramatic_question", "beats",
    "passthrough_refs", "unknowns", "confidence", "note",
}
STAGE_B_ENRICHMENT_FIELDS = {"beat_ref", "audience_effect", "performance", "transition", "character_effects"}
STAGE_B_TOP_LEVEL_FIELDS = {
    "version", "beat_enrichments", "character_directions", "performance_arc",
    "information_strategy", "rhythm_strategy", "visual_priority",
    "scene_exit_intent", "prohibited_interpretations", "confidence", "note",
}
CHARACTER_DIRECTION_FIELDS = {"character_ref", "direction", "objective", "obstacle", "strategy", "performance_notes"}
CHARACTER_EFFECT_FIELDS = {"character_ref", "effect"}


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
    "required": sorted(STAGE_B_TOP_LEVEL_FIELDS),
    "properties": {
        "version": {"const": DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION},
        "beat_enrichments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": sorted(STAGE_B_ENRICHMENT_FIELDS),
            "properties": {
                "beat_ref": {"type": "string"},
                "audience_effect": {"type": "string"},
                "performance": {"type": "string"},
                "transition": {"type": "string"},
                "character_effects": {"type": "array"},
            },
        }},
        "character_directions": {"type": "array"},
        "performance_arc": {"type": "array"},
        "information_strategy": {"type": "array"},
        "rhythm_strategy": {"type": "object"},
        "visual_priority": {"type": "array"},
        "scene_exit_intent": {"type": "string"},
        "prohibited_interpretations": {"type": "array"},
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


def validate_director_beat_plan_ir_schema(value: Any) -> dict[str, Any]:
    errors = _schema_check(value, DIRECTOR_BEAT_PLAN_IR_SCHEMA)
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "version": DIRECTOR_BEAT_PLAN_IR_VERSION}


def validate_director_creative_enrichment_ir_schema(value: Any) -> dict[str, Any]:
    errors = _schema_check(value, DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA)
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "version": DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION}


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
        for enrichment in value.get("beat_enrichments", []) if isinstance(value.get("beat_enrichments"), list) else []:
            if not isinstance(enrichment, Mapping):
                continue
            ref = _text(enrichment.get("beat_ref")); seen.append(ref)
            if ref not in beat_set:
                errors.append({"code": "DIRECTOR_ENRICHMENT_BEAT_REF_UNKNOWN", "beat_ref": ref})
            effects = enrichment.get("character_effects") if isinstance(enrichment.get("character_effects"), list) else []
            for effect in effects:
                if not isinstance(effect, Mapping) or set(effect) != CHARACTER_EFFECT_FIELDS or not _text(effect.get("character_ref")) or not isinstance(effect.get("effect"), str):
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


def compile_progressive_director_proposal(*, beat_plan_ir: Mapping[str, Any], enrichment_ir: Mapping[str, Any], baseline_treatment: Mapping[str, Any], source_scene: Mapping[str, Any]) -> dict[str, Any]:
    """Merge two validated proposals without creating new creative semantics."""

    source_units = (baseline_treatment.get("source_constraints") or {}).get("source_authoring_units", [])
    stage_a = validate_director_beat_plan_ir(beat_plan_ir, source_units=source_units)
    if stage_a["status"] != "qualified":
        raise ValueError({"code": "DIRECTOR_BEAT_PLAN_IR_INVALID", "report": stage_a})
    materialized = materialize_director_beat_plan_ids(beat_plan_ir, scene_id=_text(source_scene.get("scene_id") or baseline_treatment.get("scene_id")))
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


def build_stage_a_persistence_patch(*, ir: Mapping[str, Any], fingerprint: str, authorization_id: str, attempt_id: str) -> dict[str, Any]:
    """Return model_info-only state; never replaces DecisionPacket.proposal."""

    return {"progressive_director_authoring": {"stage_a": {"status": "VALIDATED", "ir": copy.deepcopy(dict(ir)), "fingerprint": str(fingerprint), "authorization_id": str(authorization_id), "attempt_id": str(attempt_id), "authoring_stage": "BEAT_PLAN"}}}


def build_director_beat_plan_prompt(*, scene_id: str, source_units: list[Mapping[str, Any]], declared_participants: list[Any] | None = None) -> tuple[str, str]:
    """Build the small Stage A prompt without any Stage B output burden."""

    system = "你是受来源约束的导演结构规划助手。只输出 director_beat_plan_ir_v1 JSON，不输出表演、镜头或人物表演语义。"
    user = (
        "DIRECTOR_BEAT_PLAN_IR_V1\n"
        f"SCENE_ID={json.dumps(scene_id, ensure_ascii=False)}\n"
        f"SOURCE_AUTHORING_UNITS={json.dumps(source_units, ensure_ascii=False, sort_keys=True)}\n"
        f"DECLARED_PARTICIPANTS={json.dumps(declared_participants or [], ensure_ascii=False, sort_keys=True)}\n"
        "REQUIRED_TOP_LEVEL_FIELDS=version,scene_label,scene_objective,dramatic_question,beats,passthrough_refs,unknowns,confidence,note\n"
        "REQUIRED_BEAT_FIELDS=refs,purpose,objective,information_change,hook\n"
        "禁止省略字段、增加字段、补写来源事实；所有 SAU 必须恰好出现在 beats[].refs 或 passthrough_refs。"
    )
    return system, user


def build_director_creative_enrichment_prompt(*, scene_id: str, beat_plan: Mapping[str, Any], declared_participants: list[Any] | None = None) -> tuple[str, str]:
    """Build the Stage B prompt over a validated local beat plan."""

    system = "你是受 Stage A 约束的导演表现层助手。只输出 director_creative_enrichment_ir_v1 JSON，不得重排或修改 Stage A。"
    user = (
        "DIRECTOR_CREATIVE_ENRICHMENT_IR_V1\n"
        f"SCENE_ID={json.dumps(scene_id, ensure_ascii=False)}\n"
        f"VALIDATED_BEAT_PLAN={json.dumps(beat_plan, ensure_ascii=False, sort_keys=True)}\n"
        f"DECLARED_PARTICIPANTS={json.dumps(declared_participants or [], ensure_ascii=False, sort_keys=True)}\n"
        "每个 DBP beat_ref 必须恰好有一个 beat_enrichment；只填写 audience_effect,performance,transition,character_effects。"
        "不得输出或修改 refs、purpose、objective、information_change、hook、scene_objective、dramatic_question。"
    )
    return system, user


__all__ = [
    "DIRECTOR_BEAT_PLAN_IR_VERSION", "DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION",
    "DIRECTOR_BEAT_PLAN_IR_SCHEMA", "DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA",
    "validate_director_beat_plan_ir_schema", "validate_director_beat_plan_ir",
    "materialize_director_beat_plan_ids", "validate_director_creative_enrichment_ir_schema",
    "validate_director_creative_enrichment_ir", "compile_progressive_director_proposal",
    "build_stage_a_persistence_patch", "build_director_beat_plan_prompt", "build_director_creative_enrichment_prompt",
]
