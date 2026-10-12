"""Claim-aware authoring sidecar contract for future Director provider output.

The sidecar is produced with the authoring result.  It is never reconstructed
from prose and it never self-authenticates source support.
"""
from __future__ import annotations

from typing import Any, Mapping

from .director_claim_authority import authority_requirement
from .director_claim_entity_binding import validate_claim_entities
from .director_claim_ir import CLAIM_TYPES, CANONICALITIES, MODALITIES, POLARITIES, AUTHORITIES, claim_fingerprint


AUTHORING_MANIFEST_VERSION = "director_authoring_claim_manifest_v1"
STAGE_A_FIELD_CONTRACT_VERSION = "director_stage_a_field_semantic_contract_v1"
STAGE_B_FIELD_CONTRACT_VERSION = "director_stage_b_field_semantic_contract_v1"
COMPLETENESS_CONTRACT_VERSION = "director_claim_manifest_completeness_contract_v1"


def make_manifest_claim(*, claim_id: str, claim_type: str, subject: Mapping[str, Any], predicate: str, object_: Mapping[str, Any], qualifiers: Mapping[str, Any] | None = None, polarity: str = "POSITIVE", modality: str = "ASSERTED", canonicality: str = "CANONICAL_ASSERTION", authority_required: str = "SOURCE", source_refs: list[str] | None = None, source_claim_ids: list[str] | None = None, origin: str = "STAGE_A", provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    claim = {
        "schema_version": "director_claim_ir_v1",
        "claim_id": str(claim_id),
        "claim_type": str(claim_type),
        "subject": dict(subject),
        "predicate": str(predicate),
        "object": dict(object_),
        "qualifiers": dict(qualifiers or {}),
        "polarity": str(polarity),
        "modality": str(modality),
        "canonicality": str(canonicality),
        "authority_required": str(authority_required),
        "source_refs": sorted(set(str(value) for value in (source_refs or []))),
        "source_claim_ids": sorted(set(str(value) for value in (source_claim_ids or []))),
        "origin": str(origin),
    }
    if provenance:
        claim["provenance"] = dict(provenance)
    claim["fingerprint"] = claim_fingerprint(claim)
    return claim


def validate_manifest_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = ("schema_version", "claim_id", "claim_type", "subject", "predicate", "object", "qualifiers", "polarity", "modality", "canonicality", "authority_required", "source_refs", "source_claim_ids", "origin", "fingerprint")
    for field in required:
        if field not in claim:
            errors.append(f"MISSING_{field}")
    if claim.get("schema_version") != "director_claim_ir_v1":
        errors.append("CLAIM_SCHEMA_INVALID")
    for field, allowed in (("claim_type", CLAIM_TYPES), ("polarity", POLARITIES), ("modality", MODALITIES), ("canonicality", CANONICALITIES), ("authority_required", AUTHORITIES), ("origin", ("STAGE_A", "STAGE_B"))):
        if field in claim and claim.get(field) not in allowed:
            errors.append(f"{field.upper()}_INVALID")
    for field in ("subject", "object", "qualifiers"):
        if field in claim and not isinstance(claim[field], Mapping):
            errors.append(f"{field.upper()}_MUST_BE_OBJECT")
    for field in ("source_refs", "source_claim_ids"):
        if field in claim and not isinstance(claim[field], list):
            errors.append(f"{field.upper()}_MUST_BE_ARRAY")
    if claim.get("fingerprint") and claim.get("fingerprint") != claim_fingerprint(claim):
        errors.append("FINGERPRINT_MISMATCH")
    entity_result = validate_claim_entities(claim)
    if entity_result["status"] != "PASS":
        errors.extend(str(item) for item in entity_result["errors"])
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors}


def stage_a_field_semantic_contract() -> dict[str, Any]:
    return {
        "schema_version": STAGE_A_FIELD_CONTRACT_VERSION,
        "stage": "STAGE_A",
        "fields": {
            "purpose": {"allowed_claim_types": ["DRAMATIC_GROUPING"], "canonical_fact_creation": False},
            "objective": {"allowed_claim_types": ["DRAMATIC_OBJECTIVE"], "canonical_fact_creation": False, "character_intent_requires_explicit_manifest_claim": True},
            "information_change": {"allowed_claim_types": ["INFORMATION_REVEAL", "INFORMATION_WITHHOLD"], "requires_source_claim_ids_for_canonical_delta": True},
            "hook": {"allowed_claim_types": ["DRAMATIC_GROUPING", "AUDIENCE_EFFECT"], "canonical_fact_creation": False},
            "scene_objective": {"allowed_claim_types": ["DRAMATIC_OBJECTIVE"], "canonical_fact_creation": False},
            "dramatic_question": {"allowed_claim_types": ["DRAMATIC_QUESTION"], "canonical_fact_creation": False},
            "referenced_source_claim_ids": {"role": "typed_source_reference", "creates_no_new_fact": True},
        },
        "prose_role": "human-readable rendering only",
    }


def stage_b_field_semantic_contract() -> dict[str, Any]:
    return {
        "schema_version": STAGE_B_FIELD_CONTRACT_VERSION,
        "stage": "STAGE_B",
        "fields": {
            "performance": {"allowed_claim_types": ["PERFORMANCE_DIRECTION", "PERFORMANCE_OPTION"], "canonical_fact_creation": False},
            "audience_effect": {"allowed_claim_types": ["AUDIENCE_EFFECT", "AUDIENCE_INTERPRETATION"], "canonical_fact_creation": False},
            "information_strategy": {"allowed_claim_types": ["INFORMATION_STRATEGY", "INFORMATION_REVEAL", "INFORMATION_WITHHOLD"], "canonical_fact_creation": False},
            "visual_priority": {"allowed_claim_types": ["VISUAL_PRIORITY"], "canonical_fact_creation": False},
            "delegation": {"allowed_claim_types": ["AUTHORITY_DELEGATION"], "canonical_fact_creation": False},
            "canonical_facts": {"allowed_claim_types": sorted(set(CLAIM_TYPES) - {"PERFORMANCE_OPTION", "PERFORMANCE_DIRECTION"}), "source_support_required": True},
        },
        "prose_role": "human-readable rendering only",
    }


def claim_manifest_completeness_contract() -> dict[str, Any]:
    return {
        "schema_version": COMPLETENESS_CONTRACT_VERSION,
        "principle": "Completeness is checked against semantic slots derived from the structured BeatPlan shape, never against a lexical blacklist.",
        "required": ["semantic_slots", "covered_slots", "claims"],
        "uncovered_slot_policy": "BLOCKED",
        "unclassified_prose_policy": "BLOCKED unless field contract marks the field human-readable-only",
    }


def _derived_stage_a_slots(beat_plan_ir: Mapping[str, Any]) -> set[str]:
    slots: set[str] = set()
    for field in ("scene_objective", "dramatic_question"):
        if beat_plan_ir.get(field) not in (None, "", [], {}):
            slots.add(field)
    beats = beat_plan_ir.get("beats")
    if isinstance(beats, list):
        for index, beat in enumerate(beats):
            if not isinstance(beat, Mapping):
                continue
            beat_ref = str(beat.get("beat_ref") or f"beat_{index}")
            for field in ("purpose", "objective", "information_change", "hook"):
                if beat.get(field) not in (None, "", [], {}):
                    slots.add(f"{beat_ref}.{field}")
    return slots


def validate_claim_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if manifest.get("schema_version") != AUTHORING_MANIFEST_VERSION:
        errors.append({"code": "SCHEMA_VERSION_INVALID"})
    if manifest.get("authoring_stage") not in {"STAGE_A", "STAGE_B"}:
        errors.append({"code": "AUTHORING_STAGE_INVALID"})
    claims = manifest.get("claims")
    if not isinstance(claims, list):
        errors.append({"code": "CLAIMS_MUST_BE_ARRAY"})
        claims = []
    ids: set[str] = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            errors.append({"index": index, "code": "CLAIM_MUST_BE_OBJECT"})
            continue
        result = validate_manifest_claim(claim)
        if result["status"] != "PASS":
            errors.append({"index": index, "code": "CLAIM_INVALID", "errors": result["errors"]})
        claim_id = str(claim.get("claim_id") or "")
        if claim_id in ids:
            errors.append({"index": index, "code": "DUPLICATE_CLAIM_ID"})
        ids.add(claim_id)
        authority = authority_requirement({**claim, "origin": manifest.get("authoring_stage")})
        if authority["status"] in {"BLOCKED", "DOWNSTREAM_FORBIDDEN"}:
            errors.append({"index": index, "code": "AUTHORITY_MATRIX_REJECTED", "reason": authority["reason"]})
    for field in ("semantic_slots", "covered_slots"):
        if not isinstance(manifest.get(field), list):
            errors.append({"code": f"{field.upper()}_MUST_BE_ARRAY"})
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "claim_count": len(claims), "claim_ids": sorted(ids)}


def validate_claim_manifest_completeness(authoring_result: Mapping[str, Any]) -> dict[str, Any]:
    manifest = authoring_result.get("claim_manifest") if isinstance(authoring_result, Mapping) else None
    if not isinstance(manifest, Mapping):
        return {"status": "BLOCKED", "errors": ["CLAIM_MANIFEST_REQUIRED"]}
    derived = _derived_stage_a_slots(authoring_result.get("beat_plan_ir") if isinstance(authoring_result.get("beat_plan_ir"), Mapping) else {})
    declared = set(str(value) for value in (manifest.get("semantic_slots") or []))
    covered = set(str(value) for value in (manifest.get("covered_slots") or []))
    errors = [{"code": "SEMANTIC_SLOT_UNCOVERED", "slot": slot} for slot in sorted(declared - covered)]
    if derived and declared != derived:
        errors.append({"code": "SEMANTIC_SLOT_DECLARATION_MISMATCH", "derived": sorted(derived), "declared": sorted(declared)})
    if derived and covered != derived:
        errors.append({"code": "SEMANTIC_SLOT_COVERAGE_MISMATCH", "derived": sorted(derived), "covered": sorted(covered)})
    claim_slots = set()
    for claim in manifest.get("claims") or []:
        if isinstance(claim, Mapping):
            slot = (claim.get("qualifiers") or {}).get("semantic_slot")
            if slot:
                claim_slots.add(str(slot))
    errors.extend({"code": "CLAIM_SLOT_NOT_DECLARED", "slot": slot} for slot in sorted(claim_slots - declared))
    if derived:
        missing_claim_slots = sorted(derived - claim_slots)
        errors.extend({"code": "SEMANTIC_SLOT_WITHOUT_EXPLICIT_CLAIM", "slot": slot} for slot in missing_claim_slots)
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "derived_slots": sorted(derived), "declared_slots": sorted(declared), "covered_slots": sorted(covered), "claim_slots": sorted(claim_slots)}


def validate_authoring_response(authoring_result: Mapping[str, Any]) -> dict[str, Any]:
    manifest = authoring_result.get("claim_manifest") if isinstance(authoring_result, Mapping) else None
    if not isinstance(manifest, Mapping):
        return {"status": "BLOCKED", "errors": ["CLAIM_MANIFEST_REQUIRED"]}
    schema = validate_claim_manifest(manifest)
    completeness = validate_claim_manifest_completeness(authoring_result)
    errors = [{"source": "schema", **item} for item in schema["errors"]] + [{"source": "completeness", **item} for item in completeness["errors"]]
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "schema": schema, "completeness": completeness}


__all__ = ["AUTHORING_MANIFEST_VERSION", "STAGE_A_FIELD_CONTRACT_VERSION", "STAGE_B_FIELD_CONTRACT_VERSION", "COMPLETENESS_CONTRACT_VERSION", "make_manifest_claim", "validate_manifest_claim", "validate_claim_manifest", "validate_claim_manifest_completeness", "validate_authoring_response", "stage_a_field_semantic_contract", "stage_b_field_semantic_contract", "claim_manifest_completeness_contract"]
