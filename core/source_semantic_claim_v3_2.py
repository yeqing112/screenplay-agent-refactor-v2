"""Provider-free Claim V3.2 execution contracts.

V3 and V3.1 registries remain immutable historical contracts. This module
versions current execution separately, validates relation roles generically,
and provides no Provider or persistence access.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping, Sequence

from .provider_structured_output_qualification import fingerprint
from .source_semantic_claim_v3_1 import (
    DEFERRED_SECOND_ORDER,
    PROGRAM_DETERMINISTIC,
    PROVIDER_PROPOSABLE,
    first_order_relation_ownership_registry_v1,
    qualifier_registry_v3,
    relation_signature_registry_v3,
)
from .source_semantic_claim_v3 import CLAIM_V3_REQUIRED_KEYS, RELATION_SIGNATURES


RELATION_SIGNATURE_REGISTRY_V4_VERSION = "source_claim_relation_signature_registry_v4"
QUALIFIER_REGISTRY_V4_VERSION = "source_claim_qualifier_registry_v4"
PROVIDER_PREDICATE_REGISTRY_V3_VERSION = "source_claim_proposal_predicate_registry_v3"
ROLE_REF_CONSTRAINT_VERSION = "source_claim_role_ref_constraint_v1"
ENTITY_REF_QUALIFIER_DOMAIN_AUDIT_VERSION = "provider_entity_ref_qualifier_domain_audit_v1"
PROMPT_CONTRACT_V3_2_VERSION = "source_claim_predicate_prompt_contract_v3_2"
PROPOSAL_ATTEMPT_ID = "v7.7.10-source-semantic-claim-v3-2-reproposal-single-call"


def qualifier_registry_v4() -> dict[str, Any]:
    prior = qualifier_registry_v3()
    return {
        "schema_version": QUALIFIER_REGISTRY_V4_VERSION,
        "supersedes_for_new_execution_only": prior["schema_version"],
        "qualifiers": {"guided_character": {"value_type": "ENTITY_REF"}},
        "wire_value_type": "string",
        "excluded_from_current_provider_surface": {
            "speaker_binding": "PROGRAM_OWNED_PROVENANCE",
            "destination": "DUPLICATES_OBJECT_REF",
            "transfer_source": "ENTITY_REF_DOMAIN_UNRESOLVED",
            "property_domain": "NO_CURRENT_EXECUTABLE_PROVIDER_RELATION",
            "state_domain": "NO_CURRENT_EXECUTABLE_PROVIDER_RELATION",
            "light_state": "NO_CURRENT_EXECUTABLE_PROVIDER_RELATION",
        },
        "historical_v3_registry_mutated": False,
    }


def relation_signature_registry_v4() -> dict[str, Any]:
    prior = relation_signature_registry_v3()
    signatures = copy.deepcopy(prior["signatures"])
    signatures["enter_guided"].update({
        "allowed_qualifier_keys": ["guided_character"],
        "required_qualifier_keys": ["guided_character"],
        "qualifier_entity_kind_constraints": {"guided_character": ["CHARACTER"]},
        "ref_constraints": [{
            "operator": "NOT_EQUAL",
            "left_role": "subject_ref",
            "right_role": "qualifier_ref:guided_character",
        }],
    })
    signatures["received_by"].update({
        "allowed_qualifier_keys": [],
        "required_qualifier_keys": [],
        "qualifier_entity_kind_constraints": {},
        "ref_constraints": [],
    })
    signatures["left_by"]["allowed_qualifier_keys"] = []
    signatures["left_by"]["required_qualifier_keys"] = []
    signatures["left_by"]["ref_constraints"] = []
    for predicate in ("has_property", "state_value"):
        signatures[predicate]["allowed_qualifier_keys"] = []
        signatures[predicate]["required_qualifier_keys"] = []
        signatures[predicate]["qualifier_entity_kind_constraints"] = {}
        signatures[predicate]["ref_constraints"] = []
    signatures["speech_act"].update({
        "allowed_qualifier_keys": [], "required_qualifier_keys": [], "ref_constraints": [],
        "proposal_owner": PROGRAM_DETERMINISTIC, "proposal_mode": PROGRAM_DETERMINISTIC,
        "provider_proposable": False,
    })
    for predicate in ("enter_guided", "has_property", "left_by", "received_by", "state_value"):
        signatures[predicate]["proposal_owner"] = PROVIDER_PROPOSABLE
        signatures[predicate]["proposal_mode"] = PROVIDER_PROPOSABLE
        signatures[predicate]["provider_proposable"] = True
        signatures[predicate].setdefault("ref_constraints", [])
    return {
        "schema_version": RELATION_SIGNATURE_REGISTRY_V4_VERSION,
        "supersedes_for_new_execution_only": prior["schema_version"],
        "signatures": signatures,
        "historical_v2_and_v3_registries_mutated": False,
    }


def role_ref_constraint_contract_v1() -> dict[str, Any]:
    return {
        "schema_version": ROLE_REF_CONSTRAINT_VERSION,
        "supported_operators": ["NOT_EQUAL"],
        "role_resolution": "resolved typed role refs plus qualifier_ref:<key> refs",
        "source_text_consulted": False,
        "surface_forms_consulted": False,
        "predicate_spelling_consulted": False,
    }


def validate_relation_role_ref_constraints(
    *,
    claim: Mapping[str, Any],
    signature: Mapping[str, Any],
    typed_qualifiers: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply generic role-ref operators to resolved refs, never source text."""
    roles: dict[str, str] = {}
    for role in ("subject_ref", "object_ref"):
        if isinstance(claim.get(role), str):
            roles[role] = str(claim[role])
    for key, value in typed_qualifiers.items():
        if isinstance(value, Mapping) and value.get("value_type") == "ENTITY_REF" and isinstance(value.get("ref"), str):
            roles[f"qualifier_ref:{key}"] = str(value["ref"])
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    constraints = signature.get("ref_constraints") if isinstance(signature.get("ref_constraints"), list) else []
    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, Mapping):
            errors.append(f"RELATION_REF_CONSTRAINT_INVALID:{index}")
            continue
        operator = constraint.get("operator")
        left_role = str(constraint.get("left_role") or "")
        right_role = str(constraint.get("right_role") or "")
        left_ref = roles.get(left_role)
        right_ref = roles.get(right_role)
        row_errors: list[str] = []
        if operator != "NOT_EQUAL":
            row_errors.append(f"RELATION_REF_CONSTRAINT_OPERATOR_UNSUPPORTED:{operator}")
        if left_ref is None or right_ref is None:
            row_errors.append(f"RELATION_REF_CONSTRAINT_ROLE_UNRESOLVED:{left_role}:{right_role}")
        elif operator == "NOT_EQUAL" and left_ref == right_ref:
            row_errors.append(f"RELATION_REF_CONSTRAINT_VIOLATION:{signature.get('predicate')}:{left_role}:{right_role}")
        errors.extend(row_errors)
        results.append({
            "operator": operator, "left_role": left_role, "right_role": right_role,
            "left_ref": left_ref, "right_ref": right_ref,
            "status": "BLOCKED" if row_errors else "PASS", "errors": row_errors,
        })
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "resolved_roles": roles,
        "constraint_results": results,
        "inputs_are_typed_roles_only": True,
    }


def provider_entity_ref_qualifier_domain_audit(
    *,
    qualifier_registry: Mapping[str, Any],
    relation_registry: Mapping[str, Any],
) -> dict[str, Any]:
    qualifier_rows = qualifier_registry.get("qualifiers") if isinstance(qualifier_registry.get("qualifiers"), Mapping) else {}
    signatures = relation_registry.get("signatures") if isinstance(relation_registry.get("signatures"), Mapping) else {}
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for predicate, signature in sorted(signatures.items(), key=lambda item: str(item[0])):
        if not isinstance(signature, Mapping) or signature.get("proposal_owner") != PROVIDER_PROPOSABLE:
            continue
        constraints = signature.get("qualifier_entity_kind_constraints") if isinstance(signature.get("qualifier_entity_kind_constraints"), Mapping) else {}
        for key in sorted({str(item) for item in signature.get("allowed_qualifier_keys", [])}):
            definition = qualifier_rows.get(key)
            if not isinstance(definition, Mapping):
                errors.append(f"PROVIDER_QUALIFIER_UNREGISTERED:{predicate}:{key}")
                continue
            if definition.get("value_type") != "ENTITY_REF":
                continue
            domain = constraints.get(key)
            valid = isinstance(domain, list) and bool(domain) and all(isinstance(kind, str) and kind for kind in domain)
            if not valid:
                errors.append(f"PROVIDER_ENTITY_REF_QUALIFIER_DOMAIN_MISSING:{predicate}:{key}")
            rows.append({
                "predicate": str(predicate), "qualifier": key,
                "value_type": "ENTITY_REF",
                "allowed_entity_kinds": list(domain) if isinstance(domain, list) else [],
                "status": "PASS" if valid else "BLOCKED",
            })
    return {
        "schema_version": ENTITY_REF_QUALIFIER_DOMAIN_AUDIT_VERSION,
        "status": "PASS" if not errors else "BLOCKED",
        "rows": rows,
        "provider_entity_ref_qualifier_use_count": len(rows),
        "unresolved_entity_ref_qualifier_domain_count": sum(row["status"] != "PASS" for row in rows),
        "errors": sorted(set(errors)),
    }


def provider_predicate_registry_v3(
    *,
    relation_registry: Mapping[str, Any],
    qualifier_registry: Mapping[str, Any],
    entity_registry: Mapping[str, Any],
) -> dict[str, Any]:
    signatures = relation_registry.get("signatures") if isinstance(relation_registry.get("signatures"), Mapping) else {}
    entities = entity_registry.get("entities") if isinstance(entity_registry.get("entities"), Mapping) else {}
    counts = Counter(str(row.get("kind") or "") for row in entities.values() if isinstance(row, Mapping))
    qualifier_rows = qualifier_registry.get("qualifiers") if isinstance(qualifier_registry.get("qualifiers"), Mapping) else {}
    executable: dict[str, dict[str, Any]] = {}
    dormant: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, raw in sorted(signatures.items(), key=lambda item: str(item[0])):
        if not isinstance(raw, Mapping):
            errors.append(f"RELATION_SIGNATURE_INVALID:{name}")
            continue
        if raw.get("proposal_owner") != PROVIDER_PROPOSABLE:
            continue
        subject_kinds = sorted(set(raw.get("allowed_subject_kinds") or []))
        object_kinds = sorted(set(raw.get("allowed_object_kinds") or []))
        subject_counts = {kind: counts[kind] for kind in subject_kinds}
        object_counts = {kind: counts[kind] for kind in object_kinds}
        missing: list[str] = []
        required_qualifier_domains: dict[str, dict[str, int]] = {}
        kind_constraints = raw.get("qualifier_entity_kind_constraints") if isinstance(raw.get("qualifier_entity_kind_constraints"), Mapping) else {}
        for key in sorted(set(raw.get("required_qualifier_keys") or [])):
            q = qualifier_rows.get(key)
            if not isinstance(q, Mapping):
                errors.append(f"REQUIRED_QUALIFIER_NOT_REGISTERED:{name}:{key}")
                missing.append(f"QUALIFIER_NOT_REGISTERED:{key}")
            elif q.get("value_type") == "ENTITY_REF":
                domain = kind_constraints.get(key)
                if not isinstance(domain, list) or not domain:
                    errors.append(f"REQUIRED_ENTITY_REF_QUALIFIER_DOMAIN_MISSING:{name}:{key}")
                    missing.append(f"QUALIFIER_DOMAIN_MISSING:{key}")
                else:
                    available = {kind: counts[kind] for kind in domain}
                    required_qualifier_domains[key] = available
                    if not any(available.values()):
                        missing.append(f"QUALIFIER_ENTITY_KIND_UNAVAILABLE:{key}")
        if not subject_kinds or not object_kinds:
            errors.append(f"RELATION_KIND_DOMAIN_EMPTY:{name}")
        if not any(subject_counts.values()):
            missing.append("SUBJECT_KIND_UNAVAILABLE")
        if not any(object_counts.values()):
            missing.append("OBJECT_KIND_UNAVAILABLE")
        row = {
            **copy.deepcopy(dict(raw)),
            "predicate": str(name),
            "available_subject_kind_counts": subject_counts,
            "available_object_kind_counts": object_counts,
            "required_qualifier_entity_kind_counts": required_qualifier_domains,
            "missing_type_dependencies": missing,
            "execution_status": "EXECUTABLE" if not missing else "TYPE_DEPENDENCY_UNAVAILABLE",
        }
        (executable if row["execution_status"] == "EXECUTABLE" else dormant)[str(name)] = row
    domain_audit = provider_entity_ref_qualifier_domain_audit(qualifier_registry=qualifier_registry, relation_registry=relation_registry)
    return {
        "schema_version": PROVIDER_PREDICATE_REGISTRY_V3_VERSION,
        "status": "PASS" if not errors and domain_audit["status"] == "PASS" else "BLOCKED",
        "predicates": executable,
        "dormant_predicates": dormant,
        "predicate_count": len(executable),
        "dormant_predicate_count": len(dormant),
        "program_deterministic_predicates": [name for name, row in sorted(signatures.items()) if isinstance(row, Mapping) and row.get("proposal_owner") == PROGRAM_DETERMINISTIC],
        "second_order_predicates": ["knows", "uncertainty"],
        "second_order_provider_proposable": False,
        "entity_ref_qualifier_domain_audit_status": domain_audit["status"],
        "semantics": "TYPE_EXECUTABLE != SOURCE_SUPPORTED",
        "errors": sorted(set(errors + domain_audit["errors"])),
        "source_text_consulted": False,
        "predicate_name_semantics_inferred": False,
    }


_DEFINITIONS = {
    "enter_guided": "One CHARACTER guides a DIFFERENT CHARACTER into one LOCATION. subject_ref is the guide, object_ref is the destination, and guided_character is the guided person. All three roles are required.",
    "left_by": "A CHARACTER explicitly leaves one OBJECT. This relation has no qualifiers.",
    "received_by": "A CHARACTER explicitly receives one OBJECT. Do not infer who transferred it. This relation has no qualifiers.",
    "has_property": "An OBJECT has one typed PROPERTY_VALUE entity.",
    "state_value": "An ENVIRONMENT has one typed STATE_VALUE entity.",
}


def predicate_prompt_contract_v3_2(relation_registry: Mapping[str, Any]) -> dict[str, Any]:
    signatures = relation_registry.get("signatures") if isinstance(relation_registry.get("signatures"), Mapping) else {}
    rows: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, signature in sorted(signatures.items()):
        if not isinstance(signature, Mapping):
            errors.append(f"PREDICATE_SEMANTIC_DEFINITION_MISSING:{name}")
            continue
        # Program-owned and deferred signatures are intentionally outside the
        # Provider prompt. Definitions are required only for Provider-owned rows.
        if signature.get("proposal_owner") != PROVIDER_PROPOSABLE:
            continue
        if name not in _DEFINITIONS:
            errors.append(f"PREDICATE_SEMANTIC_DEFINITION_MISSING:{name}")
            continue
        rows[name] = {
            "predicate": name,
            "proposal_owner": signature.get("proposal_owner"),
            "allowed_subject_kinds": list(signature.get("allowed_subject_kinds") or []),
            "allowed_object_kinds": list(signature.get("allowed_object_kinds") or []),
            "allowed_qualifier_keys": list(signature.get("allowed_qualifier_keys") or []),
            "required_qualifier_keys": list(signature.get("required_qualifier_keys") or []),
            "semantic_definition": _DEFINITIONS[name],
        }
    return {
        "schema_version": PROMPT_CONTRACT_V3_2_VERSION,
        "status": "PASS" if not errors else "BLOCKED",
        "predicates": rows,
        "story_specific_examples": False,
        "source_prose_used_to_define_predicates": False,
        "errors": sorted(set(errors)),
    }


def build_reproposal_prompt(
    *,
    source_units: Sequence[Mapping[str, Any]],
    provider_entity_view: Mapping[str, Any],
    provider_registry: Mapping[str, Any],
    predicate_contract: Mapping[str, Any],
    qualifier_registry: Mapping[str, Any],
    polarities: Sequence[str],
    modalities: Sequence[str],
) -> tuple[str, str]:
    import json

    executable = provider_registry.get("predicates") if isinstance(provider_registry.get("predicates"), Mapping) else {}
    definitions = predicate_contract.get("predicates") if isinstance(predicate_contract.get("predicates"), Mapping) else {}
    predicate_view = {name: definitions[name] for name in sorted(executable) if name in definitions}
    all_qualifiers = qualifier_registry.get("qualifiers") if isinstance(qualifier_registry.get("qualifiers"), Mapping) else {}
    allowed_keys = sorted({key for signature in executable.values() for key in signature.get("allowed_qualifier_keys", [])})
    qualifier_view = {key: all_qualifiers[key] for key in allowed_keys if key in all_qualifiers}
    rows: list[dict[str, Any]] = []
    for unit in source_units:
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        rows.append({
            "source_unit_ref": str(unit.get("unit_id") or ""),
            "source_type": str(unit.get("source_type") or ""),
            "evidence_refs": list(unit.get("source_evidence_refs") or []),
            "exact_evidence_text": str(evidence.get("text") or ""),
        })
    system = (
        "Propose zero or more atomic FIRST_ORDER claims that are explicitly supported by the supplied frozen source evidence "
        "and fully expressible in one of the listed typed relations. Return one JSON object matching the strict schema, without markdown. "
        "A source unit may produce zero or more claims. Do not force meaning into the closest predicate. If a required participant, "
        "argument, provenance, state, or modality cannot be preserved, omit the claim. Do not infer, repair, normalize, or invent facts. "
        "Use only the supplied entity refs; display forms explain refs but never identify entities. Use only executable predicates and the "
        "listed qualifier rules. Do not return entity kinds, claim types, relation classes, IDs, or authority fields."
    )
    user = (
        "Executable predicate definitions and exact qualifier rules:\n"
        + json.dumps(predicate_view, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n\nProvider-writable qualifier definitions:\n"
        + json.dumps(qualifier_view, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n\nAllowed entity refs (display forms are explanatory only):\n"
        + json.dumps(provider_entity_view.get("entities", {}), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n\nAllowed polarity values:\n"
        + json.dumps(list(polarities), ensure_ascii=False)
        + "\n\nAllowed modality values:\n"
        + json.dumps(list(modalities), ensure_ascii=False)
        + "\n\nFrozen SourceAuthoringUnits and exact evidence text:\n"
        + json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2)
    )
    return system, user


def validate_provider_candidate_v3_2(
    candidate: Mapping[str, Any], *,
    provider_registry: Mapping[str, Any],
    relation_registry: Mapping[str, Any],
    entity_registry: Mapping[str, Any],
    qualifier_registry: Mapping[str, Any],
    evidence_unit_bindings: Mapping[str, Sequence[str]],
    allowed_source_unit_refs: Sequence[str],
) -> dict[str, Any]:
    from .source_semantic_claim_v3_1 import validate_provider_candidate_v3_1

    base = validate_provider_candidate_v3_1(
        candidate,
        provider_registry=provider_registry,
        entity_registry=entity_registry,
        qualifier_registry=qualifier_registry,
    )
    errors = list(base.get("errors", []))
    signature_rows = relation_registry.get("signatures") if isinstance(relation_registry.get("signatures"), Mapping) else {}
    signature = signature_rows.get(candidate.get("predicate")) if isinstance(candidate, Mapping) else None
    role_audit = validate_relation_role_ref_constraints(
        claim=candidate,
        signature=signature if isinstance(signature, Mapping) else {},
        typed_qualifiers=base.get("typed_qualifiers", {}),
    )
    errors.extend(role_audit["errors"])
    candidate_units = candidate.get("source_unit_refs") if isinstance(candidate.get("source_unit_refs"), list) else []
    candidate_evidence = candidate.get("evidence_refs") if isinstance(candidate.get("evidence_refs"), list) else []
    allowed_units = set(str(item) for item in allowed_source_unit_refs)
    if not candidate_units:
        errors.append("SOURCE_UNIT_REFS_REQUIRED")
    for unit in candidate_units:
        if unit not in allowed_units:
            errors.append(f"SOURCE_UNIT_REF_UNKNOWN:{unit}")
    if not candidate_evidence:
        errors.append("EVIDENCE_REFS_REQUIRED")
    for evidence in candidate_evidence:
        units = set(str(item) for item in evidence_unit_bindings.get(str(evidence), []))
        if not units:
            errors.append(f"EVIDENCE_REF_UNKNOWN:{evidence}")
        elif not units.intersection(str(item) for item in candidate_units):
            errors.append(f"EVIDENCE_UNIT_BINDING_MISMATCH:{evidence}")

    entity_rows = entity_registry.get("entities") if isinstance(entity_registry.get("entities"), Mapping) else {}
    projection = None
    if not errors and isinstance(signature, Mapping):
        subject = entity_rows[candidate["subject_ref"]]
        obj = entity_rows[candidate["object_ref"]]
        projection = {
            "schema_version": "source_semantic_claim_candidate_projection_v3",
            "claim_type": signature["claim_type"],
            "relation_class": signature["relation_class"],
            "subject": {"ref": candidate["subject_ref"], "kind": subject["kind"]},
            "predicate": candidate["predicate"],
            "object": {"ref": candidate["object_ref"], "kind": obj["kind"]},
            "qualifiers": base.get("typed_qualifiers", {}),
            "polarity": candidate["polarity"], "modality": candidate["modality"],
            "evidence_refs": sorted(candidate_evidence),
            "source_unit_refs": sorted(candidate_units),
        }
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "typed_qualifiers": base.get("typed_qualifiers", {}),
        "role_constraint_audit": role_audit,
        "projection": projection,
        "verifier_eligible": False,
        "authority": "UNTRUSTED_PROPOSED",
        "canonical": False,
    }


def assign_reproposal_claim_ids(
    candidate_results: Sequence[Mapping[str, Any]], *,
    entity_registry_fingerprint: str,
) -> dict[str, Any]:
    prepared: list[tuple[str, Mapping[str, Any]]] = []
    for row in candidate_results:
        projection = row.get("projection")
        if row.get("status") != "PASS" or not isinstance(projection, Mapping):
            continue
        material = {
            "proposal_attempt_id": PROPOSAL_ATTEMPT_ID,
            "entity_registry_fingerprint": entity_registry_fingerprint,
            "relation_registry_version": RELATION_SIGNATURE_REGISTRY_V4_VERSION,
            "qualifier_registry_version": QUALIFIER_REGISTRY_V4_VERSION,
            "provider_predicate_registry_version": PROVIDER_PREDICATE_REGISTRY_V3_VERSION,
            "projection": dict(projection),
        }
        prepared.append((fingerprint(material), projection))
    prepared.sort(key=lambda item: item[0])
    if len({fp for fp, _ in prepared}) != len(prepared):
        return {"status": "BLOCKED", "errors": ["DUPLICATE_REPROPOSAL_CANDIDATE"], "rows": []}
    rows = [{
        "claim_id": f"SCC_V7_7_10_{index:04d}",
        "candidate_fingerprint": fp,
        "authority": "UNTRUSTED_PROPOSED",
        "canonical": False,
        "historical_superseded_candidate_refs": ["V7.7.9:CANDIDATE_0", "V7.7.9:CANDIDATE_1"],
        "proposal_attempt_id": PROPOSAL_ATTEMPT_ID,
        "projection": dict(projection),
    } for index, (fp, projection) in enumerate(prepared, 1)]
    return {
        "status": "PASS",
        "id_owner": "program",
        "provider_supplied_id": False,
        "historical_ids_reused": False,
        "rows": rows,
        "candidate_fingerprint_ordering": [fp for fp, _ in prepared],
        "proposal_attempt_id": PROPOSAL_ATTEMPT_ID,
    }


__all__ = [
    "RELATION_SIGNATURE_REGISTRY_V4_VERSION", "QUALIFIER_REGISTRY_V4_VERSION",
    "PROVIDER_PREDICATE_REGISTRY_V3_VERSION", "ROLE_REF_CONSTRAINT_VERSION",
    "PROPOSAL_ATTEMPT_ID", "qualifier_registry_v4", "relation_signature_registry_v4",
    "role_ref_constraint_contract_v1", "validate_relation_role_ref_constraints",
    "provider_entity_ref_qualifier_domain_audit", "provider_predicate_registry_v3",
    "predicate_prompt_contract_v3_2", "validate_provider_candidate_v3_2",
    "build_reproposal_prompt", "assign_reproposal_claim_ids",
]
