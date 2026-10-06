"""Source-grounded Director authoring primitives.

This module keeps the immutable ScriptIR source projection separate from
Director creative authoring.  It is deliberately provider-free: projecting
source units and validating a candidate never invents a beat, scene name,
character fact, dialogue, or transition.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping


SOURCE_AUTHORING_UNIT_SCHEMA_VERSION = "source_authoring_unit_v1"
DIRECTOR_TREATMENT_SCHEMA_VERSION_V3 = "director_treatment_v3"
DIRECTOR_CREATIVE_AUTHORITY = "AUTHORIZED_CREATIVE_PROJECTION"
SOURCE_BEAT_AUTHORITY = "SOURCE_TEXT"
SOURCE_UNIT_TYPES = frozenset({"SOURCE_BEAT", "SOURCE_ACTION", "SOURCE_DIALOGUE", "SOURCE_BLOCK"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def is_source_grounded_scene(scene: Mapping[str, Any] | None) -> bool:
    """Return true only for the V3.1 source-grounded scene shape."""

    if not isinstance(scene, Mapping):
        return False
    payload_version = _text(scene.get("source_grounded_schema_version"))
    return payload_version == "source_grounded_script_payload_v3_1" or (
        _text(scene.get("timeline_origin")).upper() == "SOURCE_GROUNDED"
        and "source_identity_evidence" in scene
        and not _text(scene.get("name"))
    )


def _evidence_refs(value: Any) -> list[str]:
    """Extract stable evidence IDs without copying creative semantics."""

    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            ref = _text(item.get("evidence_id") or item.get("anchor_ref"))
        else:
            ref = _text(item)
        if ref and ref not in result:
            result.append(ref)
    return result


def _unit_payload(scene: Mapping[str, Any], source_type: str, source_ref: str, source: Mapping[str, Any], order: int, unit_id: str) -> dict[str, Any]:
    evidence = source.get("source_evidence") if isinstance(source, Mapping) else None
    if source_type == "SOURCE_DIALOGUE":
        binding = source.get("speaker_binding") if isinstance(source.get("speaker_binding"), Mapping) else {}
        return {
            "unit_id": unit_id,
            "schema_version": SOURCE_AUTHORING_UNIT_SCHEMA_VERSION,
            "source_type": source_type,
            "source_ref": source_ref,
            "source_order": order,
            "source_evidence_refs": _evidence_refs(evidence),
            "speaker": _text(source.get("speaker")),
            "text": str(source.get("text") or ""),
            "binding_classification": _text(binding.get("classification")),
            "binding_type": _text(binding.get("binding_type")),
            "source_evidence": copy.deepcopy(evidence),
        }
    if source_type == "SOURCE_BEAT":
        return {
            "unit_id": unit_id,
            "schema_version": SOURCE_AUTHORING_UNIT_SCHEMA_VERSION,
            "source_type": source_type,
            "source_ref": source_ref,
            "source_order": order,
            "source_evidence_refs": _evidence_refs(source.get("source_evidence")),
            "event": str(source.get("event") or source.get("text") or ""),
            "authority": SOURCE_BEAT_AUTHORITY,
            "source_evidence": copy.deepcopy(source.get("source_evidence")),
        }
    return {
        "unit_id": unit_id,
        "schema_version": SOURCE_AUTHORING_UNIT_SCHEMA_VERSION,
        "source_type": source_type,
        "source_ref": source_ref,
        "source_order": order,
        "source_evidence_refs": _evidence_refs(evidence),
        "text": str(source.get("text") or source.get("event") or ""),
        "source_evidence": copy.deepcopy(evidence),
    }


def project_source_authoring_units(scene: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Project authoritative ScriptIR timeline items into generic units.

    The ScriptIR ``script_blocks`` order is authoritative.  This function
    never groups adjacent actions, infers dramatic purpose, or creates a
    synthetic source beat when the source has none.
    """

    if not isinstance(scene, Mapping):
        return []
    scene_id = _text(scene.get("scene_id"))
    actions = {str(item.get("action_id")): item for item in _list(scene.get("actions")) if isinstance(item, Mapping) and _text(item.get("action_id"))}
    dialogues = {str(item.get("dialogue_id")): item for item in _list(scene.get("dialogues")) if isinstance(item, Mapping) and _text(item.get("dialogue_id"))}
    beats = {str(item.get("beat_id") or item.get("id")): item for item in _list(scene.get("beats") or scene.get("dramatic_beats")) if isinstance(item, Mapping) and _text(item.get("beat_id") or item.get("id"))}
    blocks = [item for item in _list(scene.get("script_blocks")) if isinstance(item, Mapping)]
    blocks = sorted(enumerate(blocks), key=lambda pair: (int(pair[1].get("order") or 0), pair[0]))
    units: list[dict[str, Any]] = []
    for order, (_index, block) in enumerate(blocks, start=1):
        block_type = _text(block.get("type")).upper()
        source_ref = _text(block.get("ref"))
        if block_type == "ACTION" and source_ref in actions:
            source_type, source = "SOURCE_ACTION", actions[source_ref]
        elif block_type == "DIALOGUE" and source_ref in dialogues:
            source_type, source = "SOURCE_DIALOGUE", dialogues[source_ref]
        elif block_type in {"BEAT", "SOURCE_BEAT"} and source_ref in beats:
            source_type, source = "SOURCE_BEAT", beats[source_ref]
        elif source_ref:
            # Preserve an unknown block as an auditable structural unit.  The
            # validator will reject it as an invalid source reference instead
            # of silently dropping timeline coverage.
            source_type, source = "SOURCE_BLOCK", block
        else:
            continue
        unit_id = f"SAU_{scene_id}_{order:03d}"
        units.append(_unit_payload(scene, source_type, source_ref, source, order, unit_id))
    return units


def source_authoring_unit_contract(units: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_AUTHORING_UNIT_SCHEMA_VERSION,
        "unit_count": len(units),
        "units": copy.deepcopy(units),
        "fingerprint": _fingerprint(units),
    }


def _empty_creative_projection(units: list[dict[str, Any]]) -> dict[str, Any]:
    passthrough = [
        str(unit["unit_id"])
        for unit in units
        if unit.get("source_type") in {"SOURCE_ACTION", "SOURCE_DIALOGUE"}
    ]
    return {
        "status": "AUTHORING_REQUIRED",
        "authority": DIRECTOR_CREATIVE_AUTHORITY,
        "director_scene_label": "",
        "director_scene_label_authority": DIRECTOR_CREATIVE_AUTHORITY,
        "scene_objective": "",
        "dramatic_question": "",
        "creative_beats": [],
        "explicit_passthrough_unit_refs": passthrough,
        "character_directions": [],
        "performance_arc": [],
        "information_strategy": [],
        "rhythm_strategy": {},
        "visual_priority": [],
        "scene_exit_intent": "",
        "prohibited_interpretations": [],
    }


def build_source_grounded_director_preview(
    *, scene: Mapping[str, Any], source_script_revision: str = "", source_script_hash: str = "", source_script_ir_version_id: int | None = None,
) -> dict[str, Any]:
    """Build a non-creative production preview for a V3.1 scene."""

    units = project_source_authoring_units(scene)
    scene_id = _text(scene.get("scene_id"))
    source_constraints = {
        "scene_id": scene_id,
        "scene_identity_evidence": copy.deepcopy(_list(scene.get("source_identity_evidence"))),
        "declared_participants": copy.deepcopy(_list(scene.get("participants"))),
        "source_authoring_units": units,
        "explicit_story_constraints": copy.deepcopy(_list(scene.get("required_visual_proofs"))),
    }
    projection = _empty_creative_projection(units)
    preview = {
        "schema_version": DIRECTOR_TREATMENT_SCHEMA_VERSION_V3,
        "scene_id": scene_id,
        "scene_name": "",
        "source_constraints": source_constraints,
        "creative_projection": projection,
        "unknowns": [],
        "status": "AUTHORING_REQUIRED",
        "qualification_state": "AUTHORING_REQUIRED",
        "source_script_revision": str(source_script_revision or ""),
        "source_script_hash": str(source_script_hash or ""),
        "source_script_ir_version_id": source_script_ir_version_id,
        "model_info": {"mode": "source_grounded_provider_free_preview", "llm_called": False, "provider_calls": 0},
    }
    preview["source_authoring_units_fingerprint"] = _fingerprint(units)
    preview["candidate_fingerprint"] = _fingerprint(preview)
    return preview


def _unit_signature(unit: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _text(unit.get("unit_id")), _text(unit.get("source_type")), _text(unit.get("source_ref")),
        int(unit.get("source_order") or 0), tuple(unit.get("source_evidence_refs") or []),
        _text(unit.get("speaker")), str(unit.get("text") or ""),
        _text(unit.get("binding_classification")), _text(unit.get("binding_type")),
    )


def _candidate_projection(candidate: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    constraints = candidate.get("source_constraints") if isinstance(candidate.get("source_constraints"), Mapping) else {}
    projection = candidate.get("creative_projection") if isinstance(candidate.get("creative_projection"), Mapping) else {}
    return dict(constraints), dict(projection)


def validate_director_contract_v2(candidate: dict[str, Any], *, scene: Mapping[str, Any], production: bool = False) -> dict[str, Any]:
    """Validate source-grounded DirectorTreatment V3 candidates.

    V1 remains beat-centric elsewhere.  This validator uses stable generic
    SourceAuthoringUnit references and keeps source dialogue/participants
    immutable while allowing creative beats to be absent during preview.
    """

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(candidate, Mapping):
        return {"status": "blocked", "errors": [{"code": "DIRECTOR_TREATMENT_SCHEMA_INVALID"}], "warnings": []}
    if _text(candidate.get("schema_version")) not in {"", DIRECTOR_TREATMENT_SCHEMA_VERSION_V3}:
        errors.append({"code": "DIRECTOR_TREATMENT_SCHEMA_INVALID"})
    expected_units = project_source_authoring_units(scene)
    expected_by_id = {str(unit["unit_id"]): unit for unit in expected_units}
    constraints, projection = _candidate_projection(candidate)
    if _text(constraints.get("scene_id")) != _text(scene.get("scene_id")):
        errors.append({"code": "DIRECTOR_SOURCE_SCENE_ID_INVALID"})
    if _text(candidate.get("scene_name")) or _text(constraints.get("scene_name")):
        errors.append({"code": "DIRECTOR_SOURCE_SCENE_NAME_MUTATION"})
    if constraints.get("source_beats") not in (None, [], {}):
        errors.append({"code": "DIRECTOR_SOURCE_BEATS_NOT_ALLOWED"})
    supplied_units = constraints.get("source_authoring_units")
    if not isinstance(supplied_units, list):
        errors.append({"code": "DIRECTOR_SOURCE_AUTHORING_UNITS_REQUIRED"})
        supplied_units = []
    supplied_by_id = {str(unit.get("unit_id")): unit for unit in supplied_units if isinstance(unit, Mapping)}
    for unit_id, expected in expected_by_id.items():
        actual = supplied_by_id.get(unit_id)
        if actual is None:
            errors.append({"code": "DIRECTOR_SOURCE_UNIT_REF_INVALID", "unit_ref": unit_id})
            continue
        if _text(actual.get("source_type")) != _text(expected.get("source_type")) or _text(actual.get("source_ref")) != _text(expected.get("source_ref")):
            errors.append({"code": "DIRECTOR_SOURCE_UNIT_REF_INVALID", "unit_ref": unit_id})
        if _text(expected.get("source_type")) == "SOURCE_DIALOGUE":
            if _text(actual.get("speaker")) != _text(expected.get("speaker")):
                errors.append({"code": "DIRECTOR_SOURCE_SPEAKER_MUTATION", "unit_ref": unit_id})
            if str(actual.get("text") or "") != str(expected.get("text") or "") or _text(actual.get("binding_classification")) != _text(expected.get("binding_classification")) or _text(actual.get("binding_type")) != _text(expected.get("binding_type")):
                errors.append({"code": "DIRECTOR_SOURCE_DIALOGUE_MUTATION", "unit_ref": unit_id})
    for unit_id in supplied_by_id:
        if unit_id not in expected_by_id:
            errors.append({"code": "DIRECTOR_SOURCE_UNIT_REF_INVALID", "unit_ref": unit_id})
    if supplied_units and [_unit_signature(x) for x in supplied_units if isinstance(x, Mapping)] != [_unit_signature(x) for x in expected_units]:
        errors.append({"code": "DIRECTOR_SOURCE_AUTHORING_UNITS_MUTATED"})

    declared = set()
    for item in _list(scene.get("participants")):
        if isinstance(item, Mapping):
            declared.add(_text(item.get("id") or item.get("character_id") or item.get("name")))
            declared.add(_text(item.get("name")))
        else:
            declared.add(_text(item))
    for direction in _list(projection.get("character_directions")):
        if not isinstance(direction, Mapping):
            errors.append({"code": "DIRECTOR_PARTICIPANT_REF_INVALID"})
            continue
        ref = _text(direction.get("character_ref") or direction.get("character") or direction.get("name"))
        if ref and ref not in declared:
            errors.append({"code": "DIRECTOR_PARTICIPANT_REF_INVALID", "participant_ref": ref})

    creative_beats = projection.get("creative_beats")
    if not isinstance(creative_beats, list):
        errors.append({"code": "DIRECTOR_CREATIVE_BEAT_SCHEMA_INVALID"})
        creative_beats = []
    covered: set[str] = set()
    for beat in creative_beats:
        if not isinstance(beat, Mapping):
            errors.append({"code": "DIRECTOR_CREATIVE_BEAT_SCHEMA_INVALID"})
            continue
        refs = beat.get("derived_from_source_unit_refs")
        if not isinstance(refs, list) or not refs:
            errors.append({"code": "DIRECTOR_CREATIVE_BEAT_SOURCE_REF_REQUIRED", "creative_beat_id": beat.get("creative_beat_id")})
            refs = []
        for ref in refs:
            ref_text = _text(ref)
            if ref_text not in expected_by_id:
                errors.append({"code": "DIRECTOR_SOURCE_UNIT_REF_INVALID", "unit_ref": ref_text})
            else:
                covered.add(ref_text)
                expected_unit = expected_by_id[ref_text]
                dialogue_projection = beat.get("source_dialogue") or beat.get("dialogue")
                if _text(expected_unit.get("source_type")) == "SOURCE_DIALOGUE" and isinstance(dialogue_projection, Mapping):
                    if _text(dialogue_projection.get("speaker")) != _text(expected_unit.get("speaker")):
                        errors.append({"code": "DIRECTOR_SOURCE_SPEAKER_MUTATION", "unit_ref": ref_text})
                    if str(dialogue_projection.get("text") or "") != str(expected_unit.get("text") or "") or _text(dialogue_projection.get("binding_classification")) not in {"", _text(expected_unit.get("binding_classification"))}:
                        errors.append({"code": "DIRECTOR_SOURCE_DIALOGUE_MUTATION", "unit_ref": ref_text})
        if _text(beat.get("authority")) != DIRECTOR_CREATIVE_AUTHORITY or _text(beat.get("authority")) == SOURCE_BEAT_AUTHORITY:
            errors.append({"code": "DIRECTOR_CREATIVE_AUTHORITY_INVALID", "creative_beat_id": beat.get("creative_beat_id")})
        if not _text(beat.get("creative_beat_id")):
            errors.append({"code": "DIRECTOR_CREATIVE_BEAT_SCHEMA_INVALID"})
        if not isinstance(beat.get("character_effects", []), list):
            errors.append({"code": "DIRECTOR_CREATIVE_BEAT_SCHEMA_INVALID", "creative_beat_id": beat.get("creative_beat_id")})
        if "hook_intent" in beat and not isinstance(beat.get("hook_intent"), bool):
            errors.append({"code": "DIRECTOR_CREATIVE_BEAT_SCHEMA_INVALID", "creative_beat_id": beat.get("creative_beat_id")})

    passthrough = projection.get("explicit_passthrough_unit_refs", [])
    if not isinstance(passthrough, list):
        passthrough = []
    for ref in passthrough:
        if _text(ref) not in expected_by_id:
            errors.append({"code": "DIRECTOR_SOURCE_UNIT_REF_INVALID", "unit_ref": _text(ref)})
        else:
            covered.add(_text(ref))
    story_units = {str(unit["unit_id"]) for unit in expected_units if unit.get("source_type") in {"SOURCE_ACTION", "SOURCE_DIALOGUE"}}
    missing = sorted(story_units - covered)
    if missing:
        errors.append({"code": "DIRECTOR_SOURCE_TIMELINE_COVERAGE_INCOMPLETE", "missing_unit_refs": missing})
    if not creative_beats and not errors:
        status = "AUTHORING_REQUIRED"
        warnings.append({"code": "DIRECTOR_CREATIVE_AUTHORING_REQUIRED"})
    else:
        status = "qualified" if not errors else "blocked"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "source_unit_count": len(expected_units),
        "source_action_count": sum(unit.get("source_type") == "SOURCE_ACTION" for unit in expected_units),
        "source_dialogue_count": sum(unit.get("source_type") == "SOURCE_DIALOGUE" for unit in expected_units),
        "creative_beat_count": len(creative_beats),
        "covered_story_unit_count": len(story_units & covered),
        "story_unit_count": len(story_units),
        "synthetic_source_beat_count": 0,
        "synthetic_source_scene_name_count": 0,
    }


def validate_source_dialogue_protection(candidate: Mapping[str, Any], *, scene: Mapping[str, Any]) -> dict[str, Any]:
    """Small explicit audit used by tests and the V7.1 evidence runner."""

    report = validate_director_contract_v2(dict(candidate), scene=scene)
    dialogue_errors = [item for item in report.get("errors", []) if item.get("code") in {"DIRECTOR_SOURCE_DIALOGUE_MUTATION", "DIRECTOR_SOURCE_SPEAKER_MUTATION"}]
    return {"status": "PASS" if not dialogue_errors else "FAIL", "errors": dialogue_errors}


__all__ = [
    "SOURCE_AUTHORING_UNIT_SCHEMA_VERSION", "DIRECTOR_TREATMENT_SCHEMA_VERSION_V3", "DIRECTOR_CREATIVE_AUTHORITY", "SOURCE_BEAT_AUTHORITY", "SOURCE_UNIT_TYPES",
    "is_source_grounded_scene", "project_source_authoring_units", "source_authoring_unit_contract", "build_source_grounded_director_preview", "validate_director_contract_v2", "validate_source_dialogue_protection",
]
