"""Provider-free adapter for semantic verification of typed source claims.

This module turns an already frozen Claim V3.2 proposal into the existing
Fact Semantic Verifier transport.  It never creates facts, retrieves source
material, or persists an authority decision.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

from .fact_semantic_grounding import classify_anchor_surface, confirmation_ceiling
from .fact_semantic_verifier import FORBIDDEN_FIELDS, VERDICTS, compile_semantic_authority


ADAPTER_VERSION = "source_claim_semantic_verifier_adapter_v1"
ATOMICITY_VERSION = "source_claim_typed_atomicity_guard_v1"
SUPPORT_ROLE_VERSION = "source_claim_support_role_registry_v1"
OVERLAY_VERSION = "source_claim_semantic_authority_overlay_shadow_v1"
TRANSPORT_FACT_ID = "FACT_0001"

SUPPORT_ROLE_REGISTRY: dict[str, str] = {
    "ACTION": "ACTION_OCCURRENCE",
    "SPEECH_ACT": "SPEECH_ACT",
    "OBJECT_PROPERTY": "WORLD_ASSERTION",
    "ENVIRONMENT_STATE": "WORLD_ASSERTION",
    "POSSESSION": "WORLD_ASSERTION",
    "PROVENANCE": "WORLD_ASSERTION",
}


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def support_role_registry_v1() -> dict[str, Any]:
    return {
        "schema_version": SUPPORT_ROLE_VERSION,
        "mapping": copy.deepcopy(SUPPORT_ROLE_REGISTRY),
        "predicate_name_inference": False,
        "source_prose_consulted": False,
    }


def required_components(projection: Mapping[str, Any], relation_signature: Mapping[str, Any]) -> list[str]:
    """Derive component IDs from typed fields and required qualifier keys."""
    result = ["SUBJECT", "PREDICATE", "OBJECT"]
    for key in sorted(str(item) for item in relation_signature.get("required_qualifier_keys", [])):
        result.append(f"QUALIFIER:{key}")
    result.extend(["POLARITY", "MODALITY"])
    return result


def typed_atomicity_guard(projection: Mapping[str, Any], relation_signature: Mapping[str, Any]) -> dict[str, Any]:
    qualifier_rows = projection.get("qualifiers") if isinstance(projection.get("qualifiers"), Mapping) else {}
    errors: list[str] = []
    if not isinstance(projection.get("predicate"), str) or projection.get("predicate") != relation_signature.get("predicate"):
        errors.append("TYPED_ATOMICITY_REGISTERED_PREDICATE_REQUIRED")
    for key in ("subject", "object"):
        if not isinstance(projection.get(key), Mapping) or not projection[key].get("ref") or not projection[key].get("kind"):
            errors.append(f"TYPED_ATOMICITY_ROLE_MISSING:{key.upper()}")
    for key in relation_signature.get("required_qualifier_keys", []):
        value = qualifier_rows.get(key)
        if not isinstance(value, Mapping) or not value.get("ref") or not value.get("kind"):
            errors.append(f"TYPED_ATOMICITY_REQUIRED_QUALIFIER_MISSING:{key}")
    role = {
        "subject_ref": projection.get("subject", {}).get("ref") if isinstance(projection.get("subject"), Mapping) else None,
        "object_ref": projection.get("object", {}).get("ref") if isinstance(projection.get("object"), Mapping) else None,
    }
    for key, value in qualifier_rows.items():
        if isinstance(value, Mapping) and value.get("value_type") == "ENTITY_REF":
            role[f"qualifier_ref:{key}"] = value.get("ref")
    for constraint in relation_signature.get("ref_constraints", []):
        if not isinstance(constraint, Mapping):
            errors.append("TYPED_ATOMICITY_REF_CONSTRAINT_INVALID")
            continue
        if constraint.get("operator") == "NOT_EQUAL":
            left, right = role.get(constraint.get("left_role")), role.get(constraint.get("right_role"))
            if not left or not right or left == right:
                errors.append("TYPED_ATOMICITY_ROLE_CONSTRAINT_FAILED")
        else:
            errors.append("TYPED_ATOMICITY_REF_CONSTRAINT_UNSUPPORTED")
    if isinstance(projection.get("nested_claim"), Mapping) or isinstance(projection.get("claims"), list):
        errors.append("TYPED_ATOMICITY_NESTED_OR_CONJUNCTION_BLOCKED")
    return {
        "schema_version": ATOMICITY_VERSION,
        "status": "PASS" if not errors else "BLOCKED",
        "predicate_count": 1 if projection.get("predicate") else 0,
        "complete_relation_signature": not any(error.startswith("TYPED_ATOMICITY_REGISTERED") for error in errors),
        "typed_roles": role,
        "representation_is_not_composite": True,
        "uses_json_dict_as_composite_signal": False,
        "errors": sorted(set(errors)),
    }


def verifier_id_mapping(claim_ref: str) -> dict[str, Any]:
    row = {"transport_fact_id": TRANSPORT_FACT_ID, "claim_ref": str(claim_ref), "transport_id_is_production_fact_id": False}
    return {
        "schema_version": "source_claim_verifier_transport_id_mapping_v1",
        "status": "PASS" if claim_ref else "BLOCKED",
        "mappings": [row],
        "mapping_fingerprint": _fingerprint(row),
        "program_owned": True,
        "provider_may_not_modify": True,
    }


def adapter_contract() -> dict[str, Any]:
    return {
        "schema_version": ADAPTER_VERSION,
        "role": "semantic_verifier_not_fact_writer_or_retriever",
        "provider_owns": ["semantic_verdict", "supported_components", "unsupported_components", "rationale"],
        "program_owns": ["claim_ref", "transport_fact_id", "typed_assertion", "evidence_refs", "final_authority", "final_status", "downstream_eligibility"],
        "provider_fact_creation": False,
        "provider_evidence_creation": False,
        "source_retrieval": False,
        "proposal_raw_included": False,
        "proposal_prompt_included": False,
        "forbidden_provider_fields": list(FORBIDDEN_FIELDS),
    }


def build_verifier_packet(*, claim_ref: str, projection: Mapping[str, Any], relation_signature: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    mapping = verifier_id_mapping(claim_ref)
    fact_id = mapping["mappings"][0]["transport_fact_id"]
    support_role = SUPPORT_ROLE_REGISTRY.get(str(projection.get("relation_class") or ""))
    component_ids = required_components(projection, relation_signature)
    surface = classify_anchor_surface(evidence.get("text"))
    ceiling = confirmation_ceiling(surface, support_role or "WORLD_ASSERTION")
    assertion = {
        "subject": copy.deepcopy(projection.get("subject")),
        "predicate": projection.get("predicate"),
        "object": copy.deepcopy(projection.get("object")),
        "qualifiers": copy.deepcopy(projection.get("qualifiers")),
        "polarity": projection.get("polarity"),
        "modality": projection.get("modality"),
    }
    fact = {
        "fact_id": fact_id,
        "subject_id": projection.get("subject", {}).get("ref"),
        "predicate": projection.get("predicate"),
        "value": assertion,
        "evidence": [{"anchor_ref": evidence.get("evidence_id")}],
    }
    context = {
        "fact_id": fact_id,
        "provider_epistemic_class": None,
        "resolved_evidence": [{"anchor_ref": evidence.get("evidence_id"), "exact_text": evidence.get("text"), "source_unit_ref": evidence.get("source_unit_ref")}],
        "anchor_surface_classes": [surface],
        "confirmation_ceilings": [ceiling],
        "machine_guard_findings": [],
    }
    return {
        "schema_version": ADAPTER_VERSION,
        "status": "PASS" if support_role else "BLOCKED",
        "claim_ref": claim_ref,
        "id_mapping": mapping,
        "fact": fact,
        "machine_context": context,
        "typed_assertion": assertion,
        "required_semantic_components": component_ids,
        "support_role": support_role,
        "anchor_surface": surface,
        "confirmation_ceiling": ceiling,
    }


def evidence_authority_audit(*, projection: Mapping[str, Any], source_unit: Mapping[str, Any], source_fingerprint: str, expected_source_fingerprint: str) -> dict[str, Any]:
    evidence = source_unit.get("source_evidence") if isinstance(source_unit.get("source_evidence"), Mapping) else {}
    refs = projection.get("evidence_refs") if isinstance(projection.get("evidence_refs"), list) else []
    units = projection.get("source_unit_refs") if isinstance(projection.get("source_unit_refs"), list) else []
    errors = []
    if refs != [evidence.get("evidence_id")]: errors.append("EVIDENCE_REF_BINDING_MISMATCH")
    if units != [source_unit.get("unit_id")]: errors.append("SOURCE_UNIT_BINDING_MISMATCH")
    if source_fingerprint != expected_source_fingerprint: errors.append("SOURCE_FINGERPRINT_DRIFT")
    if not evidence.get("text"): errors.append("RESOLVED_EVIDENCE_MISSING")
    return {"schema_version": "source_claim_evidence_authority_audit_v1", "status": "PASS" if not errors else "BLOCKED", "claim_evidence_refs": refs, "claim_source_unit_refs": units, "resolved_evidence": {"evidence_id": evidence.get("evidence_id"), "text": evidence.get("text"), "sha256": evidence.get("sha256")}, "source_fingerprint": source_fingerprint, "errors": errors}


def component_contract(result: Mapping[str, Any], required: Sequence[str]) -> dict[str, Any]:
    supported = result.get("supported_components") if isinstance(result.get("supported_components"), list) else []
    unsupported = result.get("unsupported_components") if isinstance(result.get("unsupported_components"), list) else []
    allowed = set(required)
    errors: list[str] = []
    if len(supported) != len(set(supported)) or len(unsupported) != len(set(unsupported)):
        errors.append("VERIFIER_COMPONENT_DUPLICATE")
    if set(supported) - allowed or set(unsupported) - allowed:
        errors.append("VERIFIER_COMPONENT_CONTRACT_INVALID")
    if set(supported) & set(unsupported):
        errors.append("VERIFIER_COMPONENT_CONTRACT_INVALID")
    if result.get("verdict") == "ENTAILED":
        if unsupported or set(supported) != allowed:
            errors.append("VERIFIER_ENTAILED_COMPONENT_COVERAGE_INVALID")
    return {"status": "PASS" if not errors else "BLOCKED", "verdict": result.get("verdict"), "required_components": list(required), "supported_components": supported, "unsupported_components": unsupported, "errors": sorted(set(errors))}


def compile_shadow_overlay(*, packet: Mapping[str, Any], result: Mapping[str, Any], evidence_status: str, atomicity: Mapping[str, Any], component_audit: Mapping[str, Any]) -> dict[str, Any]:
    fact_id = packet["fact"]["fact_id"]
    blockers = list(atomicity.get("errors") or [])
    if component_audit.get("status") != "PASS": blockers.append("VERIFIER_COMPONENT_CONTRACT_INVALID")
    compiled = compile_semantic_authority(
        facts=[packet["fact"]], verifier_results=[result],
        machine_guards={fact_id: {"hard_blockers": sorted(set(blockers)), "confirmation_ceilings": [packet["confirmation_ceiling"]]}},
        evidence_authority_status=evidence_status,
    )
    row = compiled["facts"][0]
    return {"schema_version": OVERLAY_VERSION, "shadow_only": True, "production_persisted": False, "claim_ref": packet["claim_ref"], "transport_fact_id": fact_id, "verifier_verdict": result.get("verdict"), "semantic_disposition": row["semantic_disposition"], "effective_authority": row["effective_authority"], "effective_status": row["effective_status"], "downstream_eligible": row["downstream_eligible"], "review_required": row["review_required"], "machine_guard_overrides": row["machine_guard_overrides"], "compiler": "fact_semantic_verifier.compile_semantic_authority", "compiler_overlay": compiled, "fingerprint": _fingerprint({"claim_ref": packet["claim_ref"], "row": row})}


__all__ = ["ADAPTER_VERSION", "ATOMICITY_VERSION", "SUPPORT_ROLE_VERSION", "OVERLAY_VERSION", "TRANSPORT_FACT_ID", "adapter_contract", "support_role_registry_v1", "required_components", "typed_atomicity_guard", "verifier_id_mapping", "build_verifier_packet", "evidence_authority_audit", "component_contract", "compile_shadow_overlay"]
