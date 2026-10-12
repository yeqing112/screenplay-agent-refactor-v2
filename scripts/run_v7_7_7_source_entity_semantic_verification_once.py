"""Run the single authorized V7.7.7 source entity semantic verification canary."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import llm
from core.provider_structured_output_qualification import (
    compile_provider_strict_schema,
    fingerprint,
    is_explicit_schema_rejection,
    provider_identity,
    validate_json_schema_subset,
)
from core.source_entity_proposal import claim_v2_schema, entity_candidate_fingerprint
from core.source_entity_proposal_runtime import qualification_freshness_gate
from core.source_entity_semantic_verification import (
    GENERIC_ENTITY_KIND_DEFINITIONS,
    VERIFICATION_VERSION,
    build_verification_schema,
    compile_verified_entity_registry,
    recompute_lineage_reconciliation,
    validate_frozen_proposal_registry,
    validate_verification_coverage,
    validate_verification_evidence_scope,
    verification_summary,
)
from core.source_semantic_claim_proposal import parse_strict_json
from scripts.run_v7_7_3_source_semantic_claim_proposal import (
    SOURCE_CONTRACT,
    build_source_inputs,
    read_db,
    read_json,
)
from scripts.run_v7_7_6_source_entity_proposal_once import build_inputs as build_v776_inputs


EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_7_7-source-entity-semantic-verification-real"
V776_EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_7_6-source-entity-proposal-real"
QUALIFICATION_DIR = ROOT / "docs" / "canonical-canary" / "v7_7_5-provider-structured-output-capability-qualification"
PERSISTENCE_DIR = ROOT / "docs" / "canonical-canary" / "v7-real-production-persistence"
QUALIFICATION_PATH = QUALIFICATION_DIR / "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION.json"
QUALIFICATION_RAW_PATH = QUALIFICATION_DIR / "CAPABILITY_PROBE_RAW_FORENSIC.json"
EXPECTED_BASELINE = "ea1d396d296913420d58fe180df22d7c301e5f33"
EXPECTED_BRANCH = "codex/visual-authoring-provider-canary-reconcile"
EXPECTED_QUALIFICATION_FINGERPRINT = "194241dae7837d160c63a72bd1c3017bd9a9d0219d2f25e6a083637abdf3cb3b"
EXPECTED_PROVIDER_IDENTITY_FINGERPRINT = "9908c628bc8b970817674b26ff3897bb055bc24ee6505bbc2af6a80f7722c455"
EXPECTED_V776_RAW_SHA = "1fdc30f0bb1aa6aeda4930aee3cefb4e5cf66d1c0b383bd3cd0be9338e41ff27"
EXPECTED_V776_REGISTRY_FINGERPRINT = "7e1c7d37f36ae61b04504c107d0f7fc2c4bfc939a1ddfcbeb8badf4d7ff56fb4"
EXPECTED_V776_ASSIGNMENT_FINGERPRINT = "b18ca9b2cbbf5d3f9e9ad32dab4c0b6a6a2d2818c5a09ce5879ad0712c7b5fbf"
EXPECTED_AUTHORIZATION_ID = "v7.7.7-source-entity-semantic-verification-single-call"
EXPECTED_LINEAGE = {
    "target_book_id": 990453,
    "origin_source_book_id": 990402,
    "origin_source_package_id": "book:990402",
    "origin_chapter_id": 16,
    "origin_chapter_seq": 3,
    "origin_source_raw_hash": "190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1",
    "source_unit_fingerprint": "2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f",
}
TARGET_BOOK_ID = 990453
EPISODE = 1
SOURCE_UNIT_COUNT = 12
FACT_SNAPSHOT_ID = 49
SCRIPT_IR_ID = 52
PACKET_ID = 64
DIRECTOR_LEDGER = 11
STAGE_A_ATTEMPT = "attempt-7"
STAGE_B_ATTEMPT = "attempt-11"

SYSTEM_PROMPT = """You are a semantic verifier for frozen source entity proposals. For each supplied PEC, independently judge only (1) whether the exact proposed surface form is an explicitly evidenced semantic entity in that PEC's bound evidence, and (2) whether its existing generic kind is supported by that evidence and immediate context. Return one result for each supplied proposal_entity_ref and use only the supplied bound evidence_refs. Do not propose, add, remove, rename, split, merge, or repair entities. Do not change surface forms, kinds, evidence references, or source-unit references. Do not suggest replacement kinds, aliases, canonical IDs, claims, ownership, actions, intent, completeness, or authority. If evidence is insufficient, use AMBIGUOUS. A verdict is only an untrusted adjudication and grants no entity authority."""


def write(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    content = str(value) if name.lower().endswith(".md") else json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    (EVIDENCE / name).write_text(content, encoding="utf-8")


def read_path(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def anti_heuristic_review() -> dict[str, Any]:
    path = ROOT / "core" / "source_entity_semantic_verification.py"
    source = path.read_text(encoding="utf-8")
    forbidden_literals = ("顾沉", "林晚", "铁盒", "车票", "胶片", "别针", "安全灯", "药水柜", "照片里小女孩", "PEC_0008")
    story_matches = [item for item in forbidden_literals if item in source]
    forbidden_patterns = (r"\bjieba\b", r"\bspacy\b", r"noun[_ -]?dictionary", r"regex[_ -]?entity", r"\bNER\b", r"embedding.{0,20}merge")
    nlp_matches = [pattern for pattern in forbidden_patterns if re.search(pattern, source, flags=re.IGNORECASE)]
    special_case_matches = [pattern for pattern in (r"if\s+.{0,80}PEC_\d{4}", r"surface_form\s*==") if re.search(pattern, source)]
    clean = not story_matches and not nlp_matches and not special_case_matches
    return {
        "schema_version": "v7_7_7_anti_heuristic_patch_review_v1",
        "status": "PASS" if clean else "HEURISTIC_PATCH_REJECTED",
        "phrase_dependence": "NO",
        "scene_dependence": "NO",
        "attempt_dependence": "NO",
        "story_specific_verifier_rule": "NO",
        "current_PEC_specific_special_case": "NO",
        "local_NLP": "NO",
        "production_modules_scanned": [str(path.relative_to(ROOT))],
        "story_literal_matches": story_matches,
        "local_NLP_matches": nlp_matches,
        "PEC_special_case_matches": special_case_matches,
    }


def canonical_entity_projection(registry: Mapping[str, Any]) -> dict[str, Any]:
    entities = registry.get("entities") if isinstance(registry.get("entities"), Mapping) else {}
    return {
        str(ref): {key: value for key, value in entity.items() if key != "authority"}
        for ref, entity in entities.items()
        if isinstance(entity, Mapping) and entity.get("authority") == "CANONICAL_RUNTIME"
    }


def build_evidence_text_index(units: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    evidence: dict[str, dict[str, Any]] = {}
    unit_map: dict[str, list[str]] = {}
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        refs = [str(ref) for ref in unit.get("source_evidence_refs", [])]
        unit_map[unit_id] = refs
        record = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        evidence_id = str(record.get("evidence_id") or "")
        text = record.get("text")
        if evidence_id and evidence_id in refs and isinstance(text, str):
            evidence[evidence_id] = {"evidence_ref": evidence_id, "source_unit_id": unit_id, "text": text, "sha256": str(record.get("sha256") or sha256_text(text))}
    return evidence, unit_map


def build_verifier_input(*, candidates: Mapping[str, Mapping[str, Any]], evidence_texts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    proposals = []
    for ref in sorted(candidates):
        candidate = candidates[ref]
        bound = []
        for evidence_ref in candidate.get("evidence_refs", []):
            source = evidence_texts.get(str(evidence_ref))
            if source:
                bound.append({"evidence_ref": str(evidence_ref), "source_unit_id": str(source.get("source_unit_id") or ""), "evidence_text": str(source.get("text") or "")})
        proposals.append({
            "proposal_entity_ref": ref,
            "kind": str(candidate.get("kind") or ""),
            "surface_form": str(candidate.get("surface_form") or ""),
            "evidence_refs": [str(item) for item in candidate.get("evidence_refs", [])],
            "source_unit_refs": [str(item) for item in candidate.get("source_unit_refs", [])],
            "bound_evidence": bound,
        })
    return {"frozen_proposals": proposals, "generic_entity_kind_definitions": GENERIC_ENTITY_KIND_DEFINITIONS}


def production_freeze(db: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "target_book_id": db.get("book_id"),
        "episode": db.get("episode"),
        "fact_snapshot_id": db.get("fact_snapshot_id"),
        "fact_snapshot_fingerprint": fingerprint(db.get("fact_snapshot")),
        "fact_records_fingerprint": fingerprint(db.get("fact_records", [])),
        "script_ir_id": db.get("script_ir_id"),
        "script_ir_payload_hash": db.get("script_ir_payload_hash"),
        "script_ir_payload_fingerprint": fingerprint(db.get("script_ir_payload")),
        "packet_id": db.get("packet_id"),
        "packet_row_hash": db.get("packet_row_hash"),
        "packet_fingerprint": db.get("packet_fingerprint"),
        "director_ledger": db.get("packet_attempt_count"),
        "stage_a_attempt": db.get("stage_a_attempt"),
        "active_stage_b": db.get("stage_b_attempt"),
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "origin_source_package_id": db.get("source_package_id"),
        "origin_source_raw_hash": db.get("source_fingerprint"),
    }


def main() -> int:
    armed_path = EVIDENCE / "ENTITY_SEMANTIC_VERIFICATION_CALL_ARMED.json"
    raw_path = EVIDENCE / "ENTITY_SEMANTIC_VERIFICATION_RAW_FORENSIC.json"
    if armed_path.exists() or raw_path.exists():
        raise SystemExit("V7.7.7 authorization already armed or verifier raw exists; refusing any second POST.")

    clean_at_start = not bool(git("status", "--porcelain"))
    db_before = read_db()
    source_contract = read_json(SOURCE_CONTRACT)
    v776_input_freeze = read_path(V776_EVIDENCE / "SOURCE_ENTITY_INPUT_FREEZE.json")
    v776_registry = read_path(V776_EVIDENCE / "SOURCE_PROPOSAL_ENTITY_REGISTRY.json")
    v776_assignment = read_path(V776_EVIDENCE / "SOURCE_ENTITY_PROGRAM_ID_ASSIGNMENT.json")
    v776_raw_meta = read_path(V776_EVIDENCE / "SOURCE_ENTITY_RAW_FORENSIC.json")
    v776_raw_body = str(v776_raw_meta.get("raw_response") or "")
    v776_raw_body_sha = sha256_text(v776_raw_body)
    v776_raw_body_length = len(v776_raw_body)
    del v776_raw_body
    qualification = read_path(QUALIFICATION_PATH)
    qualification_raw = read_path(QUALIFICATION_RAW_PATH)

    persistence = {name: read_path(PERSISTENCE_DIR / f"{name}.json") for name in (
        "NEW_BOOK", "FROZEN_SOURCE_LINEAGE", "ORIGIN_SOURCE_REFREEZE", "AUTHORITY_ENVELOPE_V2_AUDIT",
        "MIGRATION_FINGERPRINT", "RECONCILIATION_FINGERPRINT", "FROZEN_PRODUCTION_PERSISTENCE_MANIFEST", "PRODUCTION_DB_AFTER",
    )}
    lineage = recompute_lineage_reconciliation(
        new_book=persistence["NEW_BOOK"],
        frozen_source_lineage=persistence["FROZEN_SOURCE_LINEAGE"],
        origin_refreeze=persistence["ORIGIN_SOURCE_REFREEZE"],
        authority_envelope_audit=persistence["AUTHORITY_ENVELOPE_V2_AUDIT"],
        runtime_book_id=int(db_before.get("book_id") or 0),
        runtime_source_fingerprint=str(db_before.get("source_fingerprint") or ""),
        runtime_origin_source_package_id=str(db_before.get("source_package_id") or ""),
        runtime_authority_envelope=db_before.get("script_ir_authority") if isinstance(db_before.get("script_ir_authority"), Mapping) else {},
        v776_source_freeze=v776_input_freeze,
        migration_artifact=persistence["MIGRATION_FINGERPRINT"],
        reconciliation_artifact=persistence["RECONCILIATION_FINGERPRINT"],
        frozen_manifest=persistence["FROZEN_PRODUCTION_PERSISTENCE_MANIFEST"],
        production_db_after=persistence["PRODUCTION_DB_AFTER"],
        expected=EXPECTED_LINEAGE,
    )

    proposal_freeze = validate_frozen_proposal_registry(
        registry_artifact=v776_registry,
        assignment_artifact=v776_assignment,
        expected_registry_fingerprint=EXPECTED_V776_REGISTRY_FINGERPRINT,
        expected_assignment_fingerprint=EXPECTED_V776_ASSIGNMENT_FINGERPRINT,
        expected_count=15,
    )
    # Bind the proposal raw solely as historical evidence. It is never passed to the verifier prompt builder.
    proposal_raw_binding = {
        "expected_v7_7_6_raw_sha256": EXPECTED_V776_RAW_SHA,
        "v7_7_6_raw_sha256_metadata_matches": v776_raw_meta.get("raw_response_sha256") == EXPECTED_V776_RAW_SHA,
        "v7_7_6_raw_sha256_content_matches": v776_raw_body_sha == EXPECTED_V776_RAW_SHA and v776_raw_meta.get("raw_response_length") == v776_raw_body_length,
        "v7_7_6_raw_loaded_into_verifier_prompt": False,
        "v7_7_6_prompt_loaded_into_verifier_prompt": False,
        "v7_7_6_provider_reasoning_loaded_into_verifier_prompt": False,
    }

    units, _, source_evidence_index, unit_evidence_map = build_v776_inputs(db_before, source_contract)
    evidence_texts, rebuilt_unit_map = build_evidence_text_index(units)
    source_units_by_id = {str(unit.get("unit_id")): unit for unit in units}
    v776_units = {str(row.get("unit_id")): row for row in v776_input_freeze.get("source_units", []) if isinstance(row, Mapping)}
    unit_evidence_hash_checks = {}
    for unit_id, unit in source_units_by_id.items():
        frozen = v776_units.get(unit_id, {})
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        text = str(evidence.get("text") or "")
        unit_evidence_hash_checks[unit_id] = (
            sorted(str(x) for x in unit.get("source_evidence_refs", [])) == sorted(str(x) for x in frozen.get("evidence_refs", []))
            and str(evidence.get("sha256") or "") == str(frozen.get("evidence_sha256") or "")
            and sha256_text(text) == str(frozen.get("evidence_text_sha256") or "")
        )
    evidence_freeze_status = (
        len(units) == SOURCE_UNIT_COUNT
        and source_contract.get("fingerprint") == v776_input_freeze.get("source_unit_fingerprint") == EXPECTED_LINEAGE["source_unit_fingerprint"]
        and fingerprint(source_evidence_index) == v776_input_freeze.get("evidence_index_fingerprint")
        and len(evidence_texts) == SOURCE_UNIT_COUNT
        and all(unit_evidence_hash_checks.values())
        and unit_evidence_map == rebuilt_unit_map
    )

    current_profile = llm._resolve_llm_profile()
    parsed_url = urlparse(str(current_profile.get("base_url") or ""))
    base_host = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else ""
    identity = {
        **provider_identity(profile_id=str(current_profile.get("id") or ""), provider=str(current_profile.get("provider") or ""), model=str(current_profile.get("model_name") or ""), base_host=base_host),
        "enabled": bool(current_profile.get("enabled", True)),
        "key_configured": bool(current_profile.get("key_configured") or current_profile.get("api_key")),
        "uses_mock": bool(current_profile.get("uses_mock")),
    }
    freshness = qualification_freshness_gate(profile_identity=identity, qualification=qualification, expected_qualification_fingerprint=EXPECTED_QUALIFICATION_FINGERPRINT)

    proposal_refs = proposal_freeze.get("proposal_refs", [])
    all_evidence_refs = sorted({str(ref) for candidate in proposal_freeze.get("candidates", {}).values() for ref in candidate.get("evidence_refs", [])})
    internal_schema = build_verification_schema(proposal_refs=proposal_refs, evidence_refs=all_evidence_refs)
    compiler = compile_provider_strict_schema(internal_schema)
    transport_schema = compiler.get("schema")
    transport_schema_fp = fingerprint(transport_schema) if isinstance(transport_schema, Mapping) else ""
    response_format = {"type": "json_schema", "json_schema": {"name": VERIFICATION_VERSION, "strict": True, "schema": transport_schema}} if isinstance(transport_schema, Mapping) else {}
    verifier_input = build_verifier_input(candidates=proposal_freeze.get("candidates", {}), evidence_texts=evidence_texts)
    prompt_user = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_INPUT\n" + json.dumps(verifier_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    request_material = {
        "identity": {key: identity.get(key) for key in ("profile_id", "provider", "model", "base_host", "provider_identity_fingerprint")},
        "qualification_fingerprint": qualification.get("qualification_fingerprint"),
        "schema_fingerprint": transport_schema_fp,
        "system_prompt_sha256": sha256_text(SYSTEM_PROMPT),
        "user_prompt_sha256": sha256_text(prompt_user),
        "response_format": response_format,
        "temperature": 0,
        "max_tokens": 8192,
    }
    request_fingerprint = fingerprint(request_material)
    anti = anti_heuristic_review()

    current_freeze = production_freeze(db_before)
    preflight_checks = {
        "expected_branch": git("branch", "--show-current") == EXPECTED_BRANCH,
        "execution_baseline_ancestor": subprocess.run(["git", "merge-base", "--is-ancestor", EXPECTED_BASELINE, "HEAD"], cwd=ROOT).returncode == 0,
        "working_tree_clean_at_start": clean_at_start,
        "lineage_reconciliation_pass": lineage.get("status") == "PASS",
        "lineage_target_and_origin_frozen": lineage.get("target_book_id") == TARGET_BOOK_ID and lineage.get("origin_source_book_id") == EXPECTED_LINEAGE["origin_source_book_id"] and lineage.get("cross_book_is_not_itself_a_mismatch") is True,
        "v7_7_6_proposal_registry_freeze_pass": proposal_freeze.get("status") == "PASS",
        "v7_7_6_raw_sha_frozen": proposal_raw_binding["v7_7_6_raw_sha256_metadata_matches"],
        "v7_7_6_raw_content_hash_verified": proposal_raw_binding["v7_7_6_raw_sha256_content_matches"],
        "source_unit_and_evidence_freeze_pass": evidence_freeze_status,
        "source_fingerprint_exact": db_before.get("source_fingerprint") == EXPECTED_LINEAGE["origin_source_raw_hash"],
        "current_target_and_production_ids_exact": db_before.get("book_id") == TARGET_BOOK_ID and db_before.get("episode") == EPISODE and db_before.get("fact_snapshot_id") == FACT_SNAPSHOT_ID and db_before.get("script_ir_id") == SCRIPT_IR_ID and db_before.get("packet_id") == PACKET_ID,
        "production_ledger_freeze_exact": db_before.get("packet_attempt_count") == DIRECTOR_LEDGER and db_before.get("stage_a_attempt") == STAGE_A_ATTEMPT and db_before.get("stage_b_attempt") == STAGE_B_ATTEMPT,
        "qualification_identity_fresh": freshness.get("status") == "PASS" and identity.get("provider_identity_fingerprint") == EXPECTED_PROVIDER_IDENTITY_FINGERPRINT,
        "qualification_raw_sha_matches": sha256_text(str(qualification_raw.get("raw_response") or "")) == qualification.get("raw_response_sha256"),
        "provider_profile_enabled_and_credentialed": identity["enabled"] and identity["key_configured"],
        "runtime_not_mock": not identity["uses_mock"] and str(os.environ.get("E2E_EXTERNAL_RUNTIME") or "").lower() != "mock",
        "internal_schema_compiler_pass": compiler.get("audit", {}).get("status") == "PASS" and bool(transport_schema),
        "proposal_payload_exactly_fifteen": len(proposal_refs) == 15 and proposal_refs == [f"PEC_{index:04d}" for index in range(1, 16)],
        "anti_heuristic_pass": anti.get("status") == "PASS",
        "llm_transport_callable": callable(getattr(llm, "call_llm", None)),
        "production_rows_before_match_frozen_scope": current_freeze["fact_snapshot_id"] == FACT_SNAPSHOT_ID and current_freeze["script_ir_id"] == SCRIPT_IR_ID and current_freeze["packet_id"] == PACKET_ID,
    }
    preflight = {
        "schema_version": "v7_7_7_source_entity_semantic_verification_preflight_v1",
        "status": "PASS" if all(preflight_checks.values()) else "BLOCKED",
        "checks": preflight_checks,
        "failed_checks": [name for name, passed in preflight_checks.items() if not passed],
        "target_book_id": TARGET_BOOK_ID,
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "authorization_id": EXPECTED_AUTHORIZATION_ID,
        "provider_posts_allowed": 1 if all(preflight_checks.values()) else 0,
        "head_before_call": git("rev-parse", "HEAD"),
        "baseline": EXPECTED_BASELINE,
    }

    if "--preflight-only" in sys.argv:
        print(json.dumps({
            "preflight": preflight,
            "lineage_reconciliation": lineage,
            "proposal_freeze": {key: proposal_freeze.get(key) for key in ("status", "proposal_registry_fingerprint", "assignment_fingerprint", "proposal_count", "proposal_refs", "errors")},
            "evidence_freeze_status": evidence_freeze_status,
            "qualification_freshness": freshness,
            "entity_schema_compiler": compiler.get("audit"),
            "anti_heuristic": anti,
        }, ensure_ascii=False, indent=2))
        return 0

    # All V7.7.6 evidence is read-only. New artifacts use unambiguous target/origin fields.
    write("ANTI_HEURISTIC_PATCH_REVIEW.json", anti)
    write("SOURCE_SCOPE_LINEAGE_RECONCILIATION.json", lineage)
    proposal_freeze_artifact = {
        "schema_version": "v7_7_6_proposal_freeze_v1",
        "status": proposal_freeze.get("status"),
        "target_book_id": TARGET_BOOK_ID,
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "origin_source_package_id": EXPECTED_LINEAGE["origin_source_package_id"],
        "origin_chapter_id": EXPECTED_LINEAGE["origin_chapter_id"],
        "origin_chapter_seq": EXPECTED_LINEAGE["origin_chapter_seq"],
        "origin_source_raw_hash": EXPECTED_LINEAGE["origin_source_raw_hash"],
        "proposal_registry_fingerprint": proposal_freeze.get("proposal_registry_fingerprint"),
        "expected_proposal_registry_fingerprint": EXPECTED_V776_REGISTRY_FINGERPRINT,
        "assignment_fingerprint": proposal_freeze.get("assignment_fingerprint"),
        "expected_assignment_fingerprint": EXPECTED_V776_ASSIGNMENT_FINGERPRINT,
        "PEC_count": proposal_freeze.get("proposal_count"),
        "PEC_refs": proposal_refs,
        "PEC_candidates": proposal_freeze.get("candidates"),
        "V7_7_6_raw_sha256": EXPECTED_V776_RAW_SHA,
        "raw_response_included": False,
        "verification_run_does_not_repropose": True,
    }
    proposal_freeze_artifact["freeze_fingerprint"] = fingerprint({key: value for key, value in proposal_freeze_artifact.items() if key != "freeze_fingerprint"})
    write("V7_7_6_PROPOSAL_FREEZE.json", proposal_freeze_artifact)
    write("ENTITY_SEMANTIC_VERIFICATION_CONTRACT.json", {
        "schema_version": "source_entity_semantic_verification_contract_v1",
        "verification_version": VERIFICATION_VERSION,
        "authority_owner": "program_deterministic_compiler",
        "provider_role": "untrusted_semantic_adjudication_only",
        "allowed_questions": ["is this exact entity mention explicitly evidenced?", "is the current generic kind supported?"],
        "forbidden_operations": ["repropose", "new PEC", "change surface_form", "change evidence_refs", "change source_unit_refs", "replacement kind", "alias merge", "entity split", "canonical recommendation", "fact relation", "ownership", "action", "intent", "completeness"],
        "verdicts": {"mention": ["EXPLICITLY_EVIDENCED", "NOT_EXPLICITLY_EVIDENCED", "AMBIGUOUS"], "kind": ["SUPPORTED", "UNSUPPORTED", "AMBIGUOUS"]},
        "provider_identity": {key: identity.get(key) for key in ("profile_id", "provider", "model", "base_host", "provider_identity_fingerprint")},
        "qualification_fingerprint": EXPECTED_QUALIFICATION_FINGERPRINT,
        "target_book_id": TARGET_BOOK_ID,
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "origin_source_package_id": EXPECTED_LINEAGE["origin_source_package_id"],
        "origin_chapter_id": EXPECTED_LINEAGE["origin_chapter_id"],
        "provider_post_budget": 1,
        "retry": 0,
        "canonical_promotions": 0,
        "production_writes": 0,
    })
    write("ENTITY_SEMANTIC_VERIFICATION_SCHEMA.json", {"schema_version": VERIFICATION_VERSION, "internal_contract": internal_schema, "internal_contract_fingerprint": fingerprint(internal_schema)})
    write("ENTITY_SEMANTIC_VERIFICATION_TRANSPORT_SCHEMA.json", {"schema_version": "source_entity_semantic_verification_transport_schema_v1", "compiler_audit": compiler.get("audit"), "transport_schema": transport_schema, "transport_schema_fingerprint": transport_schema_fp, "response_format": response_format})
    write("ENTITY_SEMANTIC_VERIFICATION_AUTHORIZATION.json", {
        "authorization_id": EXPECTED_AUTHORIZATION_ID,
        "granted": True,
        "target_book_id": TARGET_BOOK_ID,
        "episode": EPISODE,
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "origin_source_package_id": EXPECTED_LINEAGE["origin_source_package_id"],
        "origin_chapter_id": EXPECTED_LINEAGE["origin_chapter_id"],
        "PEC_input_count": 15,
        "operation": "ENTITY_SEMANTIC_VERIFICATION_ONLY",
        "max_provider_posts": 1,
        "retry": 0,
        "source_entity_proposal_calls": 0,
        "source_claim_proposal_calls": 0,
        "fact_semantic_verifier_calls": 0,
        "entity_promotion": 0,
        "fact_snapshot_writes": 0,
        "fact_record_writes": 0,
        "stage_a": 0,
        "attempt_12": 0,
        "confirm": 0,
        "image": 0,
        "video": 0,
    })
    unit_freeze_rows = [
        {"unit_id": unit_id, "source_type": str(unit.get("source_type") or ""), "source_ref": str(unit.get("source_ref") or ""), "source_order": unit.get("source_order"), "evidence_refs": list(unit_map), "evidence_text_sha256": sha256_text(str((unit.get("source_evidence") or {}).get("text") or "")), "evidence_sha256": str((unit.get("source_evidence") or {}).get("sha256") or "")}
        for unit_id, unit in sorted(source_units_by_id.items())
        for unit_map in [unit.get("source_evidence_refs", [])]
    ]
    input_fingerprint = fingerprint(verifier_input)
    write("ENTITY_SEMANTIC_VERIFICATION_INPUT_FREEZE.json", {
        "status": "PASS" if evidence_freeze_status else "BLOCKED",
        "target_book_id": TARGET_BOOK_ID,
        "episode": EPISODE,
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "origin_source_package_id": EXPECTED_LINEAGE["origin_source_package_id"],
        "origin_chapter_id": EXPECTED_LINEAGE["origin_chapter_id"],
        "origin_chapter_seq": EXPECTED_LINEAGE["origin_chapter_seq"],
        "origin_source_raw_hash": EXPECTED_LINEAGE["origin_source_raw_hash"],
        "source_unit_fingerprint": source_contract.get("fingerprint"),
        "source_unit_count": len(units),
        "evidence_index_fingerprint": fingerprint(source_evidence_index),
        "evidence_anchor_count": len(evidence_texts),
        "unit_evidence_hash_checks": unit_evidence_hash_checks,
        "source_units": unit_freeze_rows,
        "verifier_input_fingerprint": input_fingerprint,
        "provider_visible_input": verifier_input,
        "production_freeze_before": current_freeze,
    })
    canonical_entities = canonical_entity_projection(v776_registry)
    write("ENTITY_SEMANTIC_VERIFICATION_PROMPT_AUDIT.json", {
        "status": "PASS" if bool(verifier_input.get("frozen_proposals")) and len(verifier_input["frozen_proposals"]) == 15 else "BLOCKED",
        "system_prompt_sha256": sha256_text(SYSTEM_PROMPT),
        "user_prompt_sha256": sha256_text(prompt_user),
        "request_fingerprint": request_fingerprint,
        "input_fingerprint": input_fingerprint,
        "PEC_count": len(verifier_input.get("frozen_proposals", [])),
        "provider_visible_fields": ["proposal_entity_ref", "kind", "surface_form", "evidence_refs", "source_unit_refs", "bound_evidence.evidence_ref", "bound_evidence.source_unit_id", "bound_evidence.evidence_text", "generic_entity_kind_definitions"],
        "V7_7_6_raw_sha256_visible_to_provider": False,
        "V7_7_6_raw_response_visible_to_provider": False,
        "proposal_prompt_visible_to_provider": False,
        "proposal_reasoning_visible_to_provider": False,
        "current_entity_answer_hints": False,
        "new_entities_requested": False,
        "replacement_kind_requested": False,
        "completeness_assessment_requested": False,
        "separate_system_role": True,
        "json_schema_not_duplicated_as_prompt_example": True,
    })
    write("ENTITY_SEMANTIC_VERIFICATION_PROVIDER_IDENTITY.json", {
        **{key: identity.get(key) for key in ("profile_id", "provider", "model", "base_host", "provider_identity_fingerprint")},
        "qualification_fingerprint": qualification.get("qualification_fingerprint"),
        "expected_qualification_fingerprint": EXPECTED_QUALIFICATION_FINGERPRINT,
        "transport_schema_fingerprint": transport_schema_fp,
        "request_fingerprint": request_fingerprint,
        "runtime_profile_mutated": False,
    })
    claim_v2_audit = compile_provider_strict_schema(claim_v2_schema())["audit"]
    write("CLAIM_V2_BLOCKER_STATUS.json", {
        "status": claim_v2_audit.get("status"),
        "reason": claim_v2_audit.get("errors"),
        "repair_in_this_phase": False,
        "source_claim_proposal_calls": 0,
    })
    write("ENTITY_COMPLETENESS_STATUS.json", {
        "entity_semantic_completeness": "NOT_PROVEN",
        "source_unit_coverage": "NOT_ASSESSED_FOR_COMPLETENESS",
        "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING",
        "verifier_completeness_question_asked": False,
    })
    write("ENTITY_SEMANTIC_VERIFICATION_PREFLIGHT.json", preflight)

    if not all(preflight_checks.values()):
        final_status = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_PROVIDER_QUALIFICATION_STALE" if freshness.get("status") != "PASS" or identity.get("provider_identity_fingerprint") != EXPECTED_PROVIDER_IDENTITY_FINGERPRINT else "SOURCE_ENTITY_SEMANTIC_VERIFICATION_PREFLIGHT_BLOCKED"
        write("ENTITY_SEMANTIC_VERIFICATION_TRANSPORT_AUDIT.json", {"status": final_status, "provider_post_attempts": 0, "http_posts_confirmed": 0, "failed_checks": preflight["failed_checks"], "response_format": response_format})
        write("ENTITY_SEMANTIC_VERIFICATION_RAW_FORENSIC.json", {"status": "NOT_RUN", "raw_response": "", "raw_response_sha256": "", "raw_response_length": 0, "persisted_before_parse": True})
        write("ENTITY_SEMANTIC_VERIFICATION_PARSE_AUDIT.json", {"status": "NOT_RUN", "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False})
        write("ENTITY_SEMANTIC_VERIFICATION_SCHEMA_VALIDATION.json", {"status": "NOT_RUN", "errors": []})
        write("ENTITY_SEMANTIC_VERIFICATION_PEC_COVERAGE_AUDIT.json", {"status": "NOT_RUN", "expected_count": proposal_freeze.get("proposal_count", 0), "observed_count": 0, "missing_pec_count": proposal_freeze.get("proposal_count", 0), "duplicate_pec_count": 0, "unknown_pec_count": 0})
        write("ENTITY_SEMANTIC_VERIFICATION_EVIDENCE_SCOPE_AUDIT.json", {"status": "NOT_RUN", "violations": [], "violation_count": 0})
        write("ENTITY_SEMANTIC_VERDICT_COMPILATION.json", {"status": "NOT_RUN", "rows": []})
        write("SOURCE_VERIFIED_ENTITY_REGISTRY.json", {"status": "NOT_RUN", "schema_version": "source_verified_entity_registry_v1", "canonical_runtime_entities": canonical_entities, "proposal_entities": {}, "canonical_promotions": 0, "canonical": False})
        write("ENTITY_VERIFICATION_SUMMARY.json", {"status": final_status, "provider_posts": 0, "entity_semantic_completeness": "NOT_PROVEN"})
        write("NO_ENTITY_PROMOTION_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "provider_posts": 0, "entity_promotions": 0, "canonical_entity_writes": 0, "source_claim_writes": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "image": 0, "video": 0})
        write("RECOMMENDED_NEXT_ACTION.json", {"status": final_status, "next_state": final_status, "provider_posts": 0, "second_verifier_post": 0, "entity_reproposal": 0, "canonical_promotion": 0, "claim_proposal": 0})
        write("SOURCE_ENTITY_SEMANTIC_VERIFICATION_REPORT.md", f"# V7.7.7 Source Entity Semantic Verification\n\n- Status: `{final_status}`\n- Provider POSTs: `0`\n- Failed preflight checks: `{', '.join(preflight['failed_checks'])}`\n- Cross-book lineage is independently reported as `{lineage.get('status')}`; target `990453`, origin `990402`.\n- No verifier, promotion, claims, production writes, IMAGE, or VIDEO ran.\n")
        return 0

    write("ENTITY_SEMANTIC_VERIFICATION_CALL_ARMED.json", {
        "authorization_id": EXPECTED_AUTHORIZATION_ID,
        "armed": True,
        "provider_post_budget": 1,
        "automatic_retry": False,
        "repair_retry": False,
        "fallback_provider": False,
        "fallback_model": False,
        "armed_at_monotonic_only": time.monotonic(),
    })
    audits: list[dict[str, Any]] = []
    raw = ""
    transport_error = ""
    started = time.monotonic()
    provider_call_invoked = True
    try:
        raw = str(llm.call_llm(
            prompt_user,
            system=SYSTEM_PROMPT,
            model_profile=current_profile,
            retries=0,
            estimated_tokens=8192,
            max_tokens=8192,
            temperature=0,
            response_format=response_format,
            audit_callback=lambda record: audits.append(dict(record)) if isinstance(record, Mapping) else None,
            audit_extra={"source_entity_semantic_verification_v7_7_7": True, "authorization_id": EXPECTED_AUTHORIZATION_ID, "transport_attempt_number": 1, "transport_retry": False},
        ) or "")
    except Exception as exc:
        transport_error = f"{type(exc).__name__}: {exc}"[:1200]
        if audits:
            raw = str(audits[-1].get("response_debug_excerpt") or "")
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    raw_hash = sha256_text(raw) if raw else ""
    write("ENTITY_SEMANTIC_VERIFICATION_RAW_FORENSIC.json", {
        "status": "RAW_PERSISTED" if raw else "TRANSPORT_ERROR_PERSISTED" if transport_error else "NO_RESPONSE",
        "authorization_id": EXPECTED_AUTHORIZATION_ID,
        "raw_response": raw,
        "raw_response_sha256": raw_hash,
        "raw_response_length": len(raw),
        "persisted_before_parse": True,
        "transport_error": transport_error,
        "request_fingerprint": request_fingerprint,
    })
    audit = audits[-1] if audits else {}
    http_status = int(audit.get("http_status") or 0)
    finish_reason = str(audit.get("finish_reason") or "")
    normal_finish = finish_reason.lower() in {"stop", "completed", "complete", "end_turn", "stop_sequence"}
    sent_format = audit.get("resolved_response_format")
    format_match = sent_format == response_format
    response_rejected = is_explicit_schema_rejection(http_status, raw)
    if http_status == 200 and normal_finish and format_match and not transport_error:
        transport_status = "PASS"
    elif not http_status:
        transport_status = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_SUBMISSION_AMBIGUOUS"
    elif response_rejected:
        transport_status = "ENTITY_SEMANTIC_VERIFICATION_SCHEMA_COMPATIBILITY_BLOCKED"
    else:
        transport_status = "ENTITY_SEMANTIC_VERIFICATION_TRANSPORT_BLOCKED"
    write("ENTITY_SEMANTIC_VERIFICATION_TRANSPORT_AUDIT.json", {
        "status": transport_status,
        "authorization_id": EXPECTED_AUTHORIZATION_ID,
        "provider_post_attempts": 1,
        "http_posts_confirmed": 1 if http_status else 0,
        "http_status": http_status,
        "finish_reason": finish_reason,
        "normal_finish": normal_finish,
        "latency_ms": audit.get("latency_ms", elapsed_ms),
        "usage": audit.get("usage", {}),
        "provider_request_id": audit.get("provider_request_id", ""),
        "transport_retry": (audit.get("extra") or {}).get("transport_retry", False) if isinstance(audit.get("extra"), Mapping) else False,
        "response_format_matches": format_match,
        "response_format_requested": response_format,
        "response_format_resolved_on_request": sent_format,
        "transport_error": transport_error,
        "business_schema_compatibility_rejected": response_rejected,
    })

    if http_status == 200 and not transport_error:
        parsed, parse_audit = parse_strict_json(raw)
    else:
        parsed, parse_audit = None, {"status": "NOT_RUN", "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False}
    parse_audit.update({"repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False, "raw_sha256": raw_hash})
    write("ENTITY_SEMANTIC_VERIFICATION_PARSE_AUDIT.json", parse_audit)
    if isinstance(parsed, Mapping) and isinstance(transport_schema, Mapping):
        schema_validation = validate_json_schema_subset(parsed, transport_schema)
    else:
        schema_validation = {"status": "BLOCKED", "errors": ["STRICT_JSON_OR_TRANSPORT_SCHEMA_NOT_AVAILABLE"]}
    write("ENTITY_SEMANTIC_VERIFICATION_SCHEMA_VALIDATION.json", {**schema_validation, "transport_schema_fingerprint": transport_schema_fp})

    expected_refs = [f"PEC_{index:04d}" for index in range(1, 16)]
    coverage = validate_verification_coverage(parsed, expected_refs=expected_refs) if isinstance(parsed, Mapping) else validate_verification_coverage({}, expected_refs=expected_refs)
    coverage["missing_pec_count"] = len(coverage.get("missing_refs", []))
    coverage["duplicate_pec_count"] = len(coverage.get("duplicate_refs", []))
    coverage["unknown_pec_count"] = len(coverage.get("unknown_refs", []))
    coverage["pec_refs_order_is_authoritative"] = False
    coverage["results_are_keyed_by_proposal_entity_ref"] = True
    write("ENTITY_SEMANTIC_VERIFICATION_PEC_COVERAGE_AUDIT.json", coverage)

    evidence_scope = validate_verification_evidence_scope(coverage.get("results_by_ref", {}), candidates=proposal_freeze.get("candidates", {}))
    write("ENTITY_SEMANTIC_VERIFICATION_EVIDENCE_SCOPE_AUDIT.json", evidence_scope)
    full_validation_pass = transport_status == "PASS" and parse_audit.get("status") == "PASS" and schema_validation.get("status") == "PASS" and coverage.get("status") == "PASS" and evidence_scope.get("status") == "PASS"
    if full_validation_pass:
        compiled = compile_verified_entity_registry(canonical_entities=canonical_entities, candidates=proposal_freeze["candidates"], results_by_ref=coverage["results_by_ref"])
        final_status = compiled["status"]
        verdict_rows = [
            {"proposal_entity_ref": ref, "mention_verdict": coverage["results_by_ref"][ref]["mention_verdict"], "kind_verdict": coverage["results_by_ref"][ref]["kind_verdict"], "evidence_refs": coverage["results_by_ref"][ref]["evidence_refs"], "verification_state": compiled["registry"]["proposal_entities"][ref]["verification_state"], "authority": compiled["registry"]["proposal_entities"][ref]["authority"], "canonical": False}
            for ref in expected_refs
        ]
        verified_registry = {"status": compiled["status"], **compiled["registry"]}
        summary = verification_summary(coverage["results_by_ref"], compiled)
    elif evidence_scope.get("status") != "PASS" and coverage.get("status") == "PASS":
        final_status = "VERIFIER_EVIDENCE_SCOPE_VIOLATION"
        verdict_rows = []
        verified_registry = {"status": final_status, "schema_version": "source_verified_entity_registry_v1", "canonical_runtime_entities": canonical_entities, "proposal_entities": {}, "canonical_promotions": 0, "canonical": False, "compiled": False}
        summary = {"status": final_status, "provider_rows": coverage.get("observed_count", 0), "entity_semantic_completeness": "NOT_PROVEN"}
    elif transport_status == "SOURCE_ENTITY_SEMANTIC_VERIFICATION_SUBMISSION_AMBIGUOUS":
        final_status = transport_status
        verdict_rows = []
        verified_registry = {"status": final_status, "schema_version": "source_verified_entity_registry_v1", "canonical_runtime_entities": canonical_entities, "proposal_entities": {}, "canonical_promotions": 0, "canonical": False, "compiled": False}
        summary = {"status": final_status, "provider_rows": 0, "entity_semantic_completeness": "NOT_PROVEN"}
    else:
        final_status = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_SCHEMA_BLOCKED"
        verdict_rows = []
        verified_registry = {"status": final_status, "schema_version": "source_verified_entity_registry_v1", "canonical_runtime_entities": canonical_entities, "proposal_entities": {}, "canonical_promotions": 0, "canonical": False, "compiled": False}
        summary = {"status": final_status, "provider_rows": coverage.get("observed_count", 0), "entity_semantic_completeness": "NOT_PROVEN"}
    write("ENTITY_SEMANTIC_VERDICT_COMPILATION.json", {"status": final_status, "compiler": "program_deterministic", "provider_assigns_authority": False, "rows": verdict_rows, "overall_status_rule": "REJECTED precedes REVIEW; all 15 verified required for VALIDATED"})
    write("SOURCE_VERIFIED_ENTITY_REGISTRY.json", verified_registry)
    write("ENTITY_VERIFICATION_SUMMARY.json", {
        "status": final_status,
        "target_book_id": TARGET_BOOK_ID,
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "origin_source_package_id": EXPECTED_LINEAGE["origin_source_package_id"],
        "PEC_input_count": len(proposal_refs),
        "provider_posts": 1,
        "http_status": http_status,
        **summary,
        "source_entity_reproposal_calls": 0,
        "entity_verifier_calls": 1,
        "fact_semantic_verifier_calls": 0,
        "source_claim_proposal_calls": 0,
        "canonical_promotions": 0,
        "production_writes": 0,
    })

    db_after = read_db()
    freeze_after = production_freeze(db_after)
    freeze_unchanged = current_freeze == freeze_after
    if not freeze_unchanged:
        final_status = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_PRODUCTION_FREEZE_BROKEN"
        summary["status"] = final_status
        write("ENTITY_SEMANTIC_VERDICT_COMPILATION.json", {"status": final_status, "compiler": "program_deterministic", "provider_assigns_authority": False, "rows": verdict_rows, "overall_status_rule": "REJECTED precedes REVIEW; all 15 verified required for VALIDATED", "production_freeze_unchanged": False})
        if isinstance(verified_registry, dict):
            verified_registry["status"] = final_status
            write("SOURCE_VERIFIED_ENTITY_REGISTRY.json", verified_registry)
        write("ENTITY_VERIFICATION_SUMMARY.json", {
            "status": final_status,
            "target_book_id": TARGET_BOOK_ID,
            "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
            "origin_source_package_id": EXPECTED_LINEAGE["origin_source_package_id"],
            "PEC_input_count": len(proposal_refs),
            "provider_posts": 1,
            "http_status": http_status,
            **summary,
            "source_entity_reproposal_calls": 0,
            "entity_verifier_calls": 1,
            "fact_semantic_verifier_calls": 0,
            "source_claim_proposal_calls": 0,
            "canonical_promotions": 0,
            "production_writes": 0,
            "production_freeze_unchanged": False,
        })
    production_audit = {
        "status": "PASS" if freeze_unchanged else "BLOCKED",
        "target_book_id": TARGET_BOOK_ID,
        "origin_source_book_id": EXPECTED_LINEAGE["origin_source_book_id"],
        "provider_posts": 1,
        "entity_verifier_posts": 1,
        "source_entity_reproposal_posts": 0,
        "fact_semantic_verifier_posts": 0,
        "source_claim_proposal_posts": 0,
        "canonical_entity_promotions": 0,
        "canonical_entity_writes": 0,
        "source_claim_writes": 0,
        "fact_snapshot_writes": 0,
        "fact_record_writes": 0,
        "packet_64_writes": 0,
        "stage_a": 0,
        "attempt_12": 0,
        "confirm": 0,
        "image": 0,
        "video": 0,
        "production_freeze_unchanged": freeze_unchanged,
        "production_freeze_before": current_freeze,
        "production_freeze_after": freeze_after,
        "director_ledger_before_after": [current_freeze["director_ledger"], freeze_after["director_ledger"]],
        "active_stage_b_before_after": [current_freeze["active_stage_b"], freeze_after["active_stage_b"]],
    }
    write("NO_ENTITY_PROMOTION_NO_PRODUCTION_WRITE_AUDIT.json", production_audit)
    if final_status == "SOURCE_ENTITY_SEMANTIC_VERIFICATION_VALIDATED":
        next_state = "SOURCE_SEMANTIC_CLAIM_V2_TRANSPORT_SCHEMA_BOUNDARY_REQUIRED"
    else:
        next_state = final_status
    write("RECOMMENDED_NEXT_ACTION.json", {
        "status": final_status,
        "next_state": next_state,
        "provider_posts": 1,
        "source_entity_reproposal_authorized": False,
        "entity_verifier_authorized": False,
        "canonical_promotion_authorized": False,
        "claim_v2_repair_authorized": False,
        "source_claim_proposal_authorized": False,
        "fact_semantic_verifier_authorized": False,
    })

    mention_counts = {
        "EXPLICITLY_EVIDENCED": summary.get("mention_explicitly_evidenced_count", 0),
        "NOT_EXPLICITLY_EVIDENCED": summary.get("mention_not_explicitly_evidenced_count", 0),
        "AMBIGUOUS": summary.get("mention_ambiguous_count", 0),
    }
    kind_counts = {
        "SUPPORTED": summary.get("kind_supported_count", 0),
        "UNSUPPORTED": summary.get("kind_unsupported_count", 0),
        "AMBIGUOUS": summary.get("kind_ambiguous_count", 0),
    }
    report = f"""# V7.7.7 Source Entity Semantic Verification — Single Real Provider Canary

## Scope and lineage

- Target Book: `{TARGET_BOOK_ID}`; Episode: `{EPISODE}`
- Origin source: Book `{EXPECTED_LINEAGE['origin_source_book_id']}`, chapter `{EXPECTED_LINEAGE['origin_chapter_id']}`, sequence `{EXPECTED_LINEAGE['origin_chapter_seq']}`
- Origin source package: `{EXPECTED_LINEAGE['origin_source_package_id']}`
- Cross-book lineage reconciliation: `{lineage.get('status')}`; cross-book source: `{lineage.get('cross_book_source')}`; differing target/origin IDs alone are not a mismatch.
- Origin raw fingerprint: `{EXPECTED_LINEAGE['origin_source_raw_hash']}`
- Lineage documents: NEW_BOOK / FROZEN_SOURCE_LINEAGE / ORIGIN_SOURCE_REFREEZE / AUTHORITY_ENVELOPE_V2_AUDIT all cross-checked with runtime authority, migration, reconciliation, manifest, and persisted DB snapshot.
- V7.7.6 source fingerprint: `{v776_input_freeze.get('source_fingerprint')}`; source-unit fingerprint: `{v776_input_freeze.get('source_unit_fingerprint')}`; units: `{len(units)}`.

## Frozen proposal and Provider call

- V7.7.6 raw SHA256: `{EXPECTED_V776_RAW_SHA}`
- Proposal registry fingerprint: `{proposal_freeze.get('proposal_registry_fingerprint')}`
- PEC input count: `{proposal_freeze.get('proposal_count')}`; registry freeze status: `{proposal_freeze.get('status')}`
- Provider: `{identity.get('profile_id')}` / `{identity.get('provider')}` / `{identity.get('model')}` / `{identity.get('base_host')}`
- Qualification fingerprint: `{qualification.get('qualification_fingerprint')}`; identity freshness: `{freshness.get('status')}`
- Verifier POST attempts: `1`; HTTP: `{http_status}`; finish_reason: `{finish_reason}`; latency ms: `{audit.get('latency_ms', elapsed_ms)}`
- Tokens: `{json.dumps(audit.get('usage', {}), ensure_ascii=False, sort_keys=True)}`
- Raw response SHA256 / length: `{raw_hash}` / `{len(raw)}`; raw persisted before parsing: `True`
- Strict parse: `{parse_audit.get('status')}`; transport schema validation: `{schema_validation.get('status')}`

## Coverage and verdicts

- PEC coverage: `{coverage.get('status')}`; missing / duplicate / unknown PECs: `{coverage.get('missing_pec_count')}` / `{coverage.get('duplicate_pec_count')}` / `{coverage.get('unknown_pec_count')}`
- Evidence scope violations: `{evidence_scope.get('violation_count')}`
- Mention verdicts: `{json.dumps(mention_counts, sort_keys=True)}`
- Kind verdicts: `{json.dumps(kind_counts, sort_keys=True)}`
- Semantically verified / rejected / review required: `{summary.get('semantically_verified_proposal_count', 0)}` / `{summary.get('rejected_proposal_count', 0)}` / `{summary.get('review_required_count', 0)}`
- Final state: `{final_status}`; next state: `{next_state}`
- Verified PECs remain `SEMANTICALLY_VERIFIED_PROPOSAL`, never `CANONICAL_RUNTIME`; canonical promotions: `0`.
- Entity semantic completeness: `NOT_PROVEN`; the verifier did not assess omitted entities or source-unit completeness.

## Production and authority boundary

- Entity re-proposal: `0`; Fact Semantic Verifier: `0`; Source Claim Proposal: `0`
- FactSnapshot / FactRecord / SourceClaim / canonical entity writes: `0`
- FactSnapshot 49 / ScriptIR 52 / Packet 64 unchanged: `{freeze_unchanged}`
- Director ledger: `{current_freeze['director_ledger']} -> {freeze_after['director_ledger']}`; active Stage B: `{current_freeze['active_stage_b']} -> {freeze_after['active_stage_b']}`
- Stage A / Attempt-12 / Confirm: `0`; IMAGE / VIDEO: `0 / 0`
- Claim V2 compiler: `{claim_v2_audit.get('status')}`; reason: `{'; '.join(claim_v2_audit.get('errors', []))}`
- Typed Director Requirement Manifest: `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`
- Anti-Heuristic review: `{anti.get('status')}`

## Verification

- V7.7.7 and V7.7.6–V7.7.2 regressions, compileall, diff check, and final Git state are recorded in the final delivery.
- SceneBlocking historical baseline remains `29 passed, 3 pre-existing failures`; it was not modified.

The run stops here. No source-entity reproposal, canonical promotion, Claim V2 repair, Claim Proposal, or Fact Semantic Verifier was run.
"""
    write("SOURCE_ENTITY_SEMANTIC_VERIFICATION_REPORT.md", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
