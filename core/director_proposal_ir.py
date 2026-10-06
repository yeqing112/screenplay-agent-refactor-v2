"""Flat, provider-facing Director proposal IR and its deterministic compiler.

The provider is allowed to suggest creative semantics only.  This module is
the boundary that validates those suggestions, copies immutable source facts
from the local preview, and compiles the proposal into the existing V3
DirectorTreatment contract.  It deliberately contains no model calls and no
repair heuristics.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from core.director_source_grounded import (
    DIRECTOR_CREATIVE_AUTHORITY,
    validate_director_contract_v2,
    project_source_authoring_units,
)


DIRECTOR_PROPOSAL_IR_VERSION = "director_proposal_ir_v1"

TOP_LEVEL_FIELDS = {
    "version", "scene_label", "scene_objective", "dramatic_question", "beats",
    "character_directions", "performance_arc", "information_strategy",
    "rhythm_strategy", "visual_priority", "scene_exit_intent",
    "prohibited_interpretations", "passthrough_refs", "unknowns", "confidence", "note",
}
BEAT_FIELDS = {
    "refs", "purpose", "objective", "information_change", "audience_effect",
    "performance", "transition", "hook", "character_effects",
}
CHARACTER_EFFECT_FIELDS = {"character_ref", "effect"}
# ``direction`` is the compact provider-facing shorthand used by the MiMo
# canary.  It carries the same creative intent as the more decomposed
# objective/obstacle/strategy/performance_notes fields and is copied without
# local interpretation by the deterministic compiler.
CHARACTER_DIRECTION_FIELDS = {"character_ref", "objective", "obstacle", "strategy", "performance_notes", "direction"}
FORBIDDEN_FIELDS = {
    "creative_projection", "creative_beat_id", "authority", "source_constraints",
    "source_authoring_units", "scene_identity_evidence", "declared_participants",
    "proposal_origin", "proposal_provenance", "authority_envelope", "dialogue",
    "speaker", "binding", "speaker_binding",
}

BEAT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(BEAT_FIELDS),
    "properties": {
        "refs": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "purpose": {"type": "string"},
        "objective": {"type": "string"},
        "information_change": {"type": "string"},
        "audience_effect": {"type": "string"},
        "performance": {"type": "string"},
        "transition": {"type": "string"},
        "hook": {"type": "boolean"},
        "character_effects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(CHARACTER_EFFECT_FIELDS),
                "properties": {"character_ref": {"type": "string"}, "effect": {"type": "string"}},
            },
        },
    },
}


DIRECTOR_PROPOSAL_IR_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DirectorProposalIR v1",
    "type": "object",
    "additionalProperties": False,
    "required": sorted(TOP_LEVEL_FIELDS),
    "properties": {
        "version": {"const": DIRECTOR_PROPOSAL_IR_VERSION},
        "scene_label": {"type": "string"},
        "scene_objective": {"type": "string"},
        "dramatic_question": {"type": "string"},
        "beats": {"type": "array", "items": BEAT_JSON_SCHEMA},
        "character_directions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["character_ref"],
                "properties": {
                    "character_ref": {"type": "string"},
                    "objective": {"type": "string"},
                    "obstacle": {"type": "string"},
                    "strategy": {"type": "string"},
                    "performance_notes": {"type": "string"},
                    "direction": {"type": "string"},
                },
            },
        },
        "performance_arc": {"type": "array"},
        "information_strategy": {"type": "array"},
        "rhythm_strategy": {"type": "object"},
        "visual_priority": {"type": "array"},
        "scene_exit_intent": {"type": "string"},
        "prohibited_interpretations": {"type": "array"},
        "passthrough_refs": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array"},
        "confidence": {"type": ["number", "string"]},
        "note": {"type": "string"},
    },
    "beat_fields": sorted(BEAT_FIELDS),
    "character_effect_fields": sorted(CHARACTER_EFFECT_FIELDS),
    "character_direction_fields": sorted(CHARACTER_DIRECTION_FIELDS),
    "forbidden_fields": sorted(FORBIDDEN_FIELDS),
}


class DirectorProposalIRValidationError(ValueError):
    """Raised when a provider proposal is not safe to compile."""

    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__(json.dumps(report, ensure_ascii=False, sort_keys=True))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_scalar_text(value: Any) -> bool:
    return isinstance(value, str)


def _participant_refs(scene: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in _list(scene.get("participants")):
        if isinstance(item, Mapping):
            for key in ("id", "character_id", "name", "character_ref"):
                value = _text(item.get(key))
                if value:
                    result.add(value)
        else:
            value = _text(item)
            if value:
                result.add(value)
    return result


def _forbidden_nested_fields(value: Any, path: str = "") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_FIELDS:
                found.append({"field": key_text, "path": child_path})
            found.extend(_forbidden_nested_fields(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_nested_fields(item, f"{path}[{index}]"))
    return found


def validate_director_proposal_ir(
    ir: Any,
    *,
    source_units: list[dict[str, Any]],
    declared_participants: list[Any] | None = None,
) -> dict[str, Any]:
    """Validate the flat IR without changing it or filling omissions."""

    errors: list[dict[str, Any]] = []
    if not isinstance(ir, Mapping):
        return {"status": "blocked", "errors": [{"code": "DIRECTOR_PROPOSAL_IR_SCHEMA_INVALID"}], "warnings": []}

    unexpected = sorted(set(ir) - TOP_LEVEL_FIELDS)
    forbidden = sorted(set(ir) & FORBIDDEN_FIELDS)
    if unexpected:
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_FIELD_UNEXPECTED", "fields": unexpected})
    if forbidden:
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_FORBIDDEN_FIELD", "fields": forbidden})
    nested_forbidden = _forbidden_nested_fields(ir)
    if nested_forbidden:
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_FORBIDDEN_FIELD", "fields": nested_forbidden})
    required_missing = sorted(field for field in TOP_LEVEL_FIELDS if field not in ir)
    if required_missing:
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_FIELD_REQUIRED", "fields": required_missing})
    if _text(ir.get("version")) != DIRECTOR_PROPOSAL_IR_VERSION:
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_VERSION_INVALID"})

    by_id = {_text(unit.get("unit_id")): unit for unit in source_units if isinstance(unit, Mapping) and _text(unit.get("unit_id"))}
    covered: set[str] = set()
    beats = ir.get("beats")
    if not isinstance(beats, list):
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_BEATS_INVALID"})
        beats = []
    semantic_fields_in = 0
    participant_set = _participant_refs({"participants": declared_participants or []})
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat, Mapping):
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_BEAT_INVALID", "ordinal": index})
            continue
        beat_unexpected = sorted(set(beat) - BEAT_FIELDS)
        if beat_unexpected:
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_BEAT_FIELD_UNEXPECTED", "ordinal": index, "fields": beat_unexpected})
        refs = beat.get("refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not _text(ref) for ref in refs):
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_BEAT_REFS_REQUIRED", "ordinal": index})
            refs = []
        for ref in refs:
            ref_text = _text(ref)
            if ref_text not in by_id:
                errors.append({"code": "DIRECTOR_PROPOSAL_IR_SOURCE_REF_INVALID", "unit_ref": ref_text})
            else:
                covered.add(ref_text)
        for field in ("purpose", "objective", "information_change", "audience_effect", "performance", "transition"):
            if field not in beat or not _is_scalar_text(beat.get(field)):
                errors.append({"code": "DIRECTOR_PROPOSAL_IR_BEAT_FIELD_REQUIRED", "ordinal": index, "field": field})
            else:
                semantic_fields_in += 1
        if "hook" not in beat or not isinstance(beat.get("hook"), bool):
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_BEAT_FIELD_REQUIRED", "ordinal": index, "field": "hook"})
        else:
            semantic_fields_in += 1
        effects = beat.get("character_effects")
        if not isinstance(effects, list):
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_CHARACTER_EFFECTS_INVALID", "ordinal": index})
            effects = []
        for effect in effects:
            if not isinstance(effect, Mapping) or sorted(effect) != sorted(CHARACTER_EFFECT_FIELDS) or not _text(effect.get("character_ref")) or not _is_scalar_text(effect.get("effect")):
                errors.append({"code": "DIRECTOR_PROPOSAL_IR_CHARACTER_EFFECT_INVALID", "ordinal": index})
                continue
            ref = _text(effect.get("character_ref"))
            if ref not in participant_set:
                errors.append({"code": "DIRECTOR_PROPOSAL_IR_PARTICIPANT_INVALID", "participant_ref": ref})

    passthrough = ir.get("passthrough_refs")
    if not isinstance(passthrough, list):
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_PASSTHROUGH_INVALID"})
        passthrough = []
    for ref in passthrough:
        ref_text = _text(ref)
        if not isinstance(ref, str) or not ref_text or ref_text not in by_id:
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_SOURCE_REF_INVALID", "unit_ref": ref_text})
        else:
            covered.add(ref_text)

    # Character directions are creative semantics, but references must remain
    # within the source participant contract.
    directions = ir.get("character_directions")
    if not isinstance(directions, list):
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_CHARACTER_DIRECTIONS_INVALID"})
        directions = []
    for direction in directions:
        if not isinstance(direction, Mapping):
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_PARTICIPANT_INVALID"})
            continue
        direction_unexpected = sorted(set(direction) - CHARACTER_DIRECTION_FIELDS)
        if direction_unexpected:
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_CHARACTER_DIRECTION_FIELD_UNEXPECTED", "fields": direction_unexpected})
        ref = _text(direction.get("character_ref"))
        if not ref:
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_CHARACTER_DIRECTION_REF_REQUIRED"})
        elif ref not in participant_set:
            errors.append({"code": "DIRECTOR_PROPOSAL_IR_PARTICIPANT_INVALID", "participant_ref": ref})
        for field in set(direction) & (CHARACTER_DIRECTION_FIELDS - {"character_ref"}):
            if not isinstance(direction.get(field), str):
                errors.append({"code": "DIRECTOR_PROPOSAL_IR_CHARACTER_DIRECTION_FIELD_INVALID", "field": field})

    missing = sorted(set(by_id) - covered)
    if missing:
        errors.append({"code": "DIRECTOR_PROPOSAL_IR_SOURCE_COVERAGE_INCOMPLETE", "missing_unit_refs": missing})
    return {
        "status": "qualified" if not errors else "blocked",
        "errors": errors,
        "warnings": [],
        "version": DIRECTOR_PROPOSAL_IR_VERSION,
        "source_unit_count": len(by_id),
        "covered_source_unit_count": len(covered & set(by_id)),
        "creative_beat_count": len(beats),
        "passthrough_count": len(passthrough),
        "semantic_fields_in": semantic_fields_in,
        "forbidden_field_count": len(forbidden),
    }


def validate_director_proposal_ir_schema(value: Any) -> dict[str, Any]:
    """Small dependency-free JSON Schema 2020-12 subset used by the audit.

    The emitted schema remains the contract of record; this evaluator handles
    the keywords used by that schema so runtime tests can run without adding a
    third-party dependency to the application.
    """
    errors: list[dict[str, Any]] = []

    def check(item: Any, schema: Mapping[str, Any], path: str) -> None:
        wanted = schema.get("type")
        if wanted:
            types = wanted if isinstance(wanted, list) else [wanted]
            ok = any((kind == "object" and isinstance(item, Mapping)) or (kind == "array" and isinstance(item, list)) or (kind == "string" and isinstance(item, str)) or (kind == "boolean" and isinstance(item, bool)) or (kind == "number" and isinstance(item, (int, float)) and not isinstance(item, bool)) for kind in types)
            if not ok:
                errors.append({"path": path, "code": "SCHEMA_TYPE_INVALID", "expected": wanted}); return
        if "const" in schema and item != schema["const"]:
            errors.append({"path": path, "code": "SCHEMA_CONST_INVALID"})
        if isinstance(item, Mapping):
            required = schema.get("required", [])
            for key in required:
                if key not in item:
                    errors.append({"path": path, "code": "SCHEMA_REQUIRED_FIELD_MISSING", "field": key})
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                for key in item:
                    if key not in properties:
                        errors.append({"path": path, "code": "SCHEMA_ADDITIONAL_PROPERTY", "field": key})
            for key, child in properties.items():
                if key in item:
                    check(item[key], child, f"{path}.{key}")
        elif isinstance(item, list):
            if isinstance(schema.get("minItems"), int) and len(item) < schema["minItems"]:
                errors.append({"path": path, "code": "SCHEMA_MIN_ITEMS"})
            if isinstance(schema.get("items"), Mapping):
                for index, child in enumerate(item):
                    check(child, schema["items"], f"{path}[{index}]")

    check(value, DIRECTOR_PROPOSAL_IR_SCHEMA, "$")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def parse_director_proposal_ir(raw: str) -> dict[str, Any]:
    """Parse exactly once; malformed historical JSON must remain malformed."""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Director ProposalIR V1 is empty")
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        # Deliberately do not extract balanced fragments or repair brackets.
        raise ValueError(f"Failed to parse Director ProposalIR V1: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Director ProposalIR V1 is not a JSON object")
    if "version" not in payload or "beats" not in payload:
        raise ValueError("Director ProposalIR V1 is missing required keys: version, beats")
    return payload


def compile_director_proposal_ir(
    ir: dict[str, Any],
    baseline_treatment: dict[str, Any],
    source_scene: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a valid IR into the existing V3 contract deterministically."""

    units = project_source_authoring_units(source_scene)
    constraints = baseline_treatment.get("source_constraints") if isinstance(baseline_treatment.get("source_constraints"), Mapping) else {}
    report = validate_director_proposal_ir(ir, source_units=units, declared_participants=source_scene.get("participants", []))
    if report["status"] != "qualified":
        raise DirectorProposalIRValidationError(report)
    if not constraints or constraints.get("source_authoring_units") != units:
        raise DirectorProposalIRValidationError({"status": "blocked", "errors": [{"code": "DIRECTOR_PROPOSAL_IR_BASELINE_SOURCE_MISMATCH"}]})

    beats: list[dict[str, Any]] = []
    for ordinal, item in enumerate(ir["beats"], start=1):
        effects = [{"character_ref": effect["character_ref"], "effect": effect["effect"]} for effect in item.get("character_effects", [])]
        beats.append({
            "creative_beat_id": f"DCB_{_text(source_scene.get('scene_id'))}_{ordinal:03d}",
            "authority": DIRECTOR_CREATIVE_AUTHORITY,
            "derived_from_source_unit_refs": list(item["refs"]),
            "dramatic_purpose": item["purpose"],
            "director_objective": item["objective"],
            "information_change": item["information_change"],
            "audience_effect": item["audience_effect"],
            "character_effects": effects,
            "performance_intent": item["performance"],
            "transition_intent": item["transition"],
            "hook_intent": item["hook"],
        })
    directions = copy.deepcopy(ir["character_directions"])
    projection = {
        # Compilation creates a reviewable proposal.  Confirmation is owned
        # exclusively by the explicit production confirmation service.
        "status": "PROPOSED",
        "authority": DIRECTOR_CREATIVE_AUTHORITY,
        "director_scene_label": ir["scene_label"],
        "director_scene_label_authority": DIRECTOR_CREATIVE_AUTHORITY,
        "scene_objective": ir["scene_objective"],
        "dramatic_question": ir["dramatic_question"],
        "creative_beats": beats,
        "explicit_passthrough_unit_refs": list(ir["passthrough_refs"]),
        "character_directions": directions,
        "performance_arc": copy.deepcopy(ir["performance_arc"]),
        "information_strategy": copy.deepcopy(ir["information_strategy"]),
        "rhythm_strategy": copy.deepcopy(ir["rhythm_strategy"]),
        "visual_priority": copy.deepcopy(ir["visual_priority"]),
        "scene_exit_intent": ir["scene_exit_intent"],
        "prohibited_interpretations": copy.deepcopy(ir["prohibited_interpretations"]),
    }
    candidate = {
        "schema_version": "director_treatment_v3",
        "scene_id": _text(baseline_treatment.get("scene_id") or source_scene.get("scene_id")),
        "scene_name": "",
        "source_constraints": copy.deepcopy(constraints),
        "creative_projection": projection,
        "unknowns": copy.deepcopy(ir["unknowns"]),
        "decision": "ready_for_review",
        "confidence": ir["confidence"],
        "human_confirmation_required": True,
        "note": ir["note"],
    }
    semantic_out = report["semantic_fields_in"]
    candidate_report = validate_director_contract_v2(candidate, scene=source_scene, production=False)
    if candidate_report.get("status") != "qualified":
        raise DirectorProposalIRValidationError({"status": "blocked", "errors": [{"code": "DIRECTOR_PROPOSAL_IR_COMPILED_CANDIDATE_INVALID", "validation": candidate_report}]})
    candidate["proposal_ir_validation"] = report
    candidate["compiler_report"] = {
        "compiler": "director_proposal_ir_v1_deterministic",
        "local_ids": [beat["creative_beat_id"] for beat in beats],
        "local_authority": DIRECTOR_CREATIVE_AUTHORITY,
        "source_constraints": "copied_from_baseline",
        "semantic_fields_in": semantic_out,
        "semantic_fields_out": semantic_out,
        "local_compiler_new_creative_decision_count": 0,
        "compiled_contract_validation": candidate_report,
    }
    return candidate


def creative_semantic_diff(before_candidate: Mapping[str, Any], after_candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Compare creative meaning while ignoring confirmation metadata only."""
    ignored = {"status", "confirmation_event_ref", "proposal_origin", "proposal_provenance", "authority", "creative_beat_id"}

    def strip(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): strip(v) for k, v in value.items() if str(k) not in ignored}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value

    before = strip((before_candidate.get("creative_projection") if isinstance(before_candidate, Mapping) else {}) or {})
    after = strip((after_candidate.get("creative_projection") if isinstance(after_candidate, Mapping) else {}) or {})
    return {"creative_semantic_change_count": 0 if before == after else 1, "before_sha256": _sha256_json(before), "after_sha256": _sha256_json(after), "equal": before == after}


def _sha256_json(value: Any) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


__all__ = [
    "DIRECTOR_PROPOSAL_IR_VERSION", "DIRECTOR_PROPOSAL_IR_SCHEMA", "DirectorProposalIRValidationError",
    "validate_director_proposal_ir", "validate_director_proposal_ir_schema", "parse_director_proposal_ir", "compile_director_proposal_ir",
    "creative_semantic_diff",
]
