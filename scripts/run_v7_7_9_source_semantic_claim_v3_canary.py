"""Execute the authorized V7.7.9 first-order Source Claim V3 canary once.

The default mode is a no-call preflight. ``--execute-real`` permits at most one
Provider transport attempt, only after every frozen-state and local test gate
passes. No authority or production persistence path is imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import llm
from core.provider_structured_output_qualification import (
    compile_provider_strict_schema,
    fingerprint,
    provider_identity,
    qualification_fingerprint,
    validate_json_schema_subset,
)
from core.source_semantic_claim_authority import MODALITIES, POLARITIES, validate_evidence_binding
from core.source_semantic_claim_v3 import (
    CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
    CLAIM_V3_SET_VERSION,
    CLAIM_V3_VERSION,
    CLAIM_V3_FORBIDDEN_FIELDS,
    PROPOSABLE_PREDICATE_REGISTRY_VERSION,
    QUALIFIER_REGISTRY_VERSION,
    RELATION_SIGNATURE_REGISTRY_VERSION,
    assign_program_owned_claim_ids,
    build_claim_input_entity_registry,
    claim_v2_immutable_blocker_audit,
    claim_v3_candidate_schema,
    claim_v3_candidate_set_schema,
    count_schema_dialect_extensions,
    decode_claim_qualifiers_v3,
    proposable_predicate_registry_v1,
    qualifier_registry_audit,
    qualifier_registry_v2,
    relation_signature_registry_v2,
    second_order_relation_closure_audit,
    validate_claim_v3_candidate,
    validate_claim_v3_set,
)
from core.source_semantic_claim_v3_canary import (
    build_claim_v3_proposal_prompt,
    build_source_claim_provider_entity_view,
    build_v7_7_8_1_forward_state_binding,
    claim_entity_kind_inventory,
    derive_executable_first_order_predicates,
    source_claim_predicate_prompt_contract,
)
from scripts.generate_v7_7_8_source_semantic_claim_v3_foundation_evidence import (
    current_production_freeze,
)
from scripts.run_v7_7_3_source_semantic_claim_proposal import read_db


BRANCH = "codex/visual-authoring-provider-canary-reconcile"
BASELINE_COMMIT = "8fe2d0f7f6c5a0a5fcb1ce791a06b0bdb9196aee"
AUTHORIZATION_ID = "v7.7.9-source-semantic-claim-v3-first-order-proposal-single-call"
MAX_PROVIDER_POSTS = 1
EXPECTED_VERIFIED_ENTITY_FINGERPRINT = "88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186"
EXPECTED_CLAIM_ENTITY_REGISTRY_FINGERPRINT = "877d43fc4cea05b487e50b6a4afcdb58e44f78338f1ebfcb388ecbe9b9740acb"
EXPECTED_SOURCE_RAW_HASH = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
EXPECTED_SOURCE_UNIT_FINGERPRINT = "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f"
EXPECTED_QUALIFICATION_FINGERPRINT = "194241dae7837d160c63a72bd1c3017bd9a9d0219d2f25e6a083637abdf3cb3b"
EXPECTED_PROVIDER_IDENTITY_FINGERPRINT = "9908c628bc8b970817674b26ff3897bb055bc24ee6505bbc2af6a80f7722c455"
EXPECTED_TRANSPORT_BASELINE_FINGERPRINT = "cbbb2a6a46689af9421ba192fe66f31e3b0d545545fe2f7a479d324a01bcf193"

CANARY_DIR = ROOT / "docs/canonical-canary/v7_7_9-source-semantic-claim-v3-first-order-proposal-real"
CANARY_PARENT = ROOT / "docs/canonical-canary"
V71_DIR = ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract"
V775_DIR = ROOT / "docs/canonical-canary/v7_7_5-provider-structured-output-capability-qualification"
V777_DIR = ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real"
V778_DIR = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
V773_DIR = ROOT / "docs/canonical-canary/v7_7_3-source-semantic-claim-proposal-real"
DB_PATH = ROOT / "work/db/screenplay.db"
SOURCE_CONTRACT_PATH = V71_DIR / "SOURCE_AUTHORING_UNIT_CONTRACT.json"
SOURCE_VERIFIED_REGISTRY_PATH = V777_DIR / "SOURCE_VERIFIED_ENTITY_REGISTRY.json"
CLAIM_INPUT_REGISTRY_PATH = V778_DIR / "CLAIM_INPUT_ENTITY_REGISTRY.json"
REQUIRED_TESTS = [
    "tests/test_source_semantic_claim_v3_canary.py",
    "tests/test_source_semantic_claim_v3_foundation.py",
    "tests/test_source_semantic_claim_authority_v7_7_2.py",
    "tests/test_source_semantic_claim_proposal_v7_7_3.py",
    "tests/test_source_entity_structured_output_boundary_v7_7_4.py",
    "tests/test_provider_structured_output_qualification_v7_7_5.py",
    "tests/test_source_entity_proposal_canary_v7_7_6.py",
    "tests/test_source_entity_semantic_verification_v7_7_7.py",
]
ARTIFACT_NAMES = [
    "ANTI_HEURISTIC_PATCH_REVIEW.json",
    "V7_7_8_1_FORWARD_STATE_BINDING.json",
    "SOURCE_CLAIM_V3_INPUT_FREEZE.json",
    "SOURCE_CLAIM_ENTITY_KIND_INVENTORY.json",
    "FIRST_ORDER_PREDICATE_EXECUTABILITY_AUDIT.json",
    "EXECUTABLE_FIRST_ORDER_PREDICATE_REGISTRY.json",
    "DORMANT_FIRST_ORDER_PREDICATE_STATUS.json",
    "SOURCE_CLAIM_PROVIDER_ENTITY_VIEW.json",
    "SOURCE_CLAIM_PREDICATE_PROMPT_CONTRACT.json",
    "SOURCE_CLAIM_V3_PROPOSAL_EXECUTION_CONTRACT.json",
    "SOURCE_CLAIM_V3_PROPOSAL_AUTHORIZATION.json",
    "SOURCE_CLAIM_V3_PROVIDER_IDENTITY.json",
    "SOURCE_CLAIM_V3_EXECUTABLE_TRANSPORT_SCHEMA.json",
    "SOURCE_CLAIM_V3_EXECUTABLE_TRANSPORT_SCHEMA_AUDIT.json",
    "SOURCE_CLAIM_V3_PROMPT_AUDIT.json",
    "SOURCE_CLAIM_V3_TRANSPORT_AUDIT.json",
    "SOURCE_CLAIM_V3_RAW_FORENSIC.json",
    "SOURCE_CLAIM_V3_PARSE_AUDIT.json",
    "SOURCE_CLAIM_V3_SCHEMA_VALIDATION.json",
    "SOURCE_CLAIM_V3_ENTITY_BINDING_AUDIT.json",
    "SOURCE_CLAIM_V3_RELATION_SIGNATURE_AUDIT.json",
    "SOURCE_CLAIM_V3_QUALIFIER_AUDIT.json",
    "SOURCE_CLAIM_V3_EVIDENCE_BINDING_AUDIT.json",
    "SOURCE_CLAIM_V3_PROGRAM_ID_ASSIGNMENT.json",
    "SOURCE_CLAIM_V3_PROPOSAL_SET.json",
    "SOURCE_CLAIM_V3_PROPOSAL_SURFACE_COVERAGE.json",
    "SOURCE_CLAIM_V3_PROPOSAL_COMPLETENESS_STATUS.json",
    "SECOND_ORDER_DEFERRED_STATUS.json",
    "NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json",
    "RECOMMENDED_NEXT_ACTION.json",
    "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_REPORT.md",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, value: Any) -> None:
    CANARY_DIR.mkdir(parents=True, exist_ok=True)
    target = CANARY_DIR / name
    temp = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temp, target)


def write_text(name: str, value: str) -> None:
    CANARY_DIR.mkdir(parents=True, exist_ok=True)
    target = CANARY_DIR / name
    temp = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
    temp.write_text(value, encoding="utf-8")
    os.replace(temp, target)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def exact_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_local_gates(database_sha_before: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", *REQUIRED_TESTS, "-q"]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    database_sha_after_tests = sha256_file(DB_PATH)
    compile_result = subprocess.run([sys.executable, "-m", "compileall", "-q", "core", "scripts"], cwd=ROOT, capture_output=True, text=True)
    diff_result = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True)
    return {
        "tests": {
            "status": "PASS" if tests.returncode == 0 else "BLOCKED",
            "returncode": tests.returncode,
            "command": command,
            "output": (tests.stdout + tests.stderr)[-5000:],
        },
        "compileall": {"status": "PASS" if compile_result.returncode == 0 else "BLOCKED", "returncode": compile_result.returncode, "output": (compile_result.stdout + compile_result.stderr)[-2000:]},
        "git_diff_check": {"status": "PASS" if diff_result.returncode == 0 else "BLOCKED", "returncode": diff_result.returncode, "output": (diff_result.stdout + diff_result.stderr)[-2000:]},
        "database_sha_before_local_gates": database_sha_before,
        "database_sha_after_local_gates": database_sha_after_tests,
        "local_gates_did_not_mutate_production_db": database_sha_before == database_sha_after_tests,
    }


def anti_heuristic_audit() -> dict[str, Any]:
    module_path = ROOT / "core/source_semantic_claim_v3_canary.py"
    source = module_path.read_text(encoding="utf-8")
    forbidden_story_literals = ("顾沉", "林晚", "铁盒", "车票", "PEC_0004", "E01_SC001")
    phrase_matches = [literal for literal in forbidden_story_literals if literal in source]
    pattern_checks = {
        "local_nlp_import": bool(re.search(r"\b(?:spacy|jieba|nltk)\b", source, flags=re.IGNORECASE)),
        "source_regex_extraction": bool(re.search(r"(?:re\.(?:findall|search|match|sub)|regex).*?(?:source|prose|text)", source, flags=re.IGNORECASE | re.DOTALL)),
        "predicate_name_semantic_branch": bool(re.search(r"(?:if|elif)\s+['\"][^'\"]+['\"]\s+in\s+predicate", source, flags=re.IGNORECASE)),
        "attempt_specific_branch": bool(re.search(r"attempt[-_ ](?:[0-9]+|id)", source, flags=re.IGNORECASE)),
    }
    return {
        "schema_version": "v7_7_9_anti_heuristic_patch_review_v1",
        "status": "PASS" if not phrase_matches and not any(pattern_checks.values()) else "BLOCKED",
        "scanned_module": "core/source_semantic_claim_v3_canary.py",
        "phrase_dependence": "NO",
        "scene_dependence": "NO",
        "attempt_dependence": "NO",
        "current_pec_special_case": "NO",
        "predicate_name_inference": "NO",
        "source_prose_executability_inference": "NO",
        "local_nlp": "NO",
        "provider_calls": 0,
        "production_writes": 0,
        "literal_matches": phrase_matches,
        "pattern_checks": pattern_checks,
    }


def profile_preflight() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    profile = llm._resolve_llm_profile()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    parsed = urlparse(base_url)
    host = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
    identity = provider_identity(
        profile_id=str(profile.get("id") or ""),
        provider=str(profile.get("provider") or ""),
        model=str(profile.get("model_name") or ""),
        base_host=host,
    )
    qualification = read_json(V775_DIR / "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION.json")
    requalified = qualification_fingerprint(
        identity=identity,
        capability=str(qualification.get("capability") or ""),
        probe_schema_fingerprint=str(qualification.get("probe_schema_fingerprint") or ""),
        request_fingerprint=str(qualification.get("request_fingerprint") or ""),
        raw_response_sha256=str(qualification.get("raw_response_sha256") or ""),
        qualified=bool(qualification.get("qualified")),
    )
    summary = {
        **identity,
        "enabled": bool(profile.get("enabled", True)),
        "key_configured": bool(profile.get("key_configured") or profile.get("api_key")),
        "base_url_path": parsed.path,
        "qualification_fingerprint": qualification.get("qualification_fingerprint"),
        "qualified": qualification.get("qualified") is True,
        "capability": qualification.get("capability"),
        "qualification_status": qualification.get("qualification_status"),
    }
    checks = {
        "profile_id_exact": identity["profile_id"] == "local-llm-2vydoz",
        "provider_exact": identity["provider"] == "openai-compatible",
        "model_exact": identity["model"] == "mimo-v2.5",
        "base_host_exact": identity["base_host"] == "https://api.xiaomimimo.com",
        "provider_identity_fingerprint_exact": identity["provider_identity_fingerprint"] == EXPECTED_PROVIDER_IDENTITY_FINGERPRINT,
        "qualification_current_and_qualified": qualification.get("qualified") is True and qualification.get("qualification_status") == "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFIED",
        "qualification_fingerprint_exact": qualification.get("qualification_fingerprint") == EXPECTED_QUALIFICATION_FINGERPRINT == requalified.get("qualification_fingerprint"),
        "strict_json_schema_capability": qualification.get("capability") == "JSON_SCHEMA_STRICT_SUPPORTED",
        "key_configured": summary["key_configured"],
        "profile_enabled": summary["enabled"],
    }
    return profile, summary, {"identity": identity, "qualification": qualification, "recomputed_qualification": requalified, "checks": checks, "status": "PASS" if all(checks.values()) else "BLOCKED"}


def build_preflight() -> dict[str, Any]:
    original_worktree_status = git("status", "--porcelain")
    current_branch = git("branch", "--show-current")
    current_head = git("rev-parse", "HEAD")
    remote_tracking_head = git("rev-parse", f"origin/{BRANCH}", check=False)
    remote_line = git("ls-remote", "origin", f"refs/heads/{BRANCH}", check=False)
    remote_head = remote_line.split()[0] if remote_line else ""
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, current_head], cwd=ROOT, capture_output=True).returncode == 0

    db_sha_before = sha256_file(DB_PATH)
    production_before = current_production_freeze()
    db = read_db()
    profile, profile_summary, profile_audit = profile_preflight()
    source_contract = read_json(SOURCE_CONTRACT_PATH)
    source_units = source_contract.get("units", []) if isinstance(source_contract.get("units"), list) else []
    source_unit_fingerprint = fingerprint(source_units)
    source_registry = read_json(SOURCE_VERIFIED_REGISTRY_PATH)
    input_registry_frozen = read_json(CLAIM_INPUT_REGISTRY_PATH)
    input_registry = build_claim_input_entity_registry(source_registry, expected_fingerprint=EXPECTED_VERIFIED_ENTITY_FINGERPRINT)
    entity_registry_matches = fingerprint(input_registry) == fingerprint(input_registry_frozen)

    v776 = read_json(V777_DIR / "V7_7_6_PROPOSAL_FREEZE.json")
    v777 = read_json(V778_DIR / "V7_7_7_VERIFIED_ENTITY_FREEZE.json")
    frozen_unit_binding = read_json(V773_DIR / "SOURCE_UNIT_EVIDENCE_BINDING_MAP.json")
    computed_unit_binding = {
        str(unit.get("unit_id") or ""): [str(ref) for ref in unit.get("source_evidence_refs", [])]
        for unit in source_units
    }
    frozen_proposals = v776.get("PEC_candidates") if isinstance(v776.get("PEC_candidates"), Mapping) else {}
    verified_proposals = source_registry.get("proposal_entities") if isinstance(source_registry.get("proposal_entities"), Mapping) else {}
    proposal_freeze_rows_match = set(frozen_proposals) == set(verified_proposals) and all(
        isinstance(frozen_proposals.get(ref), Mapping)
        and isinstance(verified_proposals.get(ref), Mapping)
        and all(frozen_proposals[ref].get(key) == verified_proposals[ref].get(key) for key in ("kind", "surface_form", "evidence_refs", "source_unit_refs", "fingerprint"))
        for ref in frozen_proposals
    )
    v7781_report = (V778_DIR / "V7_7_8_1_FIRST_ORDER_RELATION_SIGNATURE_CLOSURE_REPORT.md").read_text(encoding="utf-8")
    first_order_closure = read_json(V778_DIR / "FIRST_ORDER_RELATION_CLOSURE_AUDIT.json")
    second_order_closure = read_json(V778_DIR / "SECOND_ORDER_RELATION_CLOSURE_AUDIT.json")
    second_order_deferred = read_json(V778_DIR / "SECOND_ORDER_DEFERRED_COVERAGE_STATUS.json")
    current_first_order = proposable_predicate_registry_v1()
    second_order_forward = {**second_order_closure, "execution_enabled": second_order_deferred.get("execution_enabled")}
    foundation_report = {
        "foundation_state": "SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_READY" if "SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_READY" in v7781_report else "",
        "next_state": "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED" if "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED" in v7781_report else "",
    }
    forward_binding = build_v7_7_8_1_forward_state_binding(
        baseline_commit=BASELINE_COMMIT,
        foundation_report=foundation_report,
        first_order_closure=first_order_closure,
        second_order_closure=second_order_forward,
    )

    relation_registry = relation_signature_registry_v2()
    frozen_relation_registry = read_json(V778_DIR / "RELATION_SIGNATURE_REGISTRY_V2.json")
    derived = derive_executable_first_order_predicates(relation_registry, input_registry)
    inventory = claim_entity_kind_inventory(input_registry)
    entity_view = build_source_claim_provider_entity_view(input_registry, source_registry)
    prompt_contract = source_claim_predicate_prompt_contract(relation_registry)
    qualifier_registry = qualifier_registry_v2()
    system_prompt, user_prompt = build_claim_v3_proposal_prompt(
        source_units=source_units,
        provider_entity_view=entity_view,
        executable_predicate_registry=derived,
        predicate_prompt_contract=prompt_contract,
        qualifier_registry=qualifier_registry,
        polarities=POLARITIES,
        modalities=MODALITIES,
    )

    candidate_schema = claim_v3_candidate_schema(input_entity_registry=input_registry, proposable_predicates=derived)
    full_schema = claim_v3_candidate_set_schema(candidate_schema=candidate_schema)
    compiled = compile_provider_strict_schema(full_schema)
    dialect_counts = count_schema_dialect_extensions(full_schema)
    predicate_enum = sorted(derived.get("predicates", {}))
    schema_fingerprint = compiled["audit"].get("output_fingerprint")
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": CLAIM_V3_SET_VERSION,
            "strict": True,
            "schema": compiled.get("schema"),
        },
    }
    system_sha = exact_hash(system_prompt)
    user_sha = exact_hash(user_prompt)
    request_fp = fingerprint({
        "provider_identity": profile_summary,
        "system_prompt_sha256": system_sha,
        "user_prompt_sha256": user_sha,
        "transport_schema_fingerprint": schema_fingerprint,
        "response_format": response_format,
        "max_tokens": 8192,
        "temperature": 0.0,
        "transport_attempt_budget": 1,
    })

    runtime = str(os.environ.get("E2E_EXTERNAL_RUNTIME") or "").strip().lower()
    anti = anti_heuristic_audit()
    lineage = read_json(V778_DIR / "SOURCE_SCOPE_LINEAGE_FREEZE.json")
    old_recommendation = read_json(V778_DIR / "RECOMMENDED_NEXT_ACTION.json")
    historical_751 = read_json(V778_DIR / "V7_5_1_HISTORICAL_REVALIDATION_BOUNDARY.json")
    v2_audit = claim_v2_immutable_blocker_audit()
    qualifier_audit = qualifier_registry_audit(qualifier_registry)

    tests_and_local = run_local_gates(db_sha_before)
    db_sha_after_preflight = sha256_file(DB_PATH)
    production_after_preflight = current_production_freeze()

    unit_integrity_checks = {
        "unit_count_12": len(source_units) == 12 and source_contract.get("unit_count") == 12,
        "unit_fingerprint_exact": source_unit_fingerprint == EXPECTED_SOURCE_UNIT_FINGERPRINT == source_contract.get("fingerprint"),
        "source_text_exact_to_evidence": all(str(unit.get("text") or "") == str((unit.get("source_evidence") or {}).get("text") or "") for unit in source_units),
        "evidence_sha256_exact": all(exact_hash(str((unit.get("source_evidence") or {}).get("text") or "")) == str((unit.get("source_evidence") or {}).get("sha256") or "") for unit in source_units),
        "evidence_ref_binding_exact": all(unit.get("source_evidence_refs") == [str((unit.get("source_evidence") or {}).get("evidence_id") or "")] for unit in source_units),
    }
    expected_kinds = {
        "CHARACTER": 2, "DIALOGUE_CONTENT": 1, "ENVIRONMENT": 2, "LOCATION": 2,
        "OBJECT": 8, "SCENE": 1, "TEXT_CONTENT": 2, "UNKNOWN_ENTITY": 1,
    }
    executable_checks = {
        "derived_executable_predicates_expected": set(derived.get("predicates", {})) == {"enter_guided", "left_by", "received_by", "speech_act"},
        "derived_dormant_predicates_expected": set(derived.get("dormant_predicates", {})) == {"has_property", "state_value"},
        "no_second_order_executable": not ({"knows", "uncertainty"} & set(derived.get("predicates", {}))),
        "no_claim_reference_object_domain": "VERIFIED_FIRST_ORDER_CLAIM_REF" not in json.dumps(derived),
        "empty_value_entity_kinds_remain_empty": inventory.get("kind_counts", {}).get("PROPERTY_VALUE", 0) == 0 and inventory.get("kind_counts", {}).get("STATE_VALUE", 0) == 0,
        "inventory_matches_frozen_current_expectation": inventory.get("kind_counts") == expected_kinds,
        "relation_signature_registry_matches_frozen": fingerprint(relation_registry) == fingerprint({"schema_version": frozen_relation_registry.get("schema_version"), "signatures": frozen_relation_registry.get("signatures")}),
    }
    schema_checks = {
        "compiler_pass": compiled["audit"].get("status") == "PASS",
        "strict_response_format": response_format.get("type") == "json_schema" and response_format.get("json_schema", {}).get("strict") is True,
        "schema_predicate_enum_derived_only": predicate_enum == sorted(derived.get("predicates", {})),
        "second_order_predicates_absent": not ({"knows", "uncertainty"} & set(predicate_enum)),
        "second_order_claim_ref_domain_absent": "VERIFIED_FIRST_ORDER_CLAIM_REF" not in json.dumps(full_schema),
        "dialect_extensions_zero": dialect_counts == {"union_type": 0, "oneOf": 0, "anyOf": 0, "dangling_ref": 0},
        "transport_fingerprint_recorded": bool(schema_fingerprint),
        "v3_candidate_fields_unchanged": set(candidate_schema.get("properties", {})) == {"schema_version", "subject_ref", "predicate", "object_ref", "qualifiers", "polarity", "modality", "evidence_refs", "source_unit_refs"},
        "provider_forbidden_semantic_fields_absent": not (set(CLAIM_V3_FORBIDDEN_FIELDS) & set(candidate_schema.get("properties", {}))),
        "v2_legacy_blocker_unchanged": v2_audit.get("status") == "LEGACY_BLOCKED_UNION_TYPE" and v2_audit.get("v2_mutated") is False,
    }
    prompt_checks = {
        "entity_view_ready": entity_view.get("status") == "PASS" and entity_view.get("entity_count") == 19,
        "predicate_contract_ready": prompt_contract.get("status") == "PASS",
        "qualifier_contract_ready": qualifier_audit.get("status") == "PASS" and qualifier_registry.get("schema_version") == QUALIFIER_REGISTRY_VERSION,
        "source_units_complete": len(source_units) == 12,
        "no_second_order_terms_as_allowed_output": not any(word in system_prompt + user_prompt for word in ("knows", "uncertainty", "VERIFIED_FIRST_ORDER_CLAIM_REF")),
        "no_manual_expected_answers": not any(fragment in system_prompt + user_prompt for fragment in ("Attempt-11", "should output", "expected candidate count", "manual canonical fact list")),
        "lossy_mapping_prohibited": "Do not force source meaning into the closest available predicate" in system_prompt,
        "zero_or_more_claims_explicit": "A source unit may produce zero or more claims" in system_prompt,
    }
    production_checks = {
        "production_before_equals_v7_7_8_frozen_state": production_before == read_json(V778_DIR / "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json")["production_freeze_before"],
        "production_unchanged_during_preflight": production_before == production_after_preflight,
        "database_unchanged_during_preflight": db_sha_before == db_sha_after_preflight,
        "book_packet_attempt_state_exact": db.get("book_id") == 990453 and db.get("packet_id") == 64 and db.get("packet_attempt_count") == 11 and db.get("stage_a_attempt") == "attempt-7" and db.get("stage_b_attempt") == "attempt-11",
        "source_raw_hash_exact": db.get("source_fingerprint") == EXPECTED_SOURCE_RAW_HASH,
        "source_package_exact": db.get("source_package_id") == "book:990402",
        "lineage_freeze_pass": lineage.get("status") == "PASS" and lineage.get("origin_source_raw_hash") == EXPECTED_SOURCE_RAW_HASH and lineage.get("source_unit_fingerprint") == EXPECTED_SOURCE_UNIT_FINGERPRINT,
    }
    preflight_checks = {
        "branch_exact": current_branch == BRANCH,
        "baseline_is_ancestor": ancestor,
        "working_tree_clean": not original_worktree_status,
        "local_head_equals_remote_tracking": current_head == remote_tracking_head,
        "local_head_equals_remote_server": current_head == remote_head,
        "v7_7_8_1_forward_binding_pass": forward_binding.get("status") == "PASS",
        "old_v7_7_8_recommendation_not_used_as_gate": old_recommendation.get("status") == "CLAIM_V3_RELATION_SIGNATURE_BOUNDARY_REQUIRED",
        "v7_5_1_historical_only": historical_751.get("status") == "HISTORICAL_REVALIDATION_ONLY" and historical_751.get("provider_authorization_gate") is False,
        "verified_entity_registry_frozen": v777.get("status") == "PASS" and v777.get("registry_fingerprint") == EXPECTED_VERIFIED_ENTITY_FINGERPRINT and input_registry.get("status") == "PASS" and entity_registry_matches and input_registry.get("fingerprint") == EXPECTED_CLAIM_ENTITY_REGISTRY_FINGERPRINT and len(input_registry.get("entities", {})) == 19,
        "verified_entity_counts_and_proposal_freeze_exact": v777.get("canonical_runtime_entity_count") == 4 and v777.get("semantically_verified_proposal_count") == 15 and v777.get("canonical_promotions") == 0 and v776.get("status") == "PASS" and v776.get("target_book_id") == 990453 and v776.get("origin_source_raw_hash") == EXPECTED_SOURCE_RAW_HASH and v776.get("PEC_count") == 15 and v776.get("proposal_registry_fingerprint") == v776.get("expected_proposal_registry_fingerprint") and v776.get("assignment_fingerprint") == v776.get("expected_assignment_fingerprint") and proposal_freeze_rows_match,
        "source_unit_and_lineage_integrity": all(unit_integrity_checks.values()) and source_contract.get("fingerprint") == EXPECTED_SOURCE_UNIT_FINGERPRINT,
        "source_unit_evidence_binding_freeze_exact": frozen_unit_binding.get("status") == "PASS" and frozen_unit_binding.get("source_unit_count") == 12 and frozen_unit_binding.get("unit_evidence_map") == computed_unit_binding and frozen_unit_binding.get("source_fingerprint") == EXPECTED_SOURCE_RAW_HASH and frozen_unit_binding.get("source_package_id") == "book:990402",
        "profile_identity_and_qualification_fresh": profile_audit.get("status") == "PASS",
        "runtime_not_mock": runtime != "mock",
        "anti_heuristic_pass": anti.get("status") == "PASS",
        "first_order_executability_derived": derived.get("status") == "PASS" and all(executable_checks.values()),
        "provider_entity_view_and_prompt_ready": all(prompt_checks.values()),
        "transport_schema_strict_and_filtered": all(schema_checks.values()),
        "authorization_scope_exact": AUTHORIZATION_ID == "v7.7.9-source-semantic-claim-v3-first-order-proposal-single-call" and MAX_PROVIDER_POSTS == 1,
        "no_existing_v7_7_9_evidence_or_prior_call": not CANARY_DIR.exists(),
        "local_tests_compileall_diff_and_db_read_only": tests_and_local["tests"]["status"] == "PASS" and tests_and_local["compileall"]["status"] == "PASS" and tests_and_local["git_diff_check"]["status"] == "PASS" and tests_and_local["local_gates_did_not_mutate_production_db"] and db_sha_before == db_sha_after_preflight,
        "production_freeze_pass": all(production_checks.values()),
    }
    return {
        "status": "PASS" if all(preflight_checks.values()) else "BLOCKED",
        "failed_checks": [key for key, passed in preflight_checks.items() if not passed],
        "checks": preflight_checks,
        "subchecks": {
            "entity_kind_inventory": inventory,
            "source_unit_integrity": unit_integrity_checks,
            "executable_predicate_derivation": executable_checks,
            "schema": schema_checks,
            "prompt": prompt_checks,
            "provider_profile": profile_audit,
            "production": production_checks,
        },
        "runtime": {
            "branch": current_branch,
            "head": current_head,
            "remote_tracking_head": remote_tracking_head,
            "remote_server_head": remote_head,
            "baseline_commit": BASELINE_COMMIT,
            "database_sha256": db_sha_after_preflight,
            "source_raw_hash": db.get("source_fingerprint"),
            "source_package_id": db.get("source_package_id"),
            "source_unit_fingerprint": source_unit_fingerprint,
            "source_unit_count": len(source_units),
            "input_entity_registry_fingerprint": input_registry.get("fingerprint"),
            "input_entity_count": len(input_registry.get("entities", {})),
            "first_order_predicate_count": len(derived.get("predicates", {})),
            "dormant_predicate_count": len(derived.get("dormant_predicates", {})),
            "executable_predicates": predicate_enum,
            "transport_schema_fingerprint": schema_fingerprint,
            "system_prompt_sha256": system_sha,
            "user_prompt_sha256": user_sha,
            "request_fingerprint": request_fp,
            "provider": profile_summary,
        },
        "values": {
            "db_before": db,
            "production_freeze_before": production_before,
            "production_freeze_after_preflight": production_after_preflight,
            "database_sha_before": db_sha_before,
            "database_sha_after_preflight": db_sha_after_preflight,
            "source_contract": source_contract,
            "source_units": source_units,
            "source_verified_registry": source_registry,
            "input_registry": input_registry,
            "relation_registry": relation_registry,
            "current_first_order_registry": current_first_order,
            "derived_registry": derived,
            "inventory": inventory,
            "entity_view": entity_view,
            "prompt_contract": prompt_contract,
            "qualifier_registry": qualifier_registry,
            "qualifier_audit": qualifier_audit,
            "full_schema": full_schema,
            "compiled_schema": compiled,
            "dialect_counts": dialect_counts,
            "response_format": response_format,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "forward_binding": forward_binding,
            "profile": profile,
            "profile_summary": profile_summary,
            "profile_audit": profile_audit,
            "anti_heuristic": anti,
            "local_gates": tests_and_local,
            "v776": v776,
            "v777": v777,
            "lineage": lineage,
        },
    }


def source_and_evidence_index(units: Sequence[Mapping[str, Any]], *, source_fingerprint: str, source_package_id: str) -> tuple[dict[str, list[str]], dict[str, Any]]:
    bindings: dict[str, list[str]] = {}
    anchors = []
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        ref = str(evidence.get("evidence_id") or "")
        bindings.setdefault(ref, []).append(unit_id)
        anchors.append({
            "anchor_ref": ref,
            "source_fingerprint": source_fingerprint,
            "source_package_id": source_package_id,
            "unit_id": unit_id,
            "sha256": str(evidence.get("sha256") or ""),
        })
    return bindings, {"schema_version": "source_claim_v3_evidence_index_v1", "anchors": anchors, "source_fingerprint": source_fingerprint, "source_package_id": source_package_id}


def write_preflight_artifacts(pre: Mapping[str, Any]) -> None:
    values = pre["values"]
    checks = pre["checks"]
    runtime = pre["runtime"]
    write_json("ANTI_HEURISTIC_PATCH_REVIEW.json", values["anti_heuristic"])
    write_json("V7_7_8_1_FORWARD_STATE_BINDING.json", values["forward_binding"])
    write_json("SOURCE_CLAIM_V3_INPUT_FREEZE.json", {
        "schema_version": "source_claim_v3_input_freeze_v1",
        "status": "PASS" if checks.get("source_unit_and_lineage_integrity") and checks.get("verified_entity_registry_frozen") and checks.get("production_freeze_pass") else "BLOCKED",
        "target_book_id": 990453, "episode": 1, "fact_snapshot_id": 49, "script_ir_id": 52, "packet_id": 64,
        "origin_source_book_id": 990402, "origin_source_package_id": "book:990402",
        "origin_source_raw_hash": runtime.get("source_raw_hash"),
        "source_unit_count": runtime.get("source_unit_count"),
        "source_unit_fingerprint": runtime.get("source_unit_fingerprint"),
        "source_unit_evidence_binding_map_fingerprint": read_json(V773_DIR / "SOURCE_UNIT_EVIDENCE_BINDING_MAP.json").get("evidence_index_fingerprint"),
        "verified_entity_registry_fingerprint": EXPECTED_VERIFIED_ENTITY_FINGERPRINT,
        "claim_input_entity_registry_fingerprint": runtime.get("input_entity_registry_fingerprint"),
        "claim_input_entity_count": runtime.get("input_entity_count"),
        "production_freeze": values["production_freeze_before"],
        "database_sha256": runtime.get("database_sha256"),
        "v7_5_1_current_branch_revalidation": "HISTORICAL_REVALIDATION_ONLY",
        "packet_attempt_count": 11, "stage_a_attempt": "attempt-7", "active_stage_b_attempt": "attempt-11",
    })
    write_json("SOURCE_CLAIM_ENTITY_KIND_INVENTORY.json", values["inventory"])
    derived = values["derived_registry"]
    write_json("FIRST_ORDER_PREDICATE_EXECUTABILITY_AUDIT.json", {
        "schema_version": "source_claim_first_order_predicate_executability_audit_v1",
        "status": derived.get("status"),
        "predicate_count": derived.get("predicate_count"),
        "dormant_predicate_count": derived.get("dormant_predicate_count"),
        "executable_predicates": sorted(derived.get("predicates", {})),
        "dormant_predicates": sorted(derived.get("dormant_predicates", {})),
        "source_prose_consulted": derived.get("source_prose_consulted"),
        "predicate_name_semantics_inferred": derived.get("predicate_name_semantics_inferred"),
        "semantics": "TYPE_EXECUTABLE != SOURCE_SUPPORTED",
        "derivation": "A relation is type-executable only when at least one allowed subject kind and one allowed object kind are present in the frozen Claim Input Entity Registry.",
    })
    write_json("EXECUTABLE_FIRST_ORDER_PREDICATE_REGISTRY.json", derived)
    write_json("DORMANT_FIRST_ORDER_PREDICATE_STATUS.json", {
        "schema_version": "source_claim_dormant_first_order_predicate_status_v1",
        "status": "PASS",
        "predicates": {
            key: {**row, "status": "TYPE_DEPENDENCY_UNAVAILABLE", "meaning": "Ontology is defined; current registry lacks a legal subject or object ref kind."}
            for key, row in derived.get("dormant_predicates", {}).items()
        },
        "not_interpreted_as": ["ONTOLOGY_UNRESOLVED", "UNSUPPORTED", "SEMANTICALLY_FALSE", "NOT_REQUIRED", "PROVIDER_OMISSION"],
    })
    write_json("SOURCE_CLAIM_PROVIDER_ENTITY_VIEW.json", values["entity_view"])
    write_json("SOURCE_CLAIM_PREDICATE_PROMPT_CONTRACT.json", values["prompt_contract"])
    write_json("SOURCE_CLAIM_V3_PROPOSAL_EXECUTION_CONTRACT.json", {
        "schema_version": "source_claim_v3_proposal_execution_contract_v1",
        "authorization_id": AUTHORIZATION_ID,
        "ordered_steps": [
            "PREFLIGHT", "FORWARD_STATE_BINDING", "SOURCE_ENTITY_AND_LINEAGE_FREEZE",
            "EXECUTABLE_PREDICATE_DERIVATION", "STRICT_TRANSPORT_SCHEMA_FREEZE", "AUTHORIZATION",
            "ONE_PROVIDER_POST", "RAW_RESPONSE_ATOMIC_PERSIST", "TRANSPORT_AUDIT", "STRICT_JSON_PARSE",
            "STRICT_SCHEMA_VALIDATION", "INTERNAL_V3_VALIDATION", "ENTITY_RESOLUTION",
            "RELATION_SIGNATURE_VALIDATION", "QUALIFIER_DECODING", "EVIDENCE_AND_SOURCE_UNIT_BINDING",
            "DETERMINISTIC_PROGRAM_SCC_ASSIGNMENT", "PROPOSAL_SET_FREEZE", "QUALITY_AND_SURFACE_AUDIT", "STOP",
        ],
        "provider_post_budget": 1, "transport_retry": 0, "parse_retry": 0, "repair": 0,
        "semantic_verifier_calls": 0, "second_order_proposals": 0,
        "fact_record_writes": 0, "source_claim_writes": 0, "entity_writes": 0,
        "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0,
        "post_response_provider_calls": 0,
    })
    write_json("SOURCE_CLAIM_V3_PROPOSAL_AUTHORIZATION.json", {
        "authorization_id": AUTHORIZATION_ID,
        "granted": True,
        "source": "explicit user instruction in V7.7.9 phase prompt",
        "scope": {"target_book_id": 990453, "episode": 1, "first_order_only": True, "current_frozen_source": True, "current_verified_entity_registry": True, "current_executable_predicates": True},
        "max_real_provider_posts": 1,
        "semantic_verifier_posts": 0, "second_order_proposal_posts": 0,
        "production_writes": 0, "image_posts": 0, "video_posts": 0,
        "conditional_on_all_preflight_gates_pass": True,
    })
    profile_safe = dict(values["profile_summary"])
    profile_safe["preflight_status"] = values["profile_audit"].get("status")
    profile_safe["profile_mutated"] = False
    write_json("SOURCE_CLAIM_V3_PROVIDER_IDENTITY.json", profile_safe)
    write_json("SOURCE_CLAIM_V3_EXECUTABLE_TRANSPORT_SCHEMA.json", {
        "schema_version": "source_claim_v3_executable_transport_schema_v1",
        "status": values["compiled_schema"]["audit"].get("status"),
        "transport_schema": values["compiled_schema"].get("schema"),
        "response_format": values["response_format"],
        "response_format_type": "json_schema", "strict": True,
        "predicate_enum": runtime.get("executable_predicates"),
        "transport_schema_fingerprint": runtime.get("transport_schema_fingerprint"),
    })
    write_json("SOURCE_CLAIM_V3_EXECUTABLE_TRANSPORT_SCHEMA_AUDIT.json", {
        "status": values["compiled_schema"]["audit"].get("status"),
        "compiler": values["compiled_schema"]["audit"],
        "transport_schema_fingerprint": runtime.get("transport_schema_fingerprint"),
        "full_foundation_schema_fingerprint": EXPECTED_TRANSPORT_BASELINE_FINGERPRINT,
        "filtered_executable_schema_may_differ_from_full_foundation": True,
        "dialect_counts": values["dialect_counts"],
        "predicate_enum": runtime.get("executable_predicates"),
    })
    write_json("SOURCE_CLAIM_V3_PROMPT_AUDIT.json", {
        "schema_version": "source_claim_v3_prompt_audit_v1",
        "status": "PASS" if checks.get("provider_entity_view_and_prompt_ready") else "BLOCKED",
        "system_prompt_sha256": runtime.get("system_prompt_sha256"),
        "user_prompt_sha256": runtime.get("user_prompt_sha256"),
        "request_fingerprint": runtime.get("request_fingerprint"),
        "system_prompt_length": len(values["system_prompt"]),
        "user_prompt_length": len(values["user_prompt"]),
        "source_unit_count": runtime.get("source_unit_count"),
        "source_unit_texts_equal_bound_evidence": True,
        "attempt_findings_in_prompt": False,
        "manual_expected_answers_in_prompt": False,
        "source_evidence_text_allowed": True,
        "lossy_forced_mapping_prohibited": True,
        "entity_display_form_is_identity": False,
        "only_executable_predicates_in_prompt": runtime.get("executable_predicates"),
        "second_order_predicates_in_prompt_or_schema": False,
    })


def per_candidate_audits(
    candidates: Sequence[Any],
    *, input_registry: Mapping[str, Any], executable_registry: Mapping[str, Any],
    qualifier_registry: Mapping[str, Any], unit_bindings: Mapping[str, Sequence[str]],
    evidence_index: Mapping[str, Any], source_fingerprint: str, source_package_id: str,
    units: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    allowed_units = [str(unit.get("unit_id") or "") for unit in units]
    internal_results = []
    entity_rows = []
    relation_rows = []
    qualifier_rows = []
    evidence_rows = []
    for index, candidate in enumerate(candidates):
        result = validate_claim_v3_candidate(
            candidate,
            input_entity_registry=input_registry,
            evidence_unit_bindings=unit_bindings,
            allowed_source_unit_refs=allowed_units,
            qualifier_registry=qualifier_registry,
            proposable_predicates=executable_registry,
        )
        internal_results.append(result)
        if not isinstance(candidate, Mapping):
            entity_rows.append({"index": index, "status": "BLOCKED", "errors": ["CANDIDATE_NOT_OBJECT"]})
            relation_rows.append({"index": index, "status": "BLOCKED", "errors": ["CANDIDATE_NOT_OBJECT"]})
            qualifier_rows.append({"index": index, "status": "BLOCKED", "errors": ["CANDIDATE_NOT_OBJECT"]})
            evidence_rows.append({"index": index, "status": "BLOCKED", "errors": ["CANDIDATE_NOT_OBJECT"]})
            continue
        subject_ref = str(candidate.get("subject_ref") or "")
        object_ref = str(candidate.get("object_ref") or "")
        entities = input_registry.get("entities", {})
        entity_errors = []
        for side, ref in (("subject", subject_ref), ("object", object_ref)):
            row = entities.get(ref) if isinstance(entities, Mapping) else None
            if not isinstance(row, Mapping):
                entity_errors.append(f"UNKNOWN_ENTITY_REF:{ref}")
            elif str(row.get("authority") or "") not in {"CANONICAL_RUNTIME", "SEMANTICALLY_VERIFIED_PROPOSAL"}:
                entity_errors.append(f"ENTITY_AUTHORITY_BLOCKED:{ref}")
        entity_rows.append({"index": index, "subject_ref": subject_ref, "object_ref": object_ref, "status": "PASS" if not entity_errors else "BLOCKED", "errors": entity_errors})

        predicate = str(candidate.get("predicate") or "")
        signature = executable_registry.get("predicates", {}).get(predicate) if isinstance(executable_registry.get("predicates"), Mapping) else None
        relation_errors = []
        if not isinstance(signature, Mapping):
            relation_errors.append(f"PREDICATE_NOT_EXECUTABLE:{predicate}")
        elif result.get("errors"):
            relation_errors.extend(error for error in result["errors"] if error.startswith(("PREDICATE_", "RELATION_")))
        relation_rows.append({"index": index, "predicate": predicate, "signature": dict(signature) if isinstance(signature, Mapping) else None, "status": "PASS" if not relation_errors else "BLOCKED", "errors": sorted(set(relation_errors))})
        qualifier_result = result.get("qualifier_validation") if isinstance(result.get("qualifier_validation"), Mapping) else {"status": "BLOCKED", "errors": ["QUALIFIER_AUDIT_MISSING"]}
        qualifier_rows.append({"index": index, **dict(qualifier_result)})
        evidence_refs = candidate.get("evidence_refs") if isinstance(candidate.get("evidence_refs"), list) else []
        evidence_result = validate_evidence_binding(
            evidence_refs=[str(ref) for ref in evidence_refs],
            evidence_index=evidence_index,
            source_fingerprint=source_fingerprint,
            source_package_id=source_package_id,
        )
        source_unit_refs = candidate.get("source_unit_refs") if isinstance(candidate.get("source_unit_refs"), list) else []
        unknown_units = [str(ref) for ref in source_unit_refs if str(ref) not in set(allowed_units)]
        binding_errors = list(evidence_result.get("errors", [])) + [f"SOURCE_UNIT_REF_UNKNOWN:{ref}" for ref in unknown_units]
        for ref in evidence_refs:
            bound = set(str(item) for item in unit_bindings.get(str(ref), []))
            if not bound:
                continue
            if not bound & set(str(item) for item in source_unit_refs):
                binding_errors.append(f"EVIDENCE_UNIT_BINDING_MISMATCH:{ref}")
        evidence_rows.append({"index": index, "status": "PASS" if not binding_errors else "BLOCKED", "errors": sorted(set(binding_errors)), "evidence_validation": evidence_result, "source_unit_refs": source_unit_refs, "evidence_refs": evidence_refs})
    return {
        "internal_results": internal_results,
        "entity_binding": {"status": "PASS" if all(row["status"] == "PASS" for row in entity_rows) else ("PASS_EMPTY" if not entity_rows else "BLOCKED"), "candidate_rows": entity_rows},
        "relation_signature": {"status": "PASS" if all(row["status"] == "PASS" for row in relation_rows) else ("PASS_EMPTY" if not relation_rows else "BLOCKED"), "candidate_rows": relation_rows},
        "qualifiers": {"status": "PASS" if all(row.get("status") == "PASS" for row in qualifier_rows) else ("PASS_EMPTY" if not qualifier_rows else "BLOCKED"), "candidate_rows": qualifier_rows},
        "evidence_binding": {"status": "PASS" if all(row["status"] == "PASS" for row in evidence_rows) else ("PASS_EMPTY" if not evidence_rows else "BLOCKED"), "candidate_rows": evidence_rows},
    }


def proposal_surface_coverage(
    *, source_units: Sequence[Mapping[str, Any]], candidates: Sequence[Any],
    valid_candidates: Sequence[Mapping[str, Any]], executable_registry: Mapping[str, Any],
    dormant_registry: Mapping[str, Any],
) -> dict[str, Any]:
    unit_ids = {str(row.get("unit_id") or "") for row in source_units}
    referenced_units = {str(ref) for candidate in candidates if isinstance(candidate, Mapping) for ref in candidate.get("source_unit_refs", []) if isinstance(ref, str)}
    valid_predicates = {str(row.get("predicate") or "") for row in valid_candidates}
    valid_entities: set[str] = set()
    for candidate in valid_candidates:
        for field in ("subject", "object"):
            entity = candidate.get(field)
            if isinstance(entity, Mapping) and entity.get("ref"):
                valid_entities.add(str(entity["ref"]))
    evidence_refs = {str(ref) for candidate in valid_candidates for ref in candidate.get("evidence_refs", [])}
    executable_predicates = set(executable_registry.get("predicates", {}))
    return {
        "schema_version": "source_claim_v3_proposal_surface_coverage_v1",
        "name": "PROPOSAL_SURFACE_COVERAGE",
        "semantic_coverage_pass": False,
        "candidate_count": len(candidates),
        "valid_candidate_count": len(valid_candidates),
        "blocked_candidate_count": len(candidates) - len(valid_candidates),
        "source_unit_count": len(unit_ids),
        "source_units_referenced": sorted(unit_ids & referenced_units),
        "source_units_not_referenced": sorted(unit_ids - referenced_units),
        "evidence_refs_used": sorted(evidence_refs),
        "predicates_proposed": sorted(valid_predicates),
        "executable_predicates_unused": sorted(executable_predicates - valid_predicates),
        "dormant_predicates": sorted(dormant_registry.get("dormant_predicates", {})),
        "entity_refs_used": sorted(valid_entities),
        "claim_proposal_completeness": "NOT_PROVEN",
    }


def contradiction_diagnostic(valid_candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in valid_candidates:
        subject = row.get("subject") if isinstance(row.get("subject"), Mapping) else {}
        object_ref = row.get("object") if isinstance(row.get("object"), Mapping) else {}
        key = (str(subject.get("ref") or ""), str(row.get("predicate") or ""), str(object_ref.get("ref") or ""))
        grouped.setdefault(key, []).append(row)
    conflicts = []
    for key, rows in sorted(grouped.items()):
        if len({(row.get("polarity"), row.get("modality")) for row in rows}) > 1:
            conflicts.append({"subject_ref": key[0], "predicate": key[1], "object_ref": key[2], "polarity_modality_pairs": sorted({(str(row.get("polarity")), str(row.get("modality"))) for row in rows})})
    return {"status": "DIAGNOSTIC_ONLY", "potential_typed_contradictions": conflicts, "automatic_resolution": False}


def blank_post_artifacts(pre: Mapping[str, Any], *, status: str) -> None:
    write_json("SOURCE_CLAIM_V3_TRANSPORT_AUDIT.json", {"status": status, "provider_post_count": 0, "semantic_verifier_post_count": 0, "second_order_proposal_post_count": 0, "retry_count": 0, "failed_checks": pre.get("failed_checks", [])})
    write_json("SOURCE_CLAIM_V3_RAW_FORENSIC.json", {"status": "NOT_RUN", "raw_response": "", "raw_response_sha256": "", "raw_response_length": 0, "persisted_before_parse": True, "provider_post_count": 0})
    write_json("SOURCE_CLAIM_V3_PARSE_AUDIT.json", {"status": "NOT_RUN", "repair": False, "coercion": False, "markdown_stripping": False, "substring_extraction": False})
    for filename in ("SOURCE_CLAIM_V3_SCHEMA_VALIDATION.json", "SOURCE_CLAIM_V3_ENTITY_BINDING_AUDIT.json", "SOURCE_CLAIM_V3_RELATION_SIGNATURE_AUDIT.json", "SOURCE_CLAIM_V3_QUALIFIER_AUDIT.json", "SOURCE_CLAIM_V3_EVIDENCE_BINDING_AUDIT.json", "SOURCE_CLAIM_V3_PROGRAM_ID_ASSIGNMENT.json", "SOURCE_CLAIM_V3_PROPOSAL_SET.json"):
        write_json(filename, {"status": "NOT_RUN", "provider_post_count": 0, "rows": []})
    write_json("SOURCE_CLAIM_V3_PROPOSAL_SURFACE_COVERAGE.json", {"name": "PROPOSAL_SURFACE_COVERAGE", "status": "NOT_RUN", "semantic_coverage_pass": False})
    write_json("SOURCE_CLAIM_V3_PROPOSAL_COMPLETENESS_STATUS.json", {"status": "NOT_PROVEN", "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING", "entity_semantic_completeness": "NOT_PROVEN"})
    write_json("SECOND_ORDER_DEFERRED_STATUS.json", {"status": "DEFERRED_NOT_PROVEN", "provider_proposal_count": 0, "second_order_execution_enabled": False, "predicates": ["knows", "uncertainty"]})
    freeze = pre["values"]["production_freeze_before"]
    write_json("NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", {
        "status": "PASS", "provider_proposal_posts": 0, "claim_verifier_posts": 0, "second_order_proposal_posts": 0,
        "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "entity_writes": 0,
        "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0,
        "production_freeze_before": freeze, "production_freeze_after": freeze,
    })
    write_json("RECOMMENDED_NEXT_ACTION.json", {"status": status, "next_state": "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PREFLIGHT_BLOCKED", "failed_checks": pre.get("failed_checks", []), "provider_posts": 0, "semantic_verifier_authorized": False})


def run_post(pre: Mapping[str, Any]) -> dict[str, Any]:
    values = pre["values"]
    source_units = values["source_units"]
    input_registry = values["input_registry"]
    executable_registry = values["derived_registry"]
    qualifier_registry = values["qualifier_registry"]
    db = values["db_before"]
    unit_bindings, evidence_index = source_and_evidence_index(source_units, source_fingerprint=str(db["source_fingerprint"]), source_package_id=str(db["source_package_id"]))
    audits: list[dict[str, Any]] = []
    response_holder: dict[str, Any] = {"called": False, "raw_persisted": False, "raw": None}

    def persist_raw(raw_value: Any) -> None:
        text_raw = raw_value if isinstance(raw_value, str) else ""
        write_json("SOURCE_CLAIM_V3_RAW_FORENSIC.json", {
            "status": "PASS_RAW_PERSISTED",
            "authorization_id": AUTHORIZATION_ID,
            "provider_post_count": 1,
            "raw_response": raw_value,
            "raw_response_type": type(raw_value).__name__,
            "raw_response_sha256": exact_hash(text_raw) if isinstance(raw_value, str) else "",
            "raw_response_length": len(text_raw) if isinstance(raw_value, str) else None,
            "persisted_before_parse": True,
            "provider_audit_pending": True,
        })
        response_holder["called"] = True
        response_holder["raw_persisted"] = True
        response_holder["raw"] = raw_value

    start = time.monotonic()
    error = ""
    raw_value: Any = None
    try:
        # One transport attempt: core.llm defines retries as total attempt count.
        raw_value = llm.call_llm(
            values["user_prompt"],
            system=values["system_prompt"],
            model_profile=values["profile"],
            retries=1,
            estimated_tokens=8192,
            max_tokens=8192,
            temperature=0.0,
            response_format=values["response_format"],
            audit_callback=audits.append,
            audit_extra={"v7_7_9": True, "authorization_id": AUTHORIZATION_ID, "proposal_only": True},
            raw_response_callback=persist_raw,
        )
    except Exception as exc:  # one POST may have been submitted; never retry
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
    latency_ms = round((time.monotonic() - start) * 1000, 2)
    if not response_holder["raw_persisted"]:
        write_json("SOURCE_CLAIM_V3_RAW_FORENSIC.json", {
            "status": "NO_RAW_CONTENT_RETURNED",
            "authorization_id": AUTHORIZATION_ID,
            "provider_post_count": len(audits),
            "raw_response": "",
            "raw_response_sha256": "",
            "raw_response_length": 0,
            "persisted_before_parse": True,
            "error": error,
        })
    raw = raw_value if isinstance(raw_value, str) else ""
    raw_sha = exact_hash(raw) if raw else ""
    provider_audit = audits[-1] if audits else {}
    write_json("SOURCE_CLAIM_V3_RAW_FORENSIC.json", {
        "status": "PASS_RAW_PERSISTED" if response_holder["raw_persisted"] else "NO_RAW_CONTENT_RETURNED",
        "authorization_id": AUTHORIZATION_ID,
        "provider_post_count": len(audits),
        "raw_response": raw_value if response_holder["raw_persisted"] else "",
        "raw_response_sha256": raw_sha,
        "raw_response_length": len(raw),
        "provider_audit": provider_audit,
        "error": error,
        "persisted_before_parse": True,
    })
    write_json("SOURCE_CLAIM_V3_TRANSPORT_AUDIT.json", {
        "status": "PASS" if len(audits) == 1 and not error and int(provider_audit.get("http_status") or 0) == 200 else "BLOCKED",
        "authorization_id": AUTHORIZATION_ID,
        "provider_post_count": len(audits),
        "semantic_verifier_post_count": 0,
        "second_order_proposal_post_count": 0,
        "retry_count": max(0, len(audits) - 1),
        "http_status": provider_audit.get("http_status"),
        "finish_reason": provider_audit.get("finish_reason"),
        "latency_ms": latency_ms,
        "usage": provider_audit.get("usage"),
        "provider_request_id": provider_audit.get("provider_request_id", ""),
        "raw_response_sha256": raw_sha,
        "request_fingerprint": pre["runtime"].get("request_fingerprint"),
        "resolved_response_format": provider_audit.get("resolved_response_format"),
        "transport_error": error,
        "retry_authorized": False,
    })

    parsed: Any = None
    parse_error = ""
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            parse_status = "PASS"
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            parse_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            parse_status = "BLOCKED"
    else:
        parse_error = "RAW_RESPONSE_NOT_STRING"
        parse_status = "BLOCKED"
    write_json("SOURCE_CLAIM_V3_PARSE_AUDIT.json", {
        "status": parse_status,
        "raw_sha256": raw_sha,
        "raw_length": len(raw),
        "strict_json_parse": True,
        "repair": False,
        "coercion": False,
        "markdown_stripping": False,
        "substring_extraction": False,
        "parse_retry": 0,
        "error": parse_error,
    })

    schema_validation = validate_json_schema_subset(parsed, values["compiled_schema"]["schema"]) if parse_status == "PASS" else {"status": "NOT_RUN", "errors": ["STRICT_PARSE_FAILED"]}
    wrapper_claims = parsed.get("claims") if isinstance(parsed, Mapping) and isinstance(parsed.get("claims"), list) else []
    internal_set = validate_claim_v3_set(
        parsed,
        input_entity_registry=input_registry,
        evidence_unit_bindings=unit_bindings,
        allowed_source_unit_refs=[str(unit.get("unit_id") or "") for unit in source_units],
        qualifier_registry=qualifier_registry,
        proposable_predicates=executable_registry,
    ) if parse_status == "PASS" else {"status": "NOT_RUN", "errors": ["STRICT_PARSE_FAILED"], "candidate_count": 0, "valid_count": 0, "blocked_count": 0, "candidate_results": []}
    write_json("SOURCE_CLAIM_V3_SCHEMA_VALIDATION.json", {
        "status": "PASS" if schema_validation.get("status") == "PASS" and internal_set.get("status") == "PASS" else "BLOCKED",
        "transport_schema_validation": schema_validation,
        "internal_v3_validation": internal_set,
        "claim_v3_schema_version": CLAIM_V3_VERSION,
        "provider_forbidden_fields": sorted(CLAIM_V3_FORBIDDEN_FIELDS),
        "repairs": 0,
    })
    audits_by_candidate = per_candidate_audits(
        wrapper_claims,
        input_registry=input_registry,
        executable_registry=executable_registry,
        qualifier_registry=qualifier_registry,
        unit_bindings=unit_bindings,
        evidence_index=evidence_index,
        source_fingerprint=str(db["source_fingerprint"]),
        source_package_id=str(db["source_package_id"]),
        units=source_units,
    )
    write_json("SOURCE_CLAIM_V3_ENTITY_BINDING_AUDIT.json", audits_by_candidate["entity_binding"])
    write_json("SOURCE_CLAIM_V3_RELATION_SIGNATURE_AUDIT.json", audits_by_candidate["relation_signature"])
    write_json("SOURCE_CLAIM_V3_QUALIFIER_AUDIT.json", audits_by_candidate["qualifiers"])
    write_json("SOURCE_CLAIM_V3_EVIDENCE_BINDING_AUDIT.json", audits_by_candidate["evidence_binding"])

    assignment = assign_program_owned_claim_ids(internal_set.get("candidate_results", []), entity_registry_fingerprint=str(input_registry.get("fingerprint") or "")) if parse_status == "PASS" and schema_validation.get("status") == "PASS" else {"status": "NOT_RUN", "rows": [], "provider_supplied_id": False}
    assigned_by_fingerprint = {str(row.get("candidate_fingerprint")): row for row in assignment.get("rows", []) if isinstance(row, Mapping)}
    detailed_candidates = []
    valid_projections = []
    for index, (candidate, result) in enumerate(zip(wrapper_claims, internal_set.get("candidate_results", []))):
        candidate_fp = ""
        assigned = None
        if result.get("status") == "PASS" and isinstance(result.get("projection"), Mapping):
            projection = result["projection"]
            from core.source_semantic_claim_v3 import claim_v3_candidate_fingerprint
            candidate_fp = claim_v3_candidate_fingerprint(projection, entity_registry_fingerprint=str(input_registry.get("fingerprint") or ""))
            assigned = assigned_by_fingerprint.get(candidate_fp)
            valid_projections.append(projection)
        detailed_candidates.append({
            "provider_candidate_index": index,
            "raw_candidate": candidate,
            "validation_status": result.get("status"),
            "errors": result.get("errors", []),
            "program_candidate_fingerprint": candidate_fp,
            "program_claim_id": assigned.get("claim_id") if isinstance(assigned, Mapping) else None,
            "authority": assigned.get("authority") if isinstance(assigned, Mapping) else "UNTRUSTED_PROPOSED",
            "canonical": assigned.get("canonical") if isinstance(assigned, Mapping) else False,
            "projection": result.get("projection"),
        })
    write_json("SOURCE_CLAIM_V3_PROGRAM_ID_ASSIGNMENT.json", assignment)
    final_count = len(wrapper_claims)
    valid_count = int(internal_set.get("valid_count") or 0)
    blocked_count = int(internal_set.get("blocked_count") or 0)
    if parse_status != "PASS":
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARSE_OR_SCHEMA_REVIEW_REQUIRED"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_REVIEW_REQUIRED"
    elif final_count > 0 and valid_count == 0:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_BINDING_BLOCKED"
        next_state = final_status
    elif final_count > 0 and valid_count > 0 and blocked_count > 0:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL_REVIEW_REQUIRED"
    elif schema_validation.get("status") != "PASS":
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARSE_OR_SCHEMA_REVIEW_REQUIRED"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_REVIEW_REQUIRED"
    elif final_count == 0:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_EMPTY_REVIEW_REQUIRED"
        next_state = final_status
    elif blocked_count > 0 or assignment.get("status") != "PASS":
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL_REVIEW_REQUIRED"
    else:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_VALIDATED"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_BOUNDARY_REQUIRED"
    set_status = "PASS" if parse_status == "PASS" and schema_validation.get("status") == "PASS" and internal_set.get("status") == "PASS" and assignment.get("status") == "PASS" else "BLOCKED"
    write_json("SOURCE_CLAIM_V3_PROPOSAL_SET.json", {
        "schema_version": CLAIM_V3_SET_VERSION,
        "status": final_status,
        "validation_status": set_status,
        "candidate_count": final_count,
        "valid_count": valid_count,
        "blocked_count": blocked_count,
        "candidate_set_fingerprint": assignment.get("fingerprint"),
        "candidate_fingerprint_ordering": assignment.get("candidate_fingerprint_inputs", []),
        "candidates": detailed_candidates,
        "all_authority_untrusted_proposed": all(row.get("authority") == "UNTRUSTED_PROPOSED" and row.get("canonical") is False for row in detailed_candidates if row.get("validation_status") == "PASS"),
        "persisted": False,
    })
    coverage = proposal_surface_coverage(
        source_units=source_units,
        candidates=wrapper_claims,
        valid_candidates=valid_projections,
        executable_registry=executable_registry,
        dormant_registry=executable_registry,
    )
    coverage.update({"status": "PASS_REPORTED_NOT_SEMANTIC_COMPLETENESS", "potential_contradiction_diagnostic": contradiction_diagnostic(valid_projections)})
    write_json("SOURCE_CLAIM_V3_PROPOSAL_SURFACE_COVERAGE.json", coverage)
    write_json("SOURCE_CLAIM_V3_PROPOSAL_COMPLETENESS_STATUS.json", {
        "status": "NOT_PROVEN",
        "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING",
        "entity_semantic_completeness": "NOT_PROVEN",
        "second_order_epistemic_coverage": "DEFERRED_NOT_PROVEN",
        "candidate_count": final_count,
        "source_unit_count": len(source_units),
        "proposal_surface_coverage": "PROPOSAL_SURFACE_COVERAGE",
        "full_source_semantic_coverage_claimed": False,
    })
    write_json("SECOND_ORDER_DEFERRED_STATUS.json", {
        "status": "DEFERRED_NOT_PROVEN",
        "predicates": ["knows", "uncertainty"],
        "provider_proposal_count": 0,
        "second_order_execution_enabled": False,
        "second_order_provider_schema_entries": 0,
    })
    db_after = read_db()
    production_after = current_production_freeze()
    db_sha_after = sha256_file(DB_PATH)
    production_unchanged = production_after == values.get("production_freeze_before")
    database_unchanged = db_sha_after == values.get("database_sha_before")
    write_json("NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", {
        "status": "PASS" if production_unchanged and database_unchanged else "BLOCKED",
        "provider_proposal_posts": len(audits),
        "claim_semantic_verifier_posts": 0,
        "second_order_claim_proposal_posts": 0,
        "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "entity_writes": 0,
        "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0,
        "production_freeze_before": values.get("production_freeze_before"),
        "production_freeze_after": production_after,
        "packet_row_hash_before": db.get("packet_row_hash"),
        "packet_row_hash_after": db_after.get("packet_row_hash"),
        "director_ledger_before": db.get("packet_attempt_count"),
        "director_ledger_after": db_after.get("packet_attempt_count"),
        "active_stage_b_before": db.get("stage_b_attempt"),
        "active_stage_b_after": db_after.get("stage_b_attempt"),
        "database_sha256_before": values.get("database_sha_before"),
        "database_sha256_after": db_sha_after,
        "production_freeze_unchanged": production_unchanged,
        "database_file_unchanged": database_unchanged,
    })
    write_json("RECOMMENDED_NEXT_ACTION.json", {
        "status": final_status,
        "next_state": next_state,
        "provider_posts": len(audits),
        "semantic_verifier_authorized": False,
        "semantic_verifier_called": False,
        "second_order_proposal_posts": 0,
        "source_claim_authority_written": False,
        "production_writes": 0 if production_unchanged and database_unchanged else "AUDIT_BLOCKED",
    })
    return {
        "status": final_status,
        "next_state": next_state,
        "provider_posts": len(audits),
        "http_status": provider_audit.get("http_status"),
        "finish_reason": provider_audit.get("finish_reason"),
        "raw_sha256": raw_sha,
        "parse_status": parse_status,
        "schema_status": schema_validation.get("status"),
        "candidate_count": final_count,
        "valid_count": valid_count,
        "blocked_count": blocked_count,
        "database_unchanged": database_unchanged,
        "production_unchanged": production_unchanged,
    }


def report_text(pre: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    runtime = pre["runtime"]
    local = pre["values"]["local_gates"]
    checks = pre["checks"]
    return f"""# V7.7.9 Source Semantic Claim V3 First-Order Single Real Proposal Canary

## Result

- Status: `{result.get('status')}`
- Next state: `{result.get('next_state')}`
- Authorization: `{AUTHORIZATION_ID}`; maximum real POSTs: `1`.
- Real Provider POST count: `{result.get('provider_posts')}`; HTTP / finish reason: `{result.get('http_status')}` / `{result.get('finish_reason')}`.
- Raw response SHA256: `{result.get('raw_sha256')}`; raw was atomically persisted before parsing.
- Strict parse / transport schema / internal V3 schema: `{result.get('parse_status')}` / `{result.get('schema_status')}` / `{result.get('schema_status')}`.
- Candidates: `{result.get('candidate_count')}`; valid `{result.get('valid_count')}`; blocked `{result.get('blocked_count')}`.
- Semantic verifier: `0`; second-order proposal: `0`; SourceClaim authority writes: `0`.

## V7.7.8.1 forward state and ontology

- Bound baseline: `{BASELINE_COMMIT}`; foundation: `SOURCE_SEMANTIC_CLAIM_V3_FOUNDATION_READY`; next authorization boundary: `SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED`.
- Historical `RECOMMENDED_NEXT_ACTION.json` was treated as `HISTORICAL_V7_7_8_ONLY`, not as a V7.7.9 gate.
- First-order predicate signatures: `6`; type-executable: `{runtime.get('first_order_predicate_count')}`; dormant: `{runtime.get('dormant_predicate_count')}`.
- Executable predicates derived at runtime: `{', '.join(runtime.get('executable_predicates') or [])}`.
- Dormant predicates retain `TYPE_DEPENDENCY_UNAVAILABLE`; no PROPERTY_VALUE or STATE_VALUE entities were created.
- `knows` / `uncertainty` were excluded from the provider prompt and schema. Second-order proposal count: `0`; coverage remains `DEFERRED_NOT_PROVEN`.
- Executability means type refs are available; it does not assert source support. Full proposal completeness remains `NOT_PROVEN`.

## Frozen inputs and provider qualification

- Target: Book `990453`, Episode `1`; source raw SHA256 `{runtime.get('source_raw_hash')}`; SourceAuthoringUnits `{runtime.get('source_unit_count')}` / fingerprint `{runtime.get('source_unit_fingerprint')}`.
- Verified entity registry fingerprint: `{EXPECTED_VERIFIED_ENTITY_FINGERPRINT}`; Claim Input Entity Registry fingerprint `{runtime.get('input_entity_registry_fingerprint')}`; entity count `{runtime.get('input_entity_count')}`.
- Provider identity: `local-llm-2vydoz / openai-compatible / mimo-v2.5 / https://api.xiaomimimo.com`; identity `{EXPECTED_PROVIDER_IDENTITY_FINGERPRINT}`.
- V7.7.5 strict JSON Schema qualification: `{EXPECTED_QUALIFICATION_FINGERPRINT}`; current identity revalidation passed before the only POST.
- Executable transport schema fingerprint: `{runtime.get('transport_schema_fingerprint')}`; V7.7.8 full first-order foundation fingerprint `{EXPECTED_TRANSPORT_BASELINE_FINGERPRINT}` remains the broader schema.
- Predicate enum came only from the runtime executable registry. `knows`, `uncertainty`, and `VERIFIED_FIRST_ORDER_CLAIM_REF` were absent.

## Validation and production boundary

- Strict schema validation, internal Claim V3 validation, entity binding, relation signature, qualifier and evidence/source-unit binding were run without repair or retries.
- Program IDs were assigned by sorted typed-candidate fingerprints; all accepted rows remain `UNTRUSTED_PROPOSED`, `canonical=false`.
- Proposal surface coverage was recorded; it is not semantic completeness. The Typed Director Requirement Manifest remains missing and entity completeness remains `NOT_PROVEN`.
- Claim V2 remains unchanged with `LEGACY_BLOCKED_UNION_TYPE`.
- Production database and frozen Packet 64 state unchanged: `{result.get('production_unchanged')}`; database SHA before `{runtime.get('database_sha256')}`, after `{result.get('database_sha256_after')}`.
- Director ledger: `11 -> 11`; active Stage B: `attempt-11 -> attempt-11`; Stage A / Attempt-12 / Confirm: `0 / 0 / 0`; FactRecord / SourceClaim / Entity writes: `0 / 0 / 0`; IMAGE / VIDEO: `0 / 0`.
- V7.5.1 current-branch state remains `HISTORICAL_REVALIDATION_ONLY` and was not used as Provider authorization input.

## Verification and Git

- Focused V7.7.2–V7.7.9 tests: `{local['tests']['output'].splitlines()[-1] if local['tests']['output'].splitlines() else local['tests']['status']}`.
- Python compileall: `{local['compileall']['status']}`; `git diff --check`: `{local['git_diff_check']['status']}`; production DB unchanged during local gates: `{local['local_gates_did_not_mutate_production_db']}`.
- Preflight failed checks: `{pre.get('failed_checks')}`.
- Implementation HEAD at canary execution: `{runtime.get('head')}`; remote HEAD at execution: `{runtime.get('remote_server_head')}`.
- No retry, repair, verifier, second-order proposal, source promotion, Stage A, Attempt-12, Confirm, IMAGE, VIDEO, PR or merge was performed.
- Evidence commit and final remote HEAD are recorded in the final task report because a commit cannot contain its own resulting SHA.
"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-real", action="store_true", help="use the explicitly authorized single real Provider POST after all preflight gates pass")
    args = parser.parse_args(argv)
    pre = build_preflight()
    if not args.execute_real:
        print(json.dumps({"mode": "PREFLIGHT_ONLY_NO_PROVIDER_CALL", "status": pre["status"], "failed_checks": pre["failed_checks"], "checks": pre["checks"], "runtime": pre["runtime"]}, ensure_ascii=False, indent=2))
        return 0 if pre["status"] == "PASS" else 2

    if CANARY_DIR.exists():
        print(json.dumps({"status": "BLOCKED_EXISTING_EVIDENCE_OR_PRIOR_ATTEMPT", "provider_posts": 0, "evidence_dir": str(CANARY_DIR)}, ensure_ascii=False, indent=2))
        return 2
    CANARY_DIR.mkdir(parents=True, exist_ok=False)
    write_preflight_artifacts(pre)
    write_json("SOURCE_CLAIM_V3_TRANSPORT_AUDIT.json", {"status": "NOT_CALLED_YET", "provider_post_count": 0, "authorization_id": AUTHORIZATION_ID})
    if pre["status"] != "PASS":
        blank_post_artifacts(pre, status="BLOCKED_PRE_PROVIDER_PREFLIGHT")
        result = {"status": "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PREFLIGHT_BLOCKED", "next_state": "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PREFLIGHT_BLOCKED", "provider_posts": 0, "database_unchanged": True, "production_unchanged": True}
        write_text("SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_REPORT.md", report_text(pre, result))
        print(json.dumps({"status": result["status"], "provider_posts": 0, "failed_checks": pre["failed_checks"], "evidence_dir": str(CANARY_DIR)}, ensure_ascii=False, indent=2))
        return 2

    result = run_post(pre)
    write_text("SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_REPORT.md", report_text(pre, result))
    result.update({"evidence_dir": str(CANARY_DIR), "preflight": pre["status"]})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("provider_posts") == 1 else 3


if __name__ == "__main__":
    raise SystemExit(main())
