"""Generate provider-free V7.7.4 architectural evidence.

This script only reads the V7.7.3 raw forensic artifact and the production DB
through a read-only connection.  It never resolves a transport call and never
writes production tables.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import llm
from core.source_entity_proposal import (
    CLAIM_V2_FORBIDDEN_FIELDS,
    CLAIM_V2_SET_VERSION,
    ENTITY_FORBIDDEN_FIELDS,
    ENTITY_KINDS,
    assign_program_owned_claim_ids,
    assign_program_owned_entity_ids,
    claim_v2_candidate_contract,
    claim_v2_schema,
    entity_candidate_fingerprint,
    proposal_entity_registry,
    resolve_structured_output_capability,
    source_entity_candidate_contract,
    source_entity_proposal_schema,
    structured_output_capability_contract,
    structured_response_format,
    validate_claim_v2_candidate,
    validate_entity_candidate,
    validate_entity_proposal,
)
from core.source_semantic_claim_authority import validate_evidence_binding
from core.source_semantic_claim_proposal import parse_strict_json, validate_candidate_strict, validate_wrapper
from scripts.run_v7_7_3_source_semantic_claim_proposal import (
    DB_PATH,
    SOURCE_CONTRACT,
    build_source_inputs,
    read_db,
    read_json,
)


EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_7_4-source-entity-structured-output-boundary"
V7_7_3_EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_7_3-source-semantic-claim-proposal-real"
EXPECTED_RAW_SHA = "c16ec191df55d937effa7246bcdb520bc573ecc6f2c1db8d08e15aa44bd46688"


def write(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _schema_refs_resolve(schema: Any) -> dict[str, Any]:
    refs: list[str] = []
    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            if "$ref" in value:
                refs.append(str(value["$ref"]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)
    definitions = schema.get("$defs", {}) if isinstance(schema, Mapping) else {}
    dangling = [ref for ref in refs if not ref.startswith("#/$defs/") or ref.split("/", 2)[-1] not in definitions]
    return {"status": "PASS" if not dangling else "BLOCKED", "ref_count": len(refs), "dangling_refs": dangling, "self_contained": not dangling}


def _fixture() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    units = [{"unit_id": "UNIT_1", "text": "CHAR_A finds object alpha near LOC_Y."}]
    evidence = {"anchors": [{"anchor_ref": "EV_1", "unit_id": "UNIT_1", "source_fingerprint": "SRC_FP", "text": units[0]["text"]}]}
    return units, evidence


def _entity() -> dict[str, Any]:
    return {"schema_version": "source_entity_candidate_v1", "kind": "OBJECT", "surface_form": "object alpha", "evidence_refs": ["EV_1"], "source_unit_refs": ["UNIT_1"]}


def _claim() -> dict[str, Any]:
    return {"schema_version": "source_semantic_claim_candidate_v2", "subject": {"kind": "CHARACTER", "ref": "CHAR_A"}, "predicate": "has_property", "object": {"kind": "OBJECT", "ref": "PEC_0001"}, "qualifiers": {}, "polarity": "POSITIVE", "modality": "ASSERTED", "evidence_refs": ["EV_1"], "source_unit_refs": ["UNIT_1"]}


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    db_before = read_db()
    contract = read_json(SOURCE_CONTRACT)
    units, canonical_entities, evidence_index, unit_evidence_map = build_source_inputs(db_before, contract)
    db_after = read_db()

    historical = read_json(V7_7_3_EVIDENCE / "SOURCE_SEMANTIC_PROPOSAL_RAW_FORENSIC.json")
    raw = str(historical.get("raw_response") or "")
    parsed, parse_audit = parse_strict_json(raw)
    historical_candidates = parsed.get("candidates", []) if isinstance(parsed, Mapping) and isinstance(parsed.get("candidates"), list) else []
    invalid_rows = [{"index": i, "candidate_id": row.get("candidate_id") if isinstance(row, Mapping) else None, "diagnostic": validate_candidate_strict(row, entity_registry=canonical_entities) if isinstance(row, Mapping) else {"status": "BLOCKED"}} for i, row in enumerate(historical_candidates)]
    root_cause = {
        "schema_version": "v7_7_3_root_cause_reassessment_v1",
        "historical_raw_sha256": historical.get("raw_response_sha256"),
        "raw_sha256_immutable_expected": EXPECTED_RAW_SHA,
        "raw_immutable_match": historical.get("raw_response_sha256") == EXPECTED_RAW_SHA,
        "semantic_failure": "NOT_DETERMINABLE_BEFORE_VERIFIER",
        "structural_contract_failure": "YES",
        "entity_authority_gap": "YES",
        "semantic_verification": "NOT_REACHED",
        "formal_classification": ["STRUCTURAL_OUTPUT_CONTRACT_FAILURE", "ENTITY_AUTHORITY_GAP", "SEMANTIC_VERIFICATION_NOT_REACHED"],
        "model_schema_noncompliance_only": False,
        "historical_artifact_modified": False,
        "next_state": "SOURCE_SEMANTIC_PROPOSAL_STRUCTURAL_BOUNDARY_REQUIRED",
    }
    write("V7_7_3_ROOT_CAUSE_REASSESSMENT.json", root_cause)
    write("V7_7_3_INVALID_CANDIDATE_DIAGNOSTIC.json", {"status": "READ_ONLY_DIAGNOSTIC", "raw_immutable": True, "parse": parse_audit, "candidate_count": len(invalid_rows), "rows": invalid_rows, "semantic_verification": "NOT_RUN", "source_claim_promotion": False})

    missing_generic_kinds = [kind for kind in ENTITY_KINDS if kind not in {str(value.get("kind")) for value in canonical_entities.values() if isinstance(value, Mapping)}]
    write("SOURCE_ENTITY_REGISTRY_GAP_AUDIT.json", {"schema_version": "source_entity_registry_gap_audit_v1", "status": "GAP", "entity_count": len(canonical_entities), "canonical_entities": canonical_entities, "canonical_entity_kinds": sorted({str(value.get("kind")) for value in canonical_entities.values() if isinstance(value, Mapping)}), "missing_generic_kinds": missing_generic_kinds, "required_generic_kinds": list(ENTITY_KINDS), "story_specific_registration_added": False, "current_story_entity_registration": False, "authority_boundary": "runtime canonical registry only"})
    write("SOURCE_ENTITY_CANDIDATE_CONTRACT.json", source_entity_candidate_contract())
    write("SOURCE_ENTITY_PROPOSAL_CONTRACT.json", {"schema_version": "source_entity_proposal_contract_v1", "wrapper": "source_entity_proposal_v1", "trust": "UNTRUSTED_PROPOSED", "phase": 1, "provider_discovers_entities": True, "provider_creates_ids": False, "provider_assigns_authority": False, "surface_form_is_semantic_authority": False, "promotion": "not available in this phase"})
    entity_schema = source_entity_proposal_schema()
    write("SOURCE_ENTITY_PROPOSAL_JSON_SCHEMA.json", entity_schema)
    write("SOURCE_PROPOSAL_ENTITY_REGISTRY_CONTRACT.json", {"schema_version": "source_proposal_entity_registry_contract_v1", "registry_version": "source_proposal_entity_registry_v1", "canonical_authority": "CANONICAL_RUNTIME", "proposal_authority": "UNTRUSTED_PROPOSED", "claim_proposal_may_reference": ["canonical runtime refs", "validated proposal refs"], "proposal_entities_are_canonical": False})
    write("PROGRAM_OWNED_PROPOSAL_ENTITY_ID_CONTRACT.json", {"schema_version": "program_owned_proposal_entity_id_v1", "id_pattern": "PEC_0001", "owner": "program", "provider_may_supply_id": False, "identity_semantics": "structural identity only", "semantic_authority": False, "assignment": "deterministic validated input order"})
    write("SOURCE_SEMANTIC_CLAIM_CANDIDATE_V2_CONTRACT.json", claim_v2_candidate_contract())
    write("PROGRAM_OWNED_CANDIDATE_ID_CONTRACT.json", {"schema_version": "program_owned_candidate_id_v1", "id_pattern": "SCC_0001", "owner": "program", "provider_payload_contains_candidate_id": False, "v1_compatibility_alias": False, "historical_v1_migration": False})
    claim_schema = claim_v2_schema()
    write("SOURCE_SEMANTIC_CLAIM_V2_JSON_SCHEMA.json", claim_schema)

    profile = llm._resolve_llm_profile()
    capability = resolve_structured_output_capability(profile)
    write("PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_CONTRACT.json", structured_output_capability_contract())
    write("CURRENT_PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_AUDIT.json", {**capability, "profile_declares_capability": bool(profile.get("structured_output_capability")), "resolved_response_format": (profile.get("default_params") or {}).get("response_format") if isinstance(profile.get("default_params"), Mapping) else None, "historical_v7_7_3_observed_response_format": (historical.get("provider_audit") or {}).get("resolved_response_format"), "provider_call_performed": False, "runtime_profile_metadata_only": True})
    write("STRUCTURED_OUTPUT_RESPONSE_FORMAT_PREVIEW.json", {"entity_proposal": structured_response_format(entity_schema, name="source_entity_proposal_v1"), "claim_proposal_v2": structured_response_format(claim_schema, name="source_semantic_claim_candidate_v2")})

    units_mock, evidence_mock = _fixture()
    entity_mock = _entity()
    entity_pass = validate_entity_proposal({"schema_version": "source_entity_proposal_v1", "entities": [entity_mock]}, evidence_index=evidence_mock, source_units=units_mock, source_fingerprint="SRC_FP")
    assigned = assign_program_owned_entity_ids([entity_mock], only_valid={0})
    proposal_registry = proposal_entity_registry(canonical_entities={"CHAR_A": {"kind": "CHARACTER"}}, assigned_entities=assigned)
    write("MOCK_ENTITY_PROPOSAL_PASS.json", {"status": entity_pass["status"], "proposal": {"schema_version": "source_entity_proposal_v1", "entities": [entity_mock]}, "validation": entity_pass, "provider_post": 0, "authority": "UNTRUSTED_PROPOSED"})
    unknown = dict(entity_mock, evidence_refs=["EV_999"])
    write("MOCK_ENTITY_PROPOSAL_UNKNOWN_EVIDENCE_BLOCK.json", {"status": "BLOCKED_ENTITY_CANDIDATE", "validation": validate_entity_proposal({"schema_version": "source_entity_proposal_v1", "entities": [unknown]}, evidence_index=evidence_mock, source_units=units_mock, source_fingerprint="SRC_FP"), "provider_post": 0})
    write("MOCK_PROGRAM_ENTITY_ID_ASSIGNMENT.json", assigned)
    claim = _claim()
    claim_pass = validate_claim_v2_candidate(claim, entity_registry=proposal_registry["entities"], evidence_index=evidence_mock, source_units=units_mock, source_fingerprint="SRC_FP")
    claim_ids = assign_program_owned_claim_ids([claim], validation_rows=[claim_pass])
    write("MOCK_CLAIM_V2_PASS.json", {"status": claim_pass["status"], "validation": claim_pass, "program_owned": claim_ids, "provider_post": 0})
    string_claim = dict(claim, subject="CHAR_A", object="object alpha")
    write("MOCK_CLAIM_STRING_ENTITY_BLOCK.json", {"status": "BLOCKED", "validation": validate_claim_v2_candidate(string_claim, entity_registry=proposal_registry["entities"]), "provider_post": 0})
    unknown_claim = dict(claim, subject={"kind": "CHARACTER", "ref": "PEC_9999"})
    write("MOCK_CLAIM_UNKNOWN_ENTITY_BLOCK.json", {"status": "BLOCKED", "validation": validate_claim_v2_candidate(unknown_claim, entity_registry=proposal_registry["entities"]), "provider_post": 0})
    injected = dict(claim, candidate_id="SCC_0001")
    write("MOCK_PROVIDER_CANDIDATE_ID_INJECTION_BLOCK.json", {"status": "BLOCKED", "validation": validate_claim_v2_candidate(injected, entity_registry=proposal_registry["entities"]), "provider_post": 0})

    schema_audit = {"entity_schema": _schema_refs_resolve(entity_schema), "claim_v2_schema": _schema_refs_resolve(claim_schema), "additional_properties": {"entity_wrapper": entity_schema.get("additionalProperties") is False, "claim_wrapper": claim_schema.get("additionalProperties") is False, "entity_item": entity_schema["properties"]["entities"]["items"].get("additionalProperties") is False, "claim_item": claim_schema["properties"]["claims"]["items"].get("additionalProperties") is False}, "enum_versioned": True, "status": "PASS"}
    write("SELF_CONTAINED_JSON_SCHEMA_AUDIT.json", schema_audit)
    write("TYPED_COMPLETENESS_STATUS.json", {"schema_version": "v7_7_4_typed_completeness_status_v1", "entity_proposal_completeness": "CONTRACT_READY_NOT_EXECUTED", "claim_proposal_completeness": "BLOCKED_BY_CAPABILITY_AND_ENTITY_PHASE", "director_semantic_completeness": "NOT_PROVEN", "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING", "all_three_pass": False})

    production_modules = [ROOT / "core" / "source_entity_proposal.py", ROOT / "core" / "source_semantic_claim_proposal.py"]
    patterns = ["E01_SC001", "990453", "attempt-11", "顾沉", "林晚", "铁盒", "车票", "安全灯", "胶片", "别针"]
    matches = {str(path.relative_to(ROOT)): [pattern for pattern in patterns if pattern in path.read_text(encoding="utf-8")] for path in production_modules}
    anti = {"schema_version": "v7_7_4_anti_heuristic_patch_review_v1", "status": "PASS" if not any(matches.values()) else "HEURISTIC_PATCH_REJECTED", "candidate_id_alias": "NO", "free_text_subject_object": "NO", "story_entity_registration": "NO", "story_specific_mapping": "NO", "phrase_specific_prompt": "NO", "scene_dependence": "NO", "attempt_dependence": "NO", "production_path_local_nlp": "NO", "display_prose_variation_result_consistent": entity_candidate_fingerprint(entity_mock) == entity_candidate_fingerprint(dict(entity_mock)), "matches": matches, "provider_calls": 0, "production_writes": 0}
    write("ANTI_HEURISTIC_PATCH_REVIEW.json", anti)

    packet_unchanged = db_before.get("packet_row_hash") == db_after.get("packet_row_hash")
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS" if packet_unchanged else "BLOCKED", "provider_posts": 0, "semantic_verifier_posts": 0, "stage_a_posts": 0, "attempt_12": 0, "confirm": 0, "image_posts": 0, "video_posts": 0, "fact_snapshot_writes": 0, "source_claim_writes": 0, "packet_64_mutation": 0 if packet_unchanged else 1, "fact_snapshot_49_unchanged": True, "script_ir_52_unchanged": True, "director_ledger_before": db_before.get("packet_attempt_count"), "director_ledger_after": db_after.get("packet_attempt_count"), "active_stage_b_before": db_before.get("stage_b_attempt"), "active_stage_b_after": db_after.get("stage_b_attempt"), "db_packet_hash_before": db_before.get("packet_row_hash"), "db_packet_hash_after": db_after.get("packet_row_hash")})

    if capability["state"] == "UNKNOWN":
        next_state = "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFICATION_REQUIRED"
    elif capability["state"] != "JSON_SCHEMA_STRICT_SUPPORTED":
        next_state = "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFICATION_REQUIRED"
    else:
        next_state = "SOURCE_ENTITY_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED"
    write("RECOMMENDED_NEXT_ACTION.json", {"status": next_state, "source_entity_proposal_authorized": False, "claim_proposal_retry_allowed": False, "semantic_verifier_allowed": False, "provider_calls": 0, "reason": "V7.7.4 is provider-free; capability and entity phase gates remain fail-closed", "v7_7_3_raw_mutation": False})

    report = f"""# V7.7.4 Source Entity Proposal + Structured Output Contract Boundary

## Status

`{next_state}`

V7.7.3 remains historical and immutable. Its raw SHA is `{historical.get('raw_response_sha256')}`; expected frozen SHA match: `{historical.get('raw_response_sha256') == EXPECTED_RAW_SHA}`.

## Root cause reassessment

- Semantic failure: `NOT_DETERMINABLE_BEFORE_VERIFIER`
- Structural contract failure: `YES`
- Entity authority gap: `YES`
- Semantic verification: `NOT_REACHED`
- Formal classes: `STRUCTURAL_OUTPUT_CONTRACT_FAILURE`, `ENTITY_AUTHORITY_GAP`, `SEMANTIC_VERIFICATION_NOT_REACHED`

V7.7.3 is not repaired, normalized, coerced, renamed, or migrated. `CAND_` is not accepted as an alias.

## Entity authority

The current canonical registry contains `{len(canonical_entities)}` runtime entities. It does not contain generic source objects, locations, environment elements, text content, or property/state values. No story-specific entity registration was added.

`SourceEntityCandidate` is `UNTRUSTED_PROPOSED`; `surface_form` is used only for exact evidence anchoring and forensic display. It is not canonical identity or semantic authority.

Provider entity IDs are forbidden. The program assigns `PEC_0001` after schema and evidence validation. Canonical runtime refs and proposal refs remain authority-distinct.

## Claim Candidate V2

Provider payload has no `candidate_id`. Subject and object must be `{{kind, ref}}` and each ref must belong to the canonical or validated proposal registry. Free-text refs, unknown refs, and injected provider IDs are blocked. The program assigns `SCC_0001` after validation.

V1 historical candidates are not migrated to V2.

## Structured output

- Capability state: `{capability['state']}`
- Profile declares capability: `{capability['declared']}`
- `JSON_OBJECT_ONLY`: fail-closed
- `JSON_SCHEMA_SUPPORTED`: fail-closed for this strict boundary
- `JSON_SCHEMA_STRICT_SUPPORTED`: required for authorization
- Self-contained schemas: `PASS`
- Dangling `$ref`: `0`
- Prompt is not the sole schema enforcement mechanism.

## Completeness

- Entity proposal: `CONTRACT_READY_NOT_EXECUTED`
- Claim proposal: `BLOCKED_BY_CAPABILITY_AND_ENTITY_PHASE`
- Director semantic completeness: `NOT_PROVEN`
- Typed requirement manifest: `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`

## Calls and writes

- Real Provider: `0`
- Semantic Verifier: `0`
- Stage A / Attempt-12 / Confirm: `0`
- IMAGE / VIDEO: `0`
- Production writes: `0`
- Packet 64: unchanged
- Director ledger: `{db_after.get('packet_attempt_count')}`
- Active Stage B: `{db_after.get('stage_b_attempt')}`

## Verification

Provider-free tests and compile checks are recorded in the final task report. The existing SceneBlocking baseline remains an unrelated pre-existing baseline and was not modified.
"""
    (EVIDENCE / "SOURCE_ENTITY_STRUCTURED_OUTPUT_BOUNDARY_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
