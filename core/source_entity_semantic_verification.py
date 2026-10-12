"""Provider-neutral adjudication contracts for frozen source entity proposals.

Provider verdicts are evidence only. This module compiles them into
program-owned proposal states and never creates canonical entity authority.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .provider_structured_output_qualification import fingerprint
from .source_entity_proposal import entity_candidate_fingerprint


VERIFICATION_VERSION = "source_entity_semantic_verification_v1"
VERIFIED_ENTITY_REGISTRY_VERSION = "source_verified_entity_registry_v1"
MENTION_VERDICTS = ("EXPLICITLY_EVIDENCED", "NOT_EXPLICITLY_EVIDENCED", "AMBIGUOUS")
KIND_VERDICTS = ("SUPPORTED", "UNSUPPORTED", "AMBIGUOUS")
RESULT_KEYS = {"proposal_entity_ref", "mention_verdict", "kind_verdict", "evidence_refs"}

GENERIC_ENTITY_KIND_DEFINITIONS = {
    "CHARACTER": "An explicitly mentioned person or character.",
    "SCENE": "An explicitly identified scene as a narrative or production unit.",
    "LOCATION": "A place or spatial location explicitly referenced.",
    "OBJECT": "A physical object or prop explicitly referenced.",
    "ENVIRONMENT": "An environmental feature, condition, or material element.",
    "DIALOGUE_CONTENT": "Explicit spoken dialogue content.",
    "TEXT_CONTENT": "Explicit written or readable textual content.",
    "PROPERTY_VALUE": "A value serving as a property rather than an independent physical entity.",
    "STATE_VALUE": "A value or state rather than an independent entity.",
    "UNKNOWN_ENTITY": "An explicit entity mention whose safe generic classification cannot be determined.",
}


def build_verification_schema(*, proposal_refs: Sequence[str], evidence_refs: Sequence[str]) -> dict[str, Any]:
    """Build a self-contained internal contract; compile it separately for transport."""
    refs = sorted({str(ref) for ref in proposal_refs})
    evidence = sorted({str(ref) for ref in evidence_refs})
    result = {
        "type": "object",
        "required": ["proposal_entity_ref", "mention_verdict", "kind_verdict", "evidence_refs"],
        "additionalProperties": False,
        "properties": {
            "proposal_entity_ref": {"type": "string", "enum": refs},
            "mention_verdict": {"type": "string", "enum": list(MENTION_VERDICTS)},
            "kind_verdict": {"type": "string", "enum": list(KIND_VERDICTS)},
            "evidence_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "enum": evidence}},
        },
        "authority": "PROVIDER_VERDICT_ONLY",
        "trust": "UNTRUSTED_ADJUDICATION",
    }
    return {
        "type": "object",
        "required": ["schema_version", "results"],
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": VERIFICATION_VERSION},
            "results": {"type": "array", "minItems": len(refs), "items": result},
        },
        "schema_version": VERIFICATION_VERSION,
        "authority": "PROVIDER_VERDICT_ONLY",
        "trust": "UNTRUSTED_ADJUDICATION",
        "notes": "A verdict does not grant entity authority or completeness.",
    }


def validate_frozen_proposal_registry(
    *,
    registry_artifact: Mapping[str, Any],
    assignment_artifact: Mapping[str, Any],
    expected_registry_fingerprint: str,
    expected_assignment_fingerprint: str,
    expected_count: int = 15,
) -> dict[str, Any]:
    entities = registry_artifact.get("entities") if isinstance(registry_artifact.get("entities"), Mapping) else {}
    declared_registry_fp = fingerprint(entities)
    rows = assignment_artifact.get("rows") if isinstance(assignment_artifact.get("rows"), list) else []
    declared_assignment_fp = str(assignment_artifact.get("fingerprint") or "")
    proposal_rows = [
        (str(ref), value)
        for ref, value in entities.items()
        if isinstance(value, Mapping) and value.get("authority") == "UNTRUSTED_PROPOSED"
    ]
    proposal_rows.sort(key=lambda pair: pair[0])
    proposal_refs = [ref for ref, _ in proposal_rows]
    expected_refs = [f"PEC_{index:04d}" for index in range(1, expected_count + 1)]
    errors: list[str] = []
    if registry_artifact.get("schema_version") != "source_proposal_entity_registry_v1":
        errors.append("PROPOSAL_REGISTRY_SCHEMA_VERSION_INVALID")
    if registry_artifact.get("status") != "PASS":
        errors.append("PROPOSAL_REGISTRY_STATUS_INVALID")
    if registry_artifact.get("persisted") is not False:
        errors.append("PROPOSAL_REGISTRY_NOT_EVIDENCE_ONLY")
    if declared_registry_fp != expected_registry_fingerprint or registry_artifact.get("fingerprint") != expected_registry_fingerprint:
        errors.append("PROPOSAL_REGISTRY_FINGERPRINT_MISMATCH")
    if declared_assignment_fp != expected_assignment_fingerprint or assignment_artifact.get("id_owner") != "program" or assignment_artifact.get("provider_supplied_id") is True or assignment_artifact.get("provider_supplied_ids") is True or assignment_artifact.get("provider_owned_ids") is True:
        errors.append("PROGRAM_ASSIGNMENT_FINGERPRINT_OR_OWNER_MISMATCH")
    if len(proposal_rows) != expected_count or proposal_refs != expected_refs:
        errors.append("PROPOSAL_ENTITY_COUNT_OR_REF_SET_MISMATCH")
    assignment_by_ref: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("status") != "PROPOSED":
            continue
        ref = str(row.get("proposal_entity_ref") or "")
        if not ref or ref in assignment_by_ref:
            errors.append("PROGRAM_ASSIGNMENT_DUPLICATE_OR_EMPTY_REF")
            continue
        assignment_by_ref[ref] = row
    if set(assignment_by_ref) != set(expected_refs):
        errors.append("PROGRAM_ASSIGNMENT_REF_SET_MISMATCH")
    candidate_by_ref: dict[str, dict[str, Any]] = {}
    for ref, value in proposal_rows:
        assignment = assignment_by_ref.get(ref)
        if not assignment:
            continue
        source_candidate = assignment.get("entity") if isinstance(assignment.get("entity"), Mapping) else {}
        candidate = {key: value.get(key) for key in ("kind", "surface_form", "evidence_refs", "source_unit_refs")}
        if any(not candidate.get(key) for key in candidate):
            errors.append(f"FROZEN_CANDIDATE_FIELD_MISSING:{ref}")
        if value.get("ref") != ref or value.get("fingerprint") != assignment.get("fingerprint"):
            errors.append(f"FROZEN_CANDIDATE_IDENTITY_MISMATCH:{ref}")
        if entity_candidate_fingerprint(source_candidate) != assignment.get("fingerprint"):
            errors.append(f"ASSIGNED_CANDIDATE_FINGERPRINT_MISMATCH:{ref}")
        if {key: source_candidate.get(key) for key in candidate} != candidate:
            errors.append(f"FROZEN_CANDIDATE_PAYLOAD_MISMATCH:{ref}")
        candidate_by_ref[ref] = {"ref": ref, **candidate, "fingerprint": str(assignment.get("fingerprint") or "")}
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "proposal_registry_fingerprint": declared_registry_fp,
        "expected_proposal_registry_fingerprint": expected_registry_fingerprint,
        "assignment_fingerprint": declared_assignment_fp,
        "expected_assignment_fingerprint": expected_assignment_fingerprint,
        "proposal_count": len(proposal_rows),
        "proposal_refs": proposal_refs,
        "canonical_entity_count": sum(1 for value in entities.values() if isinstance(value, Mapping) and value.get("authority") == "CANONICAL_RUNTIME"),
        "candidates": candidate_by_ref,
    }


def validate_verification_coverage(value: Any, *, expected_refs: Sequence[str]) -> dict[str, Any]:
    refs = [str(ref) for ref in expected_refs]
    expected = set(refs)
    rows = value.get("results") if isinstance(value, Mapping) and isinstance(value.get("results"), list) else []
    observed = [str(row.get("proposal_entity_ref") or "") for row in rows if isinstance(row, Mapping)]
    duplicates = sorted({ref for ref in observed if ref and observed.count(ref) > 1})
    unknown = sorted({ref for ref in observed if ref not in expected})
    missing = sorted(expected - set(observed))
    malformed_rows = [index for index, row in enumerate(rows) if not isinstance(row, Mapping) or set(row) != RESULT_KEYS]
    errors = []
    if not isinstance(value, Mapping) or value.get("schema_version") != VERIFICATION_VERSION:
        errors.append("VERIFICATION_WRAPPER_SCHEMA_VERSION_INVALID")
    if len(rows) != len(refs):
        errors.append("VERIFICATION_ROW_COUNT_MISMATCH")
    if duplicates:
        errors.append("DUPLICATE_PEC_REF")
    if unknown:
        errors.append("UNKNOWN_PEC_REF")
    if missing:
        errors.append("MISSING_PEC_REF")
    if malformed_rows:
        errors.append("VERIFICATION_ROW_SHAPE_INVALID")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "expected_count": len(refs),
        "observed_count": len(rows),
        "expected_refs": sorted(expected),
        "observed_refs": observed,
        "missing_refs": missing,
        "duplicate_refs": duplicates,
        "unknown_refs": unknown,
        "malformed_row_indexes": malformed_rows,
        "results_by_ref": {str(row.get("proposal_entity_ref")): dict(row) for row in rows if isinstance(row, Mapping) and row.get("proposal_entity_ref")},
    }


def validate_verification_evidence_scope(
    results_by_ref: Mapping[str, Any], *, candidates: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for ref, result in results_by_ref.items():
        candidate = candidates.get(str(ref))
        if not candidate:
            violations.append({"proposal_entity_ref": str(ref), "code": "UNKNOWN_PEC_REF"})
            continue
        evidence_refs = result.get("evidence_refs") if isinstance(result, Mapping) and isinstance(result.get("evidence_refs"), list) else []
        allowed = {str(item) for item in candidate.get("evidence_refs", [])}
        observed = [str(item) for item in evidence_refs]
        if not observed:
            violations.append({"proposal_entity_ref": str(ref), "code": "VERIFIER_EVIDENCE_EMPTY"})
        for evidence_ref in observed:
            if evidence_ref not in allowed:
                code = "VERIFIER_EVIDENCE_SCOPE_VIOLATION"
                violations.append({"proposal_entity_ref": str(ref), "evidence_ref": evidence_ref, "code": code})
    return {"status": "PASS" if not violations else "BLOCKED", "violations": violations, "violation_count": len(violations), "cross_candidate_evidence_laundering_blocked": any(v["code"] == "VERIFIER_EVIDENCE_SCOPE_VIOLATION" for v in violations)}


def compile_verified_entity_registry(
    *,
    canonical_entities: Mapping[str, Any],
    candidates: Mapping[str, Mapping[str, Any]],
    results_by_ref: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    compiled: dict[str, Any] = {}
    for ref in sorted(candidates):
        candidate = candidates[ref]
        result = results_by_ref[ref]
        mention = str(result["mention_verdict"])
        kind = str(result["kind_verdict"])
        if mention == "NOT_EXPLICITLY_EVIDENCED" or kind == "UNSUPPORTED":
            state = "ENTITY_PROPOSAL_REJECTED"
            authority = "REJECTED_PROPOSAL"
        elif mention == "EXPLICITLY_EVIDENCED" and kind == "SUPPORTED":
            state = "SEMANTICALLY_VERIFIED_PROPOSAL"
            authority = "SEMANTICALLY_VERIFIED_PROPOSAL"
        else:
            state = "ENTITY_SEMANTIC_REVIEW_REQUIRED"
            authority = "ENTITY_SEMANTIC_REVIEW_REQUIRED"
        compiled[ref] = {
            **dict(candidate),
            "ref": ref,
            "authority": authority,
            "verification_state": state,
            "mention_verdict": mention,
            "kind_verdict": kind,
            "verification_evidence_refs": list(result["evidence_refs"]),
            "canonical": False,
        }
    rejected = sum(row["verification_state"] == "ENTITY_PROPOSAL_REJECTED" for row in compiled.values())
    reviews = sum(row["verification_state"] == "ENTITY_SEMANTIC_REVIEW_REQUIRED" for row in compiled.values())
    verified = sum(row["verification_state"] == "SEMANTICALLY_VERIFIED_PROPOSAL" for row in compiled.values())
    if rejected:
        status = "SOURCE_ENTITY_PROPOSAL_REVISION_BOUNDARY_REQUIRED"
    elif reviews:
        status = "SOURCE_ENTITY_SEMANTIC_REVIEW_REQUIRED"
    elif verified == len(candidates) and verified > 0:
        status = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_VALIDATED"
    else:
        status = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_SCHEMA_BLOCKED"
    canonical = {
        str(ref): {**(dict(value) if isinstance(value, Mapping) else {}), "ref": str(ref), "authority": "CANONICAL_RUNTIME"}
        for ref, value in canonical_entities.items()
    }
    registry = {
        "schema_version": VERIFIED_ENTITY_REGISTRY_VERSION,
        "authority_boundary": "CANONICAL_RUNTIME remains authoritative; verified PECs remain non-canonical proposals",
        "canonical_runtime_entities": canonical,
        "proposal_entities": compiled,
        "canonical_promotions": 0,
        "canonical": False,
    }
    registry["fingerprint"] = fingerprint(registry)
    return {
        "status": status,
        "verified_count": verified,
        "rejected_count": rejected,
        "review_required_count": reviews,
        "registry": registry,
    }


def verification_summary(results_by_ref: Mapping[str, Mapping[str, Any]], compiled: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(results_by_ref.values())
    states = [row.get("verification_state") for row in compiled.get("registry", {}).get("proposal_entities", {}).values()]
    return {
        "mention_explicitly_evidenced_count": sum(row.get("mention_verdict") == "EXPLICITLY_EVIDENCED" for row in rows),
        "mention_not_explicitly_evidenced_count": sum(row.get("mention_verdict") == "NOT_EXPLICITLY_EVIDENCED" for row in rows),
        "mention_ambiguous_count": sum(row.get("mention_verdict") == "AMBIGUOUS" for row in rows),
        "kind_supported_count": sum(row.get("kind_verdict") == "SUPPORTED" for row in rows),
        "kind_unsupported_count": sum(row.get("kind_verdict") == "UNSUPPORTED" for row in rows),
        "kind_ambiguous_count": sum(row.get("kind_verdict") == "AMBIGUOUS" for row in rows),
        "semantically_verified_proposal_count": states.count("SEMANTICALLY_VERIFIED_PROPOSAL"),
        "rejected_proposal_count": states.count("ENTITY_PROPOSAL_REJECTED"),
        "review_required_count": states.count("ENTITY_SEMANTIC_REVIEW_REQUIRED"),
        "canonical_promotions": 0,
        "entity_semantic_completeness": "NOT_PROVEN",
    }


def recompute_lineage_reconciliation(
    *,
    new_book: Mapping[str, Any],
    frozen_source_lineage: Mapping[str, Any],
    origin_refreeze: Mapping[str, Any],
    authority_envelope_audit: Mapping[str, Any],
    runtime_book_id: int,
    runtime_source_fingerprint: str,
    runtime_origin_source_package_id: str,
    runtime_authority_envelope: Mapping[str, Any],
    v776_source_freeze: Mapping[str, Any],
    migration_artifact: Mapping[str, Any],
    reconciliation_artifact: Mapping[str, Any],
    frozen_manifest: Mapping[str, Any],
    production_db_after: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    lineage = frozen_source_lineage.get("source_lineage") if isinstance(frozen_source_lineage.get("source_lineage"), Mapping) else {}
    locator = lineage.get("origin_source_locator") if isinstance(lineage.get("origin_source_locator"), Mapping) else {}
    actual = origin_refreeze.get("actual") if isinstance(origin_refreeze.get("actual"), Mapping) else {}
    origin_expected = origin_refreeze.get("expected") if isinstance(origin_refreeze.get("expected"), Mapping) else {}
    audited_fields = authority_envelope_audit.get("lineage_fields") if isinstance(authority_envelope_audit.get("lineage_fields"), Mapping) else {}
    new_book_row = new_book.get("book") if isinstance(new_book.get("book"), Mapping) else {}
    runtime_locator = runtime_authority_envelope.get("origin_source_locator") if isinstance(runtime_authority_envelope.get("origin_source_locator"), Mapping) else {}
    manifest_origin = frozen_manifest.get("origin") if isinstance(frozen_manifest.get("origin"), Mapping) else {}
    migration_payload = migration_artifact.get("migration") if isinstance(migration_artifact.get("migration"), Mapping) else {}
    reconciliation_payload = reconciliation_artifact.get("reconciliation") if isinstance(reconciliation_artifact.get("reconciliation"), Mapping) else {}
    expected_title = str(origin_expected.get("expected_title") or "")
    actual_title = str(actual.get("title") or "")
    checks = {
        "new_book_artifact_pass": new_book.get("status") == "PASS" and new_book.get("new_book_not_origin") is True and new_book_row.get("status") == "imported",
        "frozen_source_lineage_artifact_pass": frozen_source_lineage.get("status") == "PASS" and not (frozen_source_lineage.get("placeholder_scan", {}).get("placeholders") or []),
        "origin_refreeze_artifact_pass": origin_refreeze.get("status") == "PASS",
        "frozen_persistence_manifest_pass": frozen_manifest.get("status") == "FROZEN_COMPLETE_SELF_CONSISTENT",
        "persistence_run_id_matches": new_book.get("persistence_run_id") == frozen_manifest.get("persistence_run_id"),
        "target_book_id_matches_new_book": new_book_row.get("id") == expected.get("target_book_id") == runtime_book_id,
        "target_book_id_matches_frozen_db_after": production_db_after.get("new_book_id") == expected.get("target_book_id"),
        "origin_book_id_matches_locator_and_refreeze": locator.get("book_id") == actual.get("book_id") == origin_expected.get("book_id") == expected.get("origin_source_book_id"),
        "origin_chapter_id_matches": locator.get("chapter_id") == actual.get("chapter_id") == origin_expected.get("chapter_id") == expected.get("origin_chapter_id"),
        "origin_chapter_seq_matches": locator.get("chapter_seq") == actual.get("chapter_seq") == origin_expected.get("chapter_seq") == expected.get("origin_chapter_seq"),
        "origin_package_matches_lineage_and_envelope": lineage.get("origin_source_package_id") == audited_fields.get("origin_source_package_id") == runtime_origin_source_package_id == v776_source_freeze.get("source_package_id") == expected.get("origin_source_package_id") == f"book:{expected.get('origin_source_book_id')}",
        "origin_kind_matches_frozen_and_authority": lineage.get("origin_source_kind") == audited_fields.get("origin_source_kind") == runtime_authority_envelope.get("origin_source_kind") == "BOOK_CHAPTER",
        "origin_raw_hash_matches_all_sources": all(value == expected.get("origin_source_raw_hash") for value in (lineage.get("origin_source_raw_hash"), actual.get("raw_sha256"), origin_expected.get("expected_raw_sha256"), audited_fields.get("origin_source_raw_hash"), runtime_authority_envelope.get("origin_source_raw_hash"), runtime_source_fingerprint, v776_source_freeze.get("source_fingerprint"), manifest_origin.get("raw_sha256"))),
        "origin_raw_length_matches": actual.get("raw_byte_length") == origin_expected.get("expected_raw_byte_length") == manifest_origin.get("raw_byte_length"),
        "origin_title_matches_after_documented_normalization": " ".join(actual_title.split()) == " ".join(expected_title.split()),
        "origin_version_id_matches": lineage.get("origin_source_version_id") == audited_fields.get("origin_source_version_id") == runtime_authority_envelope.get("origin_source_version_id") == f"chapter:{expected.get('origin_chapter_id')}:sha256:{expected.get('origin_source_raw_hash')}",
        "production_migration_used_no_provider": migration_payload.get("provider_calls") == 0,
        "source_unit_freeze_matches_v776": v776_source_freeze.get("status") == "PASS" and v776_source_freeze.get("source_unit_count") == 12 and v776_source_freeze.get("source_unit_fingerprint") == expected.get("source_unit_fingerprint"),
        "migration_artifact_matches_frozen_and_authority": migration_artifact.get("status") == "PASS" and fingerprint(migration_payload) == migration_artifact.get("migration_fingerprint") == frozen_manifest.get("migration_fingerprint") == lineage.get("migration_fingerprint") == audited_fields.get("migration_fingerprint") == runtime_authority_envelope.get("migration_fingerprint"),
        "reconciliation_artifact_matches_frozen_and_authority": reconciliation_artifact.get("status") == "PASS" and fingerprint(reconciliation_payload) == reconciliation_artifact.get("reconciliation_fingerprint") == frozen_manifest.get("reconciliation_fingerprint") == lineage.get("reconciliation_fingerprint") == audited_fields.get("reconciliation_fingerprint") == runtime_authority_envelope.get("reconciliation_fingerprint"),
        "reconciliation_policy_matches": reconciliation_artifact.get("reconciliation", {}).get("policy_version") == lineage.get("reconciliation_policy_version") == audited_fields.get("reconciliation_policy_version") == runtime_authority_envelope.get("reconciliation_policy_version"),
        "structuring_response_matches": reconciliation_artifact.get("reconciliation", {}).get("source_response_sha256") == lineage.get("structuring_response_fingerprint") == audited_fields.get("structuring_response_fingerprint") == runtime_authority_envelope.get("structuring_response_fingerprint") == frozen_manifest.get("forensic_sha256"),
        "authority_envelope_audit_pass": authority_envelope_audit.get("status") == "PASS" and authority_envelope_audit.get("stale_status") == "FRESH",
        "runtime_authority_fields_match_audit": all(runtime_authority_envelope.get(key) == audited_fields.get(key) for key in ("migration_fingerprint", "origin_source_kind", "origin_source_package_id", "origin_source_raw_hash", "origin_source_version_id", "reconciliation_fingerprint", "reconciliation_policy_version", "structuring_response_fingerprint")),
        "cross_book_distinction_is_explicit": new_book_row.get("id") == expected.get("target_book_id") and actual.get("book_id") == expected.get("origin_source_book_id"),
    }
    mismatches = [key for key, passed in checks.items() if not passed]
    target_book_id = new_book_row.get("id")
    origin_book_id = actual.get("book_id")
    return {
        "schema_version": "source_scope_lineage_reconciliation_v1",
        "status": "PASS" if not mismatches else "BLOCKED",
        "checks": checks,
        "mismatches": mismatches,
        "target_book_id": target_book_id,
        "origin_source_book_id": origin_book_id,
        "origin_source_package_id": lineage.get("origin_source_package_id"),
        "origin_chapter_id": actual.get("chapter_id"),
        "origin_chapter_seq": actual.get("chapter_seq"),
        "origin_source_raw_hash": actual.get("raw_sha256"),
        "cross_book_source": target_book_id != origin_book_id,
        "cross_book_is_not_itself_a_mismatch": target_book_id != origin_book_id and checks["cross_book_distinction_is_explicit"],
        "source_unit_fingerprint": v776_source_freeze.get("source_unit_fingerprint"),
        "migration_fingerprint": lineage.get("migration_fingerprint"),
        "reconciliation_fingerprint": lineage.get("reconciliation_fingerprint"),
    }


__all__ = [
    "VERIFICATION_VERSION", "VERIFIED_ENTITY_REGISTRY_VERSION", "MENTION_VERDICTS", "KIND_VERDICTS",
    "GENERIC_ENTITY_KIND_DEFINITIONS", "build_verification_schema", "validate_frozen_proposal_registry",
    "validate_verification_coverage", "validate_verification_evidence_scope", "compile_verified_entity_registry",
    "verification_summary", "recompute_lineage_reconciliation",
]
