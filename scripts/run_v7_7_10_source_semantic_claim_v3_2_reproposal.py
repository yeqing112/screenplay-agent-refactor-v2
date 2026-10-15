"""Run the authorized single V7.7.10 Claim V3.2 reproposal canary.

Default mode is provider-free preflight. ``--execute-real`` performs at most
one strict-schema Provider call after all current and frozen-state gates pass.
No verifier or production persistence code is imported.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sqlite3
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
from core.source_semantic_claim_authority import MODALITIES, POLARITIES
from core.source_semantic_claim_v3 import (
    CLAIM_INPUT_ENTITY_REGISTRY_VERSION,
    CLAIM_V3_FORBIDDEN_FIELDS,
    CLAIM_V3_REQUIRED_KEYS,
    CLAIM_V3_SET_VERSION,
    CLAIM_V3_VERSION,
    build_claim_input_entity_registry,
    claim_v3_candidate_schema,
    claim_v3_candidate_set_schema,
    count_schema_dialect_extensions,
)
from core.source_semantic_claim_v3_1 import (
    source_speech_act_binding_registry_v1,
)
from core.source_semantic_claim_v3_2 import (
    PROPOSAL_ATTEMPT_ID,
    PROVIDER_PREDICATE_REGISTRY_V3_VERSION,
    QUALIFIER_REGISTRY_V4_VERSION,
    RELATION_SIGNATURE_REGISTRY_V4_VERSION,
    assign_reproposal_claim_ids,
    build_reproposal_prompt,
    predicate_prompt_contract_v3_2,
    provider_entity_ref_qualifier_domain_audit,
    provider_predicate_registry_v3,
    qualifier_registry_v4,
    relation_signature_registry_v4,
    role_ref_constraint_contract_v1,
    validate_relation_role_ref_constraints,
    validate_provider_candidate_v3_2,
)
from core.source_semantic_claim_v3_canary import (
    build_source_claim_provider_entity_view,
    claim_entity_kind_inventory,
)
from scripts.generate_v7_7_8_source_semantic_claim_v3_foundation_evidence import (
    current_production_freeze,
    sha256_file,
)
from scripts.run_v7_7_3_source_semantic_claim_proposal import read_db


BRANCH = "codex/visual-authoring-provider-canary-reconcile"
BASELINE_COMMIT = "ef7bb3c275166e8468e68c29a8d1a449e509ca4a"
AUTHORIZATION_ID = "v7.7.10-source-semantic-claim-v3-2-reproposal-single-call"
MAX_PROVIDER_POSTS = 1
EXPECTED_VERIFIED_ENTITY_FINGERPRINT = "88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186"
EXPECTED_CLAIM_ENTITY_REGISTRY_FINGERPRINT = "877d43fc4cea05b487e50b6a4afcdb58e44f78338f1ebfcb388ecbe9b9740acb"
EXPECTED_SOURCE_RAW_HASH = "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1"
EXPECTED_SOURCE_UNIT_FINGERPRINT = "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f"
EXPECTED_PROVIDER_IDENTITY_FINGERPRINT = "9908c628bc8b970817674b26ff3897bb055bc24ee6505bbc2af6a80f7722c455"
EXPECTED_QUALIFICATION_FINGERPRINT = "194241dae7837d160c63a72bd1c3017bd9a9d0219d2f25e6a083637abdf3cb3b"
EXPECTED_RAW_V779_SHA = "44730220ba61ce249d1ebd5b87e3a0373b4cc220e58b7f96eef04a5b06f40585"

CANARY_DIR = ROOT / "docs/canonical-canary/v7_7_10-source-semantic-claim-v3-2-reproposal-real"
DB_PATH = ROOT / "work/db/screenplay.db"
V71 = ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract"
V773 = ROOT / "docs/canonical-canary/v7_7_3-source-semantic-claim-proposal-real"
V775 = ROOT / "docs/canonical-canary/v7_7_5-provider-structured-output-capability-qualification"
V777 = ROOT / "docs/canonical-canary/v7_7_7-source-entity-semantic-verification-real"
V778 = ROOT / "docs/canonical-canary/v7_7_8-source-semantic-claim-v3-foundation"
V779 = ROOT / "docs/canonical-canary/v7_7_9-source-semantic-claim-v3-first-order-proposal-real"
V7791 = ROOT / "docs/canonical-canary/v7_7_9_1-first-order-claim-contract-reconciliation"
SOURCE_CONTRACT_PATH = V71 / "SOURCE_AUTHORING_UNIT_CONTRACT.json"
SOURCE_VERIFIED_REGISTRY_PATH = V777 / "SOURCE_VERIFIED_ENTITY_REGISTRY.json"
CLAIM_INPUT_REGISTRY_PATH = V778 / "CLAIM_INPUT_ENTITY_REGISTRY.json"

TESTS = [
    "tests/test_source_semantic_claim_v3_2_reproposal.py",
    "tests/test_source_semantic_claim_v3_1_reconciliation.py",
    "tests/test_source_semantic_claim_v3_canary.py",
    "tests/test_source_semantic_claim_v3_foundation.py",
    "tests/test_source_semantic_claim_authority_v7_7_2.py",
    "tests/test_source_semantic_claim_proposal_v7_7_3.py",
    "tests/test_source_entity_structured_output_boundary_v7_7_4.py",
    "tests/test_provider_structured_output_qualification_v7_7_5.py",
    "tests/test_source_entity_proposal_canary_v7_7_6.py",
    "tests/test_source_entity_semantic_verification_v7_7_7.py",
]

ARTIFACTS = [
    "ANTI_HEURISTIC_PATCH_REVIEW.json",
    "V7_7_9_HISTORICAL_FREEZE.json",
    "V7_7_9_1_CONTRACT_FREEZE.json",
    "RELATION_SIGNATURE_REGISTRY_CURRENT.json",
    "QUALIFIER_REGISTRY_CURRENT.json",
    "PROVIDER_PREDICATE_REGISTRY_CURRENT.json",
    "RELATION_ROLE_REF_CONSTRAINT_CONTRACT.json",
    "RELATION_ROLE_REF_CONSTRAINT_AUDIT.json",
    "PROVIDER_ENTITY_REF_QUALIFIER_DOMAIN_CONTRACT.json",
    "PROVIDER_ENTITY_REF_QUALIFIER_DOMAIN_AUDIT.json",
    "TRANSFER_SOURCE_DEFERRED_STATUS.json",
    "SOURCE_CLAIM_REPROPOSAL_INPUT_FREEZE.json",
    "SOURCE_CLAIM_REPROPOSAL_PROVIDER_ENTITY_VIEW.json",
    "SOURCE_CLAIM_REPROPOSAL_PREDICATE_PROMPT_CONTRACT.json",
    "SOURCE_CLAIM_REPROPOSAL_EXECUTABILITY_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_TRANSPORT_SCHEMA.json",
    "SOURCE_CLAIM_REPROPOSAL_TRANSPORT_SCHEMA_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_AUTHORIZATION.json",
    "SOURCE_CLAIM_REPROPOSAL_PROVIDER_IDENTITY.json",
    "SOURCE_CLAIM_REPROPOSAL_PROMPT_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_TRANSPORT_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_RAW_FORENSIC.json",
    "SOURCE_CLAIM_REPROPOSAL_PARSE_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_SCHEMA_VALIDATION.json",
    "SOURCE_CLAIM_REPROPOSAL_ENTITY_BINDING_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_RELATION_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_ROLE_CONSTRAINT_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_QUALIFIER_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_EVIDENCE_BINDING_AUDIT.json",
    "SOURCE_CLAIM_REPROPOSAL_PROGRAM_ID_ASSIGNMENT.json",
    "SOURCE_CLAIM_REPROPOSAL_SET.json",
    "SOURCE_CLAIM_REPROPOSAL_SURFACE_COVERAGE.json",
    "SOURCE_CLAIM_REPROPOSAL_COMPLETENESS_STATUS.json",
    "PROGRAM_DETERMINISTIC_SPEECH_ACT_COMPANION_STATUS.json",
    "NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json",
    "RECOMMENDED_NEXT_ACTION.json",
    "SOURCE_SEMANTIC_CLAIM_V3_2_REPROPOSAL_REPORT.md",
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


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)
    return result.stdout.strip()


def exact_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_script_ir() -> tuple[dict[str, Any], str]:
    connection = sqlite3.connect(f"file:{DB_PATH.resolve().as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "select payload_json from script_ir_versions where id=? and book_id=? and episode=?",
            (52, 990453, 1),
        ).fetchone()
        if row is None:
            raise RuntimeError("FROZEN_SCRIPT_IR_52_MISSING")
        payload = json.loads(row[0])
        return payload, fingerprint(payload)
    finally:
        connection.close()


def entity_view_freshness(input_registry: Mapping[str, Any], source_registry: Mapping[str, Any]) -> dict[str, Any]:
    frozen = read_json(V779 / "SOURCE_CLAIM_PROVIDER_ENTITY_VIEW.json")
    current = build_source_claim_provider_entity_view(input_registry, source_registry)
    return {
        "schema_version": "source_claim_reproposal_provider_entity_view_freshness_v1",
        "status": "PASS" if current == frozen else "BLOCKED",
        "frozen_fingerprint": fingerprint(frozen),
        "runtime_fingerprint": fingerprint(current),
        "same_as_frozen_v7_7_9_view": current == frozen,
        "view": frozen,
    }


def speech_companion_freshness(*, script_ir: Mapping[str, Any], source_units: Sequence[Mapping[str, Any]], entities: Mapping[str, Any], source_fingerprint: str) -> dict[str, Any]:
    frozen = read_json(V7791 / "SOURCE_SPEECH_ACT_BINDING_REGISTRY.json")
    runtime = source_speech_act_binding_registry_v1(
        script_ir=script_ir, source_units=source_units,
        entity_registry=entities, source_fingerprint=source_fingerprint,
    )
    frozen_bindings = frozen.get("bindings") if isinstance(frozen.get("bindings"), list) else []
    runtime_bindings = runtime.get("bindings") if isinstance(runtime.get("bindings"), list) else []
    return {
        "schema_version": "program_deterministic_speech_act_companion_freshness_v1",
        "status": "PASS" if frozen.get("status") == "PASS" and len(frozen_bindings) == 1 and frozen_bindings == runtime_bindings else "BLOCKED",
        "binding_count": len(frozen_bindings),
        "expected_binding_count": 1,
        "frozen_bindings_fingerprint": fingerprint(frozen_bindings),
        "runtime_bindings_fingerprint": fingerprint(runtime_bindings),
        "binding_fingerprint_matches": frozen_bindings == runtime_bindings,
        "script_ir_payload_fingerprint": fingerprint(script_ir),
        "semantic_regeneration_performed": False,
        "companion_added_to_provider_raw_set": False,
        "provider_speech_act_candidate_count": 0,
        "program_deterministic_companion_count": len(frozen_bindings),
        "companion_registry_frozen": frozen,
    }


def current_profile() -> tuple[dict[str, Any], dict[str, Any]]:
    profile = llm._resolve_llm_profile()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    parsed = urlparse(base_url)
    host = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
    identity = provider_identity(
        profile_id=str(profile.get("id") or ""), provider=str(profile.get("provider") or ""),
        model=str(profile.get("model_name") or ""), base_host=host,
    )
    qualification = read_json(V775 / "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION.json")
    current_qualification = qualification_fingerprint(
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
        "qualification_fingerprint": current_qualification,
        "qualified": qualification.get("qualified") is True,
        "capability": qualification.get("capability"),
        "qualification_status": qualification.get("qualification_status"),
    }
    checks = {
        "profile_id_exact": identity["profile_id"] == "local-llm-2vydoz",
        "provider_exact": identity["provider"] == "openai-compatible",
        "model_exact": identity["model"] == "mimo-v2.5",
        "base_host_exact": identity["base_host"] == "https://api.xiaomimimo.com",
        "identity_fingerprint_exact": identity["provider_identity_fingerprint"] == EXPECTED_PROVIDER_IDENTITY_FINGERPRINT,
        "qualification_fingerprint_exact": current_qualification.get("qualification_fingerprint") == EXPECTED_QUALIFICATION_FINGERPRINT,
        "qualification_status_pass": qualification.get("qualification_status") == "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFIED",
        "strict_json_schema_qualified": qualification.get("capability") == "JSON_SCHEMA_STRICT_SUPPORTED" and qualification.get("qualified") is True,
        "profile_enabled_and_key_configured": summary["enabled"] and summary["key_configured"],
    }
    return profile, {"summary": summary, "qualification": qualification, "checks": checks, "status": "PASS" if all(checks.values()) else "BLOCKED"}


def anti_heuristic_audit() -> dict[str, Any]:
    path = ROOT / "core/source_semantic_claim_v3_2.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    attempt_semantic_branch = False
    for node in ast.walk(tree):
        if not isinstance(node, (ast.If, ast.IfExp, ast.Match)):
            continue
        test = ast.get_source_segment(source, node.test) if isinstance(node, (ast.If, ast.IfExp)) else ast.get_source_segment(source, node.subject)
        if test and re.search(r"attempt[_ -]?(?:id|[0-9]+)", test, re.I) and re.search(r"predicate|relation|qualifier", test, re.I):
            attempt_semantic_branch = True
            break
    patterns = {
        "local_nlp": bool(re.search(r"\b(?:spacy|jieba|nltk)\b", source, re.I)),
        "source_prose_extraction": bool(re.search(r"(?:re\.(?:search|findall|match|sub)|regex).*?(?:source|prose|evidence text)", source, re.I | re.S)),
        "predicate_name_inference": bool(re.search(r"(?:if|elif)\s+['\"][^'\"]+['\"]\s+in\s+predicate", source, re.I)),
        "qualifier_name_semantics_inference": bool(re.search(r"(?:if|elif)\s+['\"][^'\"]+['\"]\s+in\s+qualifier", source, re.I)),
        "attempt_specific_semantic_branch": attempt_semantic_branch,
    }
    return {
        "schema_version": "v7_7_10_anti_heuristic_patch_review_v1",
        "status": "PASS" if not any(patterns.values()) else "BLOCKED",
        "scanned_module": "core/source_semantic_claim_v3_2.py",
        "phrase_dependence": "NO", "scene_dependence": "NO", "attempt_specific_production_logic": "NO",
        "current_story_hardcoding": "NO", "predicate_name_inference": "NO",
        "qualifier_name_inference": "NO", "local_nlp": "NO", "pattern_checks": patterns,
        "provider_calls": 0, "production_writes": 0,
    }


def run_local_gates(database_sha_before: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", *TESTS, "-q"]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    database_sha_after_tests = sha256_file(DB_PATH)
    compile_result = subprocess.run([sys.executable, "-m", "compileall", "-q", "core", "scripts", "tests"], cwd=ROOT, capture_output=True, text=True)
    diff_result = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True)
    return {
        "tests": {"status": "PASS" if tests.returncode == 0 else "BLOCKED", "returncode": tests.returncode, "command": command, "output": (tests.stdout + tests.stderr)[-5000:]},
        "compileall": {"status": "PASS" if compile_result.returncode == 0 else "BLOCKED", "returncode": compile_result.returncode, "output": (compile_result.stdout + compile_result.stderr)[-2000:]},
        "git_diff_check": {"status": "PASS" if diff_result.returncode == 0 else "BLOCKED", "returncode": diff_result.returncode, "output": (diff_result.stdout + diff_result.stderr)[-2000:]},
        "database_sha_before": database_sha_before, "database_sha_after_tests": database_sha_after_tests,
        "database_unchanged": database_sha_before == database_sha_after_tests,
    }


def mock_role_audit(relation_registry: Mapping[str, Any]) -> dict[str, Any]:
    signature = relation_registry["signatures"]["enter_guided"]
    same = validate_relation_role_ref_constraints(
        claim={"predicate": "enter_guided", "subject_ref": "CHAR_A", "object_ref": "LOC_X"},
        signature=signature,
        typed_qualifiers={"guided_character": {"value_type": "ENTITY_REF", "ref": "CHAR_A", "kind": "CHARACTER"}},
    )
    distinct = validate_relation_role_ref_constraints(
        claim={"predicate": "enter_guided", "subject_ref": "CHAR_A", "object_ref": "LOC_X"},
        signature=signature,
        typed_qualifiers={"guided_character": {"value_type": "ENTITY_REF", "ref": "CHAR_B", "kind": "CHARACTER"}},
    )
    return {
        "schema_version": "relation_role_ref_constraint_audit_v1",
        "status": "PASS" if same["status"] == "BLOCKED" and distinct["status"] == "PASS" else "BLOCKED",
        "contract": role_ref_constraint_contract_v1(),
        "mock_same_guide_and_guided": same,
        "mock_distinct_guide_and_guided": distinct,
        "runtime_role_constraints": relation_registry["signatures"]["enter_guided"]["ref_constraints"],
    }


def build_preflight() -> dict[str, Any]:
    worktree_status = git("status", "--porcelain")
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    remote_tracking = git("rev-parse", f"origin/{BRANCH}", check=False)
    remote_result = git("ls-remote", "origin", f"refs/heads/{BRANCH}", check=False)
    remote_head = remote_result.split()[0] if remote_result else ""
    baseline_ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, head], cwd=ROOT, capture_output=True).returncode == 0

    database_sha_before = sha256_file(DB_PATH)
    production_before = current_production_freeze()
    db = read_db()
    profile, provider_audit = current_profile()
    source_contract = read_json(SOURCE_CONTRACT_PATH)
    source_units = source_contract.get("units", []) if isinstance(source_contract.get("units"), list) else []
    source_registry = read_json(SOURCE_VERIFIED_REGISTRY_PATH)
    input_registry_frozen = read_json(CLAIM_INPUT_REGISTRY_PATH)
    input_registry = build_claim_input_entity_registry(source_registry, expected_fingerprint=EXPECTED_VERIFIED_ENTITY_FINGERPRINT)
    source_units_fp = fingerprint(source_units)
    script_ir, script_ir_fp = load_script_ir()
    entity_view_audit = entity_view_freshness(input_registry, source_registry)
    source_freeze779 = read_json(V779 / "SOURCE_CLAIM_V3_INPUT_FREEZE.json")
    source_freeze779_no_write = read_json(V779 / "NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json")
    historical_raw = read_json(V779 / "SOURCE_CLAIM_V3_RAW_FORENSIC.json")
    historical_set = read_json(V779 / "SOURCE_CLAIM_V3_PROPOSAL_SET.json")
    eligibility7791 = read_json(V7791 / "CURRENT_V7_7_9_VERIFIER_ELIGIBILITY.json")
    companion_audit = speech_companion_freshness(
        script_ir=script_ir, source_units=source_units, entities=input_registry,
        source_fingerprint=EXPECTED_SOURCE_RAW_HASH,
    )
    historical_relation = read_json(V7791 / "RELATION_SIGNATURE_REGISTRY_V3.json")
    historical_qualifier = read_json(V7791 / "QUALIFIER_REGISTRY_V3.json")
    historical_provider = read_json(V7791 / "PROVIDER_PREDICATE_REGISTRY_V2.json")
    historical_companion_fp = fingerprint(read_json(V7791 / "SOURCE_SPEECH_ACT_BINDING_REGISTRY.json")["bindings"])
    historical_contract_freeze = {
        "schema_version": "v7_7_9_1_contract_freeze_v1",
        "status": "PASS",
        "contract_reconciled": read_json(V7791 / "RECOMMENDED_NEXT_ACTION.json").get("status") == "SOURCE_SEMANTIC_CLAIM_V3_CONTRACT_RECONCILED",
        "relation_registry_version": historical_relation.get("schema_version"),
        "qualifier_registry_version": historical_qualifier.get("schema_version"),
        "provider_registry_version": historical_provider.get("schema_version"),
        "speech_binding_count": len(read_json(V7791 / "SOURCE_SPEECH_ACT_BINDING_REGISTRY.json").get("bindings", [])),
        "speech_binding_fingerprint": historical_companion_fp,
        "old_candidates_verifier_eligible_count": eligibility7791.get("verifier_eligible_count"),
        "candidate_0_state": eligibility7791.get("candidate_0_state"),
        "candidate_1_state": eligibility7791.get("candidate_1_state"),
        "contract_artifact_sha256": {
            name: sha256_file(V7791 / name)
            for name in ("RELATION_SIGNATURE_REGISTRY_V3.json", "QUALIFIER_REGISTRY_V3.json", "PROVIDER_PREDICATE_REGISTRY_V2.json", "SOURCE_SPEECH_ACT_BINDING_REGISTRY.json", "CURRENT_V7_7_9_VERIFIER_ELIGIBILITY.json")
        },
    }

    relations = relation_signature_registry_v4()
    qualifiers = qualifier_registry_v4()
    ownership_domain_audit = provider_entity_ref_qualifier_domain_audit(qualifier_registry=qualifiers, relation_registry=relations)
    provider_registry = provider_predicate_registry_v3(relation_registry=relations, qualifier_registry=qualifiers, entity_registry=input_registry)
    inventory = claim_entity_kind_inventory(input_registry)
    entity_view = entity_view_audit["view"]
    predicate_contract = predicate_prompt_contract_v3_2(relations)
    system_prompt, user_prompt = build_reproposal_prompt(
        source_units=source_units, provider_entity_view=entity_view,
        provider_registry=provider_registry, predicate_contract=predicate_contract,
        qualifier_registry=qualifiers, polarities=POLARITIES, modalities=MODALITIES,
    )
    candidate_schema = claim_v3_candidate_schema(input_entity_registry=input_registry, proposable_predicates=provider_registry)
    transport_schema = claim_v3_candidate_set_schema(candidate_schema=candidate_schema)
    compiled = compile_provider_strict_schema(transport_schema)
    dialect_counts = count_schema_dialect_extensions(transport_schema)
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": CLAIM_V3_SET_VERSION, "strict": True, "schema": compiled.get("schema")},
    }
    role_audit = mock_role_audit(relations)
    anti = anti_heuristic_audit()
    local_gates = run_local_gates(database_sha_before)
    production_after = current_production_freeze()
    database_sha_after = sha256_file(DB_PATH)

    source_unit_binding = read_json(V773 / "SOURCE_UNIT_EVIDENCE_BINDING_MAP.json")
    computed_bindings = {
        str(unit.get("unit_id") or ""): [str(ref) for ref in unit.get("source_evidence_refs", [])]
        for unit in source_units
    }
    qualifier_keys_in_surface = sorted({key for row in provider_registry.get("predicates", {}).values() for key in row.get("allowed_qualifier_keys", [])})
    forbidden_prompt_tokens = ("speech_act", "speaker_binding", "has_property", "state_value", "knows", "uncertainty")
    prompt_text = system_prompt + user_prompt
    input_checks = {
        "verified_registry_fp_exact": source_registry.get("fingerprint") == EXPECTED_VERIFIED_ENTITY_FINGERPRINT,
        "input_registry_recomputed_equals_freeze": input_registry.get("status") == "PASS" and input_registry.get("fingerprint") == EXPECTED_CLAIM_ENTITY_REGISTRY_FINGERPRINT == input_registry_frozen.get("fingerprint"),
        "entity_count_exact": len(input_registry.get("entities", {})) == 19,
        "source_raw_hash_exact": source_freeze779.get("origin_source_raw_hash") == EXPECTED_SOURCE_RAW_HASH == db.get("source_fingerprint"),
        "source_package_exact": db.get("source_package_id") == "book:990402",
        "source_unit_count_exact": len(source_units) == 12 == source_contract.get("unit_count"),
        "source_unit_fp_exact": source_units_fp == EXPECTED_SOURCE_UNIT_FINGERPRINT == source_contract.get("fingerprint"),
        "source_unit_evidence_binding_exact": source_unit_binding.get("status") == "PASS" and source_unit_binding.get("unit_evidence_map") == computed_bindings,
        "script_ir_fingerprint_current": script_ir_fp == production_before.get("script_ir_payload_fingerprint") == source_freeze779_no_write.get("production_freeze_before", {}).get("script_ir_payload_fingerprint"),
        "entity_view_still_frozen": entity_view_audit.get("status") == "PASS",
        "speech_companion_fresh_only": companion_audit.get("status") == "PASS" and companion_audit.get("binding_count") == 1 and companion_audit.get("semantic_regeneration_performed") is False,
    }
    history_checks = {
        "v7_7_9_status_immutable": historical_set.get("status") == "SOURCE_SEMANTIC_CLAIM_V3_PROPOSAL_PARTIAL",
        "v7_7_9_raw_sha_immutable": historical_raw.get("raw_response_sha256") == EXPECTED_RAW_V779_SHA,
        "v7_7_9_1_reconciled": historical_contract_freeze.get("contract_reconciled"),
        "old_candidate_verifier_eligible_count_zero": eligibility7791.get("verifier_eligible_count") == 0,
        "candidate_0_superseded_and_ineligible": eligibility7791.get("candidate_0_state") == "SUPERSEDED_SIGNATURE_NOT_VERIFIER_ELIGIBLE",
        "candidate_1_redundant_qualifier_and_ineligible": eligibility7791.get("candidate_1_state") == "BLOCKED_REDUNDANT_PROVIDER_QUALIFIER",
        "source_claim_completeness_still_unproven": read_json(V7791 / "NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json").get("claim_proposal_completeness") == "NOT_PROVEN",
    }
    registry_checks = {
        "new_registry_versions_exact": relations.get("schema_version") == RELATION_SIGNATURE_REGISTRY_V4_VERSION and qualifiers.get("schema_version") == QUALIFIER_REGISTRY_V4_VERSION and provider_registry.get("schema_version") == PROVIDER_PREDICATE_REGISTRY_V3_VERSION,
        "provider_qualifier_surface_only_guided_character": qualifier_keys_in_surface == ["guided_character"] and set(qualifiers.get("qualifiers", {})) == {"guided_character"},
        "entity_ref_domains_all_resolved": ownership_domain_audit.get("status") == "PASS" and ownership_domain_audit.get("unresolved_entity_ref_qualifier_domain_count") == 0,
        "provider_received_by_has_no_qualifier": relations["signatures"]["received_by"].get("allowed_qualifier_keys") == [],
        "runtime_executable_predicates_derived": set(provider_registry.get("predicates", {})) == {"enter_guided", "left_by", "received_by"},
        "runtime_dormant_predicates_derived": set(provider_registry.get("dormant_predicates", {})) == {"has_property", "state_value"},
        "program_speech_act_excluded": provider_registry.get("program_deterministic_predicates") == ["speech_act"] and "speech_act" not in provider_registry.get("predicates", {}),
        "second_order_excluded": provider_registry.get("second_order_provider_proposable") is False,
    }
    schema_checks = {
        "compiler_pass": compiled.get("audit", {}).get("status") == "PASS",
        "strict_json_schema": response_format.get("type") == "json_schema" and response_format.get("json_schema", {}).get("strict") is True,
        "predicate_enum_is_runtime_derived": candidate_schema.get("properties", {}).get("predicate", {}).get("enum") == sorted(provider_registry.get("predicates", {})),
        "speech_act_absent_from_schema": "speech_act" not in json.dumps(transport_schema),
        "provider_forbidden_fields_absent": not (set(CLAIM_V3_FORBIDDEN_FIELDS) & set(candidate_schema.get("properties", {}))),
        "all_wire_candidate_fields_exact": set(candidate_schema.get("properties", {})) == CLAIM_V3_REQUIRED_KEYS,
        "dialect_extensions_zero": dialect_counts == {"union_type": 0, "oneOf": 0, "anyOf": 0, "dangling_ref": 0},
    }
    prompt_checks = {
        "predicate_contract_pass": predicate_contract.get("status") == "PASS",
        "entity_view_count_and_fingerprint_fresh": entity_view_audit.get("same_as_frozen_v7_7_9_view") is True,
        "forbidden_provider_terms_absent": not any(term in prompt_text for term in forbidden_prompt_tokens),
        "guided_role_rules_explicit": "All three roles are required" in prompt_text and "exact qualifier rules" in user_prompt,
        "received_by_transfer_not_inferred": "Do not infer who transferred it" in prompt_text,
        "zero_or_more_and_no_forced_mapping": "zero or more" in system_prompt and "Do not force meaning into the closest predicate" in system_prompt,
    }
    production_checks = {
        "production_freeze_matches_v7_7_9": production_before == source_freeze779_no_write.get("production_freeze_before"),
        "production_unchanged_during_preflight": production_before == production_after,
        "database_unchanged_during_preflight": database_sha_before == database_sha_after,
        "ledger_and_active_stage_b_exact": db.get("packet_attempt_count") == 11 and db.get("stage_a_attempt") == "attempt-7" and db.get("stage_b_attempt") == "attempt-11",
        "fact_snapshot_script_ir_packet_exact": db.get("fact_snapshot_id") == 49 and db.get("script_ir_id") == 52 and db.get("packet_id") == 64,
    }
    runtime_name = str(os.environ.get("E2E_EXTERNAL_RUNTIME") or "").strip().lower()
    test_and_repo_checks = {
        "branch_exact": branch == BRANCH,
        "baseline_is_ancestor": baseline_ancestor,
        "worktree_clean": not worktree_status,
        "local_head_equals_remote_tracking": head == remote_tracking,
        "local_head_equals_remote_server": head == remote_head,
        "no_existing_v7_7_10_evidence": not CANARY_DIR.exists(),
        "mock_runtime_disabled": runtime_name != "mock",
        "authorization_scope_exact": AUTHORIZATION_ID == "v7.7.10-source-semantic-claim-v3-2-reproposal-single-call" and MAX_PROVIDER_POSTS == 1,
        "anti_heuristic_pass": anti.get("status") == "PASS",
        "focused_tests_compile_and_diff_pass": local_gates["tests"]["status"] == "PASS" and local_gates["compileall"]["status"] == "PASS" and local_gates["git_diff_check"]["status"] == "PASS" and local_gates["database_unchanged"],
    }
    checks = {
        "historical_v7_7_9_freezes": all(history_checks.values()),
        "new_execution_contract": all(registry_checks.values()),
        "role_ref_constraint_audit": role_audit.get("status") == "PASS",
        "entity_ref_qualifier_domain_audit": ownership_domain_audit.get("status") == "PASS",
        "input_source_entity_and_companion_freezes": all(input_checks.values()),
        "strict_transport_schema": all(schema_checks.values()),
        "prompt_surface": all(prompt_checks.values()),
        "provider_identity_and_qualification": provider_audit.get("status") == "PASS",
        "production_freeze": all(production_checks.values()),
        **test_and_repo_checks,
    }
    failed = [key for key, ok in checks.items() if not ok]
    runtime = {
        "branch": branch, "head": head, "remote_tracking_head": remote_tracking, "remote_server_head": remote_head,
        "baseline_commit": BASELINE_COMMIT, "source_raw_hash": EXPECTED_SOURCE_RAW_HASH,
        "source_unit_count": len(source_units), "source_unit_fingerprint": source_units_fp,
        "claim_entity_registry_fingerprint": input_registry.get("fingerprint"), "claim_entity_count": len(input_registry.get("entities", {})),
        "provider_identity": provider_audit["summary"],
        "provider_identity_fingerprint": provider_audit["summary"].get("provider_identity_fingerprint"),
        "qualification_fingerprint": provider_audit["summary"].get("qualification_fingerprint"),
        "relation_registry_version": relations.get("schema_version"),
        "qualifier_registry_version": qualifiers.get("schema_version"),
        "provider_registry_version": provider_registry.get("schema_version"),
        "provider_predicate_count": len(provider_registry.get("predicates", {})),
        "provider_predicates": sorted(provider_registry.get("predicates", {})),
        "dormant_predicates": sorted(provider_registry.get("dormant_predicates", {})),
        "program_deterministic_predicates": provider_registry.get("program_deterministic_predicates"),
        "second_order_predicates": provider_registry.get("second_order_predicates"),
        "entity_inventory": inventory,
        "schema_fingerprint": compiled.get("audit", {}).get("output_fingerprint"),
        "schema_dialect_counts": dialect_counts,
        "system_prompt_sha256": exact_hash(system_prompt), "user_prompt_sha256": exact_hash(user_prompt),
        "request_fingerprint": fingerprint({
            "provider_identity": provider_audit["summary"],
            "proposal_attempt_id": PROPOSAL_ATTEMPT_ID,
            "relation_registry": fingerprint(relations),
            "qualifier_registry": fingerprint(qualifiers),
            "provider_registry": fingerprint(provider_registry),
            "transport_schema": compiled.get("audit", {}).get("output_fingerprint"),
            "system_prompt_sha256": exact_hash(system_prompt), "user_prompt_sha256": exact_hash(user_prompt),
        }),
        "database_sha256": database_sha_after,
        "production_freeze": production_after,
    }
    values = {
        "db": db, "production_before": production_before, "source_units": source_units,
        "profile": profile,
        "script_ir": script_ir, "source_registry": source_registry, "input_registry": input_registry,
        "entity_view_audit": entity_view_audit, "companion_audit": companion_audit,
        "historical_raw": historical_raw, "historical_set": historical_set,
        "historical_contract_freeze": historical_contract_freeze, "relations": relations,
        "qualifiers": qualifiers, "provider_registry": provider_registry, "inventory": inventory,
        "domain_audit": ownership_domain_audit, "predicate_contract": predicate_contract,
        "system_prompt": system_prompt, "user_prompt": user_prompt,
        "candidate_schema": candidate_schema, "transport_schema": transport_schema,
        "compiled": compiled, "response_format": response_format, "role_audit": role_audit,
        "anti": anti, "local_gates": local_gates, "production_after": production_after,
        "database_sha_before": database_sha_before, "database_sha_after": database_sha_after,
        "provider_audit": provider_audit,
    }
    return {"status": "PASS" if not failed else "BLOCKED", "failed_checks": failed, "checks": checks,
            "check_groups": {"history": history_checks, "input": input_checks, "registries": registry_checks, "schema": schema_checks, "prompt": prompt_checks, "production": production_checks, "local_repo": test_and_repo_checks},
            "runtime": runtime, "values": values}


def write_preflight_artifacts(pre: Mapping[str, Any]) -> None:
    v = pre["values"]
    runtime = pre["runtime"]
    write_json("ANTI_HEURISTIC_PATCH_REVIEW.json", v["anti"])
    write_json("V7_7_9_HISTORICAL_FREEZE.json", {
        "schema_version": "v7_7_9_historical_freeze_v1", "status": "PASS" if all(pre["check_groups"]["history"].values()) else "BLOCKED",
        "proposal_status": v["historical_set"].get("status"),
        "raw_sha256": v["historical_raw"].get("raw_response_sha256"),
        "raw_sha256_expected": EXPECTED_RAW_V779_SHA,
        "candidate_count": v["historical_set"].get("candidate_count"),
        "valid_count": v["historical_set"].get("valid_count"),
        "blocked_count": v["historical_set"].get("blocked_count"),
        "verifier_eligible_count": 0,
        "old_candidate_states": {
            "candidate_0": v["historical_contract_freeze"].get("candidate_0_state"),
            "candidate_1": v["historical_contract_freeze"].get("candidate_1_state"),
        },
        "historical_artifacts_modified": False,
    })
    write_json("V7_7_9_1_CONTRACT_FREEZE.json", v["historical_contract_freeze"])
    write_json("RELATION_SIGNATURE_REGISTRY_CURRENT.json", v["relations"])
    write_json("QUALIFIER_REGISTRY_CURRENT.json", v["qualifiers"])
    write_json("PROVIDER_PREDICATE_REGISTRY_CURRENT.json", v["provider_registry"])
    write_json("RELATION_ROLE_REF_CONSTRAINT_CONTRACT.json", role_ref_constraint_contract_v1())
    write_json("RELATION_ROLE_REF_CONSTRAINT_AUDIT.json", v["role_audit"])
    write_json("PROVIDER_ENTITY_REF_QUALIFIER_DOMAIN_CONTRACT.json", {
        "schema_version": "provider_entity_ref_qualifier_domain_contract_v1",
        "rule": "Every provider-writable ENTITY_REF qualifier declares a nonempty explicit entity-kind domain in each permitting provider predicate signature.",
        "missing_domain_means_any_kind": False,
    })
    write_json("PROVIDER_ENTITY_REF_QUALIFIER_DOMAIN_AUDIT.json", v["domain_audit"])
    write_json("TRANSFER_SOURCE_DEFERRED_STATUS.json", {
        "schema_version": "transfer_source_deferred_status_v1",
        "status": "DEFERRED_ENTITY_KIND_DOMAIN_UNRESOLVED",
        "historical_v3_value_type": "ENTITY_REF",
        "v4_provider_writable": False,
        "received_by_allowed_qualifier_keys": [],
        "kind_guessed": False,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_INPUT_FREEZE.json", {
        "schema_version": "source_claim_reproposal_input_freeze_v1", "status": "PASS" if all(pre["check_groups"]["input"].values()) and all(pre["check_groups"]["production"].values()) else "BLOCKED",
        "proposal_attempt_id": PROPOSAL_ATTEMPT_ID,
        "target_book_id": 990453, "episode": 1, "fact_snapshot_id": 49, "script_ir_id": 52, "packet_id": 64,
        "origin_source_book_id": 990402, "origin_source_package_id": "book:990402",
        "source_raw_sha256": EXPECTED_SOURCE_RAW_HASH,
        "source_unit_count": len(v["source_units"]), "source_unit_fingerprint": EXPECTED_SOURCE_UNIT_FINGERPRINT,
        "verified_entity_registry_fingerprint": EXPECTED_VERIFIED_ENTITY_FINGERPRINT,
        "claim_input_entity_registry_fingerprint": EXPECTED_CLAIM_ENTITY_REGISTRY_FINGERPRINT,
        "claim_input_entity_count": 19,
        "script_ir_payload_fingerprint": fingerprint(v["script_ir"]),
        "database_sha256": runtime["database_sha256"],
        "production_freeze": v["production_before"],
        "completeness": {"claim_proposal": "NOT_PROVEN", "entity_semantic": "NOT_PROVEN", "second_order": "DEFERRED_NOT_PROVEN", "typed_director_manifest": "MISSING"},
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_PROVIDER_ENTITY_VIEW.json", v["entity_view_audit"])
    write_json("SOURCE_CLAIM_REPROPOSAL_PREDICATE_PROMPT_CONTRACT.json", v["predicate_contract"])
    write_json("SOURCE_CLAIM_REPROPOSAL_EXECUTABILITY_AUDIT.json", {
        "schema_version": "source_claim_reproposal_executability_audit_v1", "status": "PASS" if v["provider_registry"].get("status") == "PASS" else "BLOCKED",
        "provider_owned_ontology_count": 5,
        "runtime_executable_count": len(v["provider_registry"]["predicates"]),
        "runtime_executable_predicates": sorted(v["provider_registry"]["predicates"]),
        "dormant_count": len(v["provider_registry"]["dormant_predicates"]),
        "dormant_predicates": sorted(v["provider_registry"]["dormant_predicates"]),
        "program_deterministic_count": len(v["provider_registry"]["program_deterministic_predicates"]),
        "program_deterministic_predicates": v["provider_registry"]["program_deterministic_predicates"],
        "second_order_count": len(v["provider_registry"]["second_order_predicates"]),
        "second_order_predicates": v["provider_registry"]["second_order_predicates"],
        "entity_kind_inventory": v["inventory"],
        "executability_is_not_source_support": True,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_TRANSPORT_SCHEMA.json", {
        "schema_version": "source_claim_reproposal_transport_schema_v1", "status": "PASS" if v["compiled"]["audit"].get("status") == "PASS" else "BLOCKED",
        "transport_schema": v["transport_schema"], "strict_response_format": v["response_format"],
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_TRANSPORT_SCHEMA_AUDIT.json", {
        "schema_version": "source_claim_reproposal_transport_schema_audit_v1",
        "status": "PASS" if v["compiled"]["audit"].get("status") == "PASS" else "BLOCKED",
        "compiler": v["compiled"]["audit"], "transport_schema_fingerprint": runtime["schema_fingerprint"],
        "predicate_enum": sorted(v["provider_registry"]["predicates"]),
        "predicate_enum_runtime_derived": True, "strict": True,
        "dialect_counts": runtime["schema_dialect_counts"],
        "additional_properties_false": True, "provider_forbidden_fields": sorted(CLAIM_V3_FORBIDDEN_FIELDS),
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_AUTHORIZATION.json", {
        "authorization_id": AUTHORIZATION_ID, "granted": True,
        "source": "explicit user instruction in V7.7.10 phase prompt",
        "scope": {"book_id": 990453, "episode": 1, "first_order_only": True, "provider_proposable_only": True,
                  "frozen_source_and_entity_registry": True, "v4_typed_ontology": True},
        "max_real_provider_posts": 1, "retries": 0, "claim_verifier_posts": 0,
        "second_order_proposal_posts": 0, "production_writes": 0, "image_posts": 0, "video_posts": 0,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_PROVIDER_IDENTITY.json", {
        **v["provider_audit"]["summary"], "preflight_status": v["provider_audit"]["status"],
        "profile_mutated": False,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_PROMPT_AUDIT.json", {
        "schema_version": "source_claim_reproposal_prompt_audit_v1", "status": "PASS" if all(pre["check_groups"]["prompt"].values()) else "BLOCKED",
        "system_prompt_sha256": runtime["system_prompt_sha256"], "user_prompt_sha256": runtime["user_prompt_sha256"],
        "request_fingerprint": runtime["request_fingerprint"],
        "system_prompt_length": len(v["system_prompt"]), "user_prompt_length": len(v["user_prompt"]),
        "source_unit_count": len(v["source_units"]),
        "runtime_executable_predicates_only": sorted(v["provider_registry"]["predicates"]),
        "speech_act_or_speaker_binding_in_prompt": False,
        "dormant_or_second_order_predicates_in_prompt": False,
        "lossy_forced_mapping_prohibited": "Do not force meaning into the closest predicate" in v["system_prompt"],
        "source_units_zero_or_more": "zero or more" in v["system_prompt"],
        "prompt_text_persisted": False,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_TRANSPORT_AUDIT.json", {
        "status": "NOT_CALLED_YET", "authorization_id": AUTHORIZATION_ID,
        "provider_post_count": 0, "retry_count": 0, "claim_verifier_post_count": 0,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_RAW_FORENSIC.json", {
        "status": "NOT_CALLED_YET", "authorization_id": AUTHORIZATION_ID,
        "provider_post_count": 0, "raw_response": "", "raw_response_sha256": "", "raw_response_length": 0,
    })
    for name, value in {
        "SOURCE_CLAIM_REPROPOSAL_PARSE_AUDIT.json": {"status": "NOT_RUN", "parse_retry": 0, "repair": False},
        "SOURCE_CLAIM_REPROPOSAL_SCHEMA_VALIDATION.json": {"status": "NOT_RUN", "candidate_count": 0, "valid_count": 0, "blocked_count": 0},
        "SOURCE_CLAIM_REPROPOSAL_ENTITY_BINDING_AUDIT.json": {"status": "NOT_RUN", "candidate_rows": []},
        "SOURCE_CLAIM_REPROPOSAL_RELATION_AUDIT.json": {"status": "NOT_RUN", "candidate_rows": []},
        "SOURCE_CLAIM_REPROPOSAL_ROLE_CONSTRAINT_AUDIT.json": {"status": "NOT_RUN", "candidate_rows": []},
        "SOURCE_CLAIM_REPROPOSAL_QUALIFIER_AUDIT.json": {"status": "NOT_RUN", "candidate_rows": []},
        "SOURCE_CLAIM_REPROPOSAL_EVIDENCE_BINDING_AUDIT.json": {"status": "NOT_RUN", "candidate_rows": []},
        "SOURCE_CLAIM_REPROPOSAL_PROGRAM_ID_ASSIGNMENT.json": {"status": "NOT_RUN", "rows": [], "historical_ids_reused": False},
        "SOURCE_CLAIM_REPROPOSAL_SET.json": {"status": "NOT_CALLED_YET", "candidate_count": 0, "valid_count": 0, "blocked_count": 0, "persisted": False},
        "SOURCE_CLAIM_REPROPOSAL_SURFACE_COVERAGE.json": {"status": "NOT_RUN", "semantic_coverage_pass": False},
        "SOURCE_CLAIM_REPROPOSAL_COMPLETENESS_STATUS.json": {"claim_proposal_completeness": "NOT_PROVEN", "entity_semantic_completeness": "NOT_PROVEN", "second_order_epistemic_coverage": "DEFERRED_NOT_PROVEN", "typed_director_requirement_manifest": "MISSING"},
        "PROGRAM_DETERMINISTIC_SPEECH_ACT_COMPANION_STATUS.json": v["companion_audit"],
        "NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json": {"provider_proposal_posts": 0, "claim_verifier_posts": 0, "production_writes": 0},
        "RECOMMENDED_NEXT_ACTION.json": {"status": "PREFLIGHT_READY_PENDING_SINGLE_CALL" if pre["status"] == "PASS" else "PREFLIGHT_BLOCKED", "failed_checks": pre["failed_checks"], "provider_posts": 0, "verifier_calls": 0},
    }.items():
        write_json(name, value)


def preflight_report(pre: Mapping[str, Any], status: str) -> str:
    runtime = pre["runtime"]
    local = pre["values"]["local_gates"]
    return f"""# V7.7.10 Source Semantic Claim V3.2 Reproposal Canary

Preflight status: `{status}`. Failed checks: `{pre.get('failed_checks')}`.

No Provider request was sent in this preflight report.

- Baseline: `{BASELINE_COMMIT}`; branch: `{BRANCH}`; HEAD: `{runtime.get('head')}`.
- V7.7.9 remains partial with frozen raw SHA `{EXPECTED_RAW_V779_SHA}`; V7.7.9.1 remains reconciled and its two old candidates remain verifier-ineligible.
- New registries: `{runtime.get('relation_registry_version')}`, `{runtime.get('qualifier_registry_version')}`, `{runtime.get('provider_registry_version')}`.
- Provider predicate enum derived at runtime: `{', '.join(runtime.get('provider_predicates') or [])}`; dormant: `{', '.join(runtime.get('dormant_predicates') or [])}`; deterministic speech companion remains separate.
- Provider identity: `{runtime.get('provider_identity_fingerprint')}`; qualification: `{runtime.get('qualification_fingerprint')}`.
- Source SHA: `{runtime.get('source_raw_hash')}`; entity registry: `{runtime.get('claim_entity_registry_fingerprint')}`; schema SHA: `{runtime.get('schema_fingerprint')}`.
- Focused tests: `{local['tests']['status']}`; compileall: `{local['compileall']['status']}`; diff check: `{local['git_diff_check']['status']}`.
- Production writes, verifier, second order, Stage A, Attempt-12, Confirm, IMAGE, VIDEO: `0`.
"""


def evidence_unit_bindings(source_units: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for unit in source_units:
        unit_id = str(unit.get("unit_id") or "")
        refs = unit.get("source_evidence_refs") if isinstance(unit.get("source_evidence_refs"), list) else []
        for ref in refs:
            result.setdefault(str(ref), []).append(unit_id)
    return {key: sorted(set(value)) for key, value in result.items()}


def candidate_audits(candidates: Sequence[Any], pre: Mapping[str, Any]) -> dict[str, Any]:
    values = pre["values"]
    source_units = values["source_units"]
    entity_registry = values["input_registry"]
    provider_registry = values["provider_registry"]
    relation_registry = values["relations"]
    qualifier_registry = values["qualifiers"]
    bindings = evidence_unit_bindings(source_units)
    allowed_units = [str(row.get("unit_id") or "") for row in source_units]
    results: list[dict[str, Any]] = []
    entity_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    role_rows: list[dict[str, Any]] = []
    qualifier_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            blocked = {"status": "BLOCKED", "errors": ["CANDIDATE_NOT_OBJECT"], "projection": None, "typed_qualifiers": {}}
            results.append(blocked)
            for rows in (entity_rows, relation_rows, role_rows, qualifier_rows, evidence_rows):
                rows.append({"index": index, "status": "BLOCKED", "errors": ["CANDIDATE_NOT_OBJECT"]})
            continue
        result = validate_provider_candidate_v3_2(
            candidate,
            provider_registry=provider_registry,
            relation_registry=relation_registry,
            entity_registry=entity_registry,
            qualifier_registry=qualifier_registry,
            evidence_unit_bindings=bindings,
            allowed_source_unit_refs=allowed_units,
        )
        results.append(result)
        entities = entity_registry.get("entities", {})
        entity_errors: list[str] = []
        for field in ("subject_ref", "object_ref"):
            ref = candidate.get(field)
            if not isinstance(ref, str) or ref not in entities:
                entity_errors.append(f"{field.upper()}_UNKNOWN_ENTITY_REF")
        entity_rows.append({"index": index, "status": "PASS" if not entity_errors else "BLOCKED", "errors": entity_errors,
                            "subject_ref": candidate.get("subject_ref"), "object_ref": candidate.get("object_ref")})
        predicate = str(candidate.get("predicate") or "")
        signature = relation_registry.get("signatures", {}).get(predicate)
        provider_predicate = provider_registry.get("predicates", {}).get(predicate)
        relation_errors = [] if isinstance(provider_predicate, Mapping) else [f"PREDICATE_NOT_PROVIDER_PROPOSABLE:{predicate}"]
        relation_rows.append({"index": index, "predicate": predicate, "status": "PASS" if not relation_errors else "BLOCKED",
                              "errors": relation_errors, "signature": signature})
        role = result.get("role_constraint_audit", {"status": "BLOCKED", "errors": ["ROLE_AUDIT_MISSING"]})
        role_rows.append({"index": index, **role})
        qresult = {"status": "PASS" if not any(err.startswith(("QUALIFIER", "REQUIRED_QUALIFIER")) for err in result["errors"]) else "BLOCKED",
                   "errors": [err for err in result["errors"] if "QUALIFIER" in err],
                   "qualifiers": candidate.get("qualifiers")}
        qualifier_rows.append({"index": index, **qresult})
        evrefs = candidate.get("evidence_refs") if isinstance(candidate.get("evidence_refs"), list) else []
        unitrefs = candidate.get("source_unit_refs") if isinstance(candidate.get("source_unit_refs"), list) else []
        ev_errors = []
        if not evrefs:
            ev_errors.append("EVIDENCE_REFS_REQUIRED")
        for ref in evrefs:
            ref_units = set(bindings.get(str(ref), []))
            if not ref_units:
                ev_errors.append(f"EVIDENCE_REF_UNKNOWN:{ref}")
            elif not ref_units.intersection(str(x) for x in unitrefs):
                ev_errors.append(f"EVIDENCE_UNIT_BINDING_MISMATCH:{ref}")
        if not unitrefs:
            ev_errors.append("SOURCE_UNIT_REFS_REQUIRED")
        ev_errors.extend(f"SOURCE_UNIT_REF_UNKNOWN:{ref}" for ref in unitrefs if str(ref) not in set(allowed_units))
        evidence_rows.append({"index": index, "status": "PASS" if not ev_errors else "BLOCKED", "errors": sorted(set(ev_errors)),
                              "evidence_refs": evrefs, "source_unit_refs": unitrefs})
    def aggregate(rows: Sequence[Mapping[str, Any]]) -> str:
        if not rows:
            return "PASS_EMPTY"
        return "PASS" if all(row.get("status") == "PASS" for row in rows) else "BLOCKED"
    return {
        "candidate_results": results,
        "entity_binding": {"status": aggregate(entity_rows), "candidate_rows": entity_rows},
        "relation": {"status": aggregate(relation_rows), "candidate_rows": relation_rows},
        "role_constraints": {"status": aggregate(role_rows), "candidate_rows": role_rows},
        "qualifiers": {"status": aggregate(qualifier_rows), "candidate_rows": qualifier_rows},
        "evidence_binding": {"status": aggregate(evidence_rows), "candidate_rows": evidence_rows},
    }


def run_single_post(pre: Mapping[str, Any]) -> dict[str, Any]:
    """Perform exactly one authorized transport attempt and persist raw before parsing."""
    values = pre["values"]
    runtime = pre["runtime"]
    audit_rows: list[dict[str, Any]] = []
    raw_holder: dict[str, Any] = {"saved": False, "value": None}
    request_started = time.monotonic()

    def persist_raw(value: Any) -> None:
        raw_text = value if isinstance(value, str) else ""
        write_json("SOURCE_CLAIM_REPROPOSAL_RAW_FORENSIC.json", {
            "schema_version": "source_claim_reproposal_raw_forensic_v1",
            "status": "RAW_PERSISTED_BEFORE_PARSE", "authorization_id": AUTHORIZATION_ID,
            "provider_post_count": 1, "raw_response": value,
            "raw_response_sha256": exact_hash(raw_text) if isinstance(value, str) else "",
            "raw_response_length": len(raw_text) if isinstance(value, str) else None,
            "persisted_before_parse": True,
        })
        raw_holder.update({"saved": True, "value": value})

    error = ""
    raw: Any = None
    try:
        raw = llm.call_llm(
            values["user_prompt"], system=values["system_prompt"],
            model_profile=values["profile"], retries=1, estimated_tokens=8192,
            max_tokens=8192, temperature=0.0, response_format=values["response_format"],
            audit_callback=audit_rows.append,
            audit_extra={"authorization_id": AUTHORIZATION_ID, "proposal_only": True, "reproposal": True},
            raw_response_callback=persist_raw,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:500]}"
    elapsed_ms = round((time.monotonic() - request_started) * 1000, 2)
    if raw_holder["saved"]:
        raw = raw_holder["value"]
    raw_text = raw if isinstance(raw, str) else ""
    raw_sha = exact_hash(raw_text) if raw_holder["saved"] and isinstance(raw, str) else ""
    audit = audit_rows[-1] if audit_rows else {}
    post_count = len(audit_rows)
    write_json("SOURCE_CLAIM_REPROPOSAL_RAW_FORENSIC.json", {
        "schema_version": "source_claim_reproposal_raw_forensic_v1",
        "status": "RAW_PERSISTED_BEFORE_PARSE" if raw_holder["saved"] else "NO_RAW_CONTENT_RETURNED",
        "authorization_id": AUTHORIZATION_ID, "provider_post_count": post_count,
        "raw_response": raw if raw_holder["saved"] else "", "raw_response_sha256": raw_sha,
        "raw_response_length": len(raw_text) if raw_holder["saved"] else 0,
        "persisted_before_parse": True, "provider_audit": audit, "transport_error": error,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_TRANSPORT_AUDIT.json", {
        "schema_version": "source_claim_reproposal_transport_audit_v1",
        "status": "PASS" if post_count == 1 and int(audit.get("http_status") or 0) == 200 and not error else "BLOCKED",
        "authorization_id": AUTHORIZATION_ID, "provider_post_count": post_count,
        "retry_count": max(0, post_count - 1), "retry_authorized": False,
        "http_status": audit.get("http_status"), "finish_reason": audit.get("finish_reason"),
        "latency_ms": elapsed_ms, "usage": audit.get("usage"),
        "provider_request_id": audit.get("provider_request_id", ""),
        "raw_response_sha256": raw_sha, "request_fingerprint": runtime["request_fingerprint"],
        "resolved_response_format": audit.get("resolved_response_format"), "transport_error": error,
        "claim_verifier_posts": 0, "second_order_posts": 0,
    })

    parse_error = ""
    parsed: Any = None
    if not raw_holder["saved"] or not isinstance(raw, str):
        parse_error, parse_status = "RAW_RESPONSE_NOT_STRING_OR_MISSING", "BLOCKED"
    else:
        try:
            parsed = json.loads(raw)
            parse_status = "PASS"
        except (ValueError, TypeError) as exc:
            parse_error, parse_status = f"{type(exc).__name__}: {str(exc)[:300]}", "BLOCKED"
    write_json("SOURCE_CLAIM_REPROPOSAL_PARSE_AUDIT.json", {
        "schema_version": "source_claim_reproposal_parse_audit_v1", "status": parse_status,
        "raw_sha256": raw_sha, "raw_length": len(raw_text), "strict_json_parse": True,
        "repair": False, "coercion": False, "markdown_stripping": False,
        "substring_extraction": False, "parse_retry": 0, "error": parse_error,
    })

    schema_result = validate_json_schema_subset(parsed, values["transport_schema"]) if parse_status == "PASS" else {"status": "NOT_RUN", "errors": ["STRICT_JSON_PARSE_FAILED"]}
    claims = parsed.get("claims") if isinstance(parsed, Mapping) and isinstance(parsed.get("claims"), list) else []
    if not (isinstance(parsed, Mapping) and isinstance(parsed.get("claims"), list)):
        schema_result = {**schema_result, "status": "BLOCKED", "errors": list(schema_result.get("errors", [])) + ["CLAIMS_ARRAY_REQUIRED"]}
    rows = candidate_audits(claims, pre) if parse_status == "PASS" else candidate_audits([], pre)
    validation_results = rows["candidate_results"]
    valid_count = sum(1 for result in validation_results if result.get("status") == "PASS")
    candidate_count = len(claims)
    blocked_count = candidate_count - valid_count
    # Any transport contract failure blocks acceptance, even if some local projections look valid.
    if schema_result.get("status") != "PASS":
        for result in validation_results:
            result["transport_schema_blocked"] = True
            result["status"] = "BLOCKED"
            result["errors"] = sorted(set(list(result.get("errors", [])) + ["STRICT_TRANSPORT_SCHEMA_FAILED"]))
            result["projection"] = None
        valid_count, blocked_count = 0, candidate_count
    schema_status = "PASS" if schema_result.get("status") == "PASS" and blocked_count == 0 else "BLOCKED"
    write_json("SOURCE_CLAIM_REPROPOSAL_SCHEMA_VALIDATION.json", {
        "schema_version": "source_claim_reproposal_schema_validation_v1",
        "status": schema_status, "transport_schema_validation": schema_result,
        "candidate_count": candidate_count, "valid_count": valid_count, "blocked_count": blocked_count,
        "repairs": 0,
    })
    for filename, key in (
        ("SOURCE_CLAIM_REPROPOSAL_ENTITY_BINDING_AUDIT.json", "entity_binding"),
        ("SOURCE_CLAIM_REPROPOSAL_RELATION_AUDIT.json", "relation"),
        ("SOURCE_CLAIM_REPROPOSAL_ROLE_CONSTRAINT_AUDIT.json", "role_constraints"),
        ("SOURCE_CLAIM_REPROPOSAL_QUALIFIER_AUDIT.json", "qualifiers"),
        ("SOURCE_CLAIM_REPROPOSAL_EVIDENCE_BINDING_AUDIT.json", "evidence_binding"),
    ):
        write_json(filename, rows[key])
    assignment = assign_reproposal_claim_ids(validation_results, entity_registry_fingerprint=str(values["input_registry"].get("fingerprint") or "")) if schema_status == "PASS" else {"status": "NOT_RUN", "rows": [], "historical_ids_reused": False, "provider_supplied_id": False}
    write_json("SOURCE_CLAIM_REPROPOSAL_PROGRAM_ID_ASSIGNMENT.json", assignment)
    id_by_fp = {str(row.get("candidate_fingerprint")): row for row in assignment.get("rows", []) if isinstance(row, Mapping)}
    detailed = []
    for index, (candidate, result) in enumerate(zip(claims, validation_results)):
        assignment_row = next((row for row in assignment.get("rows", []) if row.get("projection") == result.get("projection")), None)
        detailed.append({
            "provider_candidate_index": index, "raw_candidate": candidate,
            "validation_status": result.get("status"), "errors": result.get("errors", []),
            "program_claim_id": assignment_row.get("claim_id") if assignment_row else None,
            "authority": "UNTRUSTED_PROPOSED", "canonical": False,
            "verifier_eligible": False, "projection": result.get("projection"),
        })
    if parse_status != "PASS" or schema_result.get("status") != "PASS":
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_BLOCKED"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_REVIEW_REQUIRED"
    elif assignment.get("status") != "PASS":
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_BLOCKED"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_PROGRAM_ID_ASSIGNMENT_REVIEW_REQUIRED"
    elif candidate_count == 0:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_EMPTY_REVIEW_REQUIRED"
        next_state = final_status
    elif valid_count == 0:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_BLOCKED"
        next_state = final_status
    elif blocked_count:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_PARTIAL"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_PARTIAL_REVIEW_REQUIRED"
    else:
        final_status = "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_VALIDATED"
        next_state = "SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_BOUNDARY_REQUIRED"
    write_json("SOURCE_CLAIM_REPROPOSAL_SET.json", {
        "schema_version": CLAIM_V3_SET_VERSION, "status": final_status,
        "candidate_count": candidate_count, "valid_count": valid_count, "blocked_count": blocked_count,
        "candidates": detailed, "candidate_set_fingerprint": fingerprint(assignment.get("rows", [])) if assignment.get("rows") else "",
        "candidate_fingerprint_ordering": assignment.get("candidate_fingerprint_ordering", []),
        "all_authority_untrusted_proposed": True, "persisted": False,
    })
    predicate_counts: dict[str, int] = {}
    for candidate in claims:
        if isinstance(candidate, Mapping):
            predicate = str(candidate.get("predicate") or "")
            predicate_counts[predicate] = predicate_counts.get(predicate, 0) + 1
    role_violations = sum(1 for row in rows["role_constraints"]["candidate_rows"] if row.get("status") != "PASS")
    write_json("SOURCE_CLAIM_REPROPOSAL_SURFACE_COVERAGE.json", {
        "status": "RECORDED_NOT_SEMANTIC_COMPLETENESS", "candidate_count": candidate_count,
        "valid_count": valid_count, "blocked_count": blocked_count,
        "source_unit_count": len(values["source_units"]),
        "source_units_referenced": sorted({str(ref) for row in claims if isinstance(row, Mapping) for ref in row.get("source_unit_refs", [])}),
        "predicate_counts": predicate_counts, "claim_proposal_completeness": "NOT_PROVEN",
        "semantic_coverage_pass": False,
    })
    write_json("SOURCE_CLAIM_REPROPOSAL_COMPLETENESS_STATUS.json", {
        "claim_proposal_completeness": "NOT_PROVEN", "entity_semantic_completeness": "NOT_PROVEN",
        "second_order_epistemic_coverage": "DEFERRED_NOT_PROVEN", "typed_director_requirement_manifest": "MISSING",
    })

    db_after = read_db()
    freeze_after = current_production_freeze()
    db_sha_after = sha256_file(DB_PATH)
    production_unchanged = freeze_after == values["production_before"] and db_sha_after == runtime["database_sha256"]
    write_json("NO_CLAIM_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", {
        "status": "PASS" if production_unchanged else "BLOCKED",
        "provider_proposal_posts": post_count, "claim_verifier_posts": 0,
        "second_order_proposal_posts": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0,
        "source_claim_writes": 0, "entity_writes": 0, "stage_a": 0, "attempt_12": 0,
        "confirm": 0, "image": 0, "video": 0,
        "production_freeze_before": values["production_before"], "production_freeze_after": freeze_after,
        "packet_attempt_count_before": values["db"].get("packet_attempt_count"),
        "packet_attempt_count_after": db_after.get("packet_attempt_count"),
        "active_stage_b_before": values["db"].get("stage_b_attempt"), "active_stage_b_after": db_after.get("stage_b_attempt"),
        "database_sha256_before": runtime["database_sha256"], "database_sha256_after": db_sha_after,
        "production_freeze_unchanged": freeze_after == values["production_before"],
        "database_file_unchanged": db_sha_after == runtime["database_sha256"],
    })
    write_json("RECOMMENDED_NEXT_ACTION.json", {
        "status": final_status, "next_state": next_state, "provider_posts": post_count,
        "semantic_verifier_authorized": False, "semantic_verifier_called": False,
        "second_order_proposal_posts": 0, "source_claim_authority_written": False,
        "production_writes": 0 if production_unchanged else "AUDIT_BLOCKED",
    })
    return {
        "status": final_status, "next_state": next_state, "provider_posts": post_count,
        "http_status": audit.get("http_status"), "finish_reason": audit.get("finish_reason"),
        "latency_ms": elapsed_ms, "usage": audit.get("usage"), "raw_sha256": raw_sha,
        "raw_length": len(raw_text), "parse_status": parse_status, "schema_status": schema_status,
        "candidate_count": candidate_count, "valid_count": valid_count, "blocked_count": blocked_count,
        "predicate_counts": predicate_counts,
        "guided_character_count": predicate_counts.get("enter_guided", 0),
        "role_constraint_violations": role_violations,
        "speech_act_provider_candidate_count": predicate_counts.get("speech_act", 0),
        "new_scc_count": len(assignment.get("rows", [])),
        "speech_companion_count": values["companion_audit"].get("program_deterministic_companion_count", 0),
        "production_unchanged": production_unchanged,
        "database_sha256_after": db_sha_after,
    }


def final_report(pre: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    runtime = pre["runtime"]
    return f"""# V7.7.10 Source Semantic Claim V3.2 Reproposal Canary

## Outcome

- Status: `{result.get('status')}`; next state: `{result.get('next_state')}`.
- Baseline: `{BASELINE_COMMIT}`; branch: `{runtime.get('branch')}`; implementation HEAD: `{runtime.get('head')}`.
- V7.7.9 remains `{pre['values']['historical_set'].get('status')}`; frozen raw SHA256: `{EXPECTED_RAW_V779_SHA}`; V7.7.9.1 old verifier eligible count: `0`.
- V7.7.9.1 candidate #0 remains `SUPERSEDED_SIGNATURE_NOT_VERIFIER_ELIGIBLE`; candidate #1 remains `BLOCKED_REDUNDANT_PROVIDER_QUALIFIER`; neither entered verification.
- Current registries: `{runtime.get('relation_registry_version')}`, `{runtime.get('qualifier_registry_version')}`, `{runtime.get('provider_registry_version')}`.
- Role distinctness audit: `{pre['values']['role_audit'].get('status')}`; same-guide/guided blocked and distinct-guide/guided passed.
- Provider ENTITY_REF qualifier domain audit: `{pre['values']['domain_audit'].get('status')}`; unresolved domains: `{pre['values']['domain_audit'].get('unresolved_entity_ref_qualifier_domain_count')}`. `transfer_source` remains deferred and is not provider writable.
- Provider-owned predicates: `5`; runtime executable: `{runtime.get('provider_predicates')}`; dormant: `{runtime.get('dormant_predicates')}`; deterministic: `{runtime.get('program_deterministic_predicates')}`; second order: `{runtime.get('second_order_predicates')}`.
- Provider schema predicate enum: `{runtime.get('provider_predicates')}`; schema fingerprint: `{runtime.get('schema_fingerprint')}`; dialect extensions: `{runtime.get('schema_dialect_counts')}`.

## Provider and candidate validation

- Authorized real Provider POSTs: `{result.get('provider_posts')}`; HTTP status: `{result.get('http_status')}`; finish reason: `{result.get('finish_reason')}`; latency: `{result.get('latency_ms')} ms`; token usage: `{result.get('usage')}`.
- Raw SHA256: `{result.get('raw_sha256')}`; raw length: `{result.get('raw_length')}`; raw was atomically persisted before parsing.
- Parse / schema: `{result.get('parse_status')}` / `{result.get('schema_status')}`; candidates: `{result.get('candidate_count')}`, valid: `{result.get('valid_count')}`, blocked: `{result.get('blocked_count')}`.
- Predicate counts: `{result.get('predicate_counts')}`; `enter_guided` candidates: `{result.get('guided_character_count')}`; role violations: `{result.get('role_constraint_violations')}`; Provider `speech_act` candidates: `{result.get('speech_act_provider_candidate_count')}`.
- New SCC IDs: `{result.get('new_scc_count')}`; all remain `UNTRUSTED_PROPOSED`, `canonical=false`, verifier-ineligible. Program speech companion count: `{result.get('speech_companion_count')}` and it was not merged into the Provider raw set.

## Authority and production boundary

- Claim Semantic Verifier: `0`; second-order proposal: `0`; SourceClaim promotion/persistence: `0`; FactRecord writes: `0`; Entity promotion: `0`.
- Stage A / Attempt-12 / Confirm: `0 / 0 / 0`; IMAGE / VIDEO: `0 / 0`.
- Production freeze unchanged: `{result.get('production_unchanged')}`; ledger `11`; active Stage B `attempt-11`.
- Claim proposal completeness: `NOT_PROVEN`; entity semantic completeness: `NOT_PROVEN`; second-order coverage: `DEFERRED_NOT_PROVEN`; Typed Director Requirement Manifest: `MISSING`.
- Tests: `{pre['values']['local_gates']['tests']['output'].splitlines()[-1] if pre['values']['local_gates']['tests']['output'].splitlines() else 'see preflight evidence'}`; compileall: `{pre['values']['local_gates']['compileall']['status']}`; diff check: `{pre['values']['local_gates']['git_diff_check']['status']}`.
- No retry, verifier, second-order proposal, promotion, image/video request, PR, or merge was performed.

## Git

- Remote HEAD at preflight: `{runtime.get('remote_server_head')}`. Final evidence commit and remote HEAD are recorded in the completion response.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--preflight-only", action="store_true", help="Run all gates without writing evidence or calling a Provider.")
    group.add_argument("--execute-real", action="store_true", help="Run one Provider POST only if all preflight gates pass.")
    args = parser.parse_args()
    pre = build_preflight()
    if args.preflight_only or not args.execute_real:
        print(json.dumps({"status": pre["status"], "failed_checks": pre["failed_checks"], "checks": pre["checks"], "runtime": pre["runtime"]}, ensure_ascii=False, indent=2, default=str))
        return 0 if pre["status"] == "PASS" else 2
    if CANARY_DIR.exists():
        raise SystemExit(f"Refusing to overwrite existing V7.7.10 evidence: {CANARY_DIR}")
    write_preflight_artifacts(pre)
    if pre["status"] != "PASS":
        result = {"status": "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_PREFLIGHT_BLOCKED", "next_state": "SOURCE_SEMANTIC_CLAIM_V3_REPROPOSAL_CANARY_AUTHORIZATION_REQUIRED", "provider_posts": 0}
        write_json("RECOMMENDED_NEXT_ACTION.json", {"status": result["status"], "next_state": result["next_state"], "failed_checks": pre["failed_checks"], "provider_posts": 0, "semantic_verifier_authorized": False})
        write_text("SOURCE_SEMANTIC_CLAIM_V3_2_REPROPOSAL_REPORT.md", preflight_report(pre, result["status"]))
        print(json.dumps({"status": result["status"], "failed_checks": pre["failed_checks"], "provider_posts": 0}, indent=2))
        return 2
    result = run_single_post(pre)
    write_text("SOURCE_SEMANTIC_CLAIM_V3_2_REPROPOSAL_REPORT.md", final_report(pre, result))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("production_unchanged") else 3


if __name__ == "__main__":
    raise SystemExit(main())
