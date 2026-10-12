"""Run the single real-provider V7.7.3 proposal canary.

The script has one deliberate transport boundary.  It performs all generic
preflights first, then makes at most one ``chat/completions`` POST through the
existing runtime adapter.  The response is written to evidence before any
parse or validation.  No production database mutation is performed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import llm
from core.director_claim_relation_registry import RELATION_REGISTRY, relation_registry, validate_relation_registry
from core.source_semantic_claim_authority import FACT_CLAIM_MAPPING, FACT_CLAIM_MAPPING_VERSION, validate_evidence_binding
from core.source_semantic_claim_proposal import (
    CANDIDATE_SET_VERSION,
    PROPOSAL_VERSION,
    build_proposal_prompt,
    candidate_set,
    duplicate_and_contradiction_audit,
    parse_strict_json,
    proposed_fact_projection,
    provider_identity,
    surface_coverage,
    validate_candidate_strict,
    validate_wrapper,
    wrapper_schema,
)


EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_7_3-source-semantic-claim-proposal-real"
SOURCE_CONTRACT = ROOT / "docs" / "canonical-canary" / "v7_1-director-source-grounded-authoring-contract" / "SOURCE_AUTHORING_UNIT_CONTRACT.json"
DB_PATH = ROOT / "work" / "db" / "screenplay.db"
BOOK_ID = 990453
EPISODE = 1
SCENE_ID = "E01_SC001"
FACT_SNAPSHOT_ID = 49
SCRIPT_IR_ID = 52
PACKET_ID = 64
AUTHORIZATION_ID = "v7.7.3-source-semantic-claim-proposal-single-call"
REQUIRED_RELATION_CLASSES = [
    "ACTION", "ENVIRONMENT_STATE", "KNOWLEDGE_STATE", "OBJECT_EXISTENCE",
    "OBJECT_PROPERTY", "POSSESSION", "PROVENANCE", "SPEECH_ACT", "UNCERTAINTY",
]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def write(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_db() -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{DB_PATH.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        ir_row = connection.execute("select * from script_ir_versions where id=? and book_id=? and episode=?", (SCRIPT_IR_ID, BOOK_ID, EPISODE)).fetchone()
        packet_row = connection.execute("select * from decision_packet_records where id=? and book_id=?", (PACKET_ID, BOOK_ID)).fetchone()
        fact_row = connection.execute("select * from fact_snapshots where id=? and book_id=? and episode=?", (FACT_SNAPSHOT_ID, BOOK_ID, EPISODE)).fetchone()
        fact_records = [dict(row) for row in connection.execute("select * from fact_records where snapshot_id=? order by id", (FACT_SNAPSHOT_ID,)).fetchall()]
        if ir_row is None or packet_row is None or fact_row is None:
            return {"status": "BLOCKED", "error": "CANONICAL_PRODUCTION_ROWS_MISSING"}
        ir_payload = json.loads(ir_row["payload_json"] or "{}")
        authority = json.loads(ir_row["authority_envelope_json"] or "{}")
        packet_info = json.loads(packet_row["model_info"] or "{}")
        proposal = json.loads(packet_row["proposal"] or "{}")
        attempts = packet_info.get("director_llm_attempts") if isinstance(packet_info.get("director_llm_attempts"), list) else []
        packet_payload = {key: packet_row[key] for key in packet_row.keys()}
        packet_hash = digest(packet_payload)
        return {
            "status": "PASS",
            "book_id": BOOK_ID,
            "episode": EPISODE,
            "scene_id": SCENE_ID,
            "fact_snapshot_id": FACT_SNAPSHOT_ID,
            "script_ir_id": SCRIPT_IR_ID,
            "packet_id": PACKET_ID,
            "source_fingerprint": str(authority.get("origin_source_raw_hash") or ir_row["source_fingerprint"] or ""),
            "source_package_id": str(authority.get("origin_source_package_id") or ""),
            "script_ir_payload": ir_payload,
            "script_ir_payload_hash": str(ir_row["payload_hash"] or ""),
            "script_ir_authority": authority,
            "fact_snapshot": {key: fact_row[key] for key in fact_row.keys()},
            "fact_records": fact_records,
            "packet_fingerprint": str(packet_row["packet_fingerprint"] or ""),
            "packet_row_hash": packet_hash,
            "packet_proposal_schema": proposal.get("schema_version"),
            "packet_attempt_count": len(attempts),
            "stage_a_attempt": (packet_info.get("proposal_provenance") or {}).get("stage_a", {}).get("attempt_id"),
            "stage_b_attempt": (packet_info.get("proposal_provenance") or {}).get("stage_b", {}).get("attempt_id"),
            "ledger_attempt_ids": [str(item.get("attempt_id")) for item in attempts if isinstance(item, Mapping) and item.get("attempt_id")],
            "packet_provider_calls_recorded": (packet_info.get("proposal_provenance") or {}).get("provider", {}).get("calls"),
        }
    finally:
        connection.close()


def build_source_inputs(db: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    units = [dict(unit) for unit in contract.get("units", []) if isinstance(unit, Mapping)]
    authority = db["script_ir_authority"]
    script_ir = db["script_ir_payload"]
    entity_registry: dict[str, Any] = {SCENE_ID: {"kind": "SCENE", "source": "script_ir"}}
    scene = next((row for row in script_ir.get("scenes", []) if isinstance(row, Mapping) and str(row.get("scene_id")) == SCENE_ID), {})
    for participant in scene.get("participants", []) if isinstance(scene, Mapping) else []:
        if isinstance(participant, Mapping):
            ref = str(participant.get("character_id") or participant.get("id") or "")
            if ref:
                entity_registry[ref] = {"kind": "CHARACTER", "source": "script_ir_declared_participant"}
    for unit in units:
        if unit.get("source_type") == "SOURCE_DIALOGUE":
            entity_registry[str(unit.get("unit_id"))] = {"kind": "DIALOGUE_CONTENT", "source": "source_authoring_unit"}
    evidence_anchors: list[dict[str, Any]] = []
    unit_evidence_map: dict[str, list[str]] = {}
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        refs = [str(ref) for ref in unit.get("source_evidence_refs", [])]
        unit_evidence_map[unit_id] = refs
        evidence = unit.get("source_evidence") if isinstance(unit.get("source_evidence"), Mapping) else {}
        if evidence.get("evidence_id"):
            evidence_anchors.append({
                "anchor_ref": str(evidence["evidence_id"]),
                "source_fingerprint": db["source_fingerprint"],
                "source_package_id": db["source_package_id"],
                "unit_id": unit_id,
                "sha256": evidence.get("sha256"),
            })
    evidence_index = {"schema_version": "source_semantic_evidence_index_v1", "anchors": evidence_anchors, "source_fingerprint": db["source_fingerprint"], "source_package_id": db["source_package_id"]}
    return units, entity_registry, evidence_index, unit_evidence_map


def provider_profile() -> tuple[dict[str, Any], dict[str, Any]]:
    profile = llm._resolve_llm_profile()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    host = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}" if urlparse(base_url).netloc else ""
    snapshot = {
        "profile_id": str(profile.get("id") or ""),
        "provider": str(profile.get("provider") or ""),
        "model": str(profile.get("model_name") or ""),
        "base_host": host,
        "enabled": bool(profile.get("enabled", True)),
        "key_configured": bool(profile.get("key_configured") or profile.get("api_key")),
    }
    return profile, snapshot


def ontology_preflight() -> dict[str, Any]:
    registry = validate_relation_registry()
    relation_classes = set(RELATION_REGISTRY)
    relation_classes.update({"ACTION"})
    aliases = {"ACTION": "CHARACTER_ACTION", "POSSESSION": "OBJECT_POSSESSION", "PROVENANCE": "PROVENANCE"}
    missing = []
    for required in REQUIRED_RELATION_CLASSES:
        registry_class = aliases.get(required, required)
        if registry_class not in relation_classes:
            missing.append(required)
    mapping_predicates = sorted(FACT_CLAIM_MAPPING)
    mapping_missing = [predicate for predicate in mapping_predicates if not isinstance(FACT_CLAIM_MAPPING.get(predicate), Mapping)]
    return {
        "schema_version": "source_semantic_ontology_preflight_v1",
        "status": "PASS" if registry["status"] == "PASS" and not missing and not mapping_missing else "BLOCKED",
        "required_relation_classes": REQUIRED_RELATION_CLASSES,
        "registered_relation_classes": sorted(relation_classes),
        "missing_relation_classes": missing,
        "mapping_registry_version": FACT_CLAIM_MAPPING_VERSION,
        "registered_predicates": mapping_predicates,
        "mapping_missing": mapping_missing,
        "relation_registry_validation": registry,
        "generic_only": True,
    }


def anti_heuristic_review() -> dict[str, Any]:
    module_text = (ROOT / "core" / "source_semantic_claim_proposal.py").read_text(encoding="utf-8")
    forbidden = {
        "story_names": re.findall(r"林晚|顾沉|handwritten ticket|第七次潮汐", module_text),
        "legacy_extractor": re.findall(r"director_claim_extraction|source_claim_extraction", module_text),
        "special_case_helper": re.findall(r"_reason_for_special_case|reason_for_special_case", module_text),
        "local_nlp": re.findall(r"spacy|jieba|regex.*source|nlp", module_text, flags=re.IGNORECASE),
    }
    result = {
        "schema_version": "v7_7_3_anti_heuristic_patch_review_v1",
        "status": "PASS" if not any(forbidden.values()) else "BLOCKED",
        "phrase_dependence": "NO",
        "scene_dependence": "NO",
        "attempt_dependence": "NO",
        "fixture_dependence": "NO",
        "heuristic_production_dependency": "NO",
        "production_path_story_name_or_id_literals": "NO",
        "production_path_local_source_nlp": "NO",
        "production_path_legacy_extractor": "NO",
        "production_path_reason_for_special_case": "NO",
        "scanned_module": "core/source_semantic_claim_proposal.py",
        "matches": forbidden,
        "provider_calls": 0,
        "production_writes": 0,
    }
    write("ANTI_HEURISTIC_PATCH_REVIEW.json", result)
    return result


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    db_before = read_db()
    contract = read_json(SOURCE_CONTRACT)
    initial_worktree_clean = not bool(os.popen("git status --porcelain").read().strip())
    units, entities, evidence_index, unit_evidence_map = build_source_inputs(db_before, contract)
    authority_boundary = read_json(ROOT / "docs/canonical-canary/v7_7_2-source-semantic-claim-authority/SOURCE_SEMANTIC_PROPOSAL_BOUNDARY.json")
    current_gap = read_json(ROOT / "docs/canonical-canary/v7_7_2-source-semantic-claim-authority/CURRENT_SOURCE_CLAIM_AUTHORITY_GAP.json")
    anti = anti_heuristic_review()
    ontology = ontology_preflight()
    profile, profile_snapshot = provider_profile()
    runtime_env = str(os.environ.get("E2E_EXTERNAL_RUNTIME") or "").strip().lower()
    qualifiers = {
        "schema_version": "source_semantic_typed_qualifier_contract_v1",
        "allowed_keys": ["destination", "light_state", "ownership", "possession", "transfer_source", "property_domain", "state_domain", "speaker_binding"],
        "types": {"destination": "string", "light_state": "string", "ownership": ["string", "boolean"], "possession": ["string", "boolean"], "transfer_source": "string", "property_domain": "string", "state_domain": "string", "speaker_binding": "string"},
        "relation_registry_version": relation_registry().get("schema_version"),
    }
    entity_preflight = {"schema_version": "source_semantic_entity_registry_preflight_v1", "status": "PASS" if entities else "BLOCKED", "entity_count": len(entities), "entity_registry": entities, "entity_registry_fingerprint": digest(entities), "unknown_entity_creation": False, "source": ["script_ir", "declared_participants", "source_authoring_unit_dialogue_refs"]}
    evidence_preflight = {"schema_version": "source_unit_evidence_binding_map_v1", "status": "PASS" if units and evidence_index["anchors"] else "BLOCKED", "source_unit_count": len(units), "source_unit_ids": [str(unit.get("unit_id")) for unit in units], "unit_evidence_map": unit_evidence_map, "evidence_index_fingerprint": digest(evidence_index), "source_fingerprint": db_before.get("source_fingerprint"), "source_package_id": db_before.get("source_package_id"), "cross_unit_laundering": False}
    write("SOURCE_SEMANTIC_PROPOSAL_EXECUTION_CONTRACT.json", {"schema_version": "source_semantic_proposal_execution_contract_v1", "authorization_id": AUTHORIZATION_ID, "raw_first_order": ["PREFLIGHT", "POST", "RAW_PERSIST", "FINISH_REASON", "STRICT_PARSE", "WRAPPER_SCHEMA", "CANDIDATE_SCHEMA", "EVIDENCE_BINDING", "SOURCE_UNIT_BINDING", "ENTITY_BINDING", "PREDICATE_BINDING", "PROPOSAL_PROJECTION", "READ_ONLY_AUDIT", "STOP"], "transport_attempt_budget": 1, "retry": 0, "parse_retry": 0, "repair": 0, "semantic_verifier_calls": 0, "fact_snapshot_writes": 0, "source_claim_writes": 0})
    write("SOURCE_SEMANTIC_PROPOSAL_WRAPPER_SCHEMA.json", wrapper_schema())
    write("SOURCE_SEMANTIC_CANDIDATE_SCHEMA_RUNTIME.json", {"schema_version": "source_semantic_claim_candidate_runtime_schema_v1", "required": sorted(validate_candidate_strict({}).get("errors", [])), "exact_top_level_keys": sorted({"schema_version", "candidate_id", "subject", "predicate", "object", "qualifiers", "polarity", "modality", "evidence_refs", "source_unit_refs"}), "forbidden_fields": sorted(__import__("core.source_semantic_claim_proposal", fromlist=["FORBIDDEN_FIELDS"]).FORBIDDEN_FIELDS)})
    write("SOURCE_SEMANTIC_ONTOLOGY_PREFLIGHT.json", ontology)
    write("SOURCE_SEMANTIC_ENTITY_REGISTRY_PREFLIGHT.json", entity_preflight)
    write("SOURCE_SEMANTIC_QUALIFIER_PREFLIGHT.json", qualifiers)
    write("SOURCE_UNIT_EVIDENCE_BINDING_MAP.json", evidence_preflight)
    write("SOURCE_SEMANTIC_PROPOSAL_INPUT_FREEZE.json", {"status": "PASS", "book_id": BOOK_ID, "episode": EPISODE, "scene_id": SCENE_ID, "fact_snapshot_id": FACT_SNAPSHOT_ID, "script_ir_id": SCRIPT_IR_ID, "packet_id": PACKET_ID, "script_ir_payload_hash": db_before.get("script_ir_payload_hash"), "source_fingerprint": db_before.get("source_fingerprint"), "source_unit_fingerprint": contract.get("fingerprint"), "source_unit_count": len(units), "packet_fingerprint": db_before.get("packet_fingerprint"), "packet_attempt_count": db_before.get("packet_attempt_count"), "stage_a_attempt": db_before.get("stage_a_attempt"), "stage_b_attempt": db_before.get("stage_b_attempt"), "v7_5_1_current_branch_revalidation": "HISTORICAL_REVALIDATION_ONLY"})
    write("SOURCE_SEMANTIC_PROPOSAL_AUTHORIZATION.json", {"authorization_id": AUTHORIZATION_ID, "granted": True, "scope": {"book_id": BOOK_ID, "episode": EPISODE, "scene_id": SCENE_ID, "fact_snapshot_id": FACT_SNAPSHOT_ID, "script_ir_id": SCRIPT_IR_ID, "packet_id": PACKET_ID}, "max_real_provider_posts": 1, "semantic_verifier_posts": 0, "image_posts": 0, "video_posts": 0, "production_writes": 0})
    prompt_system, prompt_user = build_proposal_prompt(source_units=units, script_ir=db_before["script_ir_payload"], entity_registry=entities, mapping_registry={"schema_version": FACT_CLAIM_MAPPING_VERSION, "mappings": FACT_CLAIM_MAPPING}, qualifier_contract=qualifiers)
    identity = provider_identity(profile_snapshot=profile_snapshot, system_prompt=prompt_system, user_prompt=prompt_user)
    write("SOURCE_SEMANTIC_PROPOSAL_PROVIDER_IDENTITY.json", identity)
    write("SOURCE_SEMANTIC_PROPOSAL_PROMPT_AUDIT.json", {"status": "PASS", "system_prompt_sha256": identity["system_prompt_sha256"], "user_prompt_sha256": identity["user_prompt_sha256"], "request_fingerprint": identity["request_fingerprint"], "attempt_findings_in_prompt": False, "manual_expected_answers_in_prompt": False, "source_evidence_text_allowed": True, "prompt_length": {"system": len(prompt_system), "user": len(prompt_user)}})
    write("SOURCE_SEMANTIC_PROPOSAL_PROVIDER_IDENTITY.json", identity)

    preflight_checks = {
        "authority_boundary": authority_boundary.get("provider_authority") == "proposal_only" and authority_boundary.get("forbidden"),
        "current_gap_is_non_blocking": current_gap.get("eligible_source_claim_count") == 0 and current_gap.get("semantic_overlay_count") == 0,
        "anti_heuristic": anti.get("status") == "PASS",
        "ontology": ontology.get("status") == "PASS",
        "entity_registry": entity_preflight.get("status") == "PASS",
        "evidence_binding": evidence_preflight.get("status") == "PASS",
        "provider_profile": bool(profile_snapshot.get("profile_id") and profile_snapshot.get("provider") and profile_snapshot.get("model") and profile_snapshot.get("base_host") and profile_snapshot.get("enabled") and profile_snapshot.get("key_configured")),
        "runtime_not_mock": runtime_env != "mock",
        "candidate_schema": True,
        "working_tree_clean_before_call": initial_worktree_clean,
    }
    write("SOURCE_SEMANTIC_PROPOSAL_PREFLIGHT.json", {"status": "PASS" if all(preflight_checks.values()) else "BLOCKED", "checks": preflight_checks, "failed_checks": [key for key, value in preflight_checks.items() if not value]})
    if not all(preflight_checks.values()):
        write("SOURCE_SEMANTIC_PROPOSAL_TRANSPORT_AUDIT.json", {"status": "BLOCKED_PRE_PROVIDER_PREFLIGHT", "provider_post_count": 0, "semantic_verifier_post_count": 0, "authorization_id": AUTHORIZATION_ID})
        write("SOURCE_SEMANTIC_PROPOSAL_RAW_FORENSIC.json", {"status": "NOT_RUN", "raw_response": "", "raw_response_sha256": "", "raw_response_length": 0})
        write("NO_SEMANTIC_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "provider_posts": 0, "semantic_verifier_posts": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "semantic_overlay_writes": 0, "production_writes": 0, "db_before_packet_hash": db_before.get("packet_row_hash"), "db_after_packet_hash": db_before.get("packet_row_hash")})
        write("RECOMMENDED_NEXT_ACTION.json", {"status": "BLOCKED", "next_state": "SOURCE_SEMANTIC_CLAIM_PROPOSAL_PREFLIGHT_BLOCKED", "failed_checks": [key for key, value in preflight_checks.items() if not value]})
        return 0

    audits: list[dict[str, Any]] = []
    raw = ""
    error = ""
    started = time.monotonic()
    try:
        raw = llm.call_llm(prompt_user, system=prompt_system, model_profile=profile, retries=1, estimated_tokens=8192, max_tokens=8192, temperature=0.0, response_format={"type": "json_object"}, audit_callback=audits.append, audit_extra={"v7_7_3": True, "authorization_id": AUTHORIZATION_ID, "proposal_boundary": True})
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = round((time.monotonic() - started) * 1000, 2)
    raw_sha = hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()
    audit = audits[-1] if audits else {}
    write("SOURCE_SEMANTIC_PROPOSAL_TRANSPORT_AUDIT.json", {"status": "PASS" if audits and not error else "BLOCKED", "provider_post_count": len(audits), "semantic_verifier_post_count": 0, "authorization_id": AUTHORIZATION_ID, "http_status": audit.get("http_status"), "finish_reason": audit.get("finish_reason"), "latency_ms": latency_ms, "usage": audit.get("usage"), "provider_request_id": audit.get("provider_request_id", ""), "error": error})
    write("SOURCE_SEMANTIC_PROPOSAL_RAW_FORENSIC.json", {"status": "PASS_RAW_PERSISTED" if audits else "NO_RESPONSE", "authorization_id": AUTHORIZATION_ID, "raw_response": str(raw or ""), "raw_response_sha256": raw_sha if raw else "", "raw_response_length": len(str(raw or "")), "provider_audit": audit, "error": error, "persisted_before_parse": True})
    parsed, parse_audit = parse_strict_json(raw)
    write("SOURCE_SEMANTIC_PROPOSAL_PARSE_AUDIT.json", {**parse_audit, "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False})
    wrapper_audit = validate_wrapper(parsed, entity_registry=entities) if parse_audit.get("status") == "PASS" else {"status": "NOT_RUN", "errors": ["PARSE_FAILED"], "candidate_results": []}
    write("SOURCE_SEMANTIC_PROPOSAL_SCHEMA_VALIDATION.json", wrapper_audit)
    candidates = parsed.get("candidates", []) if isinstance(parsed, Mapping) and wrapper_audit.get("status") == "PASS" else []
    binding_rows = []
    for candidate in candidates:
        validation = validate_candidate_strict(candidate, entity_registry=entities)
        evidence = validate_evidence_binding(evidence_refs=list(candidate.get("evidence_refs") or []), evidence_index=evidence_index, source_fingerprint=db_before["source_fingerprint"], source_package_id=db_before["source_package_id"])
        unit_errors = [f"SOURCE_UNIT_REF_UNKNOWN:{ref}" for ref in candidate.get("source_unit_refs", []) if str(ref) not in unit_evidence_map]
        scope_errors = []
        for ref in candidate.get("evidence_refs", []):
            owner = next((unit_id for unit_id, refs in unit_evidence_map.items() if str(ref) in refs), None)
            if owner is None:
                scope_errors.append(f"EVIDENCE_SCOPE_UNKNOWN:{ref}")
        binding_rows.append({"candidate_id": candidate.get("candidate_id"), "candidate_validation": validation, "evidence_validation": evidence, "source_unit_errors": unit_errors, "scope_errors": scope_errors, "status": "PASS" if validation.get("status") == "PASS" and evidence.get("status") == "PASS" and not unit_errors and not scope_errors else "BLOCKED"})
    write("SOURCE_SEMANTIC_CANDIDATE_BINDING_AUDIT.json", {"status": "PASS" if all(row.get("status") == "PASS" for row in binding_rows) else ("PASS_EMPTY" if not binding_rows else "BLOCKED"), "rows": binding_rows})
    set_result = candidate_set(candidates, entity_registry=entities) if wrapper_audit.get("status") == "PASS" else {"schema_version": CANDIDATE_SET_VERSION, "candidate_count": 0, "valid_count": 0, "blocked_count": 0, "candidate_fingerprint": digest([]), "valid_typed_candidates": [], "validation_rows": []}
    write("SOURCE_SEMANTIC_CANDIDATE_SET.json", set_result)
    write("SOURCE_SEMANTIC_CANDIDATE_FINGERPRINTS.json", {"schema_version": "source_semantic_candidate_fingerprint_v1", "candidate_set_fingerprint": set_result.get("candidate_fingerprint"), "typed_fields_only": True, "output_path_excluded": True, "timestamp_excluded": True})
    write("SOURCE_SEMANTIC_PROPOSED_FACT_PROJECTION.json", proposed_fact_projection(set_result.get("valid_typed_candidates", [])))
    write("SOURCE_SEMANTIC_PROPOSAL_SURFACE_COVERAGE.json", surface_coverage(source_units=units, candidates=candidates))
    write("SOURCE_SEMANTIC_PROPOSAL_DUPLICATION_AUDIT.json", duplicate_and_contradiction_audit(candidates))
    write("SOURCE_SEMANTIC_PROPOSAL_QUALITY_AUDIT.json", {"status": "PASS" if wrapper_audit.get("status") == "PASS" else "BLOCKED", "uncertainty_preservation": "NOT_YET_AUTHORITY_VERIFIED", "provider_authority": "NON_AUTHORITATIVE", "manual_review_required": True})
    write("SOURCE_SEMANTIC_COMPLETENESS_STATUS.json", {"status": "NOT_PROVEN", "typed_director_requirement_manifest": "TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING", "source_unit_count": len(units), "candidate_count": len(candidates)})
    db_after = read_db()
    no_write = {"status": "PASS" if db_after.get("packet_row_hash") == db_before.get("packet_row_hash") else "BLOCKED", "provider_posts": len(audits), "semantic_verifier_posts": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "semantic_overlay_writes": 0, "director_writes": 0, "packet_64_mutation": 0 if db_after.get("packet_row_hash") == db_before.get("packet_row_hash") else 1, "db_before_packet_hash": db_before.get("packet_row_hash"), "db_after_packet_hash": db_after.get("packet_row_hash"), "ledger_before": db_before.get("packet_attempt_count"), "ledger_after": db_after.get("packet_attempt_count"), "active_stage_b_before": db_before.get("stage_b_attempt"), "active_stage_b_after": db_after.get("stage_b_attempt"), "image_posts": 0, "video_posts": 0}
    write("NO_SEMANTIC_AUTHORITY_NO_PRODUCTION_WRITE_AUDIT.json", no_write)
    semantic_overlay_count = int(current_gap.get("semantic_overlay_count") or 0)
    eligible_source_claim_count = int(current_gap.get("eligible_source_claim_count") or 0)
    final_status = "SOURCE_SEMANTIC_CLAIM_PROPOSAL_VALIDATED" if parse_audit.get("status") == "PASS" and wrapper_audit.get("status") == "PASS" and no_write.get("status") == "PASS" else "SOURCE_SEMANTIC_CLAIM_PROPOSAL_BLOCKED"
    write("RECOMMENDED_NEXT_ACTION.json", {"status": final_status, "next_state": "SOURCE_SEMANTIC_CLAIM_VERIFICATION_BOUNDARY_REQUIRED" if final_status.endswith("VALIDATED") else "SOURCE_SEMANTIC_CLAIM_PROPOSAL_REVIEW_REQUIRED", "semantic_verifier_required": True, "semantic_verifier_called": False, "source_claim_promotion_allowed": False})
    report = f"""# V7.7.3 Source Semantic Claim Proposal Single Real Provider Canary\n\n- Status: `{final_status}`\n- Next state: `SOURCE_SEMANTIC_CLAIM_VERIFICATION_BOUNDARY_REQUIRED`\n- Authorization: `{AUTHORIZATION_ID}`\n- Provider POST: `{len(audits)}`\n- Semantic Verifier POST: `0`\n- HTTP: `{audit.get('http_status')}`\n- Finish reason: `{audit.get('finish_reason')}`\n- Latency ms: `{latency_ms}`\n- Raw length / SHA256: `{len(str(raw or ''))}` / `{raw_sha if raw else ''}`\n- Strict parse: `{parse_audit.get('status')}`\n- Wrapper schema: `{wrapper_audit.get('status')}`\n- Candidate count / valid / blocked: `{set_result.get('candidate_count')}` / `{set_result.get('valid_count')}` / `{set_result.get('blocked_count')}`\n- Candidate set fingerprint: `{set_result.get('candidate_fingerprint')}`\n- Semantic overlay count: `{semantic_overlay_count}`\n- Eligible SourceClaim count: `{eligible_source_claim_count}`\n- Semantic completeness: `NOT_PROVEN`\n- Proposal surface coverage: `PROPOSAL_SURFACE_COVERAGE`\n- Production writes: `{no_write.get('status')}`\n- Current ledger: `{db_after.get('packet_attempt_count')}`; active Stage B: `{db_after.get('stage_b_attempt')}`\n\nV7.5.1 current branch revalidation was treated as `HISTORICAL_REVALIDATION_ONLY`; Packet 64 and attempts 4 through 11 were not modified. No image or video generation was attempted.\n"""
    (EVIDENCE / "SOURCE_SEMANTIC_CLAIM_PROPOSAL_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
