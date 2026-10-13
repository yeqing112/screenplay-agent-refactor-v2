"""Provider-free V3 Source Semantic Claim contract and deterministic compiler.

V2 remains a frozen historical contract. V3 moves entity kinds, claim IDs,
claim types, relation classes, and qualifier semantic types into program-owned
registries. This module has no provider or persistence dependency.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .director_claim_relation_registry import RELATION_REGISTRY
from .provider_structured_output_qualification import compile_provider_strict_schema, fingerprint, validate_json_schema_subset
from .source_entity_proposal import ENTITY_KINDS, CLAIM_V2_SET_VERSION, claim_v2_schema
from .source_semantic_claim_authority import FACT_CLAIM_MAPPING, MODALITIES, POLARITIES
from .source_semantic_claim_proposal import QUALIFIER_TYPES as LEGACY_QUALIFIER_TYPES


CLAIM_V3_VERSION = "source_semantic_claim_candidate_v3"
CLAIM_V3_SET_VERSION = "source_semantic_claim_candidate_set_v3"
CLAIM_INPUT_ENTITY_REGISTRY_VERSION = "source_claim_input_entity_registry_v1"
QUALIFIER_REGISTRY_VERSION = "source_claim_qualifier_registry_v2"
RELATION_SIGNATURE_REGISTRY_VERSION = "source_claim_relation_signature_registry_v2"
PROPOSABLE_PREDICATE_REGISTRY_VERSION = "source_claim_proposal_predicate_registry_v1"
CLAIM_V3_PROJECTION_VERSION = "source_semantic_claim_candidate_projection_v3"
SECOND_ORDER_RELATION_SIGNATURE_REGISTRY_VERSION = "source_claim_second_order_relation_signature_registry_v1"
VERIFIED_FIRST_ORDER_CLAIM_REGISTRY_VERSION = "source_verified_first_order_claim_registry_v1"
CLAIM_ORDER_REGISTRY_VERSION = "source_claim_order_registry_v1"

CLAIM_V3_REQUIRED_KEYS = {
    "schema_version", "subject_ref", "predicate", "object_ref", "qualifiers",
    "polarity", "modality", "evidence_refs", "source_unit_refs",
}
CLAIM_V3_FORBIDDEN_FIELDS = {
    "candidate_id", "claim_id", "source_claim_id", "subject_kind", "object_kind",
    "claim_type", "relation_class", "authority", "canonical", "promote",
    "final_status", "final_authority", "char_start", "char_end", "byte_start",
    "byte_end", "sha256", "fingerprint", "promotion", "source_claim_supported",
}
ALLOWED_ENTITY_AUTHORITIES = {"CANONICAL_RUNTIME", "SEMANTICALLY_VERIFIED_PROPOSAL"}
BLOCKED_ENTITY_AUTHORITIES = {"UNTRUSTED_PROPOSED", "REJECTED_PROPOSAL", "ENTITY_SEMANTIC_REVIEW_REQUIRED"}
SYMBOLIC_TOKEN_PATTERN = r"[A-Z][A-Z0-9_]*"

# Registry rows are ontology data. Validators perform direct key lookup only;
# they never infer signatures from predicate spelling or source prose.
QUALIFIER_REGISTRY: dict[str, dict[str, str]] = {
    "destination": {"value_type": "ENTITY_REF"},
    "transfer_source": {"value_type": "ENTITY_REF"},
    "property_domain": {"value_type": "SYMBOLIC_TOKEN"},
    "state_domain": {"value_type": "SYMBOLIC_TOKEN"},
    "light_state": {"value_type": "SYMBOLIC_TOKEN"},
    "speaker_binding": {"value_type": "SYMBOLIC_TOKEN"},
}

RELATION_SIGNATURES: dict[str, dict[str, Any]] = {
    "enter_guided": {
        "predicate": "enter_guided", "claim_type": "CHARACTER_ACTION", "relation_class": "ACTION",
        "allowed_subject_kinds": ["CHARACTER"], "allowed_object_kinds": ["LOCATION"],
        "allowed_qualifier_keys": ["destination"], "required_qualifier_keys": [],
        "qualifier_entity_kind_constraints": {"destination": ["LOCATION"]},
    },
    "speech_act": {
        "predicate": "speech_act", "claim_type": "SOURCE_SPEECH_ACT", "relation_class": "SPEECH_ACT",
        "allowed_subject_kinds": ["CHARACTER"], "allowed_object_kinds": ["DIALOGUE_CONTENT"],
        "allowed_qualifier_keys": ["speaker_binding"], "required_qualifier_keys": [],
    },
    "has_property": {
        "predicate": "has_property", "claim_type": "OBJECT_PROPERTY", "relation_class": "OBJECT_PROPERTY",
        "allowed_subject_kinds": ["OBJECT"], "allowed_object_kinds": ["PROPERTY_VALUE"],
        "allowed_qualifier_keys": ["property_domain"], "required_qualifier_keys": [],
    },
    "state_value": {
        "predicate": "state_value", "claim_type": "ENVIRONMENT_STATE", "relation_class": "ENVIRONMENT_STATE",
        "allowed_subject_kinds": ["ENVIRONMENT"], "allowed_object_kinds": ["STATE_VALUE"],
        "allowed_qualifier_keys": ["light_state", "state_domain"], "required_qualifier_keys": [],
    },
    "received_by": {
        "predicate": "received_by", "claim_type": "OBJECT_POSSESSION", "relation_class": "POSSESSION",
        "allowed_subject_kinds": ["CHARACTER"], "allowed_object_kinds": ["OBJECT"],
        "allowed_qualifier_keys": ["transfer_source"], "required_qualifier_keys": [],
    },
    "left_by": {
        "predicate": "left_by", "claim_type": "OBJECT_PROVENANCE", "relation_class": "PROVENANCE",
        "allowed_subject_kinds": ["CHARACTER"], "allowed_object_kinds": ["OBJECT"],
        "allowed_qualifier_keys": [], "required_qualifier_keys": [],
    },
}

LEGACY_STRUCTURAL_PREDICATES = {
    "scene_existence": "STRUCTURAL_COUNT",
    "scene_identity_evidence": "STRUCTURAL_EVIDENCE_SET",
}
UNRESOLVED_RELATION_REASONS = {
    # Unknown first-order relations remain unresolved. knows/uncertainty are
    # classified by the explicit second-order ontology below.
}
OBJECT_REF_DOMAINS = ("ENTITY_REF", "VERIFIED_FIRST_ORDER_CLAIM_REF")
SECOND_ORDER_RELATION_SIGNATURES: dict[str, dict[str, Any]] = {
    "knows": {
        "predicate": "knows", "claim_type": "CHARACTER_KNOWLEDGE", "relation_class": "KNOWLEDGE_STATE",
        "status": "DEFERRED_SECOND_ORDER", "proposal_order": "SECOND_ORDER", "subject_ref_domain": "ENTITY_REF",
        "allowed_subject_kinds": ["CHARACTER"], "object_ref_domain": "VERIFIED_FIRST_ORDER_CLAIM_REF",
        "allowed_qualifier_keys": [], "required_qualifier_keys": [],
    },
    "uncertainty": {
        "predicate": "uncertainty", "claim_type": "UNCERTAINTY", "relation_class": "UNCERTAINTY",
        "status": "DEFERRED_SECOND_ORDER", "proposal_order": "SECOND_ORDER", "subject_ref_domain": "ENTITY_REF",
        "allowed_subject_kinds": ["CHARACTER"], "object_ref_domain": "VERIFIED_FIRST_ORDER_CLAIM_REF",
        "allowed_qualifier_keys": [], "required_qualifier_keys": [],
    },
}
QUALIFIER_V1_AMBIGUITY_ROWS = {
    "ownership": "Provenance actor/object direction is represented by the typed relation; a boolean ownership modifier would assert a separate ownership fact and is not uniquely defined.",
    "possession": "The possession/receipt relation is represented by the typed predicate; a boolean possession modifier would duplicate that relation without a unique temporal meaning.",
}
RELATION_CLASS_ALIASES = {"ACTION": "CHARACTER_ACTION", "POSSESSION": "OBJECT_POSSESSION"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def claim_v3_candidate_contract() -> dict[str, Any]:
    return {
        "schema_version": CLAIM_V3_VERSION,
        "trust": "UNTRUSTED_PROPOSED",
        "required": sorted(CLAIM_V3_REQUIRED_KEYS),
        "provider_may_not_supply": sorted(CLAIM_V3_FORBIDDEN_FIELDS),
        "entity_kinds_are_program_resolved": True,
        "claim_type_and_relation_class_are_program_resolved": True,
        "claim_id_owner": "program_after_validation",
        "authority": "UNTRUSTED_PROPOSED",
    }


def claim_v3_candidate_set_contract() -> dict[str, Any]:
    return {
        "schema_version": CLAIM_V3_SET_VERSION,
        "required": ["schema_version", "claims"],
        "additionalProperties": False,
        "item_contract": CLAIM_V3_VERSION,
    }


def qualifier_registry_v2() -> dict[str, Any]:
    return {"schema_version": QUALIFIER_REGISTRY_VERSION, "qualifiers": copy.deepcopy(QUALIFIER_REGISTRY), "wire_value_type": "string"}


def qualifier_registry_audit(registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = registry if isinstance(registry, Mapping) else qualifier_registry_v2()
    qualifiers = value.get("qualifiers") if isinstance(value.get("qualifiers"), Mapping) else {}
    errors: list[str] = []
    for key, row in qualifiers.items():
        if not isinstance(row, Mapping):
            errors.append(f"QUALIFIER_REGISTRY_ROW_INVALID:{key}")
            continue
        value_type = row.get("value_type")
        if not isinstance(value_type, str) or value_type not in {"ENTITY_REF", "BOOLEAN_TOKEN", "SYMBOLIC_TOKEN"}:
            errors.append(f"QUALIFIER_SEMANTIC_TYPE_NOT_UNIQUE:{key}")
    if value.get("schema_version") != QUALIFIER_REGISTRY_VERSION:
        errors.append("QUALIFIER_REGISTRY_VERSION_INVALID")
    return {
        "status": "PASS" if not errors else "BLOCKED", "errors": errors,
        "qualifier_count": len(qualifiers),
        "value_types": {str(key): str(row.get("value_type")) for key, row in sorted(qualifiers.items()) if isinstance(row, Mapping)},
        "all_keys_have_one_value_type": not errors,
        "wire_scalar_type": "string",
        "ownership_in_v3": "EXCLUDED_AMBIGUOUS",
        "possession_in_v3": "EXCLUDED_AMBIGUOUS",
    }


def qualifier_semantic_ambiguity_audit() -> dict[str, Any]:
    rows = {}
    for key, semantic_audit in QUALIFIER_V1_AMBIGUITY_ROWS.items():
        legacy_types = LEGACY_QUALIFIER_TYPES.get(key, ())
        rows[key] = {
            "legacy_v2_python_types": sorted(item.__name__.upper() for item in legacy_types),
            "legacy_v2_contract_is_ambiguous": len(legacy_types) > 1,
            "v3_supported": False,
            "v3_resolution": "OMITTED_FROM_V3_QUALIFIER_REGISTRY",
            "semantic_audit": semantic_audit,
        }
    return {
        "schema_version": "source_claim_qualifier_v1_ambiguity_audit_v1",
        "status": "PASS",
        "audited_keys": rows,
        "ambiguous_keys_excluded_from_v3": all(not row["v3_supported"] for row in rows.values()),
        "v2_unchanged": True,
    }


def relation_signature_registry_v2() -> dict[str, Any]:
    return {"schema_version": RELATION_SIGNATURE_REGISTRY_VERSION, "signatures": copy.deepcopy(RELATION_SIGNATURES)}


def proposable_predicate_registry_v1(*, mappings: Mapping[str, Any] | None = None, signatures: Mapping[str, Any] | None = None) -> dict[str, Any]:
    mappings = mappings if isinstance(mappings, Mapping) else FACT_CLAIM_MAPPING
    signature_rows = signatures if isinstance(signatures, Mapping) else RELATION_SIGNATURES
    proposable: dict[str, dict[str, Any]] = {}
    excluded_legacy: dict[str, str] = {}
    unresolved: dict[str, str] = {}
    incomplete: dict[str, list[str]] = {}
    deferred_second_order: dict[str, dict[str, Any]] = {}
    required_signature_keys = {"predicate", "claim_type", "relation_class", "allowed_subject_kinds", "allowed_object_kinds", "allowed_qualifier_keys", "required_qualifier_keys"}
    for predicate, mapping in sorted(mappings.items()):
        if not isinstance(mapping, Mapping):
            unresolved[str(predicate)] = "RELATION_SIGNATURE_UNRESOLVED: mapping is not an object."
            continue
        if mapping.get("legacy_mapping"):
            excluded_legacy[str(predicate)] = str(mapping.get("legacy_mapping"))
            continue
        second_order = SECOND_ORDER_RELATION_SIGNATURES.get(str(predicate))
        if second_order is not None:
            if second_order.get("claim_type") != mapping.get("claim_type") or second_order.get("relation_class") != mapping.get("relation_class"):
                incomplete[str(predicate)] = ["SECOND_ORDER_SIGNATURE_MAPPING_MISMATCH"]
            else:
                deferred_second_order[str(predicate)] = copy.deepcopy(second_order)
            continue
        signature = signature_rows.get(str(predicate)) if isinstance(signature_rows, Mapping) else None
        if not isinstance(signature, Mapping):
            unresolved[str(predicate)] = UNRESOLVED_RELATION_REASONS.get(str(predicate), "RELATION_SIGNATURE_UNRESOLVED: no explicit typed signature exists.")
            continue
        missing = sorted(required_signature_keys - set(signature))
        if missing or signature.get("predicate") != predicate or signature.get("claim_type") != mapping.get("claim_type") or signature.get("relation_class") != mapping.get("relation_class"):
            incomplete[str(predicate)] = missing or ["SIGNATURE_MAPPING_MISMATCH"]
            continue
        # Keep the frozen first-order transport schema byte-for-byte stable.
        # Claim ordering is reported by the separate closure/ordering contracts.
        proposable[str(predicate)] = copy.deepcopy(dict(signature))
    return {
        "schema_version": PROPOSABLE_PREDICATE_REGISTRY_VERSION,
        "status": "PASS" if not incomplete and not unresolved else "BLOCKED",
        "predicates": proposable,
        "excluded_legacy_structural_predicates": excluded_legacy,
        "unresolved_predicates": unresolved,
        "incomplete_signatures": incomplete,
        "deferred_second_order_predicates": deferred_second_order,
        "predicate_count": len(proposable),
        "excluded_legacy_count": len(excluded_legacy),
        "unresolved_relation_count": len(unresolved) + len(incomplete),
        "first_order_unresolved_count": len(unresolved) + len(incomplete),
        "deferred_second_order_predicate_count": len(deferred_second_order),
        "provider_proposable_order": "FIRST_ORDER_ONLY",
    }


def relation_signature_completeness_audit(*, mappings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    predicates = proposable_predicate_registry_v1(mappings=mappings)
    errors = list(predicates.get("incomplete_signatures", {}).keys())
    signatures = predicates.get("predicates", {})
    qualifiers = QUALIFIER_REGISTRY
    for predicate, signature in signatures.items():
        if not signature.get("allowed_subject_kinds") or not signature.get("allowed_object_kinds"):
            errors.append(f"RELATION_KINDS_MISSING:{predicate}")
        if not set(signature.get("required_qualifier_keys", [])) <= set(signature.get("allowed_qualifier_keys", [])):
            errors.append(f"REQUIRED_QUALIFIER_NOT_ALLOWED:{predicate}")
        for key in signature.get("allowed_qualifier_keys", []):
            if key not in qualifiers:
                errors.append(f"RELATION_QUALIFIER_UNREGISTERED:{predicate}:{key}")
        relation_group = RELATION_REGISTRY.get(RELATION_CLASS_ALIASES.get(str(signature.get("relation_class")), str(signature.get("relation_class"))), {})
        compatible = {str(item) for row in relation_group.values() if isinstance(row, Mapping) for item in row.get("compatible_predicates", [])}
        if predicate not in compatible:
            errors.append(f"RELATION_SIGNATURE_NOT_BACKED_BY_RELATION_REGISTRY:{predicate}")
    return {
        "schema_version": "source_claim_relation_signature_completeness_audit_v3",
        "status": "PASS" if not errors and predicates.get("status") == "PASS" else "BLOCKED",
        "errors": sorted(set(errors)),
        "proposable_predicate_count": predicates["predicate_count"],
        "first_order_proposable_predicate_count": predicates["predicate_count"],
        "first_order_unresolved_count": predicates["first_order_unresolved_count"],
        "excluded_legacy_predicate_count": predicates["excluded_legacy_count"],
        "unresolved_relation_count": predicates["unresolved_relation_count"],
        "deferred_second_order_predicate_count": predicates["deferred_second_order_predicate_count"],
        "second_order_unresolved_count": 0,
        "proposable_predicates": sorted(signatures),
        "excluded_legacy_structural_predicates": predicates["excluded_legacy_structural_predicates"],
        "unresolved_predicates": predicates["unresolved_predicates"],
        "deferred_second_order_predicates": predicates["deferred_second_order_predicates"],
        "signature_fields_required": sorted({"predicate", "claim_type", "relation_class", "allowed_subject_kinds", "allowed_object_kinds", "allowed_qualifier_keys", "required_qualifier_keys"}),
        "predicate_name_inference": False,
        "source_prose_consulted": False,
    }


def second_order_relation_signature_registry_v1() -> dict[str, Any]:
    return {
        "schema_version": SECOND_ORDER_RELATION_SIGNATURE_REGISTRY_VERSION,
        "status": "READY_FOR_POST_FIRST_ORDER_VERIFICATION",
        "predicates": copy.deepcopy(SECOND_ORDER_RELATION_SIGNATURES),
        "predicate_count": len(SECOND_ORDER_RELATION_SIGNATURES),
        "unresolved_relation_count": 0,
        "provider_proposable_now": False,
        "execution_enabled": False,
    }


def second_order_relation_closure_audit() -> dict[str, Any]:
    registry = second_order_relation_signature_registry_v1()
    errors: list[str] = []
    mappings = FACT_CLAIM_MAPPING
    relation_contracts = RELATION_REGISTRY
    for predicate, signature in registry["predicates"].items():
        mapping = mappings.get(predicate, {})
        if signature.get("predicate") != predicate:
            errors.append(f"SECOND_ORDER_PREDICATE_FIELD_MISMATCH:{predicate}")
        if signature.get("claim_type") != mapping.get("claim_type") or signature.get("relation_class") != mapping.get("relation_class"):
            errors.append(f"SECOND_ORDER_MAPPING_MISMATCH:{predicate}")
        if signature.get("object_ref_domain") not in OBJECT_REF_DOMAINS:
            errors.append(f"SECOND_ORDER_OBJECT_DOMAIN_INVALID:{predicate}")
        if signature.get("subject_ref_domain") != "ENTITY_REF" or signature.get("allowed_subject_kinds") != ["CHARACTER"]:
            errors.append(f"SECOND_ORDER_SUBJECT_DOMAIN_INVALID:{predicate}")
        if signature.get("allowed_qualifier_keys") or signature.get("required_qualifier_keys"):
            errors.append(f"SECOND_ORDER_QUALIFIERS_MUST_BE_EMPTY:{predicate}")
        relation_group = relation_contracts.get(signature["relation_class"], {})
        compatible = {str(item) for row in relation_group.values() if isinstance(row, Mapping) for item in row.get("compatible_predicates", [])}
        if predicate not in compatible:
            errors.append(f"SECOND_ORDER_RELATION_NOT_BACKED_BY_RELATION_REGISTRY:{predicate}")
    return {
        "schema_version": "source_claim_second_order_relation_closure_audit_v1",
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(errors),
        "second_order_relation_count": registry["predicate_count"],
        "second_order_unresolved_count": registry["unresolved_relation_count"],
        "provider_proposable_now": registry["provider_proposable_now"],
        "existing_relation_registry_version": "director_claim_relation_registry_v1",
        "predicate_compatibility_preserved": not errors,
    }


def verified_first_order_claim_registry_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": VERIFIED_FIRST_ORDER_CLAIM_REGISTRY_VERSION,
        "status": "CONTRACT_ONLY_NOT_MATERIALIZED",
        "required_fields": [
            "claim_ref", "claim_type", "relation_class", "subject", "predicate", "object",
            "qualifiers", "semantic_verification_state", "authority",
        ],
        "admitted_semantic_verification_state": "SEMANTICALLY_VERIFIED_SOURCE_CLAIM",
        "admitted_authority": "SEMANTICALLY_VERIFIED_SOURCE_CLAIM",
        "blocked_states": ["UNTRUSTED_PROPOSED", "REJECTED", "AMBIGUOUS"],
        "materialized_in_this_phase": False,
        "production_writes": 0,
    }


def claim_ordering_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": CLAIM_ORDER_REGISTRY_VERSION,
        "status": "PASS",
        "first_order": "FIRST_ORDER_SOURCE_CLAIM",
        "second_order": "SECOND_ORDER_EPISTEMIC_CLAIM",
        "sequence": [
            "First-order Claim V3 Proposal",
            "First-order Claim Semantic Verification",
            "Verified First-Order Claim Registry",
            "Second-order Epistemic Claim Proposal",
            "Second-order Semantic Verification",
        ],
        "second_order_before_first_order_verification": False,
        "nested_claim_json": False,
        "inline_proposition": False,
        "provider_local_proposition_ids": False,
        "one_response_claim_graph": False,
    }


def validate_second_order_claim_reference(
    *, predicate: str, subject_ref: str, object_ref: str,
    input_entity_registry: Mapping[str, Any],
    verified_first_order_claim_registry: Mapping[str, Any],
    qualifiers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    signature = SECOND_ORDER_RELATION_SIGNATURES.get(predicate)
    if not isinstance(signature, Mapping):
        return {"status": "BLOCKED", "errors": [f"SECOND_ORDER_PREDICATE_UNREGISTERED:{predicate}"], "projection": None}
    if input_entity_registry.get("schema_version") != CLAIM_INPUT_ENTITY_REGISTRY_VERSION or input_entity_registry.get("status") != "PASS":
        errors.append("SECOND_ORDER_INPUT_ENTITY_REGISTRY_NOT_READY")
    if verified_first_order_claim_registry.get("schema_version") != VERIFIED_FIRST_ORDER_CLAIM_REGISTRY_VERSION or verified_first_order_claim_registry.get("status") != "PASS":
        errors.append("SECOND_ORDER_VERIFIED_CLAIM_REGISTRY_NOT_READY")
    entities = input_entity_registry.get("entities") if isinstance(input_entity_registry.get("entities"), Mapping) else {}
    subject = entities.get(subject_ref)
    if not isinstance(subject, Mapping):
        errors.append(f"SECOND_ORDER_SUBJECT_REF_UNKNOWN:{subject_ref}")
    elif str(subject.get("authority") or "") not in ALLOWED_ENTITY_AUTHORITIES:
        errors.append(f"SECOND_ORDER_SUBJECT_AUTHORITY_BLOCKED:{subject_ref}")
    elif str(subject.get("kind") or "") not in signature["allowed_subject_kinds"]:
        errors.append(f"SECOND_ORDER_SUBJECT_KIND_MISMATCH:{subject_ref}:{subject.get('kind')}")

    claim_rows = verified_first_order_claim_registry.get("claims") if isinstance(verified_first_order_claim_registry.get("claims"), Mapping) else {}
    if object_ref in entities:
        errors.append("SECOND_ORDER_OBJECT_DOMAIN_MISMATCH")
    else:
        target = claim_rows.get(object_ref)
        if not isinstance(target, Mapping):
            errors.append(f"SECOND_ORDER_TARGET_NOT_FOUND:{object_ref}")
        else:
            required_claim_fields = {
                "claim_ref", "claim_type", "relation_class", "subject", "predicate", "object",
                "qualifiers", "semantic_verification_state", "authority",
            }
            missing_claim_fields = sorted(required_claim_fields - set(target))
            if missing_claim_fields:
                errors.append("SECOND_ORDER_TARGET_SCHEMA_INCOMPLETE:" + ",".join(missing_claim_fields))
            first_order_predicates = proposable_predicate_registry_v1().get("predicates", {})
            first_order_signature = first_order_predicates.get(str(target.get("predicate") or ""))
            if not isinstance(first_order_signature, Mapping):
                errors.append("SECOND_ORDER_TARGET_NOT_FIRST_ORDER")
            elif target.get("claim_type") != first_order_signature.get("claim_type") or target.get("relation_class") != first_order_signature.get("relation_class"):
                errors.append("SECOND_ORDER_TARGET_SIGNATURE_MISMATCH")
            if (
                target.get("authority") != "SEMANTICALLY_VERIFIED_SOURCE_CLAIM"
                or target.get("semantic_verification_state") != "SEMANTICALLY_VERIFIED_SOURCE_CLAIM"
            ):
                errors.append("SECOND_ORDER_TARGET_AUTHORITY_NOT_VERIFIED")
            if str(target.get("claim_ref") or object_ref) != object_ref:
                errors.append("SECOND_ORDER_TARGET_REF_MISMATCH")

    if qualifiers is None:
        qualifiers = {}
    if not isinstance(qualifiers, Mapping):
        errors.append("SECOND_ORDER_QUALIFIERS_MUST_BE_OBJECT")
    elif qualifiers:
        errors.extend(f"SECOND_ORDER_QUALIFIER_NOT_ALLOWED:{key}" for key in sorted(str(key) for key in qualifiers))
    projection = None
    if not errors:
        projection = {
            "claim_order": "SECOND_ORDER_EPISTEMIC_CLAIM",
            "predicate": predicate,
            "claim_type": signature["claim_type"],
            "relation_class": signature["relation_class"],
            "subject_ref": subject_ref,
            "object_ref": object_ref,
            "object_ref_domain": signature["object_ref_domain"],
            "qualifiers": {},
            "execution_enabled": False,
        }
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "projection": projection, "contract_mock_only": True}


def first_order_relation_closure_audit() -> dict[str, Any]:
    audit = relation_signature_completeness_audit()
    registry = proposable_predicate_registry_v1()
    return {
        "schema_version": "source_claim_first_order_relation_closure_audit_v1",
        "status": "PASS" if audit["status"] == "PASS" and audit["first_order_unresolved_count"] == 0 else "BLOCKED",
        "first_order_proposable_predicate_count": registry["predicate_count"],
        "first_order_unresolved_count": audit["first_order_unresolved_count"],
        "first_order_predicates": sorted(registry["predicates"]),
        "deferred_second_order_predicate_count": registry["deferred_second_order_predicate_count"],
        "second_order_predicates_are_not_in_first_order_registry": not (set(registry["predicates"]) & set(registry["deferred_second_order_predicates"])),
    }


def build_claim_input_entity_registry(source_verified_registry: Mapping[str, Any], *, expected_fingerprint: str | None = None) -> dict[str, Any]:
    declared_fp = str(source_verified_registry.get("fingerprint") or "")
    # V7.7.7 computes this fingerprint before wrapping the compiled registry
    # with its top-level execution status. Exclude both that envelope field
    # and the fingerprint itself when checking the frozen authority payload.
    fingerprint_material = {
        str(key): value
        for key, value in source_verified_registry.items()
        if key not in {"fingerprint", "status"}
    }
    actual_fp = fingerprint(fingerprint_material)
    errors: list[str] = []
    if source_verified_registry.get("schema_version") != "source_verified_entity_registry_v1":
        errors.append("VERIFIED_ENTITY_REGISTRY_VERSION_INVALID")
    if source_verified_registry.get("status") != "SOURCE_ENTITY_SEMANTIC_VERIFICATION_VALIDATED":
        errors.append("VERIFIED_ENTITY_REGISTRY_NOT_VALIDATED")
    if declared_fp != actual_fp:
        errors.append("VERIFIED_ENTITY_REGISTRY_FINGERPRINT_INVALID")
    if expected_fingerprint and declared_fp != expected_fingerprint:
        errors.append("VERIFIED_ENTITY_REGISTRY_FINGERPRINT_DRIFT")
    allowed: dict[str, dict[str, Any]] = {}
    blocked: list[dict[str, str]] = []
    duplicates: set[str] = set()
    for collection_name in ("canonical_runtime_entities", "proposal_entities"):
        collection = source_verified_registry.get(collection_name)
        if not isinstance(collection, Mapping):
            errors.append(f"VERIFIED_ENTITY_COLLECTION_INVALID:{collection_name}")
            continue
        for raw_ref, raw_entity in collection.items():
            ref = str(raw_ref)
            if not isinstance(raw_entity, Mapping):
                blocked.append({"ref": ref, "authority": "INVALID_ROW"})
                continue
            authority = str(raw_entity.get("authority") or "")
            kind = str(raw_entity.get("kind") or "")
            state = str(raw_entity.get("verification_state") or "")
            canonical_flag = raw_entity.get("canonical")
            if ref in allowed:
                duplicates.add(ref)
                continue
            allowed_canonical = collection_name == "canonical_runtime_entities" and authority == "CANONICAL_RUNTIME" and canonical_flag is not False
            allowed_verified = collection_name == "proposal_entities" and authority == "SEMANTICALLY_VERIFIED_PROPOSAL" and state == "SEMANTICALLY_VERIFIED_PROPOSAL" and canonical_flag is not True
            if allowed_canonical or allowed_verified:
                if kind not in ENTITY_KINDS:
                    errors.append(f"ENTITY_KIND_UNSUPPORTED:{ref}")
                    continue
                allowed[ref] = {"ref": ref, "kind": kind, "authority": authority, "verification_state": state or "CANONICAL_RUNTIME", "canonical": allowed_canonical, "entity_fingerprint": str(raw_entity.get("fingerprint") or "")}
            else:
                blocked.append({"ref": ref, "authority": authority or "MISSING", "verification_state": state or "NOT_APPLICABLE"})
    if duplicates:
        errors.extend(f"DUPLICATE_ENTITY_REF:{ref}" for ref in sorted(duplicates))
    registry = {
        "schema_version": CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "source_verified_entity_registry_fingerprint": declared_fp,
        "allowed_authorities": sorted(ALLOWED_ENTITY_AUTHORITIES),
        "entities": dict(sorted(allowed.items())),
        "blocked_entities": sorted(blocked, key=lambda item: (item["ref"], item["authority"])),
        "canonical_entity_count": sum(row["authority"] == "CANONICAL_RUNTIME" for row in allowed.values()),
        "verified_proposal_count": sum(row["authority"] == "SEMANTICALLY_VERIFIED_PROPOSAL" for row in allowed.values()),
        "blocked_entity_count": len(blocked),
        "canonical_promotions": 0,
        "production_writes": 0,
    }
    registry["fingerprint"] = fingerprint({key: value for key, value in registry.items() if key != "fingerprint"})
    return registry


def claim_v3_candidate_schema(*, input_entity_registry: Mapping[str, Any], proposable_predicates: Mapping[str, Any]) -> dict[str, Any]:
    refs = sorted(str(ref) for ref in (input_entity_registry.get("entities") or {}))
    predicates = sorted(str(predicate) for predicate in (proposable_predicates.get("predicates") or {}))
    candidate = {
        "type": "object", "required": sorted(CLAIM_V3_REQUIRED_KEYS), "additionalProperties": False,
        "properties": {
            "schema_version": {"const": CLAIM_V3_VERSION},
            "subject_ref": {"type": "string", "enum": refs},
            "predicate": {"type": "string", "enum": predicates},
            "object_ref": {"type": "string", "enum": refs},
            "qualifiers": {"type": "object", "additionalProperties": {"type": "string", "minLength": 1}},
            "polarity": {"type": "string", "enum": list(POLARITIES)},
            "modality": {"type": "string", "enum": list(MODALITIES)},
            "evidence_refs": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems": True},
            "source_unit_refs": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems": True},
        },
    }
    return candidate


def claim_v3_candidate_set_schema(*, candidate_schema: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": CLAIM_V3_SET_VERSION,
        "title": "Source Semantic Claim Candidate Set V3",
        "type": "object", "required": ["schema_version", "claims"], "additionalProperties": False,
        "properties": {
            "schema_version": {"const": CLAIM_V3_SET_VERSION},
            "claims": {"type": "array", "items": copy.deepcopy(dict(candidate_schema))},
        },
    }


def count_schema_dialect_extensions(schema: Any) -> dict[str, int]:
    counts = {"union_type": 0, "oneOf": 0, "anyOf": 0, "dangling_ref": 0}
    forbidden = {"$ref", "$defs", "definitions", "oneOf", "anyOf", "allOf"}

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            if isinstance(node.get("type"), list):
                counts["union_type"] += 1
            for key, value in node.items():
                if key == "oneOf":
                    counts["oneOf"] += 1
                elif key == "anyOf":
                    counts["anyOf"] += 1
                if key == "$ref":
                    counts["dangling_ref"] += 1
                if key in forbidden and key not in {"oneOf", "anyOf", "$ref"}:
                    counts["dangling_ref"] += 1
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return counts


def decode_claim_qualifiers_v3(
    wire_qualifiers: Any,
    *,
    qualifier_registry: Mapping[str, Any],
    entity_registry: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(wire_qualifiers, Mapping):
        return {"status": "BLOCKED", "errors": ["QUALIFIERS_MUST_BE_OBJECT"], "typed_qualifiers": {}}
    registry_rows = qualifier_registry.get("qualifiers") if isinstance(qualifier_registry.get("qualifiers"), Mapping) else {}
    errors: list[str] = []
    typed: dict[str, Any] = {}
    for raw_key, raw_value in wire_qualifiers.items():
        key = str(raw_key)
        definition = registry_rows.get(key)
        if not isinstance(definition, Mapping):
            errors.append(f"UNKNOWN_QUALIFIER_KEY:{key}")
            continue
        value_type = definition.get("value_type")
        if not isinstance(value_type, str):
            errors.append(f"QUALIFIER_SEMANTIC_TYPE_NOT_UNIQUE:{key}")
            continue
        if not isinstance(raw_value, str) or not raw_value:
            errors.append(f"QUALIFIER_WIRE_VALUE_MUST_BE_NONEMPTY_STRING:{key}")
            continue
        if value_type == "ENTITY_REF":
            entity = entity_registry.get(raw_value)
            if not isinstance(entity, Mapping):
                errors.append(f"UNKNOWN_ENTITY_REF:{raw_value}")
                continue
            if str(entity.get("authority") or "") not in ALLOWED_ENTITY_AUTHORITIES:
                errors.append(f"ENTITY_AUTHORITY_BLOCKED:{raw_value}")
                continue
            typed[key] = {"value_type": value_type, "ref": raw_value, "kind": str(entity.get("kind") or "")}
        elif value_type == "BOOLEAN_TOKEN":
            if raw_value == "TRUE":
                typed[key] = {"value_type": value_type, "value": True}
            elif raw_value == "FALSE":
                typed[key] = {"value_type": value_type, "value": False}
            else:
                errors.append(f"BOOLEAN_TOKEN_INVALID:{key}")
        elif value_type == "SYMBOLIC_TOKEN":
            if re.fullmatch(SYMBOLIC_TOKEN_PATTERN, raw_value) is None:
                errors.append(f"SYMBOLIC_TOKEN_INVALID:{key}")
            else:
                typed[key] = {"value_type": value_type, "value": raw_value}
        else:
            errors.append(f"QUALIFIER_VALUE_TYPE_UNSUPPORTED:{key}:{value_type}")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "typed_qualifiers": dict(sorted(typed.items()))}


def validate_claim_v3_candidate(
    candidate: Any,
    *,
    input_entity_registry: Mapping[str, Any],
    evidence_unit_bindings: Mapping[str, Sequence[str]],
    allowed_source_unit_refs: Sequence[str],
    qualifier_registry: Mapping[str, Any] | None = None,
    proposable_predicates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(candidate, Mapping):
        return {"status": "BLOCKED", "errors": ["CLAIM_V3_CANDIDATE_MUST_BE_OBJECT"], "projection": None}
    actual_keys = {str(key) for key in candidate}
    errors.extend(f"CLAIM_V3_REQUIRED_FIELD_MISSING:{key}" for key in sorted(CLAIM_V3_REQUIRED_KEYS - actual_keys))
    errors.extend(f"CLAIM_V3_FORBIDDEN_FIELD:{key}" for key in sorted(actual_keys & CLAIM_V3_FORBIDDEN_FIELDS))
    errors.extend(f"CLAIM_V3_EXTRA_FIELD:{key}" for key in sorted(actual_keys - CLAIM_V3_REQUIRED_KEYS))
    if candidate.get("schema_version") != CLAIM_V3_VERSION:
        errors.append("CLAIM_V3_SCHEMA_VERSION_INVALID")
    if input_entity_registry.get("status") != "PASS":
        errors.append("CLAIM_INPUT_ENTITY_REGISTRY_NOT_READY")

    entity_rows = input_entity_registry.get("entities") if isinstance(input_entity_registry.get("entities"), Mapping) else {}
    predicate_rows = (proposable_predicates or proposable_predicate_registry_v1()).get("predicates", {})
    qualifier_contract = qualifier_registry or qualifier_registry_v2()
    if (proposable_predicates or {}).get("status", "PASS") != "PASS":
        errors.append("PROPOSABLE_PREDICATE_REGISTRY_NOT_READY")
    if qualifier_registry_audit(qualifier_contract).get("status") != "PASS":
        errors.append("QUALIFIER_REGISTRY_NOT_READY")
    predicate = str(candidate.get("predicate") or "")
    signature = predicate_rows.get(predicate) if isinstance(predicate_rows, Mapping) else None
    if not isinstance(signature, Mapping):
        errors.append(f"PREDICATE_NOT_PROPOSABLE:{predicate}")

    resolved_refs: dict[str, dict[str, Any]] = {}
    for field, allowed_kinds_key in (("subject_ref", "allowed_subject_kinds"), ("object_ref", "allowed_object_kinds")):
        ref = candidate.get(field)
        if not isinstance(ref, str) or not ref:
            errors.append(f"{field.upper()}_INVALID")
            continue
        entity = entity_rows.get(ref)
        if not isinstance(entity, Mapping):
            errors.append(f"UNKNOWN_ENTITY_REF:{ref}")
            continue
        authority = str(entity.get("authority") or "")
        if authority not in ALLOWED_ENTITY_AUTHORITIES:
            errors.append(f"ENTITY_AUTHORITY_BLOCKED:{ref}:{authority or 'MISSING'}")
            continue
        kind = str(entity.get("kind") or "")
        resolved_refs[field] = {"ref": ref, "kind": kind, "authority": authority}
        allowed_kinds = set(str(item) for item in (signature or {}).get(allowed_kinds_key, []))
        if signature and kind not in allowed_kinds:
            side = "SUBJECT" if field == "subject_ref" else "OBJECT"
            errors.append(f"RELATION_{side}_KIND_MISMATCH:{predicate}:{kind}")

    qualifiers = candidate.get("qualifiers")
    if not isinstance(qualifiers, Mapping):
        errors.append("QUALIFIERS_MUST_BE_OBJECT")
        qualifier_result = {"status": "BLOCKED", "errors": ["QUALIFIERS_MUST_BE_OBJECT"], "typed_qualifiers": {}}
    else:
        allowed_qualifiers = set(str(item) for item in (signature or {}).get("allowed_qualifier_keys", []))
        for key in qualifiers:
            if key not in allowed_qualifiers:
                if key not in (qualifier_contract.get("qualifiers") or {}):
                    errors.append(f"UNKNOWN_QUALIFIER_KEY:{key}")
                else:
                    errors.append(f"QUALIFIER_NOT_ALLOWED_FOR_PREDICATE:{predicate}:{key}")
        required_qualifiers = set(str(item) for item in (signature or {}).get("required_qualifier_keys", []))
        errors.extend(f"REQUIRED_QUALIFIER_MISSING:{predicate}:{key}" for key in sorted(required_qualifiers - set(qualifiers)))
        qualifier_result = decode_claim_qualifiers_v3(qualifiers, qualifier_registry=qualifier_contract, entity_registry=entity_rows)
        errors.extend(qualifier_result.get("errors", []))
        kind_constraints = (signature or {}).get("qualifier_entity_kind_constraints", {})
        for key, allowed_kinds in kind_constraints.items() if isinstance(kind_constraints, Mapping) else []:
            resolved = qualifier_result.get("typed_qualifiers", {}).get(key, {})
            if resolved and resolved.get("kind") not in set(str(item) for item in allowed_kinds):
                errors.append(f"QUALIFIER_ENTITY_KIND_MISMATCH:{key}:{resolved.get('kind')}")

    if candidate.get("polarity") not in POLARITIES:
        errors.append("CLAIM_V3_POLARITY_INVALID")
    if candidate.get("modality") not in MODALITIES:
        errors.append("CLAIM_V3_MODALITY_INVALID")
    refs_by_field: dict[str, list[str]] = {}
    for field in ("evidence_refs", "source_unit_refs"):
        raw_refs = candidate.get(field)
        if not isinstance(raw_refs, list) or not raw_refs or not all(isinstance(item, str) and item for item in raw_refs):
            errors.append(f"{field.upper()}_INVALID")
            refs_by_field[field] = []
            continue
        refs = [str(item) for item in raw_refs]
        if len(refs) != len(set(refs)):
            errors.append(f"{field.upper()}_DUPLICATE")
        refs_by_field[field] = refs

    allowed_units = set(str(item) for item in allowed_source_unit_refs)
    candidate_units = set(refs_by_field.get("source_unit_refs", []))
    candidate_evidence = set(refs_by_field.get("evidence_refs", []))
    for unit_ref in sorted(candidate_units - allowed_units):
        errors.append(f"SOURCE_UNIT_REF_UNKNOWN:{unit_ref}")
    if isinstance(evidence_unit_bindings, Mapping):
        for evidence_ref in sorted(candidate_evidence):
            bound_units = set(str(item) for item in evidence_unit_bindings.get(evidence_ref, []))
            if not bound_units:
                errors.append(f"EVIDENCE_REF_UNKNOWN:{evidence_ref}")
            elif not bound_units & candidate_units:
                errors.append(f"EVIDENCE_UNIT_BINDING_MISMATCH:{evidence_ref}")
        for unit_ref in sorted(candidate_units):
            if not any(unit_ref in set(str(item) for item in evidence_unit_bindings.get(evidence_ref, [])) for evidence_ref in candidate_evidence):
                errors.append(f"SOURCE_UNIT_WITHOUT_BOUND_EVIDENCE:{unit_ref}")

    projection = None
    if not errors and isinstance(signature, Mapping):
        projection = {
            "schema_version": CLAIM_V3_PROJECTION_VERSION,
            "claim_type": signature["claim_type"],
            "relation_class": signature["relation_class"],
            "subject": {"ref": resolved_refs["subject_ref"]["ref"], "kind": resolved_refs["subject_ref"]["kind"]},
            "predicate": predicate,
            "object": {"ref": resolved_refs["object_ref"]["ref"], "kind": resolved_refs["object_ref"]["kind"]},
            "qualifiers": qualifier_result["typed_qualifiers"],
            "polarity": candidate["polarity"], "modality": candidate["modality"],
            "evidence_refs": sorted(refs_by_field["evidence_refs"]),
            "source_unit_refs": sorted(refs_by_field["source_unit_refs"]),
        }
    return {
        "status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)),
        "resolved_subject": resolved_refs.get("subject_ref"), "resolved_object": resolved_refs.get("object_ref"),
        "claim_type": signature.get("claim_type") if isinstance(signature, Mapping) else None,
        "relation_class": signature.get("relation_class") if isinstance(signature, Mapping) else None,
        "qualifier_validation": qualifier_result, "projection": projection,
    }


def validate_claim_v3_set(
    value: Any,
    *,
    input_entity_registry: Mapping[str, Any],
    evidence_unit_bindings: Mapping[str, Sequence[str]],
    allowed_source_unit_refs: Sequence[str],
    qualifier_registry: Mapping[str, Any] | None = None,
    proposable_predicates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": "BLOCKED", "errors": ["CLAIM_V3_SET_MUST_BE_OBJECT"], "candidate_results": []}
    errors: list[str] = []
    expected_keys = {"schema_version", "claims"}
    errors.extend(f"CLAIM_V3_SET_REQUIRED_FIELD_MISSING:{key}" for key in sorted(expected_keys - set(value)))
    errors.extend(f"CLAIM_V3_SET_EXTRA_FIELD:{key}" for key in sorted(set(value) - expected_keys))
    if value.get("schema_version") != CLAIM_V3_SET_VERSION:
        errors.append("CLAIM_V3_SET_SCHEMA_VERSION_INVALID")
    candidates = value.get("claims")
    if not isinstance(candidates, list):
        errors.append("CLAIM_V3_SET_CLAIMS_MUST_BE_ARRAY")
        candidates = []
    results = [validate_claim_v3_candidate(
        item, input_entity_registry=input_entity_registry,
        evidence_unit_bindings=evidence_unit_bindings,
        allowed_source_unit_refs=allowed_source_unit_refs,
        qualifier_registry=qualifier_registry, proposable_predicates=proposable_predicates,
    ) for item in candidates]
    for index, result in enumerate(results):
        errors.extend(f"CLAIM_V3_CANDIDATE_{index:04d}:{error}" for error in result["errors"])
    fps = [claim_v3_candidate_fingerprint(result["projection"]) for result in results if result.get("projection")]
    if len(fps) != len(set(fps)):
        errors.append("DUPLICATE_CLAIM_CANDIDATE")
    return {
        "status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)),
        "candidate_count": len(candidates), "valid_count": sum(result["status"] == "PASS" for result in results),
        "blocked_count": sum(result["status"] != "PASS" for result in results), "candidate_results": results,
    }


def claim_v3_candidate_fingerprint(
    projection: Mapping[str, Any], *, entity_registry_fingerprint: str = "",
    qualifier_registry_version: str = QUALIFIER_REGISTRY_VERSION,
    relation_signature_registry_version: str = RELATION_SIGNATURE_REGISTRY_VERSION,
    predicate_registry_version: str = PROPOSABLE_PREDICATE_REGISTRY_VERSION,
) -> str:
    material = {
        "schema_version": CLAIM_V3_PROJECTION_VERSION,
        "semantic_fields": {key: projection.get(key) for key in ("claim_type", "relation_class", "subject", "predicate", "object", "qualifiers", "polarity", "modality")},
        "evidence_refs": sorted(str(item) for item in projection.get("evidence_refs", [])),
        "source_unit_refs": sorted(str(item) for item in projection.get("source_unit_refs", [])),
        "registry_versions": {
            "claim_v3": CLAIM_V3_VERSION,
            "input_entity_registry_fingerprint": entity_registry_fingerprint,
            "qualifier_registry": qualifier_registry_version,
            "relation_signature_registry": relation_signature_registry_version,
            "proposable_predicate_registry": predicate_registry_version,
        },
    }
    return fingerprint(material)


def assign_program_owned_claim_ids(
    candidate_results: Sequence[Mapping[str, Any]], *, entity_registry_fingerprint: str,
) -> dict[str, Any]:
    valid = [row for row in candidate_results if row.get("status") == "PASS" and isinstance(row.get("projection"), Mapping)]
    prepared = []
    for row in valid:
        projection = dict(row["projection"])
        candidate_fp = claim_v3_candidate_fingerprint(projection, entity_registry_fingerprint=entity_registry_fingerprint)
        prepared.append((candidate_fp, projection))
    prepared.sort(key=lambda item: item[0])
    if len({candidate_fp for candidate_fp, _ in prepared}) != len(prepared):
        return {"status": "BLOCKED", "errors": ["DUPLICATE_CLAIM_CANDIDATE"], "id_owner": "program", "provider_supplied_id": False, "rows": []}
    rows = []
    for index, (candidate_fp, projection) in enumerate(prepared, start=1):
        rows.append({
            "claim_id": f"SCC_{index:04d}",
            "candidate_fingerprint": candidate_fp,
            "authority": "UNTRUSTED_PROPOSED",
            "canonical": False,
            "projection": projection,
        })
    return {
        "status": "PASS", "schema_version": CLAIM_V3_SET_VERSION,
        "id_owner": "program", "provider_supplied_id": False,
        "rows": rows,
        "fingerprint": fingerprint({"schema_version": CLAIM_V3_SET_VERSION, "rows": rows}),
        "candidate_fingerprint_inputs": [row["candidate_fingerprint"] for row in rows],
    }


def claim_v2_immutable_blocker_audit() -> dict[str, Any]:
    schema = claim_v2_schema()
    compiled = compile_provider_strict_schema(schema)
    canonical_candidate_schema = schema["properties"]["claims"]["items"]
    return {
        "schema_version": "claim_v2_immutable_blocker_audit_v1",
        "status": "LEGACY_BLOCKED_UNION_TYPE" if compiled["audit"]["status"] == "BLOCKED" and any(error.startswith("UNION_TYPE_UNSUPPORTED:") for error in compiled["audit"]["errors"]) else "UNEXPECTED_V2_STATE",
        "candidate_schema_version": "source_semantic_claim_candidate_v2",
        "candidate_set_schema_version": CLAIM_V2_SET_VERSION,
        "candidate_schema_fingerprint": fingerprint(canonical_candidate_schema),
        "candidate_set_schema_fingerprint": fingerprint(schema),
        "compiler_status": compiled["audit"]["status"],
        "compiler_errors": compiled["audit"]["errors"],
        "qualifier_contract": canonical_candidate_schema["properties"]["qualifiers"],
        "v2_mutated": False,
        "one_of_patch_used": False,
        "v3_does_not_rewrite_v2": True,
    }


__all__ = [
    "CLAIM_V3_VERSION", "CLAIM_V3_SET_VERSION", "CLAIM_INPUT_ENTITY_REGISTRY_VERSION",
    "QUALIFIER_REGISTRY_VERSION", "RELATION_SIGNATURE_REGISTRY_VERSION",
    "PROPOSABLE_PREDICATE_REGISTRY_VERSION", "CLAIM_V3_REQUIRED_KEYS", "CLAIM_V3_FORBIDDEN_FIELDS",
    "QUALIFIER_REGISTRY", "RELATION_SIGNATURES", "qualifier_registry_v2", "qualifier_registry_audit",
    "qualifier_semantic_ambiguity_audit", "relation_signature_registry_v2", "proposable_predicate_registry_v1",
    "relation_signature_completeness_audit", "build_claim_input_entity_registry", "claim_v3_candidate_contract",
    "claim_v3_candidate_set_contract", "claim_v3_candidate_schema", "claim_v3_candidate_set_schema",
    "count_schema_dialect_extensions", "decode_claim_qualifiers_v3", "validate_claim_v3_candidate",
    "validate_claim_v3_set", "claim_v3_candidate_fingerprint", "assign_program_owned_claim_ids",
    "claim_v2_immutable_blocker_audit", "SECOND_ORDER_RELATION_SIGNATURE_REGISTRY_VERSION",
    "VERIFIED_FIRST_ORDER_CLAIM_REGISTRY_VERSION", "CLAIM_ORDER_REGISTRY_VERSION",
    "OBJECT_REF_DOMAINS", "SECOND_ORDER_RELATION_SIGNATURES", "second_order_relation_signature_registry_v1",
    "second_order_relation_closure_audit", "first_order_relation_closure_audit",
    "verified_first_order_claim_registry_contract_v1", "claim_ordering_contract_v1",
    "validate_second_order_claim_reference",
]
