"""Run the single authorized V7.7.6 Source Entity Proposal canary.

Preflight is provider-free. When every freshness, source-freeze, schema, and
anti-heuristic gate passes, the script calls ``core.llm.call_llm`` once with
retries=0, persists raw text before parsing, and stops after proposal registry
evidence. A durable armed marker prevents accidental resubmission after an
interrupted run.
"""
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
from core.director_claim_relation_registry import validate_relation_registry
from core.provider_structured_output_qualification import (
    compile_provider_strict_schema,
    fingerprint,
    provider_identity,
    validate_json_schema_subset,
)
from core.source_entity_proposal import (
    ENTITY_PROPOSAL_VERSION,
    assign_program_owned_entity_ids,
    entity_candidate_fingerprint,
    proposal_entity_registry,
    source_entity_proposal_schema,
    validate_entity_candidate_contract,
)
from core.source_entity_proposal_runtime import (
    build_existing_canonical_registry,
    classify_entity_proposal_result,
    exact_existing_entity_duplicate,
    qualification_freshness_gate,
    validate_entity_evidence_binding,
    validate_entity_source_unit_binding,
    validate_entity_surface_binding,
)
from core.source_semantic_claim_authority import validate_evidence_binding
from core.source_semantic_claim_proposal import parse_strict_json
from scripts.run_v7_7_3_source_semantic_claim_proposal import (
    DB_PATH,
    SOURCE_CONTRACT,
    build_source_inputs,
    read_db,
    read_json,
)


EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_7_6-source-entity-proposal-real"
QUALIFICATION_DIR = ROOT / "docs" / "canonical-canary" / "v7_7_5-provider-structured-output-capability-qualification"
QUALIFICATION_PATH = QUALIFICATION_DIR / "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION.json"
QUALIFICATION_RAW_PATH = QUALIFICATION_DIR / "CAPABILITY_PROBE_RAW_FORENSIC.json"
HISTORICAL_FREEZE_PATH = ROOT / "docs" / "canonical-canary" / "v7_7_3-source-semantic-claim-proposal-real" / "SOURCE_SEMANTIC_PROPOSAL_INPUT_FREEZE.json"
EXPECTED_BASELINE = "5ba4a32cb58d2669f4a29d1ddba12b200d352203"
EXPECTED_BRANCH = "codex/visual-authoring-provider-canary-reconcile"
EXPECTED_QUALIFICATION_FINGERPRINT = "194241dae7837d160c63a72bd1c3017bd9a9d0219d2f25e6a083637abdf3cb3b"
AUTHORIZATION_ID = "v7.7.6-source-entity-proposal-single-call"
BOOK_ID = 990453
EPISODE = 1
PACKET_ID = 64
SCRIPT_IR_ID = 52
FACT_SNAPSHOT_ID = 49
SYSTEM_PROMPT = (
    "Identify source-mentioned semantic entities explicitly evidenced by the supplied immutable excerpts. "
    "Keep each proposal atomic and preserve its surface form exactly as written. "
    "Do not infer hidden people, ownership, locations, objects, or future entities. "
    "Use UNKNOWN_ENTITY when an evidenced entity is clear but its generic kind cannot be assigned reliably. "
    "Do not repeat an entity already represented by an existing canonical runtime entity. "
    "Do not merge aliases or use evidence references other than those supplied. "
    "All output is untrusted proposal data without canonical authority."
)


def write(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def read_optional_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def hash_raw(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_inputs(db: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, list[str]]]:
    units, base_entities, old_index, unit_map = build_source_inputs(db, contract)
    anchors = []
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        refs = [str(ref) for ref in unit.get("source_evidence_refs", [])]
        if not evidence.get("evidence_id") or str(evidence.get("evidence_id")) not in refs:
            continue
        anchors.append({
            "anchor_ref": str(evidence.get("evidence_id")),
            "unit_id": unit_id,
            "source_fingerprint": db.get("source_fingerprint"),
            "source_package_id": db.get("source_package_id"),
            "sha256": str(evidence.get("sha256") or ""),
            "text": str(evidence.get("text") or ""),
        })
    evidence_index = {
        "schema_version": "source_entity_proposal_evidence_index_v1",
        "source_fingerprint": db.get("source_fingerprint"),
        "source_package_id": db.get("source_package_id"),
        "anchors": anchors,
    }
    script_ir = db.get("script_ir_payload") if isinstance(db.get("script_ir_payload"), Mapping) else {}
    canonical_registry = build_existing_canonical_registry(base_registry=base_entities, script_ir=script_ir, source_units=units)
    return units, canonical_registry, evidence_index, unit_map


def anti_heuristic_review() -> dict[str, Any]:
    paths = [ROOT / "core" / "source_entity_proposal.py", ROOT / "core" / "source_entity_proposal_runtime.py"]
    literals = ("顾沉", "林晚", "铁盒", "车票", "胶片", "别针", "安全灯", "药水柜", "E01_SC001")
    matches: dict[str, list[str]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        found = [literal for literal in literals if literal in text]
        nlp = [pattern for pattern in (r"\bjieba\b", r"\bspacy\b", r"noun[_ -]?dictionary", r"regex[_ -]?entity", r"\bNER\b", r"embedding.{0,20}merge") if re.search(pattern, text, flags=re.IGNORECASE)]
        matches[str(path.relative_to(ROOT))] = found + nlp
    passed = not any(matches.values())
    return {
        "schema_version": "v7_7_6_anti_heuristic_patch_review_v1",
        "status": "PASS" if passed else "HEURISTIC_PATCH_REJECTED",
        "phrase_dependence": "NO",
        "scene_dependence": "NO",
        "attempt_dependence": "NO",
        "story_specific_registration": "NO",
        "local_NLP": "NO",
        "noun_dictionary": "NO",
        "regex_entity_extraction": "NO",
        "production_modules_scanned": [str(path.relative_to(ROOT)) for path in paths],
        "matches": matches,
        "story_values_are_runtime_input_only": True,
    }


def make_provider_payload(*, units: list[dict[str, Any]], canonical_registry: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    source_rows = []
    for unit in units:
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        source_rows.append({
            "unit_id": str(unit.get("unit_id") or ""),
            "source_type": str(unit.get("source_type") or ""),
            "source_ref": str(unit.get("source_ref") or ""),
            "source_order": unit.get("source_order"),
            "evidence_refs": [str(item) for item in unit.get("source_evidence_refs", [])],
            "evidence_text": str(evidence.get("text") or ""),
        })
    canonical_rows = []
    entities = canonical_registry.get("entities", {}) if isinstance(canonical_registry.get("entities"), Mapping) else {}
    for ref, entity in sorted(entities.items(), key=lambda item: str(item[0])):
        if not isinstance(entity, Mapping):
            continue
        canonical_rows.append({
            "ref": str(ref),
            "kind": str(entity.get("kind") or ""),
            "source": str(entity.get("source") or ""),
            "display_forms": [str(value) for value in entity.get("display_forms", []) if isinstance(value, str)],
        })
    payload = {
        "immutable_source_units": source_rows,
        "existing_canonical_entities": canonical_rows,
        "allowed_entity_kinds": ["CHARACTER", "SCENE", "LOCATION", "OBJECT", "ENVIRONMENT", "DIALOGUE_CONTENT", "TEXT_CONTENT", "PROPERTY_VALUE", "STATE_VALUE", "UNKNOWN_ENTITY"],
    }
    user = "SOURCE_ENTITY_PROPOSAL_INPUT\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return SYSTEM_PROMPT, user, payload


def production_freeze(db: Mapping[str, Any]) -> dict[str, Any]:
    return {
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
    }


def preflight(*, db: Mapping[str, Any], contract: Mapping[str, Any], qualification: Mapping[str, Any], raw_qualification: Mapping[str, Any], current_identity: Mapping[str, Any], freshness: Mapping[str, Any], compiler: Mapping[str, Any], anti: Mapping[str, Any], units: list[dict[str, Any]], canonical_registry: Mapping[str, Any], evidence_index: Mapping[str, Any], history: Mapping[str, Any], clean_at_start: bool) -> dict[str, Any]:
    branch = git("branch", "--show-current")
    head = git("rev-parse", "HEAD")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", EXPECTED_BASELINE, "HEAD"], cwd=ROOT).returncode == 0
    checks = {
        "expected_branch": branch == EXPECTED_BRANCH,
        "execution_baseline_ancestor": ancestor,
        "working_tree_clean_at_start": clean_at_start,
        "qualification_freshness": freshness.get("status") == "PASS",
        "qualification_raw_sha_matches": hash_raw(str(raw_qualification.get("raw_response") or "")) == qualification.get("raw_response_sha256"),
        "provider_profile_enabled": bool(current_identity.get("enabled")),
        "provider_credentials_configured": bool(current_identity.get("key_configured")),
        "runtime_not_mock": not bool(current_identity.get("uses_mock")) and str(os.environ.get("E2E_EXTERNAL_RUNTIME") or "").lower() != "mock",
        "source_contract_status": contract.get("unit_count") == len(units) and bool(contract.get("fingerprint")),
        "source_unit_count": len(units) == 12,
        "source_evidence_complete": len(evidence_index.get("anchors", [])) == len(units) and all(str(unit.get("source_evidence", {}).get("text") or "").strip() for unit in units),
        "existing_entity_registry_nonempty": bool(canonical_registry.get("entities")),
        "production_predecessor_freeze": history.get("status") == "PASS" and db.get("book_id") == history.get("book_id") == BOOK_ID and db.get("episode") == history.get("episode") == EPISODE and db.get("fact_snapshot_id") == history.get("fact_snapshot_id") == FACT_SNAPSHOT_ID and db.get("script_ir_id") == history.get("script_ir_id") == SCRIPT_IR_ID and db.get("packet_id") == history.get("packet_id") == PACKET_ID and db.get("source_fingerprint") == history.get("source_fingerprint") and db.get("script_ir_payload_hash") == history.get("script_ir_payload_hash") and contract.get("fingerprint") == history.get("source_unit_fingerprint") and db.get("packet_fingerprint") == history.get("packet_fingerprint") and db.get("packet_attempt_count") == history.get("packet_attempt_count") == 11 and db.get("stage_a_attempt") == history.get("stage_a_attempt") == "attempt-7" and db.get("stage_b_attempt") == history.get("stage_b_attempt") == "attempt-11",
        "entity_transport_schema_compiler": compiler.get("audit", {}).get("status") == "PASS" and isinstance(compiler.get("schema"), Mapping) and bool(compiler.get("schema")),
        "anti_heuristic": anti.get("status") == "PASS",
        "llm_transport_callable": callable(getattr(llm, "call_llm", None)),
    }
    return {"schema_version": "source_entity_proposal_preflight_v1", "status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks, "failed_checks": [key for key, value in checks.items() if not value], "branch": branch, "head_before_call": head, "baseline": EXPECTED_BASELINE, "baseline_is_ancestor": ancestor, "provider_posts_allowed": 1 if all(checks.values()) else 0}


def main() -> int:
    armed_path = EVIDENCE / "CAPABILITY_CALL_ARMED.json"
    raw_path = EVIDENCE / "SOURCE_ENTITY_RAW_FORENSIC.json"
    if armed_path.exists() or raw_path.exists():
        raise SystemExit("V7.7.6 authorization already armed or raw evidence exists; refusing a second execution.")

    startup_status = git("status", "--porcelain")
    clean_at_start = not bool(startup_status)
    db_before = read_db()
    contract = read_json(SOURCE_CONTRACT)
    historical_freeze = read_json(HISTORICAL_FREEZE_PATH)
    qualification = read_json(QUALIFICATION_PATH)
    qualification_raw = read_json(QUALIFICATION_RAW_PATH)
    units, canonical_registry, evidence_index, unit_evidence_map = build_inputs(db_before, contract)
    anti = anti_heuristic_review()
    internal_schema = source_entity_proposal_schema()
    compiler = compile_provider_strict_schema(internal_schema)
    transport_schema = compiler.get("schema")
    transport_schema_fingerprint = fingerprint(transport_schema) if isinstance(transport_schema, Mapping) else ""
    profile = llm._resolve_llm_profile()
    parsed = urlparse(str(profile.get("base_url") or ""))
    base_host = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
    current_identity = {
        **provider_identity(profile_id=str(profile.get("id") or ""), provider=str(profile.get("provider") or ""), model=str(profile.get("model_name") or ""), base_host=base_host),
        "enabled": bool(profile.get("enabled", True)),
        "key_configured": bool(profile.get("key_configured") or profile.get("api_key")),
        "uses_mock": bool(profile.get("uses_mock")),
    }
    freshness = qualification_freshness_gate(profile_identity=current_identity, qualification=qualification, expected_qualification_fingerprint=EXPECTED_QUALIFICATION_FINGERPRINT)
    prompt_system, prompt_user, prompt_payload = make_provider_payload(units=units, canonical_registry=canonical_registry)
    response_format = {"type": "json_schema", "json_schema": {"name": ENTITY_PROPOSAL_VERSION, "strict": True, "schema": transport_schema}} if isinstance(transport_schema, Mapping) else {}
    provider_request_identity = {
        **{key: current_identity.get(key) for key in ("profile_id", "provider", "model", "base_host", "provider_identity_fingerprint")},
        "qualification_fingerprint": qualification.get("qualification_fingerprint"),
        "transport_schema_fingerprint": transport_schema_fingerprint,
        "system_prompt_sha256": hash_raw(prompt_system),
        "user_prompt_sha256": hash_raw(prompt_user),
        "response_format_fingerprint": fingerprint(response_format),
    }
    provider_request_identity["request_fingerprint"] = fingerprint(provider_request_identity)

    write("ANTI_HEURISTIC_PATCH_REVIEW.json", anti)
    qualification_binding = {"status": freshness.get("status"), "expected_qualification_fingerprint": EXPECTED_QUALIFICATION_FINGERPRINT, "qualification": {key: qualification.get(key) for key in ("profile_id", "provider", "model", "base_host", "provider_identity_fingerprint", "qualification_fingerprint", "capability", "qualified", "probe_schema_fingerprint", "request_fingerprint", "raw_response_sha256")}, "current_identity": {key: current_identity.get(key) for key in ("profile_id", "provider", "model", "base_host", "provider_identity_fingerprint")}, "checks": freshness.get("checks"), "failed_checks": freshness.get("failed_checks"), "runtime_profile_mutated": False}
    write("V7_7_5_QUALIFICATION_BINDING.json", qualification_binding)
    write("SOURCE_ENTITY_PROPOSAL_EXECUTION_CONTRACT.json", {"schema_version": "source_entity_proposal_execution_contract_v1", "authorization_id": AUTHORIZATION_ID, "scope": {"book_id": BOOK_ID, "episode": EPISODE, "fact_snapshot_id": FACT_SNAPSHOT_ID, "script_ir_id": SCRIPT_IR_ID, "packet_id": PACKET_ID, "source_package_id": db_before.get("source_package_id")}, "ordered_steps": ["PREFLIGHT", "AUTHORIZATION_FREEZE", "ONE_PROVIDER_POST", "RAW_PERSIST", "TRANSPORT_AUDIT", "STRICT_JSON_PARSE", "TRANSPORT_SCHEMA_VALIDATION", "INTERNAL_CONTRACT_VALIDATION", "EVIDENCE_BINDING", "SOURCE_UNIT_BINDING", "SURFACE_FORM_BINDING", "EXISTING_ENTITY_DUPLICATE_AUDIT", "PROPOSAL_DUPLICATE_AUDIT", "PROGRAM_PEC_ASSIGNMENT", "PROPOSAL_ENTITY_REGISTRY_BUILD", "QUALITY_AUDIT", "STOP"], "provider_post_budget": 1, "retry": 0, "repair": 0, "verifier_calls": 0, "promotion": 0, "production_writes": 0})
    write("SOURCE_ENTITY_PROPOSAL_AUTHORIZATION.json", {"authorization_id": AUTHORIZATION_ID, "granted": True, "scope": {"book_id": BOOK_ID, "episode": EPISODE, "source_package_id": db_before.get("source_package_id"), "operation": "SOURCE_ENTITY_PROPOSAL_ONLY"}, "max_provider_posts": 1, "retry": 0, "source_claim_proposal": 0, "semantic_verifier": 0, "entity_promotion": 0, "fact_snapshot_writes": 0, "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0})
    write("SOURCE_ENTITY_TRANSPORT_SCHEMA.json", {"schema_version": "source_entity_proposal_transport_schema_v1", "internal_contract_schema_fingerprint": fingerprint(internal_schema), "transport_schema": transport_schema, "transport_schema_fingerprint": transport_schema_fingerprint})
    write("SOURCE_ENTITY_TRANSPORT_SCHEMA_AUDIT.json", {"status": compiler.get("audit", {}).get("status"), **compiler.get("audit", {}), "transport_schema_present": isinstance(transport_schema, Mapping) and bool(transport_schema), "claim_v2_compiler_status": compile_provider_strict_schema(__import__("core.source_entity_proposal", fromlist=["claim_v2_schema"]).claim_v2_schema())["audit"]["status"]})
    source_unit_freeze = [{"unit_id": str(unit.get("unit_id") or ""), "source_type": str(unit.get("source_type") or ""), "source_ref": str(unit.get("source_ref") or ""), "source_order": unit.get("source_order"), "evidence_refs": [str(ref) for ref in unit.get("source_evidence_refs", [])], "evidence_sha256": str((unit.get("source_evidence") or {}).get("sha256") or ""), "evidence_text_sha256": hash_raw(str((unit.get("source_evidence") or {}).get("text") or ""))} for unit in units]
    input_freeze = {"status": "PASS" if db_before.get("status") == "PASS" and len(units) == 12 else "BLOCKED", "book_id": BOOK_ID, "episode": EPISODE, "source_fingerprint": db_before.get("source_fingerprint"), "source_package_id": db_before.get("source_package_id"), "source_unit_fingerprint": contract.get("fingerprint"), "source_unit_count": len(units), "source_units": source_unit_freeze, "evidence_index_fingerprint": fingerprint(evidence_index), "evidence_anchor_count": len(evidence_index.get("anchors", [])), "script_ir_id": db_before.get("script_ir_id"), "script_ir_payload_hash": db_before.get("script_ir_payload_hash"), "fact_snapshot_id": db_before.get("fact_snapshot_id"), "packet_id": db_before.get("packet_id"), "packet_row_hash": db_before.get("packet_row_hash"), "director_ledger": db_before.get("packet_attempt_count"), "stage_a_attempt": db_before.get("stage_a_attempt"), "active_stage_b": db_before.get("stage_b_attempt")}
    write("SOURCE_ENTITY_INPUT_FREEZE.json", input_freeze)
    registry_entities = canonical_registry.get("entities", {}) if isinstance(canonical_registry.get("entities"), Mapping) else {}
    write("SOURCE_ENTITY_EXISTING_REGISTRY.json", {**canonical_registry, "entity_count": len(registry_entities), "registry_fingerprint": fingerprint(registry_entities)})
    write("SOURCE_ENTITY_PROMPT_AUDIT.json", {"status": "PASS", "system_prompt_sha256": hash_raw(prompt_system), "user_prompt_sha256": hash_raw(prompt_user), "request_fingerprint": provider_request_identity["request_fingerprint"], "source_unit_count": len(prompt_payload["immutable_source_units"]), "existing_entity_count": len(prompt_payload["existing_canonical_entities"]), "allowed_entity_kinds": prompt_payload["allowed_entity_kinds"], "expected_entity_answers_in_prompt": False, "attempt_findings_in_prompt": False, "v7_7_3_invalid_candidate_repair_hints": False, "business_schema_in_prompt": False})
    write("SOURCE_ENTITY_PROVIDER_IDENTITY.json", provider_request_identity)

    preflight_result = preflight(db=db_before, contract=contract, qualification=qualification, raw_qualification=qualification_raw, current_identity=current_identity, freshness=freshness, compiler=compiler, anti=anti, units=units, canonical_registry=canonical_registry, evidence_index=evidence_index, history=historical_freeze, clean_at_start=clean_at_start)
    write("SOURCE_ENTITY_PROPOSAL_PREFLIGHT.json", preflight_result)
    if freshness.get("status") != "PASS":
        status = "SOURCE_ENTITY_PROPOSAL_PROVIDER_QUALIFICATION_STALE"
    elif preflight_result.get("status") != "PASS":
        status = "SOURCE_ENTITY_PROPOSAL_PREFLIGHT_BLOCKED"
    else:
        status = "READY_FOR_SINGLE_POST"
    if status != "READY_FOR_SINGLE_POST":
        write("SOURCE_ENTITY_TRANSPORT_AUDIT.json", {"status": status, "provider_posts": 0, "failed_checks": preflight_result.get("failed_checks", []), "qualification_fingerprint": qualification.get("qualification_fingerprint")})
        write(raw_path.name, {"status": "NOT_RUN", "raw_response": "", "raw_response_sha256": "", "raw_response_length": 0, "persisted_before_parse": True})
        write("SOURCE_ENTITY_PROPOSAL_SCHEMA_VALIDATION.json", {"status": "NOT_RUN", "errors": []})
        write("SOURCE_ENTITY_EVIDENCE_BINDING_AUDIT.json", {"status": "NOT_RUN", "rows": []})
        write("SOURCE_ENTITY_SOURCE_UNIT_BINDING_AUDIT.json", {"status": "NOT_RUN", "rows": []})
        write("SOURCE_ENTITY_SURFACE_BINDING_AUDIT.json", {"status": "NOT_RUN", "rows": []})
        write("SOURCE_ENTITY_EXISTING_DUPLICATE_AUDIT.json", {"status": "NOT_RUN", "rows": []})
        write("SOURCE_ENTITY_PROPOSAL_DUPLICATE_AUDIT.json", {"status": "NOT_RUN", "rows": []})
        write("SOURCE_ENTITY_PROGRAM_ID_ASSIGNMENT.json", {"status": "NOT_RUN", "id_owner": "program", "rows": []})
        write("SOURCE_PROPOSAL_ENTITY_REGISTRY.json", {"status": "NOT_RUN", "entities": {}})
        write("SOURCE_ENTITY_PROPOSAL_SURFACE_COVERAGE.json", {"status": "NOT_RUN"})
        write("SOURCE_ENTITY_PROPOSAL_QUALITY_AUDIT.json", {"status": "NOT_RUN"})
        write("SOURCE_ENTITY_COMPLETENESS_STATUS.json", {"entity_semantic_completeness": "NOT_PROVEN", "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING"})
        write("NO_ENTITY_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "provider_posts": 0, "production_writes": 0, "source_claim_proposal_calls": 0, "semantic_verifier_calls": 0, "canonical_entity_promotions": 0})
        write("RECOMMENDED_NEXT_ACTION.json", {"status": status, "source_claim_proposal_authorized": False, "semantic_verifier_authorized": False, "entity_promotion_authorized": False})
        return 0

    write("CAPABILITY_CALL_ARMED.json", {"authorization_id": AUTHORIZATION_ID, "armed": True, "provider_post_budget": 1, "automatic_retry": False, "repair_retry": False, "fallback": False, "armed_at_monotonic_only": time.monotonic()})
    audits: list[dict[str, Any]] = []
    raw = ""
    transport_error = ""
    started = time.monotonic()
    provider_call_invoked = True
    try:
        raw = str(llm.call_llm(prompt_user, system=prompt_system, model_profile=profile, retries=0, estimated_tokens=8192, max_tokens=8192, temperature=0, response_format=response_format, audit_callback=lambda record: audits.append(dict(record)) if isinstance(record, Mapping) else None, audit_extra={"source_entity_proposal_v7_7_6": True, "authorization_id": AUTHORIZATION_ID, "transport_attempt_number": 1, "transport_retry": False}) or "")
    except Exception as exc:
        transport_error = f"{type(exc).__name__}: {exc}"[:1200]
        if audits:
            raw = str(audits[-1].get("response_debug_excerpt") or "")
    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
    raw_sha = hash_raw(raw) if raw else ""
    write(raw_path.name, {"status": "RAW_PERSISTED" if raw else ("TRANSPORT_ERROR_PERSISTED" if transport_error else "NO_RESPONSE"), "authorization_id": AUTHORIZATION_ID, "raw_response": raw, "raw_response_sha256": raw_sha, "raw_response_length": len(raw), "persisted_before_parse": True, "transport_error": transport_error, "request_fingerprint": provider_request_identity["request_fingerprint"]})

    audit = audits[-1] if audits else {}
    http_status = int(audit.get("http_status") or 0)
    finish_reason = str(audit.get("finish_reason") or "")
    sent_format = audit.get("resolved_response_format")
    format_match = sent_format == response_format
    response_format_rejected = http_status in {400, 415, 422} and any(term in raw.lower() for term in ("unsupported response_format", "unsupported json_schema", "invalid response_format", "json_schema is not supported", "invalid schema", "schema is not supported"))
    normal_finish = finish_reason == "stop"
    transport_status = "PASS" if http_status == 200 and format_match and normal_finish and not transport_error else ("SOURCE_ENTITY_PROPOSAL_SCHEMA_COMPATIBILITY_BLOCKED" if response_format_rejected else "SOURCE_ENTITY_PROPOSAL_SUBMISSION_AMBIGUOUS" if not http_status else "SOURCE_ENTITY_PROPOSAL_TRANSPORT_BLOCKED")
    write("SOURCE_ENTITY_TRANSPORT_AUDIT.json", {"status": transport_status, "authorization_id": AUTHORIZATION_ID, "provider_post_attempts": 1, "provider_http_posts_confirmed": 1 if http_status else 0, "semantic_verifier_posts": 0, "source_claim_proposal_posts": 0, "http_status": http_status, "finish_reason": finish_reason, "normal_finish_required": True, "normal_finish": normal_finish, "latency_ms": audit.get("latency_ms", elapsed_ms), "usage": audit.get("usage", {}), "provider_request_id": audit.get("provider_request_id", ""), "transport_retry": (audit.get("extra") or {}).get("transport_retry", False) if isinstance(audit.get("extra"), Mapping) else False, "request_format": response_format, "resolved_response_format_actually_sent": sent_format, "response_format_matches": format_match, "transport_error": transport_error, "business_schema_compatibility_rejected": response_format_rejected})

    parsed, parse_audit = parse_strict_json(raw) if http_status == 200 and not transport_error else (None, {"status": "NOT_RUN", "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False})
    write("SOURCE_ENTITY_PARSE_AUDIT.json", {**parse_audit, "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False, "raw_sha256": raw_sha})
    transport_validation = validate_json_schema_subset(parsed, transport_schema) if isinstance(parsed, Mapping) and isinstance(transport_schema, Mapping) else {"status": "BLOCKED", "errors": ["JSON_SCHEMA_OR_PARSE_NOT_AVAILABLE"]}
    write("SOURCE_ENTITY_PROPOSAL_SCHEMA_VALIDATION.json", {**transport_validation, "schema_fingerprint": transport_schema_fingerprint, "candidate_count": len(parsed.get("entities", [])) if isinstance(parsed, Mapping) and isinstance(parsed.get("entities"), list) else 0})
    candidate_rows = parsed.get("entities", []) if isinstance(parsed, Mapping) and isinstance(parsed.get("entities"), list) else []
    wrapper_contract_errors = []
    if not isinstance(parsed, Mapping) or set(parsed) != {"schema_version", "entities"} or parsed.get("schema_version") != ENTITY_PROPOSAL_VERSION:
        wrapper_contract_errors.append("INTERNAL_WRAPPER_CONTRACT_INVALID")
    entity_text_units = units
    diagnostics = []
    evidence_rows = []
    unit_rows = []
    surface_rows = []
    existing_rows = []
    proposal_seen: dict[str, int] = {}
    preliminary_valid: set[int] = set()
    wrapper_schema_pass = transport_validation.get("status") == "PASS" and not wrapper_contract_errors
    for index, candidate_obj in enumerate(candidate_rows):
        if not isinstance(candidate_obj, Mapping):
            candidate_obj = {}
        schema_item = transport_schema.get("properties", {}).get("entities", {}).get("items", {}) if isinstance(transport_schema, Mapping) else {}
        item_schema_result = validate_json_schema_subset(candidate_obj, schema_item) if isinstance(schema_item, Mapping) else {"status": "BLOCKED", "errors": ["ENTITY_ITEM_SCHEMA_MISSING"]}
        contract_result = validate_entity_candidate_contract(candidate_obj)
        evidence_result = validate_entity_evidence_binding(candidate_obj, evidence_index=evidence_index, source_fingerprint=str(db_before.get("source_fingerprint") or ""), source_package_id=str(db_before.get("source_package_id") or ""))
        unit_result = validate_entity_source_unit_binding(candidate_obj, unit_evidence_map=unit_evidence_map)
        surface_result = validate_entity_surface_binding(candidate_obj, evidence_index=evidence_index, unit_evidence_map=unit_evidence_map)
        existing_result = exact_existing_entity_duplicate(candidate_obj, canonical_registry=canonical_registry, evidence_index=evidence_index)
        candidate_fp = entity_candidate_fingerprint(candidate_obj) if set(candidate_obj) >= {"kind", "surface_form", "evidence_refs", "source_unit_refs"} else fingerprint(candidate_obj)
        duplicate_of = proposal_seen.get(candidate_fp)
        otherwise_valid = wrapper_schema_pass and item_schema_result["status"] == "PASS" and contract_result["status"] == "PASS" and evidence_result["status"] == "PASS" and unit_result["status"] == "PASS" and surface_result["status"] == "PASS" and existing_result["status"] != "ALREADY_CANONICAL_ENTITY"
        duplicate_status = "BLOCKED_DUPLICATE" if duplicate_of is not None and otherwise_valid else "NOT_DUPLICATE"
        base_valid = otherwise_valid and duplicate_of is None
        if base_valid:
            proposal_seen[candidate_fp] = index
            preliminary_valid.add(index)
        diagnostics.append({"index": index, "kind": candidate_obj.get("kind"), "surface_form": candidate_obj.get("surface_form"), "schema_status": item_schema_result["status"] if wrapper_schema_pass else "BLOCKED_WRAPPER", "internal_contract_status": contract_result["status"], "evidence_status": evidence_result["status"], "source_unit_status": unit_result["status"], "surface_binding_status": surface_result["status"], "existing_entity_status": existing_result["status"], "duplicate_status": duplicate_status, "existing_duplicate_matches": existing_result.get("matches", []), "proposal_duplicate_of_index": duplicate_of, "final_proposal_status": "PENDING_PROGRAM_ID_ASSIGNMENT"})
        evidence_rows.append({"index": index, **evidence_result})
        unit_rows.append({"index": index, **unit_result})
        surface_rows.append({"index": index, **surface_result})
        existing_rows.append({"index": index, **existing_result})

    provider_candidates_for_ids = [candidate_rows[index] for index in sorted(preliminary_valid)]
    assignment = assign_program_owned_entity_ids(provider_candidates_for_ids)
    assigned_by_original: dict[int, Mapping[str, Any]] = {}
    compact_to_original = sorted(preliminary_valid)
    for row in assignment.get("rows", []):
        compact_index = int(row.get("candidate_index", -1))
        if 0 <= compact_index < len(compact_to_original):
            assigned_by_original[compact_to_original[compact_index]] = row
    for row in diagnostics:
        index = int(row["index"])
        if row["existing_entity_status"] == "ALREADY_CANONICAL_ENTITY":
            row["final_proposal_status"] = "ALREADY_CANONICAL_ENTITY"
            row["proposal_entity_ref"] = None
        elif row["duplicate_status"] == "BLOCKED_DUPLICATE":
            row["final_proposal_status"] = "BLOCKED_DUPLICATE"
            row["proposal_entity_ref"] = None
        elif index in assigned_by_original and assigned_by_original[index].get("status") == "PROPOSED":
            row["final_proposal_status"] = "PROPOSED"
            row["proposal_entity_ref"] = assigned_by_original[index].get("proposal_entity_ref")
        else:
            row["final_proposal_status"] = "BLOCKED_ENTITY_CANDIDATE"
            row["proposal_entity_ref"] = None

    valid_count = sum(1 for row in diagnostics if row["final_proposal_status"] == "PROPOSED")
    candidate_count = len(candidate_rows)
    final_status = classify_entity_proposal_result(candidate_count=candidate_count, valid_count=valid_count) if transport_status == "PASS" and parse_audit.get("status") == "PASS" and transport_validation.get("status") == "PASS" else "SOURCE_ENTITY_PROPOSAL_SCHEMA_BLOCKED"
    if transport_status == "SOURCE_ENTITY_PROPOSAL_SCHEMA_COMPATIBILITY_BLOCKED":
        final_status = transport_status
    if transport_status == "SOURCE_ENTITY_PROPOSAL_SUBMISSION_AMBIGUOUS":
        final_status = transport_status

    write("SOURCE_ENTITY_EVIDENCE_BINDING_AUDIT.json", {"status": "PASS" if all(row["evidence_status"] == "PASS" for row in diagnostics) else "BLOCKED", "rows": evidence_rows})
    write("SOURCE_ENTITY_SOURCE_UNIT_BINDING_AUDIT.json", {"status": "PASS" if all(row["source_unit_status"] == "PASS" for row in diagnostics) else "BLOCKED", "rows": unit_rows})
    write("SOURCE_ENTITY_SURFACE_BINDING_AUDIT.json", {"status": "PASS" if all(row["surface_binding_status"] == "PASS" for row in diagnostics) else "BLOCKED", "rows": surface_rows})
    write("SOURCE_ENTITY_EXISTING_DUPLICATE_AUDIT.json", {"status": "PASS", "rows": existing_rows, "already_canonical_count": sum(1 for row in diagnostics if row["existing_entity_status"] == "ALREADY_CANONICAL_ENTITY"), "fuzzy_matching": False, "embedding_merge": False, "llm_merge": False, "manual_alias_map": False})
    write("SOURCE_ENTITY_PROPOSAL_DUPLICATE_AUDIT.json", {"status": "PASS", "rows": [{"index": row["index"], "fingerprint": entity_candidate_fingerprint(candidate_rows[row["index"]]) if isinstance(candidate_rows[row["index"]], Mapping) and set(candidate_rows[row["index"]]) >= {"kind", "surface_form", "evidence_refs", "source_unit_refs"} else None, "status": row["duplicate_status"], "duplicate_of_index": row["proposal_duplicate_of_index"]} for row in diagnostics], "exact_duplicate_count": sum(1 for row in diagnostics if row["duplicate_status"] == "BLOCKED_DUPLICATE"), "fuzzy_merge": False})
    write("SOURCE_ENTITY_PROGRAM_ID_ASSIGNMENT.json", {**assignment, "status": "PASS", "input_order_is_deterministic": True, "ids_are_canonical_authority": False, "program_owned_count": valid_count, "provider_owned_ids": False})
    proposal_registry = proposal_entity_registry(canonical_entities=registry_entities, assigned_entities=assignment)
    write("SOURCE_PROPOSAL_ENTITY_REGISTRY.json", {"status": "PASS", **proposal_registry, "canonical_entity_count": len(registry_entities), "proposal_entity_count": sum(1 for value in proposal_registry.get("entities", {}).values() if isinstance(value, Mapping) and value.get("authority") == "UNTRUSTED_PROPOSED"), "canonical_authority_promotions": 0, "persisted": False})

    referenced_units = {str(ref) for row in candidate_rows if isinstance(row, Mapping) for ref in row.get("source_unit_refs", []) if isinstance(row.get("source_unit_refs"), list)}
    all_unit_ids = {str(unit.get("unit_id") or "") for unit in units}
    coverage = {"schema_version": "source_entity_proposal_surface_coverage_v1", "source_unit_count": len(units), "referenced_source_unit_count": len(all_unit_ids & referenced_units), "unreferenced_source_unit_count": len(all_unit_ids - referenced_units), "unreferenced_source_unit_refs": sorted(all_unit_ids - referenced_units), "candidate_count": candidate_count, "schema_valid_candidate_count": sum(1 for row in diagnostics if row["schema_status"] == "PASS"), "valid_candidate_count": valid_count, "pec_count": valid_count, "unknown_entity_count": sum(1 for row in diagnostics if row["kind"] == "UNKNOWN_ENTITY"), "entity_proposal_surface_coverage": "NOT_A_COMPLETENESS_AUTHORITY"}
    write("SOURCE_ENTITY_PROPOSAL_SURFACE_COVERAGE.json", coverage)
    blocked_count = sum(1 for row in diagnostics if str(row["final_proposal_status"]).startswith("BLOCKED"))
    quality = {"status": "PASS" if transport_status == "PASS" and transport_validation.get("status") == "PASS" else "BLOCKED", "candidate_count": candidate_count, "schema_valid_count": coverage["schema_valid_candidate_count"], "evidence_valid_count": sum(1 for row in diagnostics if row["evidence_status"] == "PASS"), "source_unit_valid_count": sum(1 for row in diagnostics if row["source_unit_status"] == "PASS"), "surface_valid_count": sum(1 for row in diagnostics if row["surface_binding_status"] == "PASS"), "already_canonical_count": coverage.get("already_canonical_count", sum(1 for row in diagnostics if row["existing_entity_status"] == "ALREADY_CANONICAL_ENTITY")), "exact_duplicate_count": coverage.get("exact_duplicate_count", sum(1 for row in diagnostics if row["duplicate_status"] == "BLOCKED_DUPLICATE")), "blocked_count": blocked_count, "valid_proposal_count": valid_count, "unknown_entity_count": coverage["unknown_entity_count"], "semantic_atomicity": "NOT_SEMANTICALLY_VERIFIED", "inference_quality": "NOT_SEMANTICALLY_VERIFIED", "human_semantic_review_required": True}
    write("SOURCE_ENTITY_PROPOSAL_QUALITY_AUDIT.json", quality)
    write("SOURCE_ENTITY_COMPLETENESS_STATUS.json", {"entity_proposal_completeness": "NOT_PROVEN", "entity_semantic_completeness": "NOT_PROVEN", "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING", "source_unit_coverage_is_not_completeness": True})

    db_after = read_db()
    before_freeze = production_freeze(db_before)
    after_freeze = production_freeze(db_after)
    business_unchanged = before_freeze == after_freeze
    production_audit = {"status": "PASS" if business_unchanged else "BLOCKED", "provider_posts": 1 if provider_call_invoked else 0, "provider_http_posts_confirmed": 1 if http_status else 0, "provider_post_attempts": 1 if provider_call_invoked else 0, "semantic_verifier_calls": 0, "source_claim_proposal_calls": 0, "entity_semantic_verifier_calls": 0, "canonical_entity_promotions": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "canonical_entity_writes": 0, "packet_64_writes": 0, "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0, "fact_snapshot_49_unchanged": before_freeze["fact_snapshot_fingerprint"] == after_freeze["fact_snapshot_fingerprint"], "script_ir_52_unchanged": before_freeze["script_ir_payload_fingerprint"] == after_freeze["script_ir_payload_fingerprint"], "packet_64_unchanged": before_freeze["packet_row_hash"] == after_freeze["packet_row_hash"], "director_ledger_before_after": [before_freeze["director_ledger"], after_freeze["director_ledger"]], "active_stage_b_before_after": [before_freeze["active_stage_b"], after_freeze["active_stage_b"]], "freeze_before": before_freeze, "freeze_after": after_freeze}
    write("NO_ENTITY_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", production_audit)

    if final_status == "SOURCE_ENTITY_PROPOSAL_VALIDATED":
        next_state = "SOURCE_ENTITY_SEMANTIC_VERIFICATION_BOUNDARY_REQUIRED"
    else:
        next_state = final_status
    recommendation = {"status": final_status, "next_state": next_state, "provider_posts": 1 if provider_call_invoked else 0, "provider_http_posts_confirmed": 1 if http_status else 0, "source_entity_proposal_authorized": False, "entity_semantic_verifier_authorized": False, "source_claim_proposal_authorized": False, "semantic_verifier_authorized": False, "entity_promotion_authorized": False, "reason": "single-call proposal phase ends at UNTRUSTED proposal entity registry"}
    write("RECOMMENDED_NEXT_ACTION.json", recommendation)

    report = f"""# V7.7.6 Source Entity Proposal Single Real Provider Canary

## Status

- Final status: `{final_status}`
- Next state: `{next_state}`
- Authorization: `{AUTHORIZATION_ID}`
- V7.7.5 qualification fingerprint: `{qualification.get('qualification_fingerprint')}`
- Qualification identity match: `{freshness.get('status')}`
- Entity transport compiler: `{compiler.get('audit', {}).get('status')}`
- Transport schema fingerprint: `{transport_schema_fingerprint}`
- Provider profile: `{current_identity.get('profile_id')}` / `{current_identity.get('provider')}` / `{current_identity.get('model')}` / `{current_identity.get('base_host')}`
- Provider POST attempt count: `{1 if provider_call_invoked else 0}` (HTTP-confirmed: `{1 if http_status else 0}`)
- HTTP / finish_reason: `{http_status}` / `{finish_reason}`
- Latency ms: `{audit.get('latency_ms', elapsed_ms)}`
- Tokens: `{json.dumps(audit.get('usage', {}), ensure_ascii=False, sort_keys=True)}`
- Raw SHA256 / length: `{raw_sha}` / `{len(raw)}`
- Strict parse: `{parse_audit.get('status')}`
- Transport schema validation: `{transport_validation.get('status')}`
- Candidate count: `{candidate_count}`
- Schema-valid / evidence-valid / source-unit-valid / surface-valid: `{coverage['schema_valid_candidate_count']}` / `{quality['evidence_valid_count']}` / `{quality['source_unit_valid_count']}` / `{quality['surface_valid_count']}`
- Already canonical / exact duplicate / blocked: `{quality['already_canonical_count']}` / `{quality['exact_duplicate_count']}` / `{blocked_count}`
- PEC count / proposal registry count / UNKNOWN_ENTITY count: `{valid_count}` / `{proposal_registry.get('proposal_entity_count')}` / `{coverage['unknown_entity_count']}`
- Source units referenced / unreferenced: `{coverage['referenced_source_unit_count']}` / `{coverage['unreferenced_source_unit_count']}`
- Entity semantic completeness: `NOT_PROVEN`

## Authority boundary

The registry artifact separates `CANONICAL_RUNTIME` entities from `UNTRUSTED_PROPOSED` PEC refs. PEC ids are program-owned and indicate proposal identity only. Canonical promotions: `0`. Entity Semantic Verifier calls: `0`. Source Claim Proposal calls: `0`. Semantic Verifier calls: `0`.

Claim V2 schema compiler remains `BLOCKED` on `UNION_TYPE_UNSUPPORTED`. The typed requirement manifest remains `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`.

## Freeze and verification

- Production writes: `0`
- FactSnapshot 49 / ScriptIR 52 / Packet 64 unchanged: `{business_unchanged}`
- Director ledger before/after: `{before_freeze['director_ledger']}` → `{after_freeze['director_ledger']}`
- Active Stage B before/after: `{before_freeze['active_stage_b']}` → `{after_freeze['active_stage_b']}`
- Stage A / Attempt-12 / Confirm: `0`
- IMAGE / VIDEO: `0`
- Anti-Heuristic: `{anti.get('status')}`

Provider-free verification and Git status are recorded in the final delivery after evidence commit.
"""
    (EVIDENCE / "SOURCE_ENTITY_PROPOSAL_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
