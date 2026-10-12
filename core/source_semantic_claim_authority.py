"""Provider-free SourceClaim authority and deterministic materialization.

The module accepts only typed FactRecord data, a program-owned semantic
authority overlay, immutable evidence anchors, runtime entity references and
versioned relation mappings.  It never reads prose or calls a provider.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .director_claim_relation_registry import RELATION_REGISTRY_VERSION, relation_compatible


CANDIDATE_VERSION = "source_semantic_claim_candidate_v1"
FACT_VALUE_VERSION = "source_semantic_fact_value_v1"
FACT_CLAIM_MAPPING_VERSION = "source_fact_claim_mapping_registry_v1"
AUTHORITY_CONTRACT_VERSION = "director_source_claim_authority_contract_v1"
ELIGIBILITY_VERSION = "director_source_claim_materialization_eligibility_v1"
COVERAGE_VERSION = "director_source_claim_coverage_v1"
UNIT_BINDING_VERSION = "source_unit_claim_binding_v1"
SOURCE_CLAIM_SET_VERSION = "director_source_claim_set_v1"

POLARITIES = ("POSITIVE", "NEGATED", "PROHIBITION", "META_COMPLIANCE", "DELEGATION")
MODALITIES = ("ASSERTED", "UNCERTAIN", "POSSIBLE", "HYPOTHETICAL", "PLAYABLE_OPTION", "DELEGATED", "PROHIBITED")
ELIGIBLE_AUTHORITIES = ("source_text", "locked_fact", "approved_fact")
FORBIDDEN_CANDIDATE_FIELDS = {"char_start", "char_end", "byte_start", "byte_end", "sha256", "source_claim_supported", "final_authority", "final_status", "promote", "new_fact", "source_search"}

FACT_CLAIM_MAPPING: dict[str, dict[str, Any]] = {
    "scene_existence": {"claim_type": "SOURCE_EVENT", "relation_class": "OBJECT_EXISTENCE", "legacy_mapping": "STRUCTURAL_COUNT"},
    "scene_identity_evidence": {"claim_type": "SOURCE_EVENT", "relation_class": "SOURCE_EVENT", "legacy_mapping": "STRUCTURAL_EVIDENCE_SET"},
    "enter_guided": {"claim_type": "CHARACTER_ACTION", "relation_class": "ACTION"},
    "speech_act": {"claim_type": "SOURCE_SPEECH_ACT", "relation_class": "SPEECH_ACT"},
    "has_property": {"claim_type": "OBJECT_PROPERTY", "relation_class": "OBJECT_PROPERTY"},
    "state_value": {"claim_type": "ENVIRONMENT_STATE", "relation_class": "ENVIRONMENT_STATE"},
    "uncertainty": {"claim_type": "UNCERTAINTY", "relation_class": "UNCERTAINTY"},
    "received_by": {"claim_type": "OBJECT_POSSESSION", "relation_class": "POSSESSION"},
    "left_by": {"claim_type": "OBJECT_PROVENANCE", "relation_class": "PROVENANCE"},
    "knows": {"claim_type": "CHARACTER_KNOWLEDGE", "relation_class": "KNOWLEDGE_STATE"},
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _ref(value: Any) -> tuple[str, str]:
    if not isinstance(value, Mapping):
        return "", ""
    return str(value.get("kind") or ""), str(value.get("ref") or "")


def source_semantic_fact_value_contract() -> dict[str, Any]:
    return {
        "schema_version": FACT_VALUE_VERSION,
        "required": ["schema_version", "object", "qualifiers", "polarity", "modality"],
        "object": {"kind": "canonical entity or typed value kind", "ref": "canonical runtime reference or value token"},
        "qualifiers": "typed object; no arbitrary untyped authority payload",
        "polarity": list(POLARITIES),
        "modality": list(MODALITIES),
        "display_prose_allowed": False,
    }


def validate_fact_value(value: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return {"status": "BLOCKED", "errors": ["FACT_VALUE_MUST_BE_OBJECT"]}
    if value.get("schema_version") != FACT_VALUE_VERSION:
        errors.append("FACT_VALUE_SCHEMA_VERSION_INVALID")
    obj = value.get("object")
    if not isinstance(obj, Mapping) or not str(obj.get("kind") or "").strip() or not str(obj.get("ref") or "").strip():
        errors.append("FACT_VALUE_OBJECT_REF_REQUIRED")
    if not isinstance(value.get("qualifiers"), Mapping):
        errors.append("FACT_VALUE_QUALIFIERS_MUST_BE_OBJECT")
    if value.get("polarity") not in POLARITIES:
        errors.append("FACT_VALUE_POLARITY_INVALID")
    if value.get("modality") not in MODALITIES:
        errors.append("FACT_VALUE_MODALITY_INVALID")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors}


def candidate_contract() -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_VERSION,
        "trust": "UNTRUSTED_PROPOSED",
        "required": ["schema_version", "candidate_id", "subject", "predicate", "object", "qualifiers", "polarity", "modality", "evidence_refs", "source_unit_refs"],
        "provider_may_supply": ["typed claim fields", "evidence_refs", "source_unit_refs", "candidate_id"],
        "provider_may_not_supply": sorted(FORBIDDEN_CANDIDATE_FIELDS),
        "offsets_and_hashes": "program-owned evidence resolution only",
    }


def validate_candidate(candidate: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(candidate, Mapping):
        return {"status": "BLOCKED", "errors": ["CANDIDATE_MUST_BE_OBJECT"]}
    if candidate.get("schema_version") != CANDIDATE_VERSION:
        errors.append("CANDIDATE_SCHEMA_VERSION_INVALID")
    if not re.fullmatch(r"SCC_[A-Za-z0-9_]+", str(candidate.get("candidate_id") or "")):
        errors.append("CANDIDATE_ID_INVALID")
    for key in ("subject", "object", "qualifiers"):
        if not isinstance(candidate.get(key), Mapping):
            errors.append(f"CANDIDATE_{key.upper()}_INVALID")
    for key in ("evidence_refs", "source_unit_refs"):
        if not isinstance(candidate.get(key), list) or not all(isinstance(item, str) for item in candidate.get(key)):
            errors.append(f"CANDIDATE_{key.upper()}_INVALID")
    if candidate.get("polarity") not in POLARITIES:
        errors.append("CANDIDATE_POLARITY_INVALID")
    if candidate.get("modality") not in MODALITIES:
        errors.append("CANDIDATE_MODALITY_INVALID")
    def walk(value: Any, path: str = "$") -> list[str]:
        found: list[str] = []
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in FORBIDDEN_CANDIDATE_FIELDS:
                    found.append(f"{path}.{key}")
                found.extend(walk(item, f"{path}.{key}"))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found.extend(walk(item, f"{path}[{index}]"))
        return found
    forbidden = walk(candidate)
    if forbidden:
        errors.append("CANDIDATE_PROVIDER_AUTHORITY_FIELDS_FORBIDDEN:" + ",".join(forbidden))
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors}


def fact_claim_mapping_registry() -> dict[str, Any]:
    return {"schema_version": FACT_CLAIM_MAPPING_VERSION, "mappings": FACT_CLAIM_MAPPING, "relation_registry_version": RELATION_REGISTRY_VERSION, "raw_text_semantics": False}


def validate_evidence_binding(*, evidence_refs: list[str], evidence_index: Mapping[str, Any], source_fingerprint: str, source_package_id: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    refs = [str(ref) for ref in evidence_refs]
    if len(refs) != len(set(refs)):
        errors.append("EVIDENCE_REFS_DUPLICATED")
    anchors = {str(row.get("anchor_ref")): row for row in evidence_index.get("anchors", []) if isinstance(row, Mapping)}
    for ref in refs:
        anchor = anchors.get(ref)
        if not anchor:
            errors.append(f"EVIDENCE_REF_MISSING:{ref}")
            continue
        anchor_fp = str(anchor.get("source_fingerprint") or anchor.get("source_raw_hash") or "")
        if source_fingerprint and anchor_fp and anchor_fp != source_fingerprint:
            errors.append(f"EVIDENCE_STALE:{ref}")
        if source_package_id and anchor.get("source_package_id") and str(anchor.get("source_package_id")) != source_package_id:
            errors.append(f"EVIDENCE_PACKAGE_MISMATCH:{ref}")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors, "resolved_refs": [ref for ref in refs if ref in anchors]}


def validate_entity_binding(*, claim: Mapping[str, Any], entity_registry: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for field in ("subject", "object"):
        kind, ref = _ref(claim.get(field))
        if not kind or not ref:
            errors.append(f"{field.upper()}_ENTITY_REF_REQUIRED")
        elif ref not in entity_registry:
            errors.append(f"UNKNOWN_ENTITY_REF:{ref}")
        elif isinstance(entity_registry.get(ref), Mapping) and entity_registry[ref].get("kind") and str(entity_registry[ref].get("kind")) != kind:
            errors.append(f"ENTITY_KIND_MISMATCH:{ref}")
    return {"status": "PASS" if not errors else "BLOCKED", "errors": errors}


def source_claim_fingerprint(claim: Mapping[str, Any]) -> str:
    material = {
        "claim_type": claim.get("claim_type"), "subject": claim.get("subject"), "predicate": claim.get("predicate"),
        "object": claim.get("object"), "qualifiers": claim.get("qualifiers"), "polarity": claim.get("polarity"),
        "modality": claim.get("modality"), "source_fact_id": claim.get("source_fact_id"), "evidence_refs": sorted(claim.get("evidence_refs") or []),
    }
    return _sha(material)


def source_claim_set_fingerprint(claims: Iterable[Mapping[str, Any]]) -> str:
    return _sha({"schema_version": SOURCE_CLAIM_SET_VERSION, "claims": sorted((dict(item) for item in claims), key=lambda row: str(row.get("claim_id") or ""))})


def materialization_eligibility(*, fact: Mapping[str, Any], semantic_overlay: Mapping[str, Any] | None, evidence_index: Mapping[str, Any], source_fingerprint: str, entity_registry: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    fact_id = str(fact.get("fact_id") or "")
    if fact.get("status") != "confirmed":
        errors.append("FACT_STATUS_NOT_CONFIRMED")
    if fact.get("authority") not in ELIGIBLE_AUTHORITIES:
        errors.append("FACT_AUTHORITY_NOT_ELIGIBLE")
    value_result = validate_fact_value(fact.get("value"))
    if str(fact.get("predicate") or "") not in FACT_CLAIM_MAPPING:
        errors.append("FACT_PREDICATE_MAPPING_MISSING")
    if value_result["status"] != "PASS":
        mapping = FACT_CLAIM_MAPPING.get(str(fact.get("predicate") or ""), {})
        if not mapping.get("legacy_mapping"):
            errors.extend(value_result["errors"])
        else:
            errors.append("LEGACY_FACT_NOT_SOURCECLAIM_ELIGIBLE")
    overlay = semantic_overlay or {}
    if overlay.get("semantic_disposition") != "WORLD_FACT_CONFIRMED":
        errors.append("SEMANTIC_AUTHORITY_NOT_WORLD_FACT_CONFIRMED")
    if overlay.get("downstream_eligible") is not True:
        errors.append("SEMANTIC_AUTHORITY_DOWNSTREAM_NOT_ELIGIBLE")
    if overlay.get("review_required") is not False:
        errors.append("SEMANTIC_AUTHORITY_REVIEW_REQUIRED")
    evidence_refs = fact.get("evidence") if isinstance(fact.get("evidence"), list) else []
    evidence = validate_evidence_binding(evidence_refs=evidence_refs, evidence_index=evidence_index, source_fingerprint=source_fingerprint)
    if evidence["status"] != "PASS":
        errors.extend(evidence["errors"])
    entity = {"status": "PASS", "errors": []}
    if value_result["status"] == "PASS":
        value = fact.get("value") or {}
        entity = validate_entity_binding(claim={"subject": {"kind": str(fact.get("subject_type") or ""), "ref": str(fact.get("subject_id") or "")}, "object": value.get("object")}, entity_registry=entity_registry)
        if entity["status"] != "PASS":
            errors.extend(entity["errors"])
    return {"schema_version": ELIGIBILITY_VERSION, "fact_id": fact_id, "status": "PASS" if not errors else "BLOCKED", "errors": sorted(set(errors)), "value_validation": value_result, "evidence_validation": evidence, "entity_validation": entity, "provider_verdict_is_non_authoritative": True}


def materialize_source_claim_from_fact_authority(*, fact: Mapping[str, Any], semantic_overlay: Mapping[str, Any] | None, entity_registry: Mapping[str, Any], evidence_index: Mapping[str, Any], source_fingerprint: str, fact_snapshot_id: int | str, semantic_authority_fingerprint: str, relation_registry_version: str = RELATION_REGISTRY_VERSION) -> dict[str, Any]:
    eligibility = materialization_eligibility(fact=fact, semantic_overlay=semantic_overlay, evidence_index=evidence_index, source_fingerprint=source_fingerprint, entity_registry=entity_registry)
    if eligibility["status"] != "PASS":
        return {"status": "BLOCKED", "claim": None, "eligibility": eligibility}
    mapping = FACT_CLAIM_MAPPING.get(str(fact.get("predicate") or ""), {})
    value = fact.get("value") or {}
    claim = {
        "schema_version": "director_claim_ir_v1",
        "claim_id": f"SC_{fact.get('fact_id')}",
        "claim_type": mapping.get("claim_type"),
        "relation_class": mapping.get("relation_class"),
        "subject": {"kind": str(fact.get("subject_type") or ""), "ref": str(fact.get("subject_id") or "")},
        "predicate": str(fact.get("predicate") or ""),
        "object": dict(value.get("object") or {}),
        "qualifiers": dict(value.get("qualifiers") or {}),
        "polarity": value.get("polarity"),
        "modality": value.get("modality"),
        "source_fact_id": str(fact.get("fact_id") or ""),
        "fact_snapshot_id": str(fact_snapshot_id),
        "semantic_authority_fingerprint": semantic_authority_fingerprint,
        "evidence_refs": sorted(str(item) for item in fact.get("evidence") or []),
        "source_fingerprint": source_fingerprint,
        "entity_registry_fingerprint": _sha(entity_registry),
        "relation_registry_version": relation_registry_version,
    }
    claim["fingerprint"] = source_claim_fingerprint(claim)
    return {"status": "PASS", "claim": claim, "eligibility": eligibility}


def materialize_source_claim_set(*, facts: list[Mapping[str, Any]], semantic_overlay: Mapping[str, Any], entity_registry: Mapping[str, Any], evidence_index: Mapping[str, Any], source_fingerprint: str, fact_snapshot_id: int | str, semantic_authority_fingerprint: str) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    overlay_rows = {str(row.get("fact_id")): row for row in semantic_overlay.get("facts", []) if isinstance(row, Mapping)}
    for fact in facts:
        result = materialize_source_claim_from_fact_authority(fact=fact, semantic_overlay=overlay_rows.get(str(fact.get("fact_id"))), entity_registry=entity_registry, evidence_index=evidence_index, source_fingerprint=source_fingerprint, fact_snapshot_id=fact_snapshot_id, semantic_authority_fingerprint=semantic_authority_fingerprint)
        rows.append({"fact_id": fact.get("fact_id"), "status": result["status"], "errors": result["eligibility"].get("errors", [])})
        if result.get("claim"):
            claims.append(result["claim"])
    return {"schema_version": SOURCE_CLAIM_SET_VERSION, "status": "PASS" if claims and all(row["status"] == "PASS" for row in rows) else "BLOCKED", "fact_snapshot_id": fact_snapshot_id, "claims": claims, "claim_count": len(claims), "claim_set_fingerprint": source_claim_set_fingerprint(claims), "fact_results": rows}


def materialize_dialogue_speech_act_claim(*, dialogue: Mapping[str, Any], evidence_index: Mapping[str, Any], source_fingerprint: str, entity_registry: Mapping[str, Any], fact_snapshot_id: int | str, semantic_authority_fingerprint: str) -> dict[str, Any]:
    """Deterministically preserve a structured dialogue occurrence only."""
    speaker = {"kind": "CHARACTER", "ref": str(dialogue.get("speaker_ref") or dialogue.get("speaker") or "")}
    dialogue_ref = str(dialogue.get("dialogue_id") or dialogue.get("source_ref") or "")
    refs = list(dialogue.get("source_evidence_refs") or dialogue.get("evidence_refs") or [])
    claim = {"schema_version": "director_claim_ir_v1", "claim_id": f"SC_{dialogue_ref}", "claim_type": "SOURCE_SPEECH_ACT", "relation_class": "SPEECH_ACT", "subject": speaker, "predicate": "speech_act", "object": {"kind": "DIALOGUE_CONTENT", "ref": dialogue_ref}, "qualifiers": {"speaker_binding": str(dialogue.get("speaker_binding") or "")}, "polarity": "POSITIVE", "modality": "ASSERTED", "source_fact_id": dialogue_ref, "fact_snapshot_id": str(fact_snapshot_id), "semantic_authority_fingerprint": semantic_authority_fingerprint, "evidence_refs": sorted(str(item) for item in refs), "source_fingerprint": source_fingerprint, "entity_registry_fingerprint": _sha(entity_registry), "relation_registry_version": RELATION_REGISTRY_VERSION}
    claim["fingerprint"] = source_claim_fingerprint(claim)
    dialogue_entities = dict(entity_registry)
    dialogue_entities[dialogue_ref] = {"kind": "DIALOGUE_CONTENT"}
    entity = validate_entity_binding(claim=claim, entity_registry=dialogue_entities)
    evidence = validate_evidence_binding(evidence_refs=refs, evidence_index=evidence_index, source_fingerprint=source_fingerprint)
    if entity["status"] != "PASS" or evidence["status"] != "PASS":
        return {"status": "BLOCKED", "claim": None, "entity_validation": entity, "evidence_validation": evidence}
    return {"status": "PASS", "claim": claim, "entity_validation": entity, "evidence_validation": evidence, "world_fact_created": False}


def source_claim_coverage(*, source_units: list[Mapping[str, Any]], source_claims: list[Mapping[str, Any]], required_semantic_types: list[str], typed_requirement_manifest_present: bool) -> dict[str, Any]:
    available_types = sorted(set(str(claim.get("relation_class") or "") for claim in source_claims))
    missing = sorted(set(required_semantic_types) - set(available_types))
    if not typed_requirement_manifest_present:
        missing.append("TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING")
    status = "SUFFICIENT" if not missing else "INSUFFICIENT"
    return {"schema_version": COVERAGE_VERSION, "status": status, "source_unit_count": len(source_units), "source_claim_count": len(source_claims), "available_semantic_types": available_types, "required_semantic_types": sorted(set(required_semantic_types)), "missing_requirements": sorted(set(missing)), "one_source_unit_need_not_equal_one_claim": True, "director_semantic_coverage": status}


def source_unit_claim_binding(*, source_unit_id: str, source_claim_ids: list[str], source_fingerprint: str) -> dict[str, Any]:
    return {"schema_version": UNIT_BINDING_VERSION, "source_unit_id": str(source_unit_id), "source_claim_ids": sorted(set(str(item) for item in source_claim_ids)), "source_fingerprint": source_fingerprint, "status": "PASS" if source_unit_id else "BLOCKED"}


def source_claim_authority_contract() -> dict[str, Any]:
    return {"schema_version": AUTHORITY_CONTRACT_VERSION, "dual_gate": ["EVIDENCE_AUTHORITY", "SEMANTIC_AUTHORITY"], "confirmed_fact_alone_is_not_sourceclaim_authority": True, "required_overlay": {"semantic_disposition": "WORLD_FACT_CONFIRMED", "downstream_eligible": True, "review_required": False}, "provider_verdict_is_non_authoritative": True, "eligible_fact_authorities": list(ELIGIBLE_AUTHORITIES)}


__all__ = ["CANDIDATE_VERSION", "FACT_VALUE_VERSION", "FACT_CLAIM_MAPPING_VERSION", "AUTHORITY_CONTRACT_VERSION", "ELIGIBILITY_VERSION", "COVERAGE_VERSION", "UNIT_BINDING_VERSION", "SOURCE_CLAIM_SET_VERSION", "candidate_contract", "validate_candidate", "source_semantic_fact_value_contract", "validate_fact_value", "fact_claim_mapping_registry", "validate_evidence_binding", "validate_entity_binding", "source_claim_fingerprint", "source_claim_set_fingerprint", "materialization_eligibility", "materialize_source_claim_from_fact_authority", "materialize_source_claim_set", "materialize_dialogue_speech_act_claim", "source_claim_coverage", "source_unit_claim_binding", "source_claim_authority_contract"]
