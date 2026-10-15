"""Provider-free Claim V3.1 ownership and argument-completeness contracts.

This module adds a versioned layer beside V3. It leaves every V2/V3 historic
registry untouched and performs no provider calls or persistence.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping, Sequence

from .provider_structured_output_qualification import fingerprint
from .source_semantic_claim_v3 import (
    CLAIM_V3_REQUIRED_KEYS,
    RELATION_SIGNATURES,
    SECOND_ORDER_RELATION_SIGNATURES,
    qualifier_registry_v2,
    relation_signature_registry_v2,
)


RELATION_SIGNATURE_REGISTRY_V3_VERSION = "source_claim_relation_signature_registry_v3"
QUALIFIER_REGISTRY_V3_VERSION = "source_claim_qualifier_registry_v3"
PROVIDER_PREDICATE_REGISTRY_V2_VERSION = "source_claim_proposal_predicate_registry_v2"
FIRST_ORDER_RELATION_OWNERSHIP_REGISTRY_V1_VERSION = "source_claim_first_order_relation_ownership_registry_v1"
SPEECH_ACT_BINDING_REGISTRY_V1_VERSION = "source_speech_act_binding_registry_v1"
SPEECH_ACT_DETERMINISTIC_CONTRACT_V1_VERSION = "source_speech_act_deterministic_contract_v1"
SPEECH_ACT_DETERMINISTIC_CANDIDATE_V1_VERSION = "source_speech_act_deterministic_candidate_v1"
REQUIRED_QUALIFIER_EXECUTABILITY_CONTRACT_V1_VERSION = "source_claim_required_qualifier_executability_contract_v1"

PROVIDER_PROPOSABLE = "PROVIDER_PROPOSABLE"
PROGRAM_DETERMINISTIC = "PROGRAM_DETERMINISTIC"
DEFERRED_SECOND_ORDER = "DEFERRED_SECOND_ORDER"


def qualifier_registry_v3() -> dict[str, Any]:
    """Only expose keys writable by current provider-owned relations."""
    return {
        "schema_version": QUALIFIER_REGISTRY_V3_VERSION,
        "qualifiers": {
            "guided_character": {"value_type": "ENTITY_REF"},
            "transfer_source": {"value_type": "ENTITY_REF"},
        },
        "wire_value_type": "string",
        "provider_writable_keys_only": True,
        "excluded_keys": {
            "speaker_binding": "PROGRAM_OWNED_PROVENANCE_NOT_SEMANTIC_QUALIFIER",
            "destination": "DUPLICATES_ENTER_GUIDED_OBJECT_REF",
            "property_domain": "NO_CURRENT_PROVIDER_EXECUTABLE_RELATION_USES_KEY",
            "state_domain": "NO_CURRENT_PROVIDER_EXECUTABLE_RELATION_USES_KEY",
            "light_state": "NO_CURRENT_PROVIDER_EXECUTABLE_RELATION_USES_KEY",
        },
    }


def relation_signature_registry_v3() -> dict[str, Any]:
    """Return the versioned first-order ontology with explicit ownership."""
    signatures = copy.deepcopy(RELATION_SIGNATURES)
    signatures["enter_guided"].update({
        "allowed_qualifier_keys": ["guided_character"],
        "required_qualifier_keys": ["guided_character"],
        "qualifier_entity_kind_constraints": {"guided_character": ["CHARACTER"]},
    })
    signatures["speech_act"].update({
        "allowed_qualifier_keys": [],
        "required_qualifier_keys": [],
    })
    ownership = {
        "enter_guided": PROVIDER_PROPOSABLE,
        "has_property": PROVIDER_PROPOSABLE,
        "left_by": PROVIDER_PROPOSABLE,
        "received_by": PROVIDER_PROPOSABLE,
        "speech_act": PROGRAM_DETERMINISTIC,
        "state_value": PROVIDER_PROPOSABLE,
    }
    for predicate, row in signatures.items():
        row["proposal_owner"] = ownership[predicate]
        row["proposal_mode"] = ownership[predicate]
        row["provider_proposable"] = ownership[predicate] == PROVIDER_PROPOSABLE
    return {
        "schema_version": RELATION_SIGNATURE_REGISTRY_V3_VERSION,
        "supersedes_for_new_execution_only": "source_claim_relation_signature_registry_v2",
        "signatures": signatures,
        "historical_registry_mutated": False,
    }


def first_order_relation_ownership_registry_v1(
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = registry if isinstance(registry, Mapping) else relation_signature_registry_v3()
    signatures = value.get("signatures") if isinstance(value.get("signatures"), Mapping) else {}
    predicates: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, raw in sorted(signatures.items(), key=lambda item: str(item[0])):
        if not isinstance(raw, Mapping):
            errors.append(f"RELATION_SIGNATURE_INVALID:{name}")
            continue
        owner = str(raw.get("proposal_owner") or "")
        if owner not in {PROVIDER_PROPOSABLE, PROGRAM_DETERMINISTIC}:
            errors.append(f"RELATION_OWNER_INVALID:{name}")
            continue
        predicates[str(name)] = {
            "predicate": str(name),
            "claim_type": str(raw.get("claim_type") or ""),
            "relation_class": str(raw.get("relation_class") or ""),
            "proposal_owner": owner,
            "proposal_mode": owner,
            "provider_proposable": owner == PROVIDER_PROPOSABLE,
        }
    return {
        "schema_version": FIRST_ORDER_RELATION_OWNERSHIP_REGISTRY_V1_VERSION,
        "status": "PASS" if not errors and len(predicates) == 6 else "BLOCKED",
        "predicates": predicates,
        "provider_proposable_count": sum(row["proposal_owner"] == PROVIDER_PROPOSABLE for row in predicates.values()),
        "program_deterministic_count": sum(row["proposal_owner"] == PROGRAM_DETERMINISTIC for row in predicates.values()),
        "errors": sorted(errors),
    }


def proposal_ownership_classification_v1(
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    first_order = first_order_relation_ownership_registry_v1(registry)
    deferred = {
        name: {
            "predicate": name,
            "proposal_owner": DEFERRED_SECOND_ORDER,
            "provider_proposable": False,
            "requires": "verified first-order ClaimRef before execution",
        }
        for name in sorted(SECOND_ORDER_RELATION_SIGNATURES)
    }
    provider = sorted(name for name, row in first_order["predicates"].items() if row["proposal_owner"] == PROVIDER_PROPOSABLE)
    program = sorted(name for name, row in first_order["predicates"].items() if row["proposal_owner"] == PROGRAM_DETERMINISTIC)
    return {
        "schema_version": "source_claim_proposal_ownership_classification_v1",
        "status": first_order["status"],
        "classes": {
            PROVIDER_PROPOSABLE: provider,
            PROGRAM_DETERMINISTIC: program,
            DEFERRED_SECOND_ORDER: deferred,
        },
        "counts": {
            PROVIDER_PROPOSABLE: len(provider),
            PROGRAM_DETERMINISTIC: len(program),
            DEFERRED_SECOND_ORDER: len(deferred),
        },
        "second_order_registry_modified": False,
    }


def required_qualifier_executability_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": REQUIRED_QUALIFIER_EXECUTABILITY_CONTRACT_V1_VERSION,
        "rule": "Each required ENTITY_REF qualifier must have at least one registry entity of an allowed constrained kind.",
        "source_text_consulted": False,
        "predicate_name_semantics_inferred": False,
        "qualifier_name_special_cases": False,
    }


def _kind_counts(entity_registry: Mapping[str, Any]) -> Counter[str]:
    rows = entity_registry.get("entities") if isinstance(entity_registry.get("entities"), Mapping) else {}
    return Counter(str(row.get("kind") or "") for row in rows.values() if isinstance(row, Mapping))


def provider_predicate_registry_v2(
    relation_registry: Mapping[str, Any] | None = None,
    entity_registry: Mapping[str, Any] | None = None,
    qualifiers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive executable Provider-owned relations, including required ref args."""
    relations = relation_registry if isinstance(relation_registry, Mapping) else relation_signature_registry_v3()
    entities = entity_registry if isinstance(entity_registry, Mapping) else {}
    qualifier_contract = qualifiers if isinstance(qualifiers, Mapping) else qualifier_registry_v3()
    signature_rows = relations.get("signatures") if isinstance(relations.get("signatures"), Mapping) else {}
    qualifier_rows = qualifier_contract.get("qualifiers") if isinstance(qualifier_contract.get("qualifiers"), Mapping) else {}
    counts = _kind_counts(entities)
    executable: dict[str, dict[str, Any]] = {}
    dormant: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for name, signature in sorted(signature_rows.items(), key=lambda item: str(item[0])):
        if not isinstance(signature, Mapping):
            errors.append(f"RELATION_SIGNATURE_INVALID:{name}")
            continue
        if signature.get("proposal_owner") != PROVIDER_PROPOSABLE:
            continue
        subject_kinds = sorted({str(kind) for kind in signature.get("allowed_subject_kinds", []) if str(kind)})
        object_kinds = sorted({str(kind) for kind in signature.get("allowed_object_kinds", []) if str(kind)})
        if not subject_kinds or not object_kinds:
            errors.append(f"RELATION_KIND_DOMAIN_EMPTY:{name}")
            continue
        subject_counts = {kind: counts[kind] for kind in subject_kinds}
        object_counts = {kind: counts[kind] for kind in object_kinds}
        missing_dependencies: list[str] = []
        qualifier_dependencies: dict[str, dict[str, int]] = {}
        constraints = signature.get("qualifier_entity_kind_constraints") if isinstance(signature.get("qualifier_entity_kind_constraints"), Mapping) else {}
        required = {str(key) for key in signature.get("required_qualifier_keys", [])}
        for key in sorted(required):
            qualifier = qualifier_rows.get(key)
            if not isinstance(qualifier, Mapping):
                errors.append(f"REQUIRED_QUALIFIER_NOT_REGISTERED:{name}:{key}")
                missing_dependencies.append(f"QUALIFIER_NOT_REGISTERED:{key}")
                continue
            if qualifier.get("value_type") != "ENTITY_REF":
                continue
            allowed_kinds = sorted({str(kind) for kind in constraints.get(key, []) if str(kind)})
            if not allowed_kinds:
                errors.append(f"REQUIRED_ENTITY_REF_QUALIFIER_KIND_CONSTRAINT_MISSING:{name}:{key}")
                missing_dependencies.append(f"QUALIFIER_KIND_CONSTRAINT_MISSING:{key}")
                continue
            available = {kind: counts[kind] for kind in allowed_kinds}
            qualifier_dependencies[key] = available
            if not any(available.values()):
                missing_dependencies.append(f"QUALIFIER_ENTITY_KIND_UNAVAILABLE:{key}")

        row = {
            **copy.deepcopy(dict(signature)),
            "predicate": str(name),
            "available_subject_kind_counts": subject_counts,
            "available_object_kind_counts": object_counts,
            "required_qualifier_entity_kind_counts": qualifier_dependencies,
            "missing_type_dependencies": missing_dependencies,
            "execution_status": "EXECUTABLE" if any(subject_counts.values()) and any(object_counts.values()) and not missing_dependencies else "TYPE_DEPENDENCY_UNAVAILABLE",
        }
        (executable if row["execution_status"] == "EXECUTABLE" else dormant)[str(name)] = row

    ownership = first_order_relation_ownership_registry_v1(relations)
    return {
        "schema_version": PROVIDER_PREDICATE_REGISTRY_V2_VERSION,
        "status": "PASS" if not errors and ownership["status"] == "PASS" else "BLOCKED",
        "predicates": executable,
        "dormant_predicates": dormant,
        "predicate_count": len(executable),
        "dormant_predicate_count": len(dormant),
        "program_deterministic_predicates": sorted(
            name for name, row in ownership["predicates"].items()
            if row["proposal_owner"] == PROGRAM_DETERMINISTIC
        ),
        "ownership_registry_version": ownership["schema_version"],
        "required_qualifier_executability_contract": REQUIRED_QUALIFIER_EXECUTABILITY_CONTRACT_V1_VERSION,
        "semantics": "TYPE_EXECUTABLE != SOURCE_SUPPORTED",
        "errors": sorted(set(errors + ownership["errors"])),
        "source_text_consulted": False,
        "predicate_name_semantics_inferred": False,
    }


def source_speech_act_binding_registry_v1(
    *,
    script_ir: Mapping[str, Any],
    source_units: Sequence[Mapping[str, Any]],
    entity_registry: Mapping[str, Any],
    source_fingerprint: str,
) -> dict[str, Any]:
    """Bind structured ScriptIR dialogues to source units and canonical speakers.

    This joins explicit refs and structured fields only. It does not inspect
    dialogue prose to guess speakers.
    """
    entity_rows = entity_registry.get("entities") if isinstance(entity_registry.get("entities"), Mapping) else {}
    units_by_evidence: dict[str, list[Mapping[str, Any]]] = {}
    for unit in source_units:
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        evidence_id = str(evidence.get("evidence_id") or "")
        if evidence_id:
            units_by_evidence.setdefault(evidence_id, []).append(unit)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    scenes = script_ir.get("scenes") if isinstance(script_ir.get("scenes"), list) else []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, Mapping):
            errors.append(f"SCRIPT_IR_SCENE_INVALID:{scene_index}")
            continue
        dialogues = scene.get("dialogues") if isinstance(scene.get("dialogues"), list) else []
        for dialogue_index, dialogue in enumerate(dialogues):
            if not isinstance(dialogue, Mapping):
                errors.append(f"SCRIPT_IR_DIALOGUE_INVALID:{scene_index}:{dialogue_index}")
                continue
            source_evidence = dialogue.get("source_evidence") if isinstance(dialogue.get("source_evidence"), Mapping) else {}
            evidence_ref = str(source_evidence.get("evidence_id") or "")
            matching = units_by_evidence.get(evidence_ref, [])
            if len(matching) != 1:
                errors.append(f"DIALOGUE_SOURCE_UNIT_BINDING_AMBIGUOUS:{evidence_ref}")
                continue
            unit = matching[0]
            unit_ref = str(unit.get("unit_id") or "")
            if unit.get("source_type") != "SOURCE_DIALOGUE" or str(unit.get("speaker") or "") != str(dialogue.get("speaker") or ""):
                errors.append(f"DIALOGUE_STRUCTURED_SPEAKER_MISMATCH:{unit_ref}")
                continue
            dialogue_entity = entity_rows.get(unit_ref)
            if not isinstance(dialogue_entity, Mapping) or dialogue_entity.get("kind") != "DIALOGUE_CONTENT":
                errors.append(f"DIALOGUE_CONTENT_ENTITY_INVALID:{unit_ref}")
                continue
            speaker_ref = str(dialogue.get("speaker") or "")
            speaker_entity = entity_rows.get(speaker_ref)
            if not isinstance(speaker_entity, Mapping) or speaker_entity.get("kind") != "CHARACTER" or speaker_entity.get("authority") != "CANONICAL_RUNTIME":
                errors.append(f"AUTHORITATIVE_SPEAKER_REF_INVALID:{speaker_ref}")
                continue
            binding = dialogue.get("speaker_binding") if isinstance(dialogue.get("speaker_binding"), Mapping) else None
            if not binding or not binding.get("classification") or not binding.get("binding_type"):
                errors.append(f"STRUCTURED_SPEAKER_BINDING_MISSING:{unit_ref}")
                continue
            binding_evidence = []
            for collection_name in ("identity_evidence", "utterance_evidence"):
                values = binding.get(collection_name) if isinstance(binding.get(collection_name), list) else []
                binding_evidence.extend(
                    str(item.get("evidence_id")) for item in values
                    if isinstance(item, Mapping) and item.get("evidence_id")
                )
            rows.append({
                "dialogue_content_ref": unit_ref,
                "speaker_ref": speaker_ref,
                "evidence_refs": sorted(set([evidence_ref, *binding_evidence])),
                "source_unit_refs": [unit_ref],
                "speaker_binding_provenance_fingerprint": fingerprint(binding),
                "speaker_binding_classification": str(binding.get("classification")),
                "speaker_binding_type": str(binding.get("binding_type")),
                "source_fingerprint": source_fingerprint,
            })
    rows.sort(key=lambda row: (row["dialogue_content_ref"], row["speaker_ref"]))
    unique_refs = [row["dialogue_content_ref"] for row in rows]
    if len(unique_refs) != len(set(unique_refs)):
        errors.append("DIALOGUE_CONTENT_BINDING_DUPLICATE")
    return {
        "schema_version": SPEECH_ACT_BINDING_REGISTRY_V1_VERSION,
        "status": "PASS" if not errors and bool(rows) else "BLOCKED",
        "source_fingerprint": source_fingerprint,
        "binding_count": len(rows),
        "bindings": rows,
        "speaker_source": "STRUCTURED_SCRIPT_IR_DIALOGUE_SPEAKER_AND_SPEAKER_BINDING",
        "dialogue_prose_parsed_for_speaker": False,
        "errors": sorted(set(errors)),
        "production_writes": 0,
    }


def speech_act_proposal_ownership_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": "source_speech_act_proposal_ownership_contract_v1",
        "predicate": "speech_act",
        "claim_type": "SOURCE_SPEECH_ACT",
        "relation_class": "SPEECH_ACT",
        "proposal_owner": PROGRAM_DETERMINISTIC,
        "provider_proposable": False,
        "source": "grounded ScriptIR dialogue authority bound to immutable SourceAuthoringUnit evidence",
        "legacy_director_relation_registry_modified": False,
    }


def speech_act_deterministic_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": SPEECH_ACT_DETERMINISTIC_CONTRACT_V1_VERSION,
        "predicate": "speech_act",
        "claim_type": "SOURCE_SPEECH_ACT",
        "relation_class": "SPEECH_ACT",
        "meaning": "The bound speaker uttered the exact supplied dialogue-content entity.",
        "proves_dialogue_proposition_truth": False,
        "creates_world_fact": False,
        "semantic_verifier_required_for_dialogue_proposition": True,
        "speaker_binding_provenance_in_qualifiers": False,
        "provider_calls": 0,
        "production_persistence": False,
    }


def build_deterministic_speech_act_candidate(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SPEECH_ACT_DETERMINISTIC_CANDIDATE_V1_VERSION,
        "proposal_owner": PROGRAM_DETERMINISTIC,
        "predicate": "speech_act",
        "claim_type": "SOURCE_SPEECH_ACT",
        "relation_class": "SPEECH_ACT",
        "subject_ref": str(binding.get("speaker_ref") or ""),
        "object_ref": str(binding.get("dialogue_content_ref") or ""),
        "qualifiers": {},
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "evidence_refs": list(binding.get("evidence_refs") or []),
        "source_unit_refs": list(binding.get("source_unit_refs") or []),
        "program_owned_provenance": {
            "speaker_binding_provenance_fingerprint": str(binding.get("speaker_binding_provenance_fingerprint") or ""),
            "source_fingerprint": str(binding.get("source_fingerprint") or ""),
            "speaker_binding_classification": str(binding.get("speaker_binding_classification") or ""),
            "speaker_binding_type": str(binding.get("speaker_binding_type") or ""),
        },
        "authority_boundary": "STRUCTURED_SPEECH_OCCURRENCE_ONLY",
        "dialogue_proposition_world_fact": False,
        "semantic_verifier_required_for_dialogue_proposition": True,
        "persisted": False,
    }


def validate_deterministic_speech_act_candidate(
    candidate: Mapping[str, Any], binding_registry: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if candidate.get("predicate") != "speech_act":
        errors.append("PROGRAM_SPEECH_ACT_PREDICATE_INVALID")
    rows = binding_registry.get("bindings") if isinstance(binding_registry.get("bindings"), list) else []
    binding = next((row for row in rows if isinstance(row, Mapping) and row.get("dialogue_content_ref") == candidate.get("object_ref")), None)
    if binding is None:
        errors.append("AUTHORITATIVE_SPEECH_ACT_BINDING_MISSING")
    elif candidate.get("subject_ref") != binding.get("speaker_ref"):
        errors.append("SPEECH_ACT_SPEAKER_BINDING_MISMATCH")
    if candidate.get("qualifiers") != {}:
        errors.append("SPEECH_ACT_SEMANTIC_QUALIFIERS_NOT_ALLOWED")
    if binding is not None and sorted(candidate.get("evidence_refs") or []) != sorted(binding.get("evidence_refs") or []):
        errors.append("SPEECH_ACT_EVIDENCE_BINDING_MISMATCH")
    if binding is not None and candidate.get("source_unit_refs") != binding.get("source_unit_refs"):
        errors.append("SPEECH_ACT_SOURCE_UNIT_BINDING_MISMATCH")
    provenance = candidate.get("program_owned_provenance") if isinstance(candidate.get("program_owned_provenance"), Mapping) else {}
    if binding is not None and provenance.get("speaker_binding_provenance_fingerprint") != binding.get("speaker_binding_provenance_fingerprint"):
        errors.append("SPEECH_ACT_PROVENANCE_FINGERPRINT_MISMATCH")
    if binding is not None and provenance.get("source_fingerprint") != binding.get("source_fingerprint"):
        errors.append("SPEECH_ACT_SOURCE_FINGERPRINT_MISMATCH")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "dialogue_proposition_world_fact": False,
        "persisted": False,
    }


def validate_provider_candidate_v3_1(
    candidate: Mapping[str, Any], *,
    provider_registry: Mapping[str, Any],
    entity_registry: Mapping[str, Any],
    qualifier_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate current provider-owned contract, without repairing candidates."""
    errors: list[str] = []
    registry = qualifier_registry if isinstance(qualifier_registry, Mapping) else qualifier_registry_v3()
    predicates = provider_registry.get("predicates") if isinstance(provider_registry.get("predicates"), Mapping) else {}
    entities = entity_registry.get("entities") if isinstance(entity_registry.get("entities"), Mapping) else {}
    qualifiers = registry.get("qualifiers") if isinstance(registry.get("qualifiers"), Mapping) else {}
    if set(candidate) != CLAIM_V3_REQUIRED_KEYS:
        errors.append("CLAIM_V3_FIELDS_NOT_EXACT")
    predicate = str(candidate.get("predicate") or "")
    signature = predicates.get(predicate)
    if not isinstance(signature, Mapping):
        errors.append(f"PREDICATE_NOT_PROVIDER_PROPOSABLE:{predicate}")
    resolved: dict[str, Mapping[str, Any]] = {}
    for field, allowed_key in (("subject_ref", "allowed_subject_kinds"), ("object_ref", "allowed_object_kinds")):
        ref = candidate.get(field)
        entity = entities.get(ref) if isinstance(ref, str) else None
        if not isinstance(entity, Mapping):
            errors.append(f"{field.upper()}_UNKNOWN_ENTITY_REF")
            continue
        resolved[field] = entity
        if signature and entity.get("kind") not in signature.get(allowed_key, []):
            errors.append(f"RELATION_{field.upper()}_KIND_MISMATCH:{predicate}:{entity.get('kind')}")

    raw_qualifiers = candidate.get("qualifiers")
    if not isinstance(raw_qualifiers, Mapping):
        errors.append("QUALIFIERS_MUST_BE_OBJECT")
        raw_qualifiers = {}
    allowed = set(signature.get("allowed_qualifier_keys", [])) if signature else set()
    typed: dict[str, Any] = {}
    for key, value in raw_qualifiers.items():
        definition = qualifiers.get(key)
        if key not in allowed or not isinstance(definition, Mapping):
            errors.append(f"QUALIFIER_NOT_PROVIDER_WRITABLE:{key}")
            continue
        if not isinstance(value, str) or not value:
            errors.append(f"QUALIFIER_VALUE_INVALID:{key}")
            continue
        if definition.get("value_type") == "ENTITY_REF":
            entity = entities.get(value)
            if not isinstance(entity, Mapping):
                errors.append(f"QUALIFIER_ENTITY_REF_UNKNOWN:{key}")
                continue
            kinds = (signature.get("qualifier_entity_kind_constraints") or {}).get(key, [])
            if kinds and entity.get("kind") not in kinds:
                errors.append(f"QUALIFIER_ENTITY_KIND_MISMATCH:{key}:{entity.get('kind')}")
                continue
            typed[key] = {"value_type": "ENTITY_REF", "ref": value, "kind": entity.get("kind")}
        else:
            errors.append(f"QUALIFIER_VALUE_TYPE_UNSUPPORTED:{key}")
    if signature:
        missing = set(signature.get("required_qualifier_keys", [])) - set(raw_qualifiers)
        errors.extend(f"REQUIRED_QUALIFIER_MISSING:{predicate}:{key}" for key in sorted(missing))
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "typed_qualifiers": typed,
        "verifier_eligible": False,
        "authority": "UNTRUSTED_PROPOSED",
    }


__all__ = [
    "RELATION_SIGNATURE_REGISTRY_V3_VERSION", "QUALIFIER_REGISTRY_V3_VERSION",
    "PROVIDER_PREDICATE_REGISTRY_V2_VERSION", "FIRST_ORDER_RELATION_OWNERSHIP_REGISTRY_V1_VERSION",
    "SPEECH_ACT_BINDING_REGISTRY_V1_VERSION", "PROVIDER_PROPOSABLE", "PROGRAM_DETERMINISTIC",
    "DEFERRED_SECOND_ORDER", "qualifier_registry_v3", "relation_signature_registry_v3",
    "first_order_relation_ownership_registry_v1", "provider_predicate_registry_v2",
    "proposal_ownership_classification_v1",
    "required_qualifier_executability_contract_v1", "source_speech_act_binding_registry_v1",
    "speech_act_proposal_ownership_contract_v1", "speech_act_deterministic_contract_v1",
    "build_deterministic_speech_act_candidate", "validate_deterministic_speech_act_candidate",
    "validate_provider_candidate_v3_1",
]
