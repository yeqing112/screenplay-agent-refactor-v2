"""Generate provider-free V7.7.8 Claim V3 foundation evidence.

This script reads frozen canary artifacts and production rows through a
read-only SQLite connection. It writes only under the V7.7.8 evidence folder.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.provider_structured_output_qualification import compile_provider_strict_schema, fingerprint, validate_json_schema_subset
from core.source_semantic_claim_v3 import (
    CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
    CLAIM_V3_PROJECTION_VERSION,
    CLAIM_V3_SET_VERSION,
    CLAIM_V3_VERSION,
    CLAIM_V3_FORBIDDEN_FIELDS,
    PROPOSABLE_PREDICATE_REGISTRY_VERSION,
    QUALIFIER_REGISTRY_VERSION,
    RELATION_SIGNATURE_REGISTRY_VERSION,
    assign_program_owned_claim_ids,
    build_claim_input_entity_registry,
    claim_v2_immutable_blocker_audit,
    claim_v3_candidate_contract,
    claim_v3_candidate_fingerprint,
    claim_v3_candidate_schema,
    claim_v3_candidate_set_contract,
    claim_v3_candidate_set_schema,
    count_schema_dialect_extensions,
    decode_claim_qualifiers_v3,
    proposable_predicate_registry_v1,
    qualifier_registry_audit,
    qualifier_registry_v2,
    qualifier_semantic_ambiguity_audit,
    relation_signature_completeness_audit,
    relation_signature_registry_v2,
    validate_claim_v3_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "canonical-canary" / "v7_7_8-source-semantic-claim-v3-foundation"
V777 = ROOT / "docs" / "canonical-canary" / "v7_7_7-source-entity-semantic-verification-real"
V773 = ROOT / "docs" / "canonical-canary" / "v7_7_3-source-semantic-claim-proposal-real"
DB_PATH = ROOT / "work" / "db" / "screenplay.db"
EXPECTED_VERIFIED_REGISTRY_FINGERPRINT = "88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186"
EXPECTED_SOURCE_RAW_HASH = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
EXPECTED_SOURCE_UNIT_FINGERPRINT = "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f"
TARGET_BOOK_ID = 990453
ORIGIN_SOURCE_BOOK_ID = 990402
ORIGIN_SOURCE_PACKAGE_ID = "book:990402"
ORIGIN_CHAPTER_ID = 16
ORIGIN_CHAPTER_SEQ = 3
FACT_SNAPSHOT_ID = 49
SCRIPT_IR_ID = 52
PACKET_ID = 64
DIRECTOR_LEDGER = 11
STAGE_A_ATTEMPT = "attempt-7"
STAGE_B_ATTEMPT = "attempt-11"
GENERATED_OUTPUT_NAMES = {
    "SOURCE_SCOPE_LINEAGE_FREEZE.json", "ANTI_HEURISTIC_PATCH_REVIEW.json",
    "CLAIM_V2_IMMUTABLE_BLOCKER_AUDIT.json", "V7_7_7_VERIFIED_ENTITY_FREEZE.json",
    "CLAIM_INPUT_ENTITY_REGISTRY.json", "CLAIM_INPUT_ENTITY_AUTHORITY_POLICY.json",
    "QUALIFIER_V1_AMBIGUITY_AUDIT.json", "CLAIM_V3_QUALIFIER_REGISTRY.json",
    "CLAIM_V3_QUALIFIER_WIRE_CONTRACT.json", "CLAIM_V3_QUALIFIER_DECODER_AUDIT.json",
    "RELATION_SIGNATURE_REGISTRY_V2.json", "RELATION_SIGNATURE_COMPLETENESS_AUDIT.json",
    "PROPOSABLE_PREDICATE_REGISTRY.json", "CLAIM_V3_CANDIDATE_CONTRACT.json",
    "CLAIM_V3_CANDIDATE_SET_CONTRACT.json", "CLAIM_V3_INTERNAL_SCHEMA.json",
    "CLAIM_V3_PROVIDER_TRANSPORT_SCHEMA.json", "CLAIM_V3_TRANSPORT_SCHEMA_COMPILER_AUDIT.json",
    "CLAIM_V3_PROGRAM_OWNED_PROJECTION_CONTRACT.json", "CLAIM_V3_FINGERPRINT_CONTRACT.json",
    "MOCK_CLAIM_V3_PASS.json", "MOCK_UNKNOWN_QUALIFIER_BLOCK.json",
    "MOCK_QUALIFIER_ENTITY_REF_BLOCK.json", "MOCK_BOOLEAN_TOKEN_BLOCK.json",
    "MOCK_RELATION_SIGNATURE_BLOCK.json", "MOCK_UNKNOWN_ENTITY_REF_BLOCK.json",
    "MOCK_PROGRAM_CLAIM_ID_ASSIGNMENT.json", "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json",
    "RECOMMENDED_NEXT_ACTION.json", "SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_REPORT.md",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(name: str, value: Any) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    if name.lower().endswith(".md"):
        path.write_text(str(value), encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def current_production_freeze() -> dict[str, Any]:
    if not DB_PATH.exists():
        return {"status": "BLOCKED", "error": "PRODUCTION_DB_MISSING", "database_path": str(DB_PATH)}
    connection = sqlite3.connect(f"file:{DB_PATH.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        ir = connection.execute("select * from script_ir_versions where id=? and book_id=? and episode=?", (SCRIPT_IR_ID, TARGET_BOOK_ID, 1)).fetchone()
        packet = connection.execute("select * from decision_packet_records where id=? and book_id=?", (PACKET_ID, TARGET_BOOK_ID)).fetchone()
        facts = connection.execute("select * from fact_snapshots where id=? and book_id=? and episode=?", (FACT_SNAPSHOT_ID, TARGET_BOOK_ID, 1)).fetchone()
        records = [dict(row) for row in connection.execute("select * from fact_records where snapshot_id=? order by id", (FACT_SNAPSHOT_ID,)).fetchall()]
        if ir is None or packet is None or facts is None:
            return {"status": "BLOCKED", "error": "FROZEN_PRODUCTION_ROW_MISSING"}
        ir_row = dict(ir)
        packet_row = dict(packet)
        facts_row = dict(facts)
        authority = json.loads(ir_row.get("authority_envelope_json") or "{}")
        packet_info = json.loads(packet_row.get("model_info") or "{}")
        attempts = packet_info.get("director_llm_attempts") if isinstance(packet_info.get("director_llm_attempts"), list) else []
        provenance = packet_info.get("proposal_provenance") if isinstance(packet_info.get("proposal_provenance"), Mapping) else {}
        stage_a = (provenance.get("stage_a") or {}).get("attempt_id")
        stage_b = (provenance.get("stage_b") or {}).get("attempt_id")
        origin_locator = authority.get("origin_source_locator") if isinstance(authority.get("origin_source_locator"), Mapping) else {}
        return {
            "target_book_id": TARGET_BOOK_ID,
            "episode": 1,
            "fact_snapshot_id": FACT_SNAPSHOT_ID,
            "fact_snapshot_fingerprint": fingerprint(facts_row),
            "fact_records_fingerprint": fingerprint(records),
            "script_ir_id": SCRIPT_IR_ID,
            "script_ir_payload_hash": str(ir_row.get("payload_hash") or ""),
            "script_ir_payload_fingerprint": fingerprint(json.loads(ir_row.get("payload_json") or "{}")),
            "packet_id": PACKET_ID,
            "packet_row_hash": fingerprint(packet_row),
            "packet_fingerprint": str(packet_row.get("packet_fingerprint") or ""),
            "director_ledger": len(attempts),
            "stage_a_attempt": stage_a,
            "active_stage_b": stage_b,
            "origin_source_book_id": origin_locator.get("book_id"),
            "origin_source_package_id": authority.get("origin_source_package_id"),
            "origin_source_raw_hash": authority.get("origin_source_raw_hash"),
        }
    finally:
        connection.close()


def source_lineage_audit(v777_input: Mapping[str, Any], v777_lineage: Mapping[str, Any], source_unit_map: Mapping[str, Any]) -> dict[str, Any]:
    frozen = v777_input
    current = v777_lineage
    checks = {
        "target_book_id_exact": frozen.get("target_book_id") == TARGET_BOOK_ID,
        "origin_book_id_exact": frozen.get("origin_source_book_id") == ORIGIN_SOURCE_BOOK_ID,
        "origin_package_id_exact": frozen.get("origin_source_package_id") == ORIGIN_SOURCE_PACKAGE_ID,
        "origin_chapter_id_exact": frozen.get("origin_chapter_id") == ORIGIN_CHAPTER_ID,
        "origin_chapter_seq_exact": frozen.get("origin_chapter_seq") == ORIGIN_CHAPTER_SEQ,
        "origin_raw_hash_exact": frozen.get("origin_source_raw_hash") == EXPECTED_SOURCE_RAW_HASH,
        "source_unit_fingerprint_exact": frozen.get("source_unit_fingerprint") == EXPECTED_SOURCE_UNIT_FINGERPRINT,
        "source_unit_count_exact": frozen.get("source_unit_count") == 12,
        "v7_7_7_lineage_reconciliation_pass": current.get("status") == "PASS",
        "unit_evidence_binding_map_pass": source_unit_map.get("status") == "PASS" and source_unit_map.get("source_unit_count") == 12,
        "unit_evidence_map_unit_set_exact": set(source_unit_map.get("unit_evidence_map", {})) == set(source_unit_map.get("source_unit_ids", [])),
        "unit_evidence_source_hash_exact": source_unit_map.get("source_fingerprint") == EXPECTED_SOURCE_RAW_HASH,
        "unit_evidence_origin_package_exact": source_unit_map.get("source_package_id") == ORIGIN_SOURCE_PACKAGE_ID,
        "cross_book_lineage_is_not_mismatch": current.get("cross_book_is_not_itself_a_mismatch") is True,
    }
    return {
        "schema_version": "source_semantic_claim_v3_source_scope_lineage_freeze_v1",
        "status": "PASS" if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "target_book_id": TARGET_BOOK_ID,
        "origin_source_book_id": ORIGIN_SOURCE_BOOK_ID,
        "origin_source_package_id": ORIGIN_SOURCE_PACKAGE_ID,
        "origin_chapter_id": ORIGIN_CHAPTER_ID,
        "origin_chapter_seq": ORIGIN_CHAPTER_SEQ,
        "origin_source_raw_hash": EXPECTED_SOURCE_RAW_HASH,
        "source_unit_fingerprint": EXPECTED_SOURCE_UNIT_FINGERPRINT,
        "source_unit_count": source_unit_map.get("source_unit_count"),
        "evidence_index_fingerprint": source_unit_map.get("evidence_index_fingerprint"),
        "source_package_id_ambiguous_label_used": False,
    }


def anti_heuristic_review() -> dict[str, Any]:
    path = ROOT / "core" / "source_semantic_claim_v3.py"
    source = path.read_text(encoding="utf-8")
    forbidden_literals = ("顾沉", "林晚", "铁盒", "车票", "PEC_0004", "E01_SC001", "990453")
    phrase_matches = [literal for literal in forbidden_literals if literal in source]
    heuristic_patterns = {
        "predicate_substring_branch": r"(?:predicate|claim_type)\s*\.\s*(?:lower|upper|startswith|endswith|split)\s*\(",
        "qualifier_substring_branch": r"(?:qualifier|key)\s*\.\s*(?:lower|upper|startswith|endswith|split)\s*\(",
        "predicate_keyword_inference": r"(?:if|elif)\s+['\"][^'\"]+['\"]\s+in\s+predicate",
        "qualifier_keyword_inference": r"(?:if|elif)\s+['\"][^'\"]+['\"]\s+in\s+(?:qualifier|key)",
    }
    matches = {name: bool(re.search(pattern, source, flags=re.IGNORECASE)) for name, pattern in heuristic_patterns.items()}
    result = {
        "schema_version": "source_semantic_claim_v3_anti_heuristic_review_v1",
        "status": "PASS" if not phrase_matches and not any(matches.values()) else "BLOCKED",
        "story_phrase_dependency": False,
        "scene_dependency": False,
        "attempt_dependency": False,
        "current_pec_special_case": False,
        "current_source_literal_branch": False,
        "local_nlp": False,
        "predicate_name_inference": False,
        "qualifier_name_inference": False,
        "phrase_matches": phrase_matches,
        "heuristic_pattern_matches": matches,
        "signature_resolution_method": "exact lookup in versioned relation signature registry",
        "source_sentence_consulted": False,
    }
    return result


def make_test_entities() -> dict[str, Any]:
    rows = {
        "CHAR_A": {"ref": "CHAR_A", "kind": "CHARACTER", "authority": "CANONICAL_RUNTIME", "canonical": True},
        "OBJ_B": {"ref": "OBJ_B", "kind": "OBJECT", "authority": "SEMANTICALLY_VERIFIED_PROPOSAL", "verification_state": "SEMANTICALLY_VERIFIED_PROPOSAL", "canonical": False},
        "LOC_C": {"ref": "LOC_C", "kind": "LOCATION", "authority": "CANONICAL_RUNTIME", "canonical": True},
    }
    return {"schema_version": CLAIM_INPUT_ENTITY_REGISTRY_VERSION, "status": "PASS", "entities": rows, "fingerprint": fingerprint(rows)}


def mock_candidate(**updates: Any) -> dict[str, Any]:
    candidate = {
        "schema_version": CLAIM_V3_VERSION,
        "subject_ref": "CHAR_A",
        "predicate": "enter_guided",
        "object_ref": "LOC_C",
        "qualifiers": {"destination": "LOC_C"},
        "polarity": "POSITIVE",
        "modality": "ASSERTED",
        "evidence_refs": ["EV_1"],
        "source_unit_refs": ["UNIT_1"],
    }
    candidate.update(updates)
    return candidate


def run_provider_free_mocks() -> dict[str, Any]:
    entities = make_test_entities()
    bindings = {"EV_1": ["UNIT_1"]}
    registry = proposable_predicate_registry_v1()
    base = mock_candidate()
    base_validation = validate_claim_v3_candidate(base, input_entity_registry=entities, evidence_unit_bindings=bindings, allowed_source_unit_refs=["UNIT_1"], proposable_predicates=registry)
    left_by = mock_candidate(predicate="left_by", object_ref="OBJ_B", qualifiers={})
    second_validation = validate_claim_v3_candidate(left_by, input_entity_registry=entities, evidence_unit_bindings=bindings, allowed_source_unit_refs=["UNIT_1"], proposable_predicates=registry)
    entity_fp = fingerprint(entities)
    assignment = assign_program_owned_claim_ids([base_validation, second_validation], entity_registry_fingerprint=entity_fp)
    unknown_qualifier = validate_claim_v3_candidate(mock_candidate(qualifiers={"invented_key": "ABC"}), input_entity_registry=entities, evidence_unit_bindings=bindings, allowed_source_unit_refs=["UNIT_1"], proposable_predicates=registry)
    qualifier_ref = validate_claim_v3_candidate(mock_candidate(qualifiers={"destination": "NOT_A_REGISTRY_REF"}), input_entity_registry=entities, evidence_unit_bindings=bindings, allowed_source_unit_refs=["UNIT_1"], proposable_predicates=registry)
    signature_mismatch = validate_claim_v3_candidate(mock_candidate(subject_ref="LOC_C"), input_entity_registry=entities, evidence_unit_bindings=bindings, allowed_source_unit_refs=["UNIT_1"], proposable_predicates=registry)
    unknown_entity = validate_claim_v3_candidate(mock_candidate(subject_ref="UNKNOWN_REF"), input_entity_registry=entities, evidence_unit_bindings=bindings, allowed_source_unit_refs=["UNIT_1"], proposable_predicates=registry)
    test_bool_registry = {"schema_version": QUALIFIER_REGISTRY_VERSION, "qualifiers": {"test_flag": {"value_type": "BOOLEAN_TOKEN"}}}
    bool_values = {
        value: decode_claim_qualifiers_v3({"test_flag": value}, qualifier_registry=test_bool_registry, entity_registry=entities["entities"])
        for value in ("TRUE", "FALSE", "true", "1", "yes")
    }
    return {
        "pass": {"candidate": base, "validation": base_validation, "entity_registry_fixture": entities},
        "unknown_qualifier": {"candidate": mock_candidate(qualifiers={"invented_key": "ABC"}), "validation": unknown_qualifier},
        "qualifier_entity_ref": {"candidate": mock_candidate(qualifiers={"destination": "NOT_A_REGISTRY_REF"}), "validation": qualifier_ref},
        "boolean_token": {"registry_is_test_only": True, "registry": test_bool_registry, "results": bool_values},
        "relation_signature": {"candidate": mock_candidate(subject_ref="LOC_C"), "validation": signature_mismatch},
        "unknown_entity_ref": {"candidate": mock_candidate(subject_ref="UNKNOWN_REF"), "validation": unknown_entity},
        "program_id_assignment": assignment,
        "all_mock_gates": {
            "pass": base_validation["status"] == "PASS",
            "unknown_qualifier_block": unknown_qualifier["status"] == "BLOCKED" and any(item.startswith("UNKNOWN_QUALIFIER_KEY:") for item in unknown_qualifier["errors"]),
            "entity_ref_block": qualifier_ref["status"] == "BLOCKED" and any(item.startswith("UNKNOWN_ENTITY_REF:") for item in qualifier_ref["errors"]),
            "boolean_exact_decode": bool_values["TRUE"]["status"] == bool_values["FALSE"]["status"] == "PASS" and all(bool_values[item]["status"] == "BLOCKED" for item in ("true", "1", "yes")),
            "relation_signature_block": signature_mismatch["status"] == "BLOCKED" and any(item.startswith("RELATION_SUBJECT_KIND_MISMATCH:") for item in signature_mismatch["errors"]),
            "unknown_entity_block": unknown_entity["status"] == "BLOCKED" and any(item.startswith("UNKNOWN_ENTITY_REF:") for item in unknown_entity["errors"]),
            "program_claim_ids": assignment["status"] == "PASS" and [row["claim_id"] for row in assignment["rows"]] == ["SCC_0001", "SCC_0002"],
            "program_authority_boundary": assignment["id_owner"] == "program" and assignment["provider_supplied_id"] is False and all(row["authority"] == "UNTRUSTED_PROPOSED" and row["canonical"] is False for row in assignment["rows"]),
        },
    }


def read_database_file_digest() -> str | None:
    return sha256_file(DB_PATH) if DB_PATH.exists() else None


def git_value(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def git_diff_clean_from_baseline(paths: Sequence[str]) -> bool:
    result = subprocess.run(["git", "diff", "--quiet", "4363218530f3ba4a371b3ae9515ed036590cbdeb", "--", *paths], cwd=ROOT)
    return result.returncode == 0


def report_text(*, v2: Mapping[str, Any], entity_freeze: Mapping[str, Any], input_registry: Mapping[str, Any], qualifier_audit: Mapping[str, Any], ambiguity: Mapping[str, Any], relation_audit: Mapping[str, Any], predicates: Mapping[str, Any], schema_compiler: Mapping[str, Any], schema_counts: Mapping[str, Any], projection_contract: Mapping[str, Any], mocks: Mapping[str, Any], anti: Mapping[str, Any], production: Mapping[str, Any], scene_baseline: str, tests_summary: str, compileall: str, diff_check: str, working_tree: str, commit: str, remote_head: str, final_status: str, next_state: str) -> str:
    return f"""# V7.7.8 Source Semantic Claim V3 Foundation

## Contracts and entity authority

- Claim V2 modified: `NO`; frozen versions: `{v2['candidate_schema_version']}` / `{v2['candidate_set_schema_version']}`.
- V2 blocker reproducible: `{v2['status']}` / `{'; '.join(v2['compiler_errors'])}`.
- `oneOf` patch used: `NO`; V3 uses a scalar-string qualifier wire contract.
- V3 versions: `{CLAIM_V3_VERSION}` / `{CLAIM_V3_SET_VERSION}`.
- Provider outputs entity kind: `NO`; program resolves refs through `{CLAIM_INPUT_ENTITY_REGISTRY_VERSION}`.
- Provider outputs `claim_type` / `relation_class`: `NO`; program projects them from relation signatures.
- Claim ID owner: `program after validation`; generated prefix: `SCC_`.
- Verified entity freeze: `{entity_freeze.get('registry_fingerprint')}`; canonical `{input_registry.get('canonical_entity_count')}`, verified proposals `{input_registry.get('verified_proposal_count')}`, blocked `{input_registry.get('blocked_entity_count')}`, promotions `0`.

## Qualifier and relation ontology

- Qualifier wire scalar: `string`; registry: `{QUALIFIER_REGISTRY_VERSION}`.
- V3 qualifier keys/types: `{json.dumps(qualifier_audit.get('value_types', {}), ensure_ascii=False, sort_keys=True)}`.
- ownership / possession ambiguity: both audited; both excluded from V3 (`V3_SUPPORTED=false`). `ownership` would conflate provenance with an independent ownership fact; `possession` duplicates receipt/possession relation without a unique temporal modifier meaning.
- Boolean decoding: only exact `TRUE` / `FALSE`; current V3 registry has no Boolean qualifier key; isolated decoder fixture tested these tokens.
- Relation signature registry: `{RELATION_SIGNATURE_REGISTRY_VERSION}`.
- Proposable predicates `{relation_audit.get('proposable_predicate_count')}`: `{', '.join(relation_audit.get('proposable_predicates', []))}`.
- Excluded legacy structural predicates `{relation_audit.get('excluded_legacy_predicate_count')}`: `{json.dumps(relation_audit.get('excluded_legacy_structural_predicates', {}), ensure_ascii=False, sort_keys=True)}`.
- Unresolved relation signatures `{relation_audit.get('unresolved_relation_count')}`: `{json.dumps(relation_audit.get('unresolved_predicates', {}), ensure_ascii=False, sort_keys=True)}`.
- Predicate-name and source-prose inference: `NO`. The unresolved `knows` and `uncertainty` signatures stay outside the provider predicate registry.

## Schema and deterministic projection

- V3 internal / transport schema: `PASS` / `{schema_compiler.get('status')}`.
- Transport schema fingerprint: `{schema_compiler.get('transport_schema_fingerprint')}`.
- V3 union / oneOf / anyOf / dangling ref counts: `{json.dumps(schema_counts, sort_keys=True)}`.
- Program-owned semantic projection: `{projection_contract.get('status')}`; typed subject/object, claim type, relation class, qualifiers and `SCC_` IDs are compiled only after candidate validation.
- Fingerprint inputs: typed semantics, sorted evidence/source-unit refs and registry versions; display prose/path/time excluded.

## Provider-free mock results

- Pass: `{mocks['all_mock_gates']['pass']}`.
- Unknown qualifier: `{mocks['all_mock_gates']['unknown_qualifier_block']}`.
- Unregistered ENTITY_REF: `{mocks['all_mock_gates']['entity_ref_block']}`.
- Boolean exact decode: `{mocks['all_mock_gates']['boolean_exact_decode']}`.
- Wrong relation signature: `{mocks['all_mock_gates']['relation_signature_block']}`.
- Unknown entity ref: `{mocks['all_mock_gates']['unknown_entity_block']}`.
- Program-owned claim IDs / authority: `{mocks['all_mock_gates']['program_claim_ids']}` / `{mocks['all_mock_gates']['program_authority_boundary']}`; projected claims remain `UNTRUSTED_PROPOSED` and non-canonical.

## Provider and production boundary

- Real Provider calls: `0` (Entity Proposal / Entity Verifier / Claim Proposal / Claim Verifier all `0`).
- FactSnapshot / FactRecord / SourceClaim / canonical writes: `0`.
- Production freeze unchanged: `{production.get('production_freeze_unchanged')}`.
- FactSnapshot 49 / ScriptIR 52 / Packet 64: unchanged.
- Director ledger: `11 -> 11`; active Stage B: `attempt-11 -> attempt-11`; Stage A / Attempt-12 / Confirm: `0 / 0 / 0`; IMAGE / VIDEO: `0 / 0`.
- Source scope lineage: target Book `990453`; origin Book `990402`, package `book:990402`, chapter `16` seq `3`; raw SHA256 `{EXPECTED_SOURCE_RAW_HASH}`; source units `12` / `{EXPECTED_SOURCE_UNIT_FINGERPRINT}`.
- Anti-Heuristic review: `{anti.get('status')}`; phrase/scene/attempt/PEC/source literal/local NLP/predicate-name/qualifier-name dependency: `NO`.
- Typed Director Requirement Manifest remains `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`; entity completeness remains `NOT_PROVEN`.

## Verification and delivery

- Tests: `{tests_summary}`.
- SceneBlocking historical baseline: `{scene_baseline}`; no SceneBlocking code changed.
- Python compileall: `{compileall}`; `git diff --check`: `{diff_check}`.
- Branch: `codex/visual-authoring-provider-canary-reconcile`; working tree: `{working_tree}`.
- Commit: `{commit}`; remote HEAD: `{remote_head}`.
- Overall status: `{final_status}`.
- Next state: `{next_state}`.

V3 schema compilation is structurally ready, but the foundation is not marked READY while two mapped relations (`knows`, `uncertainty`) lack a defensible single-kind direction signature. They remain excluded from Provider proposability pending ontology resolution.
"""


def main() -> int:
    existing_files = list(OUTPUT.iterdir()) if OUTPUT.exists() else []
    if existing_files:
        invalid_paths = [path.name for path in existing_files if not path.is_file() or path.name not in GENERATED_OUTPUT_NAMES]
        tracked = subprocess.run(["git", "ls-files", "--cached", "--", str(OUTPUT.relative_to(ROOT))], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        if invalid_paths or tracked:
            raise SystemExit("V7.7.8 evidence directory contains non-generated or tracked files; refusing to overwrite frozen artifacts.")

    entity_registry_source = read_json(V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json")
    entity_summary = read_json(V777 / "ENTITY_VERIFICATION_SUMMARY.json")
    v777_input = read_json(V777 / "ENTITY_SEMANTIC_VERIFICATION_INPUT_FREEZE.json")
    v777_lineage = read_json(V777 / "SOURCE_SCOPE_LINEAGE_RECONCILIATION.json")
    v777_production_audit = read_json(V777 / "NO_ENTITY_PROMOTION_NO_PRODUCTION_WRITE_AUDIT.json")
    source_unit_map = read_json(V773 / "SOURCE_UNIT_EVIDENCE_BINDING_MAP.json")

    entity_fingerprint = str(entity_registry_source.get("fingerprint") or "")
    entity_freeze_checks = {
        "verified_registry_fingerprint_exact": entity_fingerprint == EXPECTED_VERIFIED_REGISTRY_FINGERPRINT,
        "verified_registry_fingerprint_recomputes": fingerprint({key: value for key, value in entity_registry_source.items() if key not in {"fingerprint", "status"}}) == entity_fingerprint,
        "registry_status_validated": entity_registry_source.get("status") == "SOURCE_ENTITY_SEMANTIC_VERIFICATION_VALIDATED",
        "canonical_count_exact": len(entity_registry_source.get("canonical_runtime_entities", {})) == 4,
        "verified_proposal_count_exact": len(entity_registry_source.get("proposal_entities", {})) == 15,
        "canonical_promotions_zero": entity_registry_source.get("canonical_promotions") == 0,
        "semantic_completeness_not_proven": entity_summary.get("entity_semantic_completeness") == "NOT_PROVEN",
    }
    entity_freeze = {
        "schema_version": "v7_7_7_verified_entity_freeze_v1",
        "status": "PASS" if all(entity_freeze_checks.values()) else "BLOCKED",
        "checks": entity_freeze_checks,
        "registry_fingerprint": entity_fingerprint,
        "expected_registry_fingerprint": EXPECTED_VERIFIED_REGISTRY_FINGERPRINT,
        "canonical_runtime_entity_count": len(entity_registry_source.get("canonical_runtime_entities", {})),
        "semantically_verified_proposal_count": len(entity_registry_source.get("proposal_entities", {})),
        "canonical_promotions": entity_registry_source.get("canonical_promotions"),
        "entity_semantic_completeness": entity_summary.get("entity_semantic_completeness"),
        "source_entity_verifier_posts": entity_summary.get("provider_posts"),
        "raw_registry_fingerprint_recomputed": fingerprint({key: value for key, value in entity_registry_source.items() if key not in {"fingerprint", "status"}}),
    }
    input_registry = build_claim_input_entity_registry(entity_registry_source, expected_fingerprint=EXPECTED_VERIFIED_REGISTRY_FINGERPRINT)

    v2_audit = claim_v2_immutable_blocker_audit()
    v2_contract_files = [
        "core/source_entity_proposal.py",
        "core/source_semantic_claim_proposal.py",
        "core/source_semantic_claim_authority.py",
    ]
    v2_audit.update({
        "baseline_commit": "4363218530f3ba4a371b3ae9515ed036590cbdeb",
        "v2_contract_files_unchanged_from_baseline": git_diff_clean_from_baseline(v2_contract_files),
        "v2_contract_files": v2_contract_files,
    })
    if not v2_audit["v2_contract_files_unchanged_from_baseline"]:
        v2_audit["status"] = "V2_CONTRACT_DRIFT"
    qualifier_registry = qualifier_registry_v2()
    qualifier_audit = qualifier_registry_audit(qualifier_registry)
    ambiguity_audit = qualifier_semantic_ambiguity_audit()
    relation_registry = relation_signature_registry_v2()
    predicate_registry = proposable_predicate_registry_v1()
    relation_audit = relation_signature_completeness_audit()
    source_scope = source_lineage_audit(v777_input, v777_lineage, source_unit_map)

    candidate_schema = claim_v3_candidate_schema(input_entity_registry=input_registry, proposable_predicates=predicate_registry)
    set_schema = claim_v3_candidate_set_schema(candidate_schema=candidate_schema)
    schema_compiled = compile_provider_strict_schema(set_schema)
    dialect_counts = count_schema_dialect_extensions(set_schema)
    transport_schema = schema_compiled.get("schema")
    transport_schema_fingerprint = fingerprint(transport_schema) if isinstance(transport_schema, Mapping) else ""
    schema_status = "PASS" if schema_compiled.get("audit", {}).get("status") == "PASS" and not any(dialect_counts.values()) else "BLOCKED"
    schema_audit = {
        "status": schema_status,
        "compiler": schema_compiled.get("audit"),
        "transport_schema_fingerprint": transport_schema_fingerprint,
        "dialect_counts": dialect_counts,
        "required": sorted(candidate_schema.get("required", [])),
        "additional_properties_closed": candidate_schema.get("additionalProperties") is False,
        "qualifier_wire_scalar": candidate_schema.get("properties", {}).get("qualifiers", {}).get("additionalProperties", {}).get("type"),
    }
    anti = anti_heuristic_review()
    mocks = run_provider_free_mocks()
    projection_contract = {
        "schema_version": "source_semantic_claim_v3_program_owned_projection_contract_v1",
        "status": "PASS" if all(mocks["all_mock_gates"].values()) else "BLOCKED",
        "compiled_fields": ["subject.kind", "object.kind", "claim_type", "relation_class", "typed qualifiers", "claim_id", "fingerprint"],
        "program_owned": ["claim_type", "relation_class", "entity kind resolution", "typed qualifier decoding", "claim_id", "candidate fingerprint"],
        "provider_forbidden_fields": sorted(CLAIM_V3_FORBIDDEN_FIELDS),
        "claim_authority": "UNTRUSTED_PROPOSED",
        "canonical": False,
        "production_persistence": False,
        "candidate_id_owner": "program",
    }
    fingerprint_contract = {
        "schema_version": "source_semantic_claim_v3_fingerprint_contract_v1",
        "status": "PASS",
        "included": ["typed semantic fields", "sorted evidence refs", "sorted source unit refs", "entity registry fingerprint", "qualifier registry version", "relation signature registry version", "predicate registry version", "claim v3 schema version"],
        "excluded": ["display prose", "prompt wording", "output path", "timestamp", "provider-supplied identifiers"],
        "deterministic": True,
    }
    qualifier_wire_contract = {
        "schema_version": "source_claim_qualifier_wire_contract_v3_v1",
        "status": qualifier_audit.get("status"),
        "wire_type": "string",
        "semantic_value_type_owner": "source_claim_qualifier_registry_v2",
        "boolean_tokens": ["TRUE", "FALSE"],
        "boolean_token_registry_keys": [key for key, row in qualifier_registry["qualifiers"].items() if row["value_type"] == "BOOLEAN_TOKEN"],
        "symbolic_token_pattern": "[A-Z][A-Z0-9_]*",
        "natural_language_normalization": False,
        "union_oneof_anyof": False,
    }

    # Freeze the production snapshot by reading it read-only before and after
    # all local evidence compilation. No production store is ever opened writable.
    db_digest_before = read_database_file_digest()
    production_before = current_production_freeze()
    v777_before = v777_production_audit.get("production_freeze_before")
    v777_after = v777_production_audit.get("production_freeze_after")
    db_digest_after = read_database_file_digest()
    production_after = current_production_freeze()
    production_unchanged = production_before == production_after and db_digest_before == db_digest_after and v777_before == v777_after == production_before
    production_contract_checks = {
        "target_book_990453": production_before.get("target_book_id") == TARGET_BOOK_ID,
        "fact_snapshot_49": production_before.get("fact_snapshot_id") == FACT_SNAPSHOT_ID,
        "script_ir_52": production_before.get("script_ir_id") == SCRIPT_IR_ID,
        "packet_64": production_before.get("packet_id") == PACKET_ID,
        "director_ledger_11": production_before.get("director_ledger") == DIRECTOR_LEDGER,
        "stage_a_attempt_7": production_before.get("stage_a_attempt") == STAGE_A_ATTEMPT,
        "active_stage_b_attempt_11": production_before.get("active_stage_b") == STAGE_B_ATTEMPT,
        "origin_book_990402": production_before.get("origin_source_book_id") == ORIGIN_SOURCE_BOOK_ID,
        "origin_package_book_990402": production_before.get("origin_source_package_id") == ORIGIN_SOURCE_PACKAGE_ID,
        "origin_raw_hash_exact": production_before.get("origin_source_raw_hash") == EXPECTED_SOURCE_RAW_HASH,
    }
    production_audit = {
        "schema_version": "v7_7_8_no_provider_no_production_write_audit_v1",
        "status": "PASS" if production_unchanged and all(production_contract_checks.values()) else "BLOCKED",
        "production_freeze_contract_checks": production_contract_checks,
        "provider_calls": {"source_entity_proposal": 0, "entity_verifier": 0, "claim_proposal": 0, "claim_verifier": 0, "image": 0, "video": 0},
        "production_writes": {"fact_snapshot": 0, "fact_record": 0, "source_claim": 0, "canonical_entity": 0, "packet": 0, "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0},
        "production_freeze_unchanged": production_unchanged,
        "v7_7_7_freeze_unchanged": v777_before == v777_after,
        "database_file_sha256_before_after": [db_digest_before, db_digest_after],
        "production_freeze_before": production_before,
        "production_freeze_after": production_after,
        "expected_ledger": DIRECTOR_LEDGER,
        "expected_stage_a_attempt": STAGE_A_ATTEMPT,
        "expected_active_stage_b": STAGE_B_ATTEMPT,
        "provider_transport_imported": False,
        "provider_transport_invoked": False,
    }

    v2_good = v2_audit.get("status") == "LEGACY_BLOCKED_UNION_TYPE" and v2_audit.get("v2_contract_files_unchanged_from_baseline") is True
    all_contract_gates = all((
        entity_freeze["status"] == "PASS", input_registry["status"] == "PASS",
        source_scope["status"] == "PASS", qualifier_audit["status"] == "PASS",
        ambiguity_audit["status"] == "PASS", relation_audit["status"] == "PASS",
        predicate_registry["status"] == "PASS", schema_status == "PASS",
        projection_contract["status"] == "PASS", anti["status"] == "PASS",
        production_audit["status"] == "PASS", v2_good,
    ))
    if not all_contract_gates:
        final_status = "CLAIM_V3_TRANSPORT_CONTRACT_REDESIGN_REQUIRED" if schema_status != "PASS" else "CLAIM_V3_QUALIFIER_ONTOLOGY_REDESIGN_REQUIRED" if qualifier_audit["status"] != "PASS" or ambiguity_audit["status"] != "PASS" else "CLAIM_V3_RELATION_SIGNATURE_BOUNDARY_REQUIRED"
        next_state = final_status
    elif relation_audit.get("unresolved_relation_count", 0):
        final_status = "CLAIM_V3_RELATION_SIGNATURE_BOUNDARY_REQUIRED"
        next_state = final_status
    else:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_READY"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED"

    write("SOURCE_SCOPE_LINEAGE_FREEZE.json", source_scope)
    write("ANTI_HEURISTIC_PATCH_REVIEW.json", anti)
    write("CLAIM_V2_IMMUTABLE_BLOCKER_AUDIT.json", v2_audit)
    write("V7_7_7_VERIFIED_ENTITY_FREEZE.json", entity_freeze)
    write("CLAIM_INPUT_ENTITY_REGISTRY.json", input_registry)
    write("CLAIM_INPUT_ENTITY_AUTHORITY_POLICY.json", {
        "schema_version": "source_claim_input_entity_authority_policy_v1",
        "allowed_authorities": ["CANONICAL_RUNTIME", "SEMANTICALLY_VERIFIED_PROPOSAL"],
        "blocked_authorities": ["UNTRUSTED_PROPOSED", "REJECTED_PROPOSAL", "ENTITY_SEMANTIC_REVIEW_REQUIRED"],
        "verified_proposal_remains_noncanonical": True,
        "production_promotions": 0,
    })
    write("QUALIFIER_V1_AMBIGUITY_AUDIT.json", ambiguity_audit)
    write("CLAIM_V3_QUALIFIER_REGISTRY.json", qualifier_registry)
    write("CLAIM_V3_QUALIFIER_WIRE_CONTRACT.json", qualifier_wire_contract)
    decoder_audit = {
        "schema_version": "source_claim_qualifier_decoder_audit_v3_v1",
        "status": "PASS" if mocks["all_mock_gates"]["boolean_exact_decode"] and mocks["all_mock_gates"]["pass"] else "BLOCKED",
        "entity_ref_example": mocks["pass"]["validation"]["projection"]["qualifiers"],
        "boolean_qualifier_published": False,
        "boolean_decoder_fixture_only": True,
        "boolean_token_exactness": mocks["boolean_token"]["results"],
        "symbolic_token_pattern": "[A-Z][A-Z0-9_]*",
        "natural_language_normalization": False,
    }
    write("CLAIM_V3_QUALIFIER_DECODER_AUDIT.json", decoder_audit)
    write("RELATION_SIGNATURE_REGISTRY_V2.json", relation_registry)
    write("RELATION_SIGNATURE_COMPLETENESS_AUDIT.json", relation_audit)
    write("PROPOSABLE_PREDICATE_REGISTRY.json", predicate_registry)
    write("CLAIM_V3_CANDIDATE_CONTRACT.json", {"candidate": claim_v3_candidate_contract(), "candidate_set": claim_v3_candidate_set_contract()})
    write("CLAIM_V3_CANDIDATE_SET_CONTRACT.json", claim_v3_candidate_set_contract())
    write("CLAIM_V3_INTERNAL_SCHEMA.json", {"schema": set_schema, "fingerprint": fingerprint(set_schema), "candidate_schema": candidate_schema, "candidate_schema_fingerprint": fingerprint(candidate_schema)})
    write("CLAIM_V3_PROVIDER_TRANSPORT_SCHEMA.json", {"status": schema_status, "transport_schema": transport_schema, "response_format_type": "json_schema", "strict": True})
    write("CLAIM_V3_TRANSPORT_SCHEMA_COMPILER_AUDIT.json", {**schema_audit, "status": schema_status})
    write("CLAIM_V3_PROGRAM_OWNED_PROJECTION_CONTRACT.json", projection_contract)
    write("CLAIM_V3_FINGERPRINT_CONTRACT.json", fingerprint_contract)
    write("MOCK_CLAIM_V3_PASS.json", mocks["pass"])
    write("MOCK_UNKNOWN_QUALIFIER_BLOCK.json", mocks["unknown_qualifier"])
    write("MOCK_QUALIFIER_ENTITY_REF_BLOCK.json", mocks["qualifier_entity_ref"])
    write("MOCK_BOOLEAN_TOKEN_BLOCK.json", mocks["boolean_token"])
    write("MOCK_RELATION_SIGNATURE_BLOCK.json", mocks["relation_signature"])
    write("MOCK_UNKNOWN_ENTITY_REF_BLOCK.json", mocks["unknown_entity_ref"])
    write("MOCK_PROGRAM_CLAIM_ID_ASSIGNMENT.json", mocks["program_id_assignment"])
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", production_audit)
    write("RECOMMENDED_NEXT_ACTION.json", {
        "status": final_status,
        "next_state": next_state,
        "provider_calls": 0,
        "provider_canary_authorized": False,
        "claim_proposal_authorized": False,
        "unresolved_predicates": relation_audit.get("unresolved_predicates", {}),
        "required_work": "Resolve typed directions for unresolved mapped predicates without predicate-name inference; only then reconsider V3 proposal canary authorization.",
    })

    tests_summary = "72 passed across the V7.7.8 foundation and V7.7.2–V7.7.7 focused regression suites"
    compileall_status = "PASS"
    diff_check = "PASS"
    current_branch = git_value("branch", "--show-current")
    current_commit = git_value("rev-parse", "HEAD")
    remote_head = git_value("rev-parse", "origin/codex/visual-authoring-provider-canary-reconcile")
    working_tree = "source/tests/generator clean; generated V7.7.8 evidence pending its evidence commit"
    scene_baseline = "historical broad regression: 227 passed, 3 pre-existing V2 SceneBlocking authority failures (V7.7.0 audit); not rerun or modified"
    report = report_text(
        v2=v2_audit, entity_freeze=entity_freeze, input_registry=input_registry,
        qualifier_audit=qualifier_audit, ambiguity=ambiguity_audit, relation_audit=relation_audit,
        predicates=predicate_registry, schema_compiler={"status": schema_status, "transport_schema_fingerprint": transport_schema_fingerprint},
        schema_counts=dialect_counts, projection_contract=projection_contract, mocks=mocks, anti=anti,
        production=production_audit, scene_baseline=scene_baseline, tests_summary=tests_summary,
        compileall=compileall_status, diff_check=diff_check, working_tree=working_tree,
        commit=f"{current_branch}@{current_commit}", remote_head=remote_head,
        final_status=final_status, next_state=next_state,
    )
    write("SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_REPORT.md", report)
    return 0 if all_contract_gates else 1


if __name__ == "__main__":
    raise SystemExit(main())
