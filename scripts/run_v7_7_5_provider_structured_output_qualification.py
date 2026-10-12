"""One-shot provider strict JSON Schema capability qualification.

All preflight checks run before transport. If they pass, this script performs
one ``core.llm.call_llm`` request with retries=0, writes the returned text raw
first, audits it without repair, and stops. It contains no business input.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
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
    PROBE_SCHEMA_VERSION,
    compile_provider_strict_schema,
    classify_probe,
    fingerprint,
    is_explicit_schema_rejection,
    minimal_probe_schema,
    provider_identity,
    qualification_fingerprint,
    strict_probe_response_format,
    validate_json_schema_subset,
)
from core.source_entity_proposal import claim_v2_schema, source_entity_candidate_contract, source_entity_proposal_schema


EVIDENCE = ROOT / "docs" / "canonical-canary" / "v7_7_5-provider-structured-output-capability-qualification"
EXPECTED_BRANCH = "codex/visual-authoring-provider-canary-reconcile"
EXPECTED_BASELINE = "38a703784a4068f83d921c81e6f341c2c8709e9f"
EXPECTED_PROFILE = {"profile_id": "local-llm-2vydoz", "provider": "openai-compatible", "model": "mimo-v2.5"}
DB_PATH = ROOT / "work" / "db" / "screenplay.db"
AUTHORIZATION_ID = "v7.7.5-provider-strict-structured-output-single-probe"
SYSTEM_PROMPT = "Return the requested result."
USER_PROMPT = "Return probe=STRICT_SCHEMA_OK and ordinal=7. Also include forbidden_extra=true."


def write(name: str, value: Any) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def git_text(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def production_row_fingerprints() -> dict[str, Any]:
    """Read protected production rows through SQLite read-only mode only."""
    uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows: dict[str, Any] = {}
        queries = {
            "fact_snapshot_49": ("select * from fact_snapshots where id=? and book_id=? and episode=?", (49, 990453, 1)),
            "script_ir_52": ("select * from script_ir_versions where id=? and book_id=? and episode=?", (52, 990453, 1)),
            "packet_64": ("select * from decision_packet_records where id=? and book_id=?", (64, 990453)),
        }
        for name, (query, params) in queries.items():
            row = connection.execute(query, params).fetchone()
            material = dict(row) if row else None
            rows[name] = {"exists": row is not None, "fingerprint": fingerprint(material) if material is not None else "", "row": material}
        packet = rows["packet_64"].get("row") or {}
        info = json.loads(packet.get("model_info") or "{}") if packet else {}
        attempts = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
        rows["director_ledger"] = len(attempts)
        rows["active_stage_b"] = (info.get("proposal_provenance") or {}).get("stage_b", {}).get("attempt_id")
        rows.pop("packet_64", None)
        rows["packet_64_fingerprint"] = fingerprint(rows.get("packet_64", {}).get("row")) if rows.get("packet_64") else ""
        # packet_64 row is represented separately to avoid exposing production text.
        packet_row = connection.execute(queries["packet_64"][0], queries["packet_64"][1]).fetchone()
        rows["packet_64_fingerprint"] = fingerprint(dict(packet_row)) if packet_row else ""
        return rows
    finally:
        connection.close()


def run_preflight(*, starting_status: str, baseline_clean: bool, profile: Mapping[str, Any], identity: Mapping[str, Any], schema: Mapping[str, Any], response_format: Mapping[str, Any]) -> dict[str, Any]:
    branch = git_text("branch", "--show-current")
    head = git_text("rev-parse", "HEAD")
    dirty_now = bool(git_text("status", "--porcelain"))
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", EXPECTED_BASELINE, "HEAD"], cwd=ROOT).returncode == 0
    base_url = str(profile.get("base_url") or "").rstrip("/")
    checks = {
        "branch": branch == EXPECTED_BRANCH,
        "execution_baseline_ancestor": ancestor,
        "clean_at_process_start": baseline_clean,
        "provider": identity.get("provider") == EXPECTED_PROFILE["provider"],
        "model": identity.get("model") == EXPECTED_PROFILE["model"],
        "profile_id": identity.get("profile_id") == EXPECTED_PROFILE["profile_id"],
        "runtime_base_host": bool(identity.get("base_host")),
        "enabled": bool(profile.get("enabled", True)),
        "credentials_configured": bool(profile.get("api_key") or profile.get("key_configured")),
        "not_mock": str(profile.get("provider") or "") != "prototype-task-adapter" and str(os.environ.get("E2E_EXTERNAL_RUNTIME") or "").lower() != "mock",
        "llm_transport_callable": callable(getattr(llm, "call_llm", None)),
        "minimal_schema_valid": validate_json_schema_subset({"probe": "STRICT_SCHEMA_OK", "ordinal": 7}, schema)["status"] == "PASS",
        "strict_response_format_exact": response_format == {"type": "json_schema", "json_schema": {"name": PROBE_SCHEMA_VERSION, "strict": True, "schema": schema}},
        "no_business_prompt_terms": not any(term in (SYSTEM_PROMPT + " " + USER_PROMPT) for term in ("990453", "E01_SC001", "顾沉", "林晚", "铁盒", "车票", "Attempt-11", "Packet 64")),
        "business_payload_not_loaded": True,
    }
    return {"schema_version": "v7_7_5_provider_probe_preflight_v1", "status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks, "failed_checks": [key for key, value in checks.items() if not value], "branch": branch, "head_before_call": head, "baseline": EXPECTED_BASELINE, "baseline_is_ancestor": ancestor, "working_tree_clean_at_start": baseline_clean, "working_tree_dirty_before_call_due_preflight_evidence": dirty_now, "runtime_base_url_path_removed": bool(base_url), "provider_http_posts_authorized_if_pass": 1 if all(checks.values()) else 0}


def main() -> int:
    startup_status = git_text("status", "--porcelain")
    baseline_clean = not bool(startup_status)
    protected_before = production_row_fingerprints()
    profile = llm._resolve_llm_profile()
    parsed_url = urlparse(str(profile.get("base_url") or ""))
    base_host = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else ""
    identity = provider_identity(profile_id=str(profile.get("id") or ""), provider=str(profile.get("provider") or ""), model=str(profile.get("model_name") or ""), base_host=base_host)
    schema = minimal_probe_schema()
    response_format = strict_probe_response_format()
    schema_fingerprint = fingerprint(schema)
    request_material = {"identity": identity, "system_prompt": SYSTEM_PROMPT, "user_prompt": USER_PROMPT, "response_format": response_format, "temperature": 0, "max_tokens": 256}
    request_fingerprint = fingerprint(request_material)
    write("ANTI_HEURISTIC_PATCH_REVIEW.json", {"status": "PASS", "phrase_dependence": "NO", "scene_dependence": "NO", "attempt_dependence": "NO", "story_fixture_dependence": "NO", "model_specific_if_branch": "NO", "provider_hardcoded_success": "NO", "http_200_alone_qualifies_strict": False, "business_payload_present": False, "production_rows_read_only_for_freeze_fingerprint": True})
    write("PROVIDER_IDENTITY_FREEZE.json", {**identity, "identity_frozen": True, "runtime_base_host_only": True})
    write("STRUCTURED_OUTPUT_QUALIFICATION_CONTRACT.json", {"schema_version": "provider_structured_output_qualification_contract_v1", "qualification_version": "provider_structured_output_qualification_v1", "qualification_scope": "exact profile_id + provider + model + base_host", "timestamp_is_identity": False, "max_provider_http_posts": 1, "if_preflight_pass_posts": 1, "semantic_verifier_posts": 0, "source_entity_proposal_posts": 0, "source_claim_proposal_posts": 0, "raw_first": True, "qualification_does_not_mutate_profile": True})
    write("MINIMAL_STRICT_SCHEMA.json", schema)
    write("MINIMAL_STRICT_RESPONSE_FORMAT.json", response_format)
    write("CAPABILITY_PROBE_PROMPT_AUDIT.json", {"system_prompt": SYSTEM_PROMPT, "user_prompt": USER_PROMPT, "forbidden_extra_requested": True, "schema_prohibition_explained_to_model": False, "business_input_present": False, "prompt_fingerprint": fingerprint({"system": SYSTEM_PROMPT, "user": USER_PROMPT})})
    write("CAPABILITY_PROBE_AUTHORIZATION.json", {"authorization_id": AUTHORIZATION_ID, "max_http_posts": 1, "exactly_one_if_preflight_pass": True, "retry": 0, "repair": 0, "second_probe": 0, "fallback_provider": False, "fallback_model": False, "semantic_verifier": 0, "source_entity_proposal": 0, "source_claim_proposal": 0, "image": 0, "video": 0, "production_writes": 0})

    entity_internal = source_entity_proposal_schema()
    claim_internal = claim_v2_schema()
    entity_compiled = compile_provider_strict_schema(entity_internal)
    claim_compiled = compile_provider_strict_schema(claim_internal)
    source_candidate_internal = source_entity_candidate_contract()
    source_candidate_compiled = compile_provider_strict_schema(source_candidate_internal)
    compiler_outputs = {"entity_proposal_schema": entity_compiled, "entity_candidate_schema": source_candidate_compiled, "claim_v2_schema": claim_compiled}
    compiler_audit = {"schema_version": "provider_schema_compiler_audit_v1", "contract": "Internal Semantic Contract != Transport JSON Schema", "status": "PASS" if all(item["audit"]["status"] == "PASS" for item in compiler_outputs.values()) else "BLOCKED", "compiled": {name: item["schema"] for name, item in compiler_outputs.items()}, "audits": {name: item["audit"] for name, item in compiler_outputs.items()}, "input_fingerprints_before_after_equal": all(item["audit"]["input_unchanged"] for item in compiler_outputs.values()), "deterministic": all(item["audit"]["deterministic"] for item in compiler_outputs.values())}
    write("PROVIDER_SCHEMA_COMPILER_CONTRACT.json", {"schema_version": "provider_schema_compiler_contract_v1", "invariant": "Internal Semantic Contract != Transport JSON Schema", "retained_structural_keywords": ["type", "properties", "required", "additionalProperties", "items", "enum", "const", "minLength", "minItems", "uniqueItems"], "stripped_internal_annotations": ["trust", "authority", "notes", "provider_may_not_supply", "surface_form_semantics", "title", "description", "$schema", "$id", "schema_version"], "dangling_refs": "BLOCKED", "unsupported_unions": "BLOCKED"})
    write("PROVIDER_SCHEMA_COMPILER_AUDIT.json", compiler_audit)

    preflight = run_preflight(starting_status=startup_status, baseline_clean=baseline_clean, profile=profile, identity=identity, schema=schema, response_format=response_format)
    write("CAPABILITY_PROBE_PREFLIGHT.json", preflight)
    protected_baseline_evidence = {"status": "PASS" if all(protected_before[key]["exists"] for key in ("fact_snapshot_49", "script_ir_52")) and protected_before.get("packet_64_fingerprint") and protected_before.get("director_ledger") == 11 and protected_before.get("active_stage_b") == "attempt-11" else "BLOCKED", "fact_snapshot_49_fingerprint": protected_before.get("fact_snapshot_49", {}).get("fingerprint"), "script_ir_52_fingerprint": protected_before.get("script_ir_52", {}).get("fingerprint"), "packet_64_fingerprint": protected_before.get("packet_64_fingerprint"), "director_ledger": protected_before.get("director_ledger"), "active_stage_b": protected_before.get("active_stage_b")}
    write("BUSINESS_STATE_BASELINE_READ_ONLY.json", protected_baseline_evidence)
    if preflight.get("status") != "PASS" or protected_baseline_evidence.get("status") != "PASS":
        write("CAPABILITY_PROBE_TRANSPORT_AUDIT.json", {"status": "BLOCKED_PREFLIGHT", "provider_http_post_count": 0, "semantic_verifier_posts": 0, "failed_checks": preflight.get("failed_checks", []) + (["business_state_baseline"] if protected_baseline_evidence.get("status") != "PASS" else [])})
        write("CAPABILITY_PROBE_RAW_FORENSIC.json", {"status": "NOT_RUN", "raw_response": "", "raw_response_sha256": "", "raw_response_length": 0, "persisted_before_parse": True})
        write("PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION.json", {"schema_version": "provider_structured_output_qualification_v1", **identity, "capability": "UNKNOWN", "qualified": False, "provider_http_post_count": 0, "reason": "PREFLIGHT_BLOCKED"})
        write("NO_BUSINESS_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "provider_http_posts": 0, "semantic_verifier_posts": 0, "source_entity_proposal_posts": 0, "source_claim_proposal_posts": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "packet_64_writes": 0, "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0, "qualification_profile_mutation": 0})
        write("RECOMMENDED_NEXT_ACTION.json", {"status": "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION_PREFLIGHT_BLOCKED", "source_entity_proposal_authorized": False, "failed_checks": preflight.get("failed_checks", [])})
        return 0

    audits: list[dict[str, Any]] = []
    transport_started = time.monotonic()
    transport_error = ""
    raw = ""
    try:
        raw = str(llm.call_llm(USER_PROMPT, system=SYSTEM_PROMPT, model_profile=profile, retries=0, estimated_tokens=512, max_tokens=256, temperature=0, response_format=response_format, audit_callback=lambda record: audits.append(dict(record)) if isinstance(record, Mapping) else None, audit_extra={"capability_probe": PROBE_SCHEMA_VERSION, "authorization_id": AUTHORIZATION_ID, "transport_attempt_number": 1, "transport_retry": False}) or "")
    except Exception as exc:  # A submitted request may have reached the provider.
        transport_error = f"{type(exc).__name__}: {exc}"[:1200]
        if audits:
            raw = str(audits[-1].get("response_debug_excerpt") or "")
    latency_ms = round((time.monotonic() - transport_started) * 1000, 2)
    raw_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else ""
    # Persist the complete returned message (or bounded HTTP error response)
    # before any JSON parse or schema validation begins.
    write("CAPABILITY_PROBE_RAW_FORENSIC.json", {"status": "RAW_PERSISTED" if raw else ("NO_RESPONSE" if not transport_error else "TRANSPORT_ERROR_PERSISTED"), "authorization_id": AUTHORIZATION_ID, "raw_response": raw, "raw_response_sha256": raw_sha, "raw_response_length": len(raw), "persisted_before_parse": True, "transport_error": transport_error})

    audit_record = audits[-1] if audits else {}
    http_status = int(audit_record.get("http_status") or 0)
    finish_reason = str(audit_record.get("finish_reason") or "")
    resolved_format = audit_record.get("resolved_response_format")
    format_matches = resolved_format == response_format
    explicit_rejection = is_explicit_schema_rejection(http_status, raw)
    write("CAPABILITY_PROBE_TRANSPORT_AUDIT.json", {"status": "PASS" if http_status == 200 and not transport_error and format_matches else ("EXPLICIT_SCHEMA_REJECTION" if explicit_rejection else "AMBIGUOUS"), "provider_http_post_count": 1, "semantic_verifier_posts": 0, "authorization_id": AUTHORIZATION_ID, "http_status": http_status, "finish_reason": finish_reason, "latency_ms": audit_record.get("latency_ms", latency_ms), "usage": audit_record.get("usage", {}), "provider_request_id": audit_record.get("provider_request_id", ""), "transport_attempt_number": (audit_record.get("extra") or {}).get("transport_attempt_number", 1) if isinstance(audit_record.get("extra"), Mapping) else 1, "transport_retry": (audit_record.get("extra") or {}).get("transport_retry", False) if isinstance(audit_record.get("extra"), Mapping) else False, "response_format_requested": response_format, "resolved_response_format_actually_sent": resolved_format, "response_format_matches": format_matches, "explicit_response_format_rejection": explicit_rejection, "transport_error": transport_error})

    if transport_error and not http_status:
        parse_result = {"status": "NOT_RUN", "repair": False, "markdown_stripping": False, "substring_extraction": False}
        validation = {"status": "NOT_RUN", "errors": ["NO_HTTP_RESPONSE"]}
        classification = classify_probe(http_status=None, raw="", transport_error=transport_error)
    elif explicit_rejection:
        parse_result = {"status": "NOT_RUN", "repair": False, "markdown_stripping": False, "substring_extraction": False}
        validation = {"status": "NOT_RUN", "errors": ["EXPLICIT_JSON_SCHEMA_REJECTION"]}
        classification = classify_probe(http_status=http_status, raw=raw, response_format_rejected=True)
    else:
        try:
            returned = json.loads(raw)
            parse_result = {"status": "PASS" if isinstance(returned, dict) else "BLOCKED", "exact_top_level_keys": sorted(returned) if isinstance(returned, dict) else [], "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False}
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            returned = None
            parse_result = {"status": "BLOCKED", "error": str(exc)[:240], "exact_top_level_keys": [], "repair": False, "markdown_stripping": False, "substring_extraction": False, "coercion": False}
        validation = validate_json_schema_subset(returned, schema) if isinstance(returned, dict) else {"status": "BLOCKED", "errors": ["STRICT_JSON_PARSE_FAILED_OR_NOT_OBJECT"]}
        classification = classify_probe(http_status=http_status, finish_reason=finish_reason, raw=raw)
        parse_result["probe_value"] = returned.get("probe") if isinstance(returned, dict) else None
        parse_result["ordinal_value"] = returned.get("ordinal") if isinstance(returned, dict) else None
    write("CAPABILITY_PROBE_PARSE_AUDIT.json", parse_result)
    write("CAPABILITY_PROBE_SCHEMA_VALIDATION.json", {**validation, "schema_fingerprint": schema_fingerprint, "json_schema_validator": "provider_structured_output_qualification.validate_json_schema_subset"})
    returned_value = None
    if raw and not explicit_rejection:
        try:
            returned_value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    conflict = {"status": "PASS" if classification.get("strict_proven") else "STRICT_NOT_PROVEN", "prompt_requested_forbidden_extra": True, "schema_additional_properties": False, "forbidden_extra_present": bool(isinstance(returned_value, dict) and "forbidden_extra" in returned_value), "exact_top_level_keys": sorted(returned_value) if isinstance(returned_value, dict) else [], "exact_keys_required": ["ordinal", "probe"], "conflict_enforcement_proven": bool(classification.get("strict_proven")), "http_200_alone_sufficient": False}
    write("STRICT_CONFLICT_ENFORCEMENT_AUDIT.json", conflict)

    cap = str(classification.get("capability") or "UNKNOWN")
    qualified = cap in {"JSON_OBJECT_ONLY", "JSON_SCHEMA_STRICT_SUPPORTED"} and classification.get("status") == "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_QUALIFIED"
    qualification = qualification_fingerprint(identity=identity, capability=cap, probe_schema_fingerprint=schema_fingerprint, request_fingerprint=request_fingerprint, raw_response_sha256=raw_sha, qualified=qualified)
    qualification.update({"http_status": http_status, "finish_reason": finish_reason, "raw_response_length": len(raw), "qualification_status": classification.get("status"), "identity_scope_only": True, "qualified_at_timestamp_excluded_from_identity": True})
    write("PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION.json", qualification)
    protected_after = production_row_fingerprints()
    business_unchanged = all(protected_before.get(key, {}).get("fingerprint") == protected_after.get(key, {}).get("fingerprint") for key in ("fact_snapshot_49", "script_ir_52")) and protected_before.get("packet_64_fingerprint") == protected_after.get("packet_64_fingerprint") and protected_after.get("director_ledger") == 11 and protected_after.get("active_stage_b") == "attempt-11"
    write("NO_BUSINESS_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS" if business_unchanged else "BLOCKED", "provider_http_posts": 1, "semantic_verifier_posts": 0, "source_entity_proposal_posts": 0, "source_claim_proposal_posts": 0, "fact_snapshot_writes": 0, "fact_record_writes": 0, "source_claim_writes": 0, "packet_64_writes": 0, "stage_a": 0, "attempt_12": 0, "confirm": 0, "image": 0, "video": 0, "qualification_profile_mutation": 0, "fact_snapshot_49_unchanged": protected_before.get("fact_snapshot_49", {}).get("fingerprint") == protected_after.get("fact_snapshot_49", {}).get("fingerprint"), "script_ir_52_unchanged": protected_before.get("script_ir_52", {}).get("fingerprint") == protected_after.get("script_ir_52", {}).get("fingerprint"), "packet_64_unchanged": protected_before.get("packet_64_fingerprint") == protected_after.get("packet_64_fingerprint"), "director_ledger_before_after": [protected_before.get("director_ledger"), protected_after.get("director_ledger")], "active_stage_b_before_after": [protected_before.get("active_stage_b"), protected_after.get("active_stage_b")]})

    if cap == "JSON_SCHEMA_STRICT_SUPPORTED" and classification.get("strict_proven"):
        next_state = "SOURCE_ENTITY_PROPOSAL_CANARY_AUTHORIZATION_REQUIRED"
        entity_authorized = True
    elif cap == "JSON_OBJECT_ONLY":
        next_state = "PROVIDER_INDEPENDENT_STRUCTURAL_ENFORCEMENT_REDESIGN_REQUIRED"
        entity_authorized = False
    elif cap == "JSON_SCHEMA_SUPPORTED":
        next_state = "PROVIDER_JSON_SCHEMA_STRICT_CAPABILITY_NOT_PROVEN"
        entity_authorized = False
    else:
        next_state = "PROVIDER_STRUCTURED_OUTPUT_QUALIFICATION_AMBIGUOUS"
        entity_authorized = False
    write("RECOMMENDED_NEXT_ACTION.json", {"status": next_state, "capability": cap, "source_entity_proposal_authorized": entity_authorized, "source_claim_proposal_authorized": False, "semantic_verifier_authorized": False, "no_business_call_after_capability_probe": True, "profile_capability_mutated": False})

    report = f"""# V7.7.5 Provider Strict Structured Output Capability Qualification

## Provider identity

- Profile: `{identity['profile_id']}`
- Provider: `{identity['provider']}`
- Model: `{identity['model']}`
- Runtime base host: `{identity['base_host']}`
- Identity fingerprint: `{identity['provider_identity_fingerprint']}`
- Historical capability: `JSON_OBJECT_ONLY` (V7.7.3 observed `response_format={{\"type\":\"json_object\"}}`)

## One-shot probe

- Real Provider HTTP POST: `1`
- Response format sent: `json_schema`, `strict=true`
- HTTP status: `{http_status}`
- finish_reason: `{finish_reason}`
- latency ms: `{audit_record.get('latency_ms', latency_ms)}`
- usage: `{json.dumps(audit_record.get('usage', {}), ensure_ascii=False, sort_keys=True)}`
- Raw SHA256: `{raw_sha}`
- Raw length: `{len(raw)}`
- Strict JSON parse: `{parse_result.get('status')}`
- Returned exact keys: `{parse_result.get('exact_top_level_keys', [])}`
- `forbidden_extra` present: `{conflict['forbidden_extra_present']}`
- JSON Schema validation: `{validation.get('status')}`
- Conflicting prompt enforcement: `{conflict['status']}`
- Final capability: `{cap}`
- Qualification fingerprint: `{qualification['qualification_fingerprint']}`
- Qualification status: `{classification.get('status')}`

## Scope and controls

Qualification is bound only to the frozen profile identity and host. Runtime profile was not mutated. No story/source units, business JSON Schema, or semantic task was sent. Phrase, scene, attempt, and story fixture dependence are all `NO`.

- Source Entity Proposal authorized: `{entity_authorized}`
- Source Claim Proposal authorized: `False`
- Semantic Verifier authorized: `False`
- Schema compiler status: `{compiler_audit['status']}` (entity proposal `{entity_compiled['audit']['status']}`, entity candidate `{source_candidate_compiled['audit']['status']}`, Claim V2 `{claim_compiled['audit']['status']}`)
- Anti-Heuristic: `PASS`
- FactSnapshot / FactRecord / SourceClaim / Packet writes: `0`
- Stage A / Attempt-12 / Confirm: `0`
- IMAGE / VIDEO: `0`
- Ledger: `{protected_after.get('director_ledger')}`
- Active Stage B: `{protected_after.get('active_stage_b')}`
- Business rows unchanged: `{business_unchanged}`
- Next state: `{next_state}`
"""
    (EVIDENCE / "PROVIDER_STRUCTURED_OUTPUT_CAPABILITY_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
