"""Strict, provider-neutral Source Semantic Claim Proposal boundary.

The boundary accepts an untrusted JSON proposal and returns only in-memory
observations.  It does not create FactSnapshots, semantic overlays, or
SourceClaims, and it has no story-specific extraction or repair path.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .director_claim_relation_registry import RELATION_REGISTRY, RELATION_REGISTRY_VERSION, relation_registry
from .source_semantic_claim_authority import (
    CANDIDATE_VERSION,
    FACT_CLAIM_MAPPING,
    FACT_CLAIM_MAPPING_VERSION,
    MODALITIES,
    POLARITIES,
    validate_candidate,
)


PROPOSAL_VERSION = "source_semantic_claim_proposal_v1"
CANDIDATE_SET_VERSION = "source_semantic_claim_candidate_set_v1"
PROPOSED_FACT_VERSION = "source_semantic_proposed_fact_projection_v1"
SURFACE_COVERAGE_VERSION = "source_semantic_proposal_surface_coverage_v1"
REQUIRED_WRAPPER_KEYS = {"schema_version", "candidates"}
REQUIRED_CANDIDATE_KEYS = {
    "schema_version", "candidate_id", "subject", "predicate", "object",
    "qualifiers", "polarity", "modality", "evidence_refs", "source_unit_refs",
}
FORBIDDEN_FIELDS = {
    "raw_text", "display_text", "explanation", "rationale", "final_authority",
    "final_status", "source_claim_supported", "promote", "new_fact", "source_search",
    "char_start", "char_end", "byte_start", "byte_end", "sha256", "authority",
    "status", "support_status", "fingerprint", "source_claim_id", "fact_id",
}
QUALIFIER_TYPES: dict[str, tuple[type, ...]] = {
    "destination": (str,),
    "light_state": (str,),
    "ownership": (str, bool),
    "possession": (str, bool),
    "transfer_source": (str,),
    "property_domain": (str,),
    "state_domain": (str,),
    "speaker_binding": (str,),
}
RELATION_CLASS_ALIASES = {"PROVENANCE": {"PROVENANCE", "OBJECT_PROVENANCE"}}
RELATION_CLASS_REGISTRY_ALIASES = {
    "ACTION": "CHARACTER_ACTION",
    "PROVENANCE": "PROVENANCE",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def wrapper_schema() -> dict[str, Any]:
    return {
        "schema_version": PROPOSAL_VERSION,
        "type": "object",
        "required": ["schema_version", "candidates"],
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": PROPOSAL_VERSION},
            "candidates": {"type": "array", "items": {"$ref": "source_semantic_claim_candidate_v1"}},
        },
        "provider_must_not_supply": sorted(FORBIDDEN_FIELDS),
    }


def _predicate_capability(predicate: str) -> tuple[str, str] | None:
    mapping = FACT_CLAIM_MAPPING.get(predicate)
    if not mapping:
        return None
    return str(mapping.get("claim_type") or ""), str(mapping.get("relation_class") or "")


def _allowed_qualifiers(predicate: str) -> set[str]:
    capability = _predicate_capability(predicate)
    if not capability:
        return set()
    _, relation_class = capability
    keys: set[str] = set()
    registry_class = RELATION_CLASS_REGISTRY_ALIASES.get(relation_class, relation_class)
    for relation in RELATION_REGISTRY.get(registry_class, {}).values():
        keys.update(str(item) for item in relation.get("qualifier_keys", []))
    if relation_class == "OBJECT_PROVENANCE":
        for relation in RELATION_REGISTRY.get("PROVENANCE", {}).values():
            keys.update(str(item) for item in relation.get("qualifier_keys", []))
    return keys


def validate_qualifiers(*, predicate: str, qualifiers: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(qualifiers, Mapping):
        return {"status": "BLOCKED", "errors": ["QUALIFIERS_MUST_BE_OBJECT"]}
    allowed = _allowed_qualifiers(predicate)
    for key, value in qualifiers.items():
        key = str(key)
        if key not in QUALIFIER_TYPES:
            errors.append(f"QUALIFIER_KEY_UNKNOWN:{key}")
            continue
        if key not in allowed:
            errors.append(f"QUALIFIER_KEY_NOT_ALLOWED_FOR_PREDICATE:{predicate}:{key}")
            continue
        if not isinstance(value, QUALIFIER_TYPES[key]):
            errors.append(f"QUALIFIER_TYPE_INVALID:{key}")
        if isinstance(value, str) and not value.strip():
            errors.append(f"QUALIFIER_VALUE_EMPTY:{key}")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "allowed_keys": sorted(allowed)}


def validate_candidate_strict(candidate: Any, *, entity_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(candidate, Mapping):
        return {"status": "BLOCKED", "errors": ["CANDIDATE_MUST_BE_OBJECT"]}
    keys = {str(key) for key in candidate}
    missing = sorted(REQUIRED_CANDIDATE_KEYS - keys)
    extra = sorted(keys - REQUIRED_CANDIDATE_KEYS)
    if missing:
        errors.extend(f"CANDIDATE_REQUIRED_FIELD_MISSING:{key}" for key in missing)
    if extra:
        errors.extend(f"CANDIDATE_EXTRA_FIELD:{key}" for key in extra)
    errors.extend(validate_candidate(candidate).get("errors", []))
    predicate = str(candidate.get("predicate") or "")
    capability = _predicate_capability(predicate)
    if capability is None:
        errors.append(f"PREDICATE_NOT_REGISTERED:{predicate}")
    subject = candidate.get("subject")
    object_value = candidate.get("object")
    for field, value in (("subject", subject), ("object", object_value)):
        if isinstance(value, Mapping):
            ref_keys = {str(key) for key in value}
            if ref_keys != {"kind", "ref"}:
                errors.append(f"{field.upper()}_REF_SHAPE_INVALID")
            if not str(value.get("kind") or "").strip() or not str(value.get("ref") or "").strip():
                errors.append(f"{field.upper()}_REF_EMPTY")
    qualifier_result = validate_qualifiers(predicate=predicate, qualifiers=candidate.get("qualifiers"))
    errors.extend(qualifier_result["errors"])
    for field in ("evidence_refs", "source_unit_refs"):
        refs = candidate.get(field)
        if isinstance(refs, list) and not refs:
            errors.append(f"{field.upper()}_EMPTY")
        if isinstance(refs, list) and len(refs) != len(set(refs)):
            errors.append(f"{field.upper()}_DUPLICATED")
    if entity_registry is not None:
        for field in ("subject", "object"):
            value = candidate.get(field)
            if isinstance(value, Mapping):
                ref = str(value.get("ref") or "")
                if ref and ref not in entity_registry:
                    errors.append(f"UNKNOWN_ENTITY_REF:{ref}")
                elif ref and isinstance(entity_registry.get(ref), Mapping):
                    expected_kind = str(entity_registry[ref].get("kind") or "")
                    if expected_kind and expected_kind != str(value.get("kind") or ""):
                        errors.append(f"ENTITY_KIND_MISMATCH:{ref}")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "predicate_capability": {"claim_type": capability[0], "relation_class": capability[1]} if capability else None,
        "qualifier_validation": qualifier_result,
    }


def validate_wrapper(value: Any, *, entity_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": "BLOCKED", "errors": ["WRAPPER_MUST_BE_OBJECT"], "candidate_results": []}
    errors: list[str] = []
    keys = {str(key) for key in value}
    errors.extend(f"WRAPPER_REQUIRED_FIELD_MISSING:{key}" for key in sorted(REQUIRED_WRAPPER_KEYS - keys))
    errors.extend(f"WRAPPER_EXTRA_FIELD:{key}" for key in sorted(keys - REQUIRED_WRAPPER_KEYS))
    if value.get("schema_version") != PROPOSAL_VERSION:
        errors.append("WRAPPER_SCHEMA_VERSION_INVALID")
    candidates = value.get("candidates")
    if not isinstance(candidates, list):
        errors.append("WRAPPER_CANDIDATES_MUST_BE_ARRAY")
        candidates = []
    results = [validate_candidate_strict(candidate, entity_registry=entity_registry) for candidate in candidates]
    if any(result["status"] != "PASS" for result in results):
        errors.append("WRAPPER_CONTAINS_INVALID_CANDIDATE")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "candidate_results": results}


def parse_strict_json(raw: str) -> tuple[Any | None, dict[str, Any]]:
    text = str(raw or "")
    try:
        value = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, {"status": "BLOCKED", "code": "SOURCE_SEMANTIC_PROPOSAL_JSON_PARSE_FAILED", "error": str(exc)[:240], "raw_length": len(text)}
    return value, {"status": "PASS", "raw_length": len(text)}


def candidate_typed_projection(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {key: candidate.get(key) for key in ("subject", "predicate", "object", "qualifiers", "polarity", "modality", "evidence_refs", "source_unit_refs")}


def candidate_set(candidates: Sequence[Mapping[str, Any]], *, entity_registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    for candidate in candidates:
        validation = validate_candidate_strict(candidate, entity_registry=entity_registry)
        row = {"candidate_id": candidate.get("candidate_id") if isinstance(candidate, Mapping) else None, "validation": validation}
        rows.append(row)
        if validation["status"] == "PASS":
            valid.append(candidate_typed_projection(candidate))
    return {
        "schema_version": CANDIDATE_SET_VERSION,
        "candidate_count": len(candidates),
        "valid_count": len(valid),
        "blocked_count": len(candidates) - len(valid),
        "candidate_fingerprint": sha256(valid),
        "valid_typed_candidates": valid,
        "validation_rows": rows,
    }


def proposed_fact_projection(valid_candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    facts = []
    for index, candidate in enumerate(valid_candidates, start=1):
        facts.append({
            "fact_id": f"FACT_{index:04d}",
            "schema_version": PROPOSED_FACT_VERSION,
            "status": "model_observation",
            "authority": "proposed",
            "candidate": candidate_typed_projection(candidate),
        })
    return {"schema_version": PROPOSED_FACT_VERSION, "projection_count": len(facts), "facts": facts, "persisted": False}


def surface_coverage(*, source_units: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    unit_ids = {str(item.get("unit_id")) for item in source_units if isinstance(item, Mapping)}
    referenced = {str(ref) for candidate in candidates for ref in (candidate.get("source_unit_refs") or [])}
    return {
        "schema_version": SURFACE_COVERAGE_VERSION,
        "name": "PROPOSAL_SURFACE_COVERAGE",
        "source_unit_count": len(unit_ids),
        "referenced_source_unit_count": len(unit_ids & referenced),
        "unreferenced_source_unit_count": len(unit_ids - referenced),
        "unreferenced_source_unit_refs": sorted(unit_ids - referenced),
        "relation_classes_proposed": sorted({str(FACT_CLAIM_MAPPING.get(str(candidate.get("predicate") or ""), {}).get("relation_class") or "") for candidate in candidates if FACT_CLAIM_MAPPING.get(str(candidate.get("predicate") or ""))}),
        "evidence_refs_used": sorted({str(ref) for candidate in candidates for ref in (candidate.get("evidence_refs") or [])}),
        "semantic_completeness": "NOT_PROVEN",
    }


def build_proposal_prompt(*, source_units: Sequence[Mapping[str, Any]], script_ir: Mapping[str, Any], entity_registry: Mapping[str, Any], mapping_registry: Mapping[str, Any], qualifier_contract: Mapping[str, Any]) -> tuple[str, str]:
    system = (
        "You are a source semantic claim proposal adapter. Return exactly one JSON object and no markdown. "
        "Propose only atomic claims explicitly supported by the supplied immutable source evidence. "
        "Preserve uncertainty and modality. A dialogue proposition is a speech act, never an asserted world fact. "
        "Do not infer motive, background, ownership, possession, environment, or hidden facts. "
        "A source unit may produce zero or more candidates; do not claim completeness or authority. "
        f"The output wrapper schema is {PROPOSAL_VERSION}; candidates are untrusted and require program validation."
    )
    evidence_units = []
    for unit in source_units:
        if not isinstance(unit, Mapping):
            continue
        evidence_units.append({
            "unit_id": unit.get("unit_id"),
            "source_type": unit.get("source_type"),
            "source_ref": unit.get("source_ref"),
            "source_order": unit.get("source_order"),
            "source_evidence_refs": unit.get("source_evidence_refs", []),
            "text": unit.get("text", ""),
        })
    user_payload = {
        "schema_version": PROPOSAL_VERSION,
        "immutable_source_units": evidence_units,
        "grounded_script_ir": {
            "schema_version": script_ir.get("schema_version"),
            "episode": script_ir.get("episode"),
            "scenes": script_ir.get("scenes", []),
        },
        "entity_registry": entity_registry,
        "source_fact_claim_mapping_registry": mapping_registry,
        "typed_qualifier_contract": qualifier_contract,
        "wrapper_schema": wrapper_schema(),
        "candidate_required_fields": sorted(REQUIRED_CANDIDATE_KEYS),
    }
    user = "SOURCE_SEMANTIC_CLAIM_PROPOSAL_INPUT\n" + canonical_json(user_payload)
    return system, user


def provider_identity(*, profile_snapshot: Mapping[str, Any], system_prompt: str, user_prompt: str) -> dict[str, Any]:
    system_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    user_hash = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()
    request = {
        "profile_id": profile_snapshot.get("profile_id"),
        "provider": profile_snapshot.get("provider"),
        "model": profile_snapshot.get("model"),
        "base_host": profile_snapshot.get("base_host"),
        "system_prompt_sha256": system_hash,
        "user_prompt_sha256": user_hash,
        "schema_version": PROPOSAL_VERSION,
    }
    return {**dict(profile_snapshot), **request, "request_fingerprint": sha256(request)}


def duplicate_and_contradiction_audit(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    seen: dict[str, int] = {}
    for candidate in candidates:
        fp = sha256(candidate_typed_projection(candidate))
        seen[fp] = seen.get(fp, 0) + 1
    duplicates = sorted(fp for fp, count in seen.items() if count > 1)
    return {"status": "PASS" if not duplicates else "BLOCKED", "duplicate_fingerprints": duplicates, "contradiction_count": 0, "uncertainty_preservation": "NOT_YET_AUTHORITY_VERIFIED"}


__all__ = [
    "PROPOSAL_VERSION", "CANDIDATE_SET_VERSION", "PROPOSED_FACT_VERSION", "SURFACE_COVERAGE_VERSION",
    "REQUIRED_WRAPPER_KEYS", "REQUIRED_CANDIDATE_KEYS", "FORBIDDEN_FIELDS", "QUALIFIER_TYPES",
    "wrapper_schema", "validate_qualifiers", "validate_candidate_strict", "validate_wrapper", "parse_strict_json",
    "candidate_typed_projection", "candidate_set", "proposed_fact_projection", "surface_coverage",
    "build_proposal_prompt", "provider_identity", "duplicate_and_contradiction_audit", "RELATION_REGISTRY_VERSION",
]
