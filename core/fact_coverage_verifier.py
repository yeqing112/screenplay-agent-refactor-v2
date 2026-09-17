"""Provider contract and deterministic authority compiler for Fact Coverage V2.

The provider proposes temporary requirement keys only.  Canonical ``REQ_*``
identities, ordering, semantic ceilings and qualification remain program-owned.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.fact_coverage import COVERAGE_STATUSES, REQUIREMENT_TYPES, fingerprint

PROPOSAL_KEY_RE = re.compile(r"^P[0-9]{3}$")
UNIT_RELEVANCES = ("RELEVANT", "NO_REQUIRED_FACT", "AMBIGUOUS")
FORBIDDEN_FIELDS = {
    "canonical_requirement_id", "requirement_ref", "new_fact", "corrected_fact",
    "replacement_fact", "new_fact_id", "fact_payload", "evidence_refs",
    "new_evidence", "new_evidence_refs", "source_modification", "final_authority",
    "final_qualification", "script_ir", "source_search", "replacement_fact",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def schema_fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def provider_schema_v2() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["requirements", "coverage_claims", "unit_assessments"],
        "additionalProperties": False,
        "properties": {
            "requirements": {"type": "array", "items": {
                "type": "object", "required": ["proposal_key", "requirement_type", "description", "source_unit_refs"], "additionalProperties": False,
                "properties": {
                    "proposal_key": {"type": "string", "pattern": r"^P[0-9]{3}$"},
                    "requirement_type": {"enum": list(REQUIREMENT_TYPES)},
                    "description": {"type": "string", "minLength": 1},
                    "source_unit_refs": {"type": "array", "items": {"type": "string", "pattern": r"^NU_[0-9]{4}$"}, "minItems": 1},
                },
            }},
            "coverage_claims": {"type": "array", "items": {
                "type": "object", "required": ["requirement_key", "fact_refs", "coverage_verdict"], "additionalProperties": False,
                "properties": {
                    "requirement_key": {"type": "string", "pattern": r"^P[0-9]{3}$"},
                    "fact_refs": {"type": "array", "items": {"type": "string", "pattern": r"^FACT_[0-9]{4}$"}},
                    "coverage_verdict": {"enum": list(COVERAGE_STATUSES)},
                },
            }},
            "unit_assessments": {"type": "array", "items": {
                "type": "object", "required": ["source_unit_ref", "relevance", "requirement_keys"], "additionalProperties": False,
                "properties": {
                    "source_unit_ref": {"type": "string", "pattern": r"^NU_[0-9]{4}$"},
                    "relevance": {"enum": list(UNIT_RELEVANCES)},
                    "requirement_keys": {"type": "array", "items": {"type": "string", "pattern": r"^P[0-9]{3}$"}},
                },
            }},
        },
    }


def contract_v2() -> dict[str, Any]:
    schema = provider_schema_v2()
    return {
        "schema_version": "fact_coverage_verifier_v2",
        "provider_owns": ["proposal_key", "requirement_type", "description", "source_unit_refs", "coverage_verdict", "fact_refs", "unit_assessment"],
        "program_owns": ["canonical_requirement_id", "final_ordering", "proposal_key_mapping", "final_coverage_disposition", "qualification_status"],
        "temporary_proposal_key_pattern": "^P[0-9]{3}$",
        "canonical_requirement_id_pattern": "^REQ_[0-9]{4}$",
        "unit_relevances": list(UNIT_RELEVANCES),
        "requirement_types": list(REQUIREMENT_TYPES),
        "coverage_statuses": list(COVERAGE_STATUSES),
        "forbidden_provider_fields": sorted(FORBIDDEN_FIELDS),
        "provider_schema": schema,
        "provider_schema_fingerprint": schema_fingerprint(schema),
        "provider_calls": 0,
        "development_preview_excluded": True,
    }


def materialize_units(*, narrative_index: dict[str, Any], raw_bytes: bytes, source_raw_hash: str, source_evidence_index: dict[str, Any] | None = None) -> dict[str, Any]:
    text = raw_bytes.decode("utf-8")
    source_by_ref = {str(row.get("anchor_ref")): row for row in (source_evidence_index or {}).get("anchors", []) if isinstance(row, dict)}
    units: list[dict[str, Any]] = []
    errors: list[str] = []
    for unit in narrative_index.get("units") or []:
        start, end = int(unit["char_start"]), int(unit["char_end"])
        exact_text = text[start:end]
        exact_hash = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
        anchor_text = "".join(str(source_by_ref[ref].get("exact_text") or "") for ref in unit.get("anchor_refs") or [] if ref in source_by_ref)
        anchor_hash = hashlib.sha256(anchor_text.encode("utf-8")).hexdigest()
        if source_evidence_index is not None and anchor_hash != unit.get("exact_text_hash"):
            errors.append(f"UNIT_ANCHOR_TEXT_HASH_MISMATCH:{unit.get('unit_id')}")
        units.append({
            "source_unit_ref": str(unit["unit_id"]), "source_order": int(unit["source_order"]),
            "char_start": start, "char_end": end, "exact_text": exact_text,
            "exact_text_sha256": exact_hash, "anchor_text_sha256": anchor_hash, "expected_anchor_text_sha256": unit.get("exact_text_hash"),
            "anchor_refs": list(unit.get("anchor_refs") or []), "source_raw_hash": source_raw_hash,
        })
    return {"schema_version": "fact_coverage_verifier_unit_materialization_v1", "provider_calls": 0, "units": units, "unit_count": len(units), "errors": errors, "status": "PASS" if not errors else "FAIL", "source_raw_hash": source_raw_hash, "fingerprint": fingerprint(units)}


def project_existing_facts(*, fact_records: list[dict[str, Any]], semantic_overlay: dict[str, Any]) -> dict[str, Any]:
    overlay = {str(row.get("fact_id")): row for row in semantic_overlay.get("facts", []) if isinstance(row, dict)}
    rows = []
    for fact in fact_records:
        fid = str(fact.get("fact_id") or "")
        sem = overlay.get(fid, {})
        rows.append({
            "fact_id": fid,
            "canonical_assertion": {key: fact.get(key) for key in ("subject_type", "subject_id", "predicate", "value", "scope")},
            "semantic_disposition": sem.get("semantic_disposition"),
            "effective_authority": sem.get("effective_authority"),
            "effective_status": sem.get("effective_status"),
            "downstream_eligible": sem.get("downstream_eligible"),
        })
    return {"schema_version": "fact_coverage_verifier_existing_fact_projection_v1", "provider_calls": 0, "facts": rows, "fact_count": len(rows), "fingerprint": fingerprint(rows)}


def build_request(*, units: dict[str, Any], facts: dict[str, Any], contract: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    return {
        "task": "fact_coverage_verifier_v2",
        "instructions": {
            "discover_minimal_story_critical_structuring_requirements": True,
            "use_only_supplied_units_and_facts": True,
            "do_not_create_or_repair_facts": True,
            "do_not_generate_canonical_req_ids": True,
            "use_temporary_proposal_keys_only": True,
            "assess_every_unit_exactly_once": True,
            "avoid_development_preview_or_expected_answers": True,
        },
        "provider": {"provider": provider, "model": model},
        "contract": {"schema_version": contract["schema_version"], "schema_fingerprint": contract["provider_schema_fingerprint"], "requirement_types": contract["requirement_types"], "coverage_statuses": contract["coverage_statuses"], "unit_relevances": contract["unit_relevances"], "forbidden_provider_fields": contract["forbidden_provider_fields"]},
        "source_narrative_units": units["units"],
        "existing_facts": facts["facts"],
    }


def _walk_forbidden(value: Any, path: str = "$") -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_FIELDS:
                found.append({"field": key_text, "path": f"{path}.{key_text}"})
            if key_text not in {"description"} and re.fullmatch(r"REQ_[0-9]{4}", str(item)):
                found.append({"field": "canonical_requirement_id_value", "path": f"{path}.{key_text}"})
            found.extend(_walk_forbidden(item, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.extend(_walk_forbidden(item, f"{path}[{i}]"))
    return found


def validate_provider_payload(payload: Any, *, unit_refs: list[str], fact_ids: list[str]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    forbidden = _walk_forbidden(payload)
    if forbidden:
        errors.append({"code": "FORBIDDEN_PROVIDER_FIELDS", "fields": forbidden})
    if not isinstance(payload, dict):
        return {"status": "FAIL", "errors": [{"code": "PROVIDER_PAYLOAD_NOT_OBJECT"}, *errors]}
    allowed_top = {"requirements", "coverage_claims", "unit_assessments"}
    extra_top = sorted(set(payload) - allowed_top)
    if extra_top:
        errors.append({"code": "UNEXPECTED_TOP_LEVEL_FIELDS", "fields": extra_top})
    requirements = payload.get("requirements")
    claims = payload.get("coverage_claims")
    assessments = payload.get("unit_assessments")
    if not all(isinstance(value, list) for value in (requirements, claims, assessments)):
        errors.append({"code": "OUTPUT_ARRAY_INVALID"})
        return {"status": "FAIL", "errors": errors, "requirements": [], "coverage_claims": [], "unit_assessments": []}
    proposal_keys: list[str] = []
    for i, row in enumerate(requirements):
        if not isinstance(row, dict):
            errors.append({"code": "REQUIREMENT_ROW_INVALID", "index": i}); continue
        if set(row) != {"proposal_key", "requirement_type", "description", "source_unit_refs"}:
            errors.append({"code": "REQUIREMENT_FIELDS_INVALID", "index": i})
        key = row.get("proposal_key")
        if not isinstance(key, str) or not PROPOSAL_KEY_RE.fullmatch(key): errors.append({"code": "PROPOSAL_KEY_INVALID", "index": i})
        proposal_keys.append(str(key))
        if row.get("requirement_type") not in REQUIREMENT_TYPES: errors.append({"code": "REQUIREMENT_TYPE_INVALID", "index": i})
        if not isinstance(row.get("description"), str) or not row.get("description"): errors.append({"code": "REQUIREMENT_DESCRIPTION_INVALID", "index": i})
        refs = row.get("source_unit_refs")
        if not isinstance(refs, list) or not refs or not all(ref in unit_refs for ref in refs): errors.append({"code": "REQUIREMENT_UNIT_REFS_INVALID", "index": i})
    duplicates = sorted({key for key in proposal_keys if proposal_keys.count(key) > 1})
    if duplicates: errors.append({"code": "DUPLICATE_PROPOSAL_KEYS", "keys": duplicates})
    claim_keys: list[str] = []
    for i, row in enumerate(claims):
        if not isinstance(row, dict) or set(row) != {"requirement_key", "fact_refs", "coverage_verdict"}:
            errors.append({"code": "COVERAGE_CLAIM_FIELDS_INVALID", "index": i}); continue
        key = row.get("requirement_key"); claim_keys.append(str(key))
        if key not in proposal_keys: errors.append({"code": "UNKNOWN_REQUIREMENT_KEY", "index": i})
        refs = row.get("fact_refs")
        if not isinstance(refs, list) or any(ref not in fact_ids for ref in refs): errors.append({"code": "UNKNOWN_FACT_REF", "index": i})
        if row.get("coverage_verdict") not in COVERAGE_STATUSES: errors.append({"code": "COVERAGE_VERDICT_INVALID", "index": i})
        if row.get("coverage_verdict") == "MISSING" and refs: errors.append({"code": "MISSING_MUST_HAVE_NO_FACT_REFS", "index": i})
    if sorted(claim_keys) != sorted(proposal_keys): errors.append({"code": "COVERAGE_CLAIMS_DO_NOT_MATCH_PROPOSALS"})
    assessed: list[str] = []
    for i, row in enumerate(assessments):
        if not isinstance(row, dict) or set(row) != {"source_unit_ref", "relevance", "requirement_keys"}:
            errors.append({"code": "UNIT_ASSESSMENT_FIELDS_INVALID", "index": i}); continue
        unit = row.get("source_unit_ref"); assessed.append(str(unit))
        if unit not in unit_refs: errors.append({"code": "UNKNOWN_UNIT_ASSESSMENT", "index": i})
        if row.get("relevance") not in UNIT_RELEVANCES: errors.append({"code": "UNIT_RELEVANCE_INVALID", "index": i})
        keys = row.get("requirement_keys")
        if not isinstance(keys, list) or any(key not in proposal_keys for key in keys): errors.append({"code": "UNIT_REQUIREMENT_KEYS_INVALID", "index": i})
        if row.get("relevance") == "RELEVANT" and not keys: errors.append({"code": "RELEVANT_UNIT_REQUIREMENT_KEYS_EMPTY", "index": i})
        if row.get("relevance") == "NO_REQUIRED_FACT" and keys: errors.append({"code": "NO_REQUIRED_FACT_KEYS_NOT_EMPTY", "index": i})
    if sorted(assessed) != sorted(unit_refs): errors.append({"code": "UNIT_ASSESSMENTS_DO_NOT_MATCH_ALL_UNITS"})
    if len(assessed) != len(set(assessed)): errors.append({"code": "DUPLICATE_UNIT_ASSESSMENT"})
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "requirements": requirements, "coverage_claims": claims, "unit_assessments": assessments, "proposal_keys": proposal_keys, "unit_refs": unit_refs, "fact_ids": fact_ids, "forbidden_fields": forbidden}


def canonicalize_requirements(validation: dict[str, Any]) -> dict[str, Any]:
    mapping = {row["proposal_key"]: f"REQ_{index:04d}" for index, row in enumerate(validation["requirements"], 1)}
    rows = []
    claims = {row["requirement_key"]: row for row in validation["coverage_claims"]}
    for row in validation["requirements"]:
        canonical_id = mapping[row["proposal_key"]]
        claim = claims[row["proposal_key"]]
        rows.append({"requirement_id": canonical_id, "proposal_key": row["proposal_key"], "requirement_type": row["requirement_type"], "description": row["description"], "source_unit_refs": row["source_unit_refs"], "supporting_fact_ids": claim["fact_refs"], "provider_coverage_verdict": claim["coverage_verdict"]})
    return {"schema_version": "fact_coverage_requirement_key_map_v2", "provider_calls": 0, "mapping": mapping, "requirements": rows, "requirement_count": len(rows), "fingerprint": fingerprint(rows)}


def compile_fact_coverage_authority_v2(*, canonical: dict[str, Any], semantic_overlay: dict[str, Any], unit_assessments: list[dict[str, Any]]) -> dict[str, Any]:
    sem = {str(row.get("fact_id")): row for row in semantic_overlay.get("facts", []) if isinstance(row, dict)}
    rows = []
    for req in canonical["requirements"]:
        refs = [fid for fid in req["supporting_fact_ids"] if fid in sem]
        dispositions = [str(sem[fid].get("semantic_disposition") or "") for fid in refs]
        provider = req["provider_coverage_verdict"]
        if provider == "MISSING": status = "MISSING"
        elif provider == "PARTIALLY_COVERED": status = "PARTIALLY_COVERED"
        elif provider == "CLAIM_ONLY": status = "CLAIM_ONLY"
        elif provider == "UNSAFE_INFERENCE": status = "UNSAFE_INFERENCE"
        elif provider == "AMBIGUOUS": status = "AMBIGUOUS"
        elif any(item == "WORLD_FACT_CONFIRMED" for item in dispositions): status = "COVERED"
        elif any(item == "PARTIAL_SUPPORT_REVIEW" for item in dispositions): status = "PARTIALLY_COVERED"
        elif any(item == "CLAIM_SUPPORTED" for item in dispositions): status = "COVERED" if req["requirement_type"] == "CLAIM_OR_BELIEF" else "CLAIM_ONLY"
        elif any(item == "INFERENCE_PROPOSED" for item in dispositions): status = "UNSAFE_INFERENCE"
        else: status = "MISSING"
        rows.append({**req, "semantic_fact_dispositions": dispositions, "final_coverage_status": status, "review_required": status != "COVERED", "machine_authority_ceiling_applied": status != provider})
    counts = {status: sum(1 for row in rows if row["final_coverage_status"] == status) for status in COVERAGE_STATUSES}
    ambiguous_units = sum(1 for row in unit_assessments if row.get("relevance") == "AMBIGUOUS")
    if ambiguous_units: qualification = "FACT_COVERAGE_REVIEW_REQUIRED"
    elif any(row["final_coverage_status"] != "COVERED" for row in rows): qualification = "FACT_COVERAGE_INSUFFICIENT"
    else: qualification = "FACT_COVERAGE_CANDIDATE_QUALIFIED"
    return {"schema_version": "fact_coverage_authority_matrix_v2", "provider_calls": 0, "rows": rows, "counts": counts, "unit_assessment_counts": {rel: sum(1 for row in unit_assessments if row.get("relevance") == rel) for rel in UNIT_RELEVANCES}, "qualification_status": qualification, "fact_coverage_qualified": qualification == "FACT_COVERAGE_CANDIDATE_QUALIFIED", "runtime_authority": True, "human_review": "NOT_RECORDED", "fingerprint": fingerprint(rows)}


__all__ = ["PROPOSAL_KEY_RE", "UNIT_RELEVANCES", "FORBIDDEN_FIELDS", "provider_schema_v2", "contract_v2", "schema_fingerprint", "materialize_units", "project_existing_facts", "build_request", "validate_provider_payload", "canonicalize_requirements", "compile_fact_coverage_authority_v2"]
