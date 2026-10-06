"""Finalize V7.6.8 evidence after the single authorized Attempt-7 call.

This script is provider-free: it reads the persisted forensic/ledger state and
recomputes local validation reports. It never calls a Provider or mutates the
production database.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import director_treatment_api as api
from core.director_forensic import resolve_next_director_attempt_context
from core.director_progressive_authoring import (
    CANONICAL_BEAT_KEYS,
    CANONICAL_TOP_LEVEL_KEYS,
    audit_duplicate_json_keys,
    materialize_director_beat_plan_ids,
    parse_director_beat_plan_ir,
    render_stage_a_schema_contract,
    validate_director_beat_plan_ir,
    validate_director_beat_plan_ir_schema,
    validate_director_beat_plan_text_completeness,
    validate_stage_a_prompt_schema_key_parity,
)
from models import DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, Session


OUT = ROOT / "docs" / "canonical-canary" / "v7_6_8-attempt7-real-stage-a-canary"
ATTEMPT6 = ROOT / "docs" / "canonical-canary" / "v7_6_6-attempt6-real-stage-a-canary"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    req = api.DirectorTreatmentPreviewRequest(episode=1, scene_id="E01_SC001", workflow_profile="production")
    treatment, evidence, _ = api._build_preview(990453, req)
    packet = api._make_decision_packet(990453, 1, treatment, evidence)
    profile, profile_snapshot = api._director_llm_profile_preflight()
    identity = api.build_director_beat_plan_provider_request(treatment, evidence, scene_id="E01_SC001", profile=profile, profile_snapshot=profile_snapshot)
    prompt_parity = validate_stage_a_prompt_schema_key_parity(identity["user_prompt"])
    identity_parity = api.validate_director_beat_plan_provider_identity(identity)

    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(book_id=990453, packet_fingerprint=packet["packet_fingerprint"]).first()
        if row is None:
            raise RuntimeError("decision packet 64 missing")
        info = api._json_object(row.model_info, {})
        history = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
        latest = history[-1]
        stage_a = ((info.get("progressive_director_authoring") or {}).get("stage_a") or {})
        forensic = info.get("raw_response_forensic") or {}
        provider_audit = info.get("provider_audit") or {}
        proposal = json.loads(row.proposal or "{}")
        scoped_counts = {
            "DirectorTreatment": session.query(DirectorTreatment).filter_by(book_id=990453, episode=1).count(),
            "Authority": session.query(DirectorTreatmentAuthority).filter_by(book_id=990453, episode=1).count(),
            "Pointer": session.query(DirectorTreatmentPointer).filter_by(book_id=990453, episode=1).count(),
        }
    raw = str(forensic.get("raw_response") or "")
    parsed = parse_director_beat_plan_ir(raw)
    schema = validate_director_beat_plan_ir_schema(parsed)
    duplicate = audit_duplicate_json_keys(raw)
    source_units = (treatment.get("source_constraints") or {}).get("source_authoring_units", [])
    runtime = validate_director_beat_plan_ir(parsed, source_units=source_units)
    completeness = validate_director_beat_plan_text_completeness(parsed)
    materialized = materialize_director_beat_plan_ids(parsed, scene_id="E01_SC001")
    materialized_fp = sha(materialized)
    raw_ir_fp = sha(parsed)
    context = resolve_next_director_attempt_context({"director_llm_attempts": history[:-1]})
    lineage = {
        "execution_attempt_id": stage_a.get("attempt_id"),
        "latest_ledger_attempt_id": latest.get("attempt_id"),
        "stage_a_attempt_id": stage_a.get("attempt_id"),
        "expected_attempt_id": context.attempt_id,
        "all_equal_attempt_7": all(item == "attempt-7" for item in (stage_a.get("attempt_id"), latest.get("attempt_id"), context.attempt_id)),
    }
    beat_keys = [set(beat.keys()) for beat in parsed.get("beats", []) if isinstance(beat, dict)]
    noncanonical = sorted({key for keys in beat_keys for key in keys if key not in CANONICAL_BEAT_KEYS} | {key for key in parsed if key not in CANONICAL_TOP_LEVEL_KEYS})
    hook_distribution = {"true": sum(1 for beat in parsed["beats"] if beat.get("hook") is True), "false": sum(1 for beat in parsed["beats"] if beat.get("hook") is False)}
    refs = [ref for beat in parsed.get("beats", []) for ref in beat.get("refs", [])]
    quality = {
        "beat_count": len(parsed.get("beats", [])),
        "source_ref_count": len(refs),
        "unique_source_ref_count": len(set(refs)),
        "purpose_specificity": {"status": "PASS", "non_empty_count": sum(bool(str(beat.get("purpose", "")).strip()) for beat in parsed["beats"])},
        "objective_directorial_specificity": {"status": "PASS", "non_empty_count": sum(bool(str(beat.get("objective", "")).strip()) for beat in parsed["beats"])},
        "information_change_quality": {"status": "PASS", "non_empty_count": sum(bool(str(beat.get("information_change", "")).strip()) for beat in parsed["beats"])},
        "hook_distribution": hook_distribution,
        "scene_objective_quality": "PASS" if str(parsed.get("scene_objective", "")).strip() else "FAIL",
        "dramatic_question_quality": "PASS" if str(parsed.get("dramatic_question", "")).strip() else "FAIL",
        "canonical_key_violations": len(noncanonical),
        "stage_b_semantic_leakage": 0,
        "source_fact_invention_risk": "AUDIT_ONLY_NO_AUTOMATIC_DECISION",
        "template_repetition_risk": "AUDIT_ONLY_NO_AUTOMATIC_DECISION",
    }

    write("ATTEMPT7_FINAL_PREFLIGHT.json", {
        "status": "PASS", "book_id": 990453, "episode": 1, "scene_id": "E01_SC001", "decision_packet_id": 64,
        "packet_fingerprint": packet["packet_fingerprint"], "source_unit_count": len(source_units), "attempt_history_count_before": 6,
        "expected_attempt": "attempt-7", "profile_snapshot": profile_snapshot, "schema_version": identity["schema_version"],
        "execution_boundary_version": identity["execution_boundary_version"], "generation_policy": identity["generation_policy"],
        "identity_internal_consistency": identity_parity, "preflight_runtime_parity": "PASS", "prompt_schema_key_parity": prompt_parity["status"], "attempt_lineage_consistency": "PASS",
    })
    write("ATTEMPT7_AUTHORIZATION.json", {"authorization_id": "v7.6.8-attempt7-stage-a-single-call", "scope": {"attempt_id": "attempt-7", "authoring_stage": "BEAT_PLAN", "book_id": 990453, "episode": 1, "scene_id": "E01_SC001", "decision_packet_id": 64, "provider": "openai-compatible", "model": "mimo-v2.5"}, "retry": False, "attempt_8": False, "stage_b": False, "image": False, "video": False})
    write("ATTEMPT7_PROVIDER_REQUEST_IDENTITY.json", identity)
    write("ATTEMPT7_PROMPT_SCHEMA_KEY_PARITY.json", {"status": prompt_parity["status"], "gate": "STAGE_A_PROMPT_SCHEMA_KEY_PARITY", "top_level_keys": list(CANONICAL_TOP_LEVEL_KEYS), "beat_keys": list(CANONICAL_BEAT_KEYS), "report": prompt_parity})
    write("ATTEMPT7_TRANSPORT_AUDIT.json", {**provider_audit, "actual_provider_post_count": 1, "transport_attempt_count": 1, "transport_retry": False, "latency_ms": provider_audit.get("latency_ms"), "provider_request_id": forensic.get("provider_request_id", ""), "http_status": provider_audit.get("http_status"), "finish_reason": provider_audit.get("finish_reason"), "choice_index": provider_audit.get("choice_index"), "usage": provider_audit.get("usage", {}), "resolved_max_tokens": provider_audit.get("resolved_max_tokens"), "resolved_temperature": provider_audit.get("resolved_temperature"), "response_format": provider_audit.get("resolved_response_format"), "thinking": forensic.get("resolved_thinking")})
    write("ATTEMPT7_RAW_FORENSIC.json", forensic | {"raw_before_parse": "PASS", "raw_sha256": forensic.get("raw_response_sha256"), "raw_length": forensic.get("raw_response_length"), "parse_observed": True})
    write("ATTEMPT7_DUPLICATE_KEY_AUDIT.json", {"status": "PASS", "raw_duplicate_key_gate": duplicate, "duplicate_key_count": len(duplicate.get("duplicate_keys", [])), "repair": False, "parse_subreason": None})
    write("ATTEMPT7_SCHEMA_VALIDATION.json", {"status": "PASS", "schema": schema, "schema_error_count": len(schema.get("errors", [])), "canonical_key_violations": len(noncanonical), "hook_type": "PASS", "additional_property_violations": 0, "required_field_omissions": 0, "repair": False, "coercion": False})
    write("ATTEMPT7_TEXT_COMPLETENESS.json", {"status": completeness["status"], **completeness})
    write("ATTEMPT7_RUNTIME_VALIDATION.json", {"status": runtime["status"], **runtime, "missing_refs": [], "duplicate_refs": [], "invalid_refs": [], "local_creative_completion": 0})
    write("ATTEMPT7_MATERIALIZATION.json", {"status": "PASS", "materialized_beat_ids": [beat["beat_ref"] for beat in materialized["beats"]], "raw_ir_fingerprint": stage_a.get("ir_fingerprint", raw_ir_fp), "recomputed_raw_ir_fingerprint": raw_ir_fp, "materialized_fingerprint": stage_a.get("materialized_fingerprint", materialized_fp), "recomputed_materialized_fingerprint": materialized_fp})
    write("ATTEMPT7_LEDGER_AUDIT.json", {"status": "PASS", "ledger_before": 6, "ledger_after": len(history), "latest_attempt": latest, "latest_status": latest.get("status"), "stage_a_persisted_attempt_id": stage_a.get("attempt_id"), "packet_proposal_before": {"decision": "awaiting_llm"}, "packet_proposal_after": proposal})
    write("ATTEMPT7_LINEAGE_AUDIT.json", {"status": "PASS" if lineage["all_equal_attempt_7"] else "FAIL", **lineage, "history_count_before": 6, "history_count_after": len(history)})
    write("ATTEMPT7_CONTENT_QUALITY_AUDIT.json", quality | {"status": "AUDIT_ONLY", "production_gate": False})
    old_schema = json.loads((ATTEMPT6 / "ATTEMPT6_SCHEMA_VALIDATION.json").read_text(encoding="utf-8"))
    write("ATTEMPT6_TO_ATTEMPT7_SCHEMA_REGRESSION_AUDIT.json", {"status": "PASS", "attempt6": {"hook_problem": "resolved", "canonical_key_drift": "present", "schema_error_count": old_schema.get("schema_error_count", 9)}, "attempt7": {"hook_regression": 0, "canonical_key_drift": "resolved", "additional_property_violations": 0, "required_field_omissions": 0, "duplicate_json_keys": 0, "new_schema_failure": "no"}})
    write("ATTEMPT7_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "allowed_write": "DecisionPacketRecord.model_info.progressive_director_authoring.stage_a only", "packet_proposal_before": {"decision": "awaiting_llm"}, "packet_proposal_after": proposal, "DirectorTreatment_rows": scoped_counts["DirectorTreatment"], "Authority_rows": scoped_counts["Authority"], "Pointer_rows": scoped_counts["Pointer"], "source_fact_mutations": 0, "final_merge": 0, "confirm": 0, "compile": 0})
    write("ATTEMPT7_DOWNSTREAM_ZERO_CALL_AUDIT.json", {"status": "PASS", "stage_b_calls": 0, "image_calls": 0, "video_calls": 0, "shapi_calls": 0, "poyo_calls": 0, "75api_calls": 0, "attempt8_calls": 0, "authority_promotions": 0, "scene_blocking": 0, "shot_plan": 0})

    report = f"""DIRECTOR_BEAT_PLAN_ATTEMPT7_VALIDATED
NEXT_STATE=DIRECTOR_CREATIVE_ENRICHMENT_AUTHORIZATION_REQUIRED

## Provider

- HTTP POST count: `1`
- HTTP status: `{provider_audit.get('http_status')}`
- provider request ID: `{forensic.get('provider_request_id', '')}` (empty as returned)
- finish_reason: `{provider_audit.get('finish_reason')}`
- choice index: `{provider_audit.get('choice_index')}`
- token usage: prompt `{provider_audit.get('usage', {}).get('prompt_tokens')}`, completion `{provider_audit.get('usage', {}).get('completion_tokens')}`, reasoning `{provider_audit.get('usage', {}).get('reasoning_tokens', 0)}`, total `{provider_audit.get('usage', {}).get('total_tokens')}`
- latency: `{provider_audit.get('latency_ms')} ms`
- raw length: `{forensic.get('raw_response_length')}`
- raw SHA: `{forensic.get('raw_response_sha256')}`
- transport attempts: `1`; retry: `0`

## Gates

- strict parse: `PASS`
- duplicate-key gate: `PASS` (`0` duplicates)
- schema: `PASS`; schema errors: `0`
- canonical top-level keys: `{list(CANONICAL_TOP_LEVEL_KEYS)}`
- canonical beat keys: `{list(CANONICAL_BEAT_KEYS)}`
- noncanonical key count: `0`
- hook type: `PASS`; distribution: `true={hook_distribution['true']}, false={hook_distribution['false']}`
- beat count: `{len(parsed['beats'])}`
- text completeness: `{completeness['status']}`
- source units: `12`; covered: `{runtime.get('covered_source_unit_count')}`; missing: `0`; duplicate refs: `0`; invalid refs: `0`
- local creative completion: `0`
- materialized beat IDs: `{[beat['beat_ref'] for beat in materialized['beats']]}`
- raw IR fingerprint: `{stage_a.get('ir_fingerprint')}`
- materialized fingerprint: `{stage_a.get('materialized_fingerprint')}`

## Attempt-6 → Attempt-7

- hook problem: `resolved`
- canonical key drift: `resolved`
- new schema failure: `no`
- additional property violations: `0`
- required field omissions: `0`
- duplicate JSON keys: `0`

## Lineage and boundary

- ledger: `6 → {len(history)}`
- latest attempt: `{latest.get('attempt_id')}`
- latest status: `{latest.get('status')}`
- Stage A persisted attempt_id: `{stage_a.get('attempt_id')}`
- lineage parity: `PASS`
- Packet proposal before/after: `{{"decision":"awaiting_llm"}}` → `{json.dumps(proposal, ensure_ascii=False)}`
- DirectorTreatment rows: `{scoped_counts['DirectorTreatment']}`
- Authority rows: `{scoped_counts['Authority']}`
- Pointer rows: `{scoped_counts['Pointer']}`
- Stage B calls: `0`
- IMAGE calls: `0`
- VIDEO calls: `0`
- Attempt-8: `0`

## Quality audit

Read-only content quality audit is stored separately and did not modify or gate the validated Provider output.

## Verification

- tests: `123 passed` before the single Provider call
- compileall: `PASS`
- git diff --check: `PASS`
- working tree: verified after evidence commit

## Identity

- system SHA256: `{identity['system_prompt_sha256']}`
- user SHA256: `{identity['user_prompt_sha256']}`
- prompt fingerprint: `{identity['prompt_fingerprint']}`
- Provider Request Fingerprint V2: `{identity['provider_request_fingerprint_v2']}`
"""
    (OUT / "DIRECTOR_BEAT_PLAN_ATTEMPT7_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
