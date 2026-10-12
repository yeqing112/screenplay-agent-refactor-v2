"""Provider-neutral V7.7.4 source entity and Claim V2 contracts.

The provider may propose typed payloads only.  Evidence binding, registry
membership, fingerprints, and program-owned identifiers are resolved by this
module.  Nothing here writes production authority or calls a provider.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .source_semantic_claim_authority import FACT_CLAIM_MAPPING, MODALITIES, POLARITIES


ENTITY_PROPOSAL_VERSION = "source_entity_proposal_v1"
ENTITY_CANDIDATE_VERSION = "source_entity_candidate_v1"
PROPOSAL_ENTITY_REGISTRY_VERSION = "source_proposal_entity_registry_v1"
CLAIM_V2_VERSION = "source_semantic_claim_candidate_v2"
CLAIM_V2_SET_VERSION = "source_semantic_claim_candidate_set_v2"
STRUCTURED_CAPABILITY_VERSION = "provider_structured_output_capability_v1"

ENTITY_KINDS = (
    "CHARACTER", "SCENE", "LOCATION", "OBJECT", "ENVIRONMENT",
    "DIALOGUE_CONTENT", "TEXT_CONTENT", "PROPERTY_VALUE", "STATE_VALUE",
    "UNKNOWN_ENTITY",
)
ENTITY_FORBIDDEN_FIELDS = {
    "canonical_entity_id", "final_authority", "final_status", "sha256",
    "char_start", "char_end", "byte_start", "byte_end", "offsets",
    "promotion", "promote", "authority", "status", "fingerprint",
}
CLAIM_V2_FORBIDDEN_FIELDS = {
    "candidate_id", "source_claim_id", "fact_id", "final_authority",
    "final_status", "promotion", "promote", "authority", "status",
    "sha256", "offsets", "char_start", "char_end", "byte_start", "byte_end",
}
ENTITY_REQUIRED_KEYS = {"schema_version", "kind", "surface_form", "evidence_refs", "source_unit_refs"}
CLAIM_V2_REQUIRED_KEYS = {"schema_version", "subject", "predicate", "object", "qualifiers", "polarity", "modality", "evidence_refs", "source_unit_refs"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _ref(value: Any) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        return "", ""
    return str(value.get("kind") or ""), str(value.get("ref") or "")


def source_entity_candidate_contract() -> dict[str, Any]:
    return {
        "type": "object",
        "schema_version": ENTITY_CANDIDATE_VERSION,
        "trust": "UNTRUSTED_PROPOSED",
        "required": sorted(ENTITY_REQUIRED_KEYS),
        "properties": {
            "schema_version": {"const": ENTITY_CANDIDATE_VERSION},
            "kind": {"type": "string", "enum": list(ENTITY_KINDS)},
            "surface_form": {"type": "string", "minLength": 1},
            "evidence_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
            "source_unit_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
        },
        "additionalProperties": False,
        "provider_may_not_supply": sorted(ENTITY_FORBIDDEN_FIELDS),
        "surface_form_semantics": "exact evidence anchoring and human-readable forensic only; never canonical identity",
        "authority": "UNTRUSTED_PROPOSED",
    }


def source_entity_proposal_schema() -> dict[str, Any]:
    item = source_entity_candidate_contract()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": ENTITY_PROPOSAL_VERSION,
        "title": "Source Entity Proposal",
        "type": "object",
        "required": ["schema_version", "entities"],
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": ENTITY_PROPOSAL_VERSION},
            "entities": {"type": "array", "items": item},
        },
    }


def _validate_ref_shape(value: Any, field: str) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{field.upper()}_REF_MUST_BE_OBJECT"]
    keys = {str(key) for key in value}
    errors: list[str] = []
    if keys != {"kind", "ref"}:
        errors.append(f"{field.upper()}_REF_SHAPE_INVALID")
    if not str(value.get("kind") or "").strip() or not str(value.get("ref") or "").strip():
        errors.append(f"{field.upper()}_REF_EMPTY")
    return errors


def _refs(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        return [f"{field.upper()}_INVALID"]
    if len(value) != len(set(value)):
        return [f"{field.upper()}_DUPLICATED"]
    return []


def _evidence_text_index(evidence_index: Mapping[str, Any], source_units: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for anchor in evidence_index.get("anchors", []) if isinstance(evidence_index.get("anchors"), list) else []:
        if isinstance(anchor, Mapping):
            ref = str(anchor.get("anchor_ref") or "")
            text = anchor.get("text")
            if ref and isinstance(text, str):
                result[ref] = text
    for unit in source_units:
        if not isinstance(unit, Mapping):
            continue
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        ref = str(evidence.get("evidence_id") or "")
        text = evidence.get("text") or unit.get("text") or unit.get("source_text")
        if ref and isinstance(text, str):
            result.setdefault(ref, text)
    return result


def validate_entity_candidate_contract(candidate: Any) -> dict[str, Any]:
    """Validate only the internal candidate contract, with no evidence access."""
    errors: list[str] = []
    if not isinstance(candidate, Mapping):
        return {"status": "BLOCKED", "errors": ["ENTITY_CANDIDATE_MUST_BE_OBJECT"]}
    keys = {str(key) for key in candidate}
    errors.extend(f"ENTITY_REQUIRED_FIELD_MISSING:{key}" for key in sorted(ENTITY_REQUIRED_KEYS - keys))
    errors.extend(f"ENTITY_EXTRA_FIELD:{key}" for key in sorted(keys - ENTITY_REQUIRED_KEYS))
    if candidate.get("schema_version") != ENTITY_CANDIDATE_VERSION:
        errors.append("ENTITY_SCHEMA_VERSION_INVALID")
    if candidate.get("kind") not in ENTITY_KINDS:
        errors.append("ENTITY_KIND_INVALID")
    if not isinstance(candidate.get("surface_form"), str) or not candidate.get("surface_form", "").strip():
        errors.append("ENTITY_SURFACE_FORM_INVALID")
    for key in ("evidence_refs", "source_unit_refs"):
        value = candidate.get(key)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(f"{key.upper()}_INVALID")
        elif len(value) != len(set(value)):
            errors.append(f"{key.upper()}_DUPLICATED")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "authority": "UNTRUSTED_PROPOSED"}


def validate_entity_candidate(
    candidate: Any,
    *,
    evidence_index: Mapping[str, Any],
    source_units: Sequence[Mapping[str, Any]],
    source_fingerprint: str = "",
) -> dict[str, Any]:
    contract_result = validate_entity_candidate_contract(candidate)
    if contract_result["status"] != "PASS":
        return contract_result
    errors: list[str] = []
    evidence_by_ref = {str(row.get("anchor_ref")): row for row in evidence_index.get("anchors", []) if isinstance(row, Mapping) and row.get("anchor_ref")}
    unit_ids = {str(unit.get("unit_id")) for unit in source_units if isinstance(unit, Mapping) and unit.get("unit_id")}
    texts = _evidence_text_index(evidence_index, source_units)
    surface_form_found = False
    for ref in candidate.get("evidence_refs", []) if isinstance(candidate.get("evidence_refs"), list) else []:
        anchor = evidence_by_ref.get(str(ref))
        if not anchor:
            errors.append(f"EVIDENCE_REF_MISSING:{ref}")
            continue
        anchor_fp = str(anchor.get("source_fingerprint") or anchor.get("source_raw_hash") or "")
        if source_fingerprint and anchor_fp and anchor_fp != source_fingerprint:
            errors.append(f"EVIDENCE_STALE:{ref}")
        if str(anchor.get("unit_id") or "") not in {str(item) for item in candidate.get("source_unit_refs", [])}:
            errors.append(f"EVIDENCE_NOT_BOUND_TO_SOURCE_UNIT:{ref}")
        surface = str(candidate.get("surface_form") or "")
        if ref in texts and surface and surface in texts[ref]:
            surface_form_found = True
        if ref not in texts:
            errors.append(f"EVIDENCE_TEXT_UNAVAILABLE:{ref}")
    if candidate.get("evidence_refs") and not surface_form_found and isinstance(candidate.get("surface_form"), str) and candidate.get("surface_form", "").strip():
        # Keep the historical single-anchor code for compatibility while
        # enforcing the contract over the complete bound evidence set.
        refs = candidate.get("evidence_refs") or []
        if len(refs) == 1:
            errors.append(f"SURFACE_FORM_NOT_IN_EVIDENCE:{refs[0]}")
        else:
            errors.append("SURFACE_FORM_NOT_IN_ANY_BOUND_EVIDENCE")
    for ref in candidate.get("source_unit_refs", []) if isinstance(candidate.get("source_unit_refs"), list) else []:
        if str(ref) not in unit_ids:
            errors.append(f"SOURCE_UNIT_REF_MISSING:{ref}")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "authority": "UNTRUSTED_PROPOSED"}


def validate_entity_proposal(
    value: Any,
    *,
    evidence_index: Mapping[str, Any],
    source_units: Sequence[Mapping[str, Any]],
    source_fingerprint: str = "",
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"status": "BLOCKED", "errors": ["ENTITY_PROPOSAL_MUST_BE_OBJECT"], "rows": []}
    errors: list[str] = []
    keys = {str(key) for key in value}
    if keys != {"schema_version", "entities"}:
        errors.extend(f"ENTITY_WRAPPER_KEY_INVALID:{key}" for key in sorted(keys ^ {"schema_version", "entities"}))
    if value.get("schema_version") != ENTITY_PROPOSAL_VERSION:
        errors.append("ENTITY_WRAPPER_SCHEMA_VERSION_INVALID")
    entities = value.get("entities")
    if not isinstance(entities, list):
        errors.append("ENTITY_WRAPPER_ENTITIES_MUST_BE_ARRAY")
        entities = []
    rows = [{"index": index, "validation": validate_entity_candidate(item, evidence_index=evidence_index, source_units=source_units, source_fingerprint=source_fingerprint)} for index, item in enumerate(entities)]
    if any(row["validation"]["status"] != "PASS" for row in rows):
        errors.append("ENTITY_WRAPPER_CONTAINS_INVALID_CANDIDATE")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "rows": rows, "candidate_count": len(entities)}


def entity_candidate_fingerprint(candidate: Mapping[str, Any]) -> str:
    return fingerprint({key: candidate.get(key) for key in ("kind", "surface_form", "evidence_refs", "source_unit_refs")})


def assign_program_owned_entity_ids(candidates: Sequence[Mapping[str, Any]], *, only_valid: set[int] | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    next_id = 1
    for index, candidate in enumerate(candidates):
        if only_valid is not None and index not in only_valid:
            continue
        fp = entity_candidate_fingerprint(candidate)
        duplicate_of = seen.get(fp)
        if duplicate_of:
            rows.append({"proposal_entity_ref": None, "status": "BLOCKED_DUPLICATE", "duplicate_of": duplicate_of, "fingerprint": fp, "candidate_index": index})
            continue
        proposal_ref = f"PEC_{next_id:04d}"
        next_id += 1
        seen[fp] = proposal_ref
        rows.append({"proposal_entity_ref": proposal_ref, "status": "PROPOSED", "authority": "UNTRUSTED_PROPOSED", "fingerprint": fp, "candidate_index": index, "entity": dict(candidate)})
    return {"schema_version": "program_owned_proposal_entity_id_v1", "id_owner": "program", "provider_supplied_id": False, "rows": rows, "fingerprint": fingerprint(rows)}


def proposal_entity_registry(*, canonical_entities: Mapping[str, Any], assigned_entities: Mapping[str, Any]) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    for ref, value in canonical_entities.items():
        base = dict(value) if isinstance(value, Mapping) else {}
        entities[str(ref)] = {**base, "ref": str(ref), "authority": "CANONICAL_RUNTIME"}
    for row in assigned_entities.get("rows", []) if isinstance(assigned_entities.get("rows"), list) else []:
        if row.get("status") != "PROPOSED":
            continue
        ref = str(row.get("proposal_entity_ref") or "")
        entity = row.get("entity") if isinstance(row.get("entity"), Mapping) else {}
        entities[ref] = {"ref": ref, "kind": entity.get("kind"), "surface_form": entity.get("surface_form"), "authority": "UNTRUSTED_PROPOSED", "evidence_refs": entity.get("evidence_refs", []), "source_unit_refs": entity.get("source_unit_refs", []), "fingerprint": row.get("fingerprint")}
    return {"schema_version": PROPOSAL_ENTITY_REGISTRY_VERSION, "authority_boundary": "canonical_entities_are_runtime_authority; proposal_entities_are_not", "entities": entities, "fingerprint": fingerprint(entities)}


def claim_v2_candidate_contract() -> dict[str, Any]:
    return {
        "schema_version": CLAIM_V2_VERSION,
        "trust": "UNTRUSTED_PROPOSED",
        "required": sorted(CLAIM_V2_REQUIRED_KEYS),
        "provider_may_not_supply": sorted(CLAIM_V2_FORBIDDEN_FIELDS),
        "candidate_id": "program-owned after validation; absent from provider payload",
        "subject_object": {"required": ["kind", "ref"], "ref_must_be_registry_member": True, "free_text": False},
        "authority": "UNTRUSTED_PROPOSED",
    }


def claim_v2_schema() -> dict[str, Any]:
    ref_shape = {"type": "object", "required": ["kind", "ref"], "additionalProperties": False, "properties": {"kind": {"type": "string", "minLength": 1}, "ref": {"type": "string", "minLength": 1}}}
    claim = {
        "type": "object", "required": sorted(CLAIM_V2_REQUIRED_KEYS), "additionalProperties": False,
        "properties": {
            "schema_version": {"const": CLAIM_V2_VERSION}, "subject": ref_shape, "predicate": {"type": "string", "enum": sorted(FACT_CLAIM_MAPPING)}, "object": ref_shape,
            "qualifiers": {"type": "object", "additionalProperties": {"type": ["string", "boolean"]}}, "polarity": {"type": "string", "enum": list(POLARITIES)}, "modality": {"type": "string", "enum": list(MODALITIES)},
            "evidence_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True}, "source_unit_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
        },
    }
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": CLAIM_V2_SET_VERSION, "title": "Source Semantic Claim Candidate V2", "type": "object", "required": ["schema_version", "claims"], "additionalProperties": False, "properties": {"schema_version": {"const": CLAIM_V2_SET_VERSION}, "claims": {"type": "array", "items": claim}}}


def validate_claim_v2_candidate(candidate: Any, *, entity_registry: Mapping[str, Any], evidence_index: Mapping[str, Any] | None = None, source_units: Sequence[Mapping[str, Any]] = (), source_fingerprint: str = "") -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(candidate, Mapping):
        return {"status": "BLOCKED", "errors": ["CLAIM_V2_MUST_BE_OBJECT"]}
    keys = {str(key) for key in candidate}
    errors.extend(f"CLAIM_V2_REQUIRED_FIELD_MISSING:{key}" for key in sorted(CLAIM_V2_REQUIRED_KEYS - keys))
    errors.extend(f"CLAIM_V2_EXTRA_FIELD:{key}" for key in sorted(keys - CLAIM_V2_REQUIRED_KEYS))
    if candidate.get("schema_version") != CLAIM_V2_VERSION:
        errors.append("CLAIM_V2_SCHEMA_VERSION_INVALID")
    if candidate.get("predicate") not in FACT_CLAIM_MAPPING:
        errors.append("CLAIM_V2_PREDICATE_NOT_REGISTERED")
    if candidate.get("polarity") not in POLARITIES:
        errors.append("CLAIM_V2_POLARITY_INVALID")
    if candidate.get("modality") not in MODALITIES:
        errors.append("CLAIM_V2_MODALITY_INVALID")
    for field in ("subject", "object"):
        errors.extend(_validate_ref_shape(candidate.get(field), field))
        kind, ref = _ref(candidate.get(field))
        if ref and ref not in entity_registry:
            errors.append(f"UNKNOWN_ENTITY_REF:{ref}")
        if ref and isinstance(entity_registry.get(ref), Mapping) and entity_registry[ref].get("kind") and str(entity_registry[ref].get("kind")) != kind:
            errors.append(f"ENTITY_KIND_MISMATCH:{ref}")
    if not isinstance(candidate.get("qualifiers"), Mapping):
        errors.append("CLAIM_V2_QUALIFIERS_MUST_BE_OBJECT")
    errors.extend(_refs(candidate.get("evidence_refs"), "evidence_refs"))
    errors.extend(_refs(candidate.get("source_unit_refs"), "source_unit_refs"))
    if evidence_index is not None:
        evidence_by_ref = {str(row.get("anchor_ref")): row for row in evidence_index.get("anchors", []) if isinstance(row, Mapping)}
        unit_ids = {str(unit.get("unit_id")) for unit in source_units if isinstance(unit, Mapping)}
        for ref in candidate.get("evidence_refs", []) if isinstance(candidate.get("evidence_refs"), list) else []:
            anchor = evidence_by_ref.get(str(ref))
            if not anchor:
                errors.append(f"EVIDENCE_REF_MISSING:{ref}")
            elif source_fingerprint and anchor.get("source_fingerprint") and str(anchor.get("source_fingerprint")) != source_fingerprint:
                errors.append(f"EVIDENCE_STALE:{ref}")
        for ref in candidate.get("source_unit_refs", []) if isinstance(candidate.get("source_unit_refs"), list) else []:
            if str(ref) not in unit_ids:
                errors.append(f"SOURCE_UNIT_REF_MISSING:{ref}")
    for key in candidate:
        if str(key) in CLAIM_V2_FORBIDDEN_FIELDS:
            errors.append(f"CLAIM_V2_PROVIDER_AUTHORITY_FIELD_FORBIDDEN:{key}")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "authority": "UNTRUSTED_PROPOSED"}


def assign_program_owned_claim_ids(candidates: Sequence[Mapping[str, Any]], *, validation_rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    rows = []
    for index, candidate in enumerate(candidates):
        if validation_rows is not None and (index >= len(validation_rows) or validation_rows[index].get("status") != "PASS"):
            continue
        rows.append({"candidate_index": index, "claim_id": f"SCC_{len(rows) + 1:04d}", "authority": "UNTRUSTED_PROPOSED", "claim": dict(candidate)})
    return {"schema_version": CLAIM_V2_SET_VERSION, "id_owner": "program", "provider_supplied_id": False, "rows": rows, "fingerprint": fingerprint(rows)}


def structured_output_capability_contract() -> dict[str, Any]:
    return {"schema_version": STRUCTURED_CAPABILITY_VERSION, "states": ["JSON_OBJECT_ONLY", "JSON_SCHEMA_SUPPORTED", "JSON_SCHEMA_STRICT_SUPPORTED", "UNKNOWN"], "authorization": {"JSON_OBJECT_ONLY": False, "JSON_SCHEMA_SUPPORTED": False, "JSON_SCHEMA_STRICT_SUPPORTED": True, "UNKNOWN": False}, "unknown_is_fail_closed": True, "profile_field": "structured_output_capability"}


def resolve_structured_output_capability(profile: Mapping[str, Any] | None) -> dict[str, Any]:
    value = str((profile or {}).get("structured_output_capability") or "").strip().upper()
    state = value if value in {"JSON_OBJECT_ONLY", "JSON_SCHEMA_SUPPORTED", "JSON_SCHEMA_STRICT_SUPPORTED", "UNKNOWN"} else "UNKNOWN"
    declared = bool(value)
    return {"schema_version": STRUCTURED_CAPABILITY_VERSION, "state": state, "declared": declared, "authorization_allowed": state == "JSON_SCHEMA_STRICT_SUPPORTED", "fail_closed": state != "JSON_SCHEMA_STRICT_SUPPORTED", "profile_id": str((profile or {}).get("id") or ""), "provider": str((profile or {}).get("provider") or ""), "model": str((profile or {}).get("model_name") or "")}


def structured_response_format(schema: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": str(name), "strict": True, "schema": dict(schema)}}


__all__ = [
    "ENTITY_PROPOSAL_VERSION", "ENTITY_CANDIDATE_VERSION", "PROPOSAL_ENTITY_REGISTRY_VERSION", "CLAIM_V2_VERSION", "CLAIM_V2_SET_VERSION", "ENTITY_KINDS", "ENTITY_FORBIDDEN_FIELDS", "CLAIM_V2_FORBIDDEN_FIELDS", "source_entity_candidate_contract", "source_entity_proposal_schema", "validate_entity_candidate_contract", "validate_entity_candidate", "validate_entity_proposal", "entity_candidate_fingerprint", "assign_program_owned_entity_ids", "proposal_entity_registry", "claim_v2_candidate_contract", "claim_v2_schema", "validate_claim_v2_candidate", "assign_program_owned_claim_ids", "structured_output_capability_contract", "resolve_structured_output_capability", "structured_response_format", "fingerprint",
]
