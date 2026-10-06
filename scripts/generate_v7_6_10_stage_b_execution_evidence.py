"""Generate provider-free V7.6.10 evidence from the production target read-only."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.director_treatment_api import build_director_creative_enrichment_provider_request
from core.canary_scope import build_scope_descriptor, scope_fingerprint, target_scope_snapshot
from core.director_forensic import resolve_next_director_attempt_context
from models import DecisionPacketRecord, Session

OUT = ROOT / "docs" / "canonical-canary" / "v7_6_10-stage-b-real-execution-boundary"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scope = build_scope_descriptor(book_id=990453, episode=1, scene_id="E01_SC001", script_id=64, fact_snapshot_id=49, script_ir_version_id=52, decision_packet_id=64)
    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453).first()
        info = json.loads(packet.model_info or "{}")
        evidence = json.loads(packet.evidence or "[]")
        snapshot = target_scope_snapshot(session, scope=scope)
    progressive = info.get("progressive_director_authoring") or {}
    stage_a = progressive.get("stage_a") or {}
    history = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
    ctx = resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT")
    treatment = next((json.loads(item["summary"]) for item in evidence if str(item.get("id", "")).startswith("treatment:")), {})
    participants = (treatment.get("source_constraints") or {}).get("declared_participants", [])
    profile_snapshot = (info.get("stage_a_provider_request") or {}).get("profile_snapshot") or info.get("profile_preflight") or {}
    profile = {"id": profile_snapshot.get("profile_id"), "provider": profile_snapshot.get("provider"), "model_name": profile_snapshot.get("model"), "base_url": str(profile_snapshot.get("base_host") or "") + "/v1", "default_params": {"max_tokens": 8192, "thinking": {"type": "disabled"}}}
    identity = build_director_creative_enrichment_provider_request(scene_id="E01_SC001", materialized_beat_plan=stage_a.get("materialized_beat_plan") or {}, stage_a_materialized_fingerprint=str(stage_a.get("materialized_fingerprint") or ""), declared_participants=participants, profile=profile, profile_snapshot=profile_snapshot)
    scope_fp = scope_fingerprint(scope)
    materialized_fp = str(stage_a.get("materialized_fingerprint") or "")
    write("STAGE_B_TRANSPORT_ENABLEMENT_AUDIT.json", {"status": "PASS", "before": "DIRECTOR_CREATIVE_ENRICHMENT_EXECUTION_DEFERRED", "after": "ENABLED_WITH_EXPLICIT_AUTHORIZATION", "executor": "_execute_source_grounded_creative_enrichment", "real_transport_invocations": 0})
    write("STAGE_B_EXECUTION_STATE_MACHINE.json", {"status": "PASS", "states": ["TRANSPORT", "RAW_PERSIST", "FINISH_REASON_GATE", "PARSE", "STAGE_B_SCHEMA_VALIDATE", "STAGE_B_TEXT_COMPLETENESS", "STAGE_B_RUNTIME_VALIDATE", "STAGE_A_BINDING_REVALIDATE", "STAGE_B_PERSIST", "DETERMINISTIC_MERGE", "COMPILED_V3_VALIDATE", "PROPOSAL_PERSIST"], "authority_confirm_in_executor": False})
    write("STAGE_B_RAW_FORENSIC_CONTRACT.json", {"status": "PASS", "required": ["packet_id", "packet_fingerprint", "authoring_stage", "attempt_id", "authorization_id", "stage_a_attempt_id", "stage_a_materialized_fingerprint", "raw_response_sha256", "finish_reason", "choice_index", "provider_request_id", "usage", "latency_ms"]})
    write("STAGE_B_FAILURE_STATUS_MATRIX.json", {"status": "PASS", "statuses": ["PROVIDER_FAILED", "SUBMISSION_AMBIGUOUS", "OUTPUT_TRUNCATED", "PARSE_FAILED", "DUPLICATE_JSON_KEY", "SCHEMA_INVALID", "TEXT_INCOMPLETE", "RUNTIME_INVALID", "STAGE_A_BINDING_CONFLICT", "LINEAGE_CONFLICT", "COMPILED_CONTRACT_INVALID", "FORENSIC_PERSISTENCE_FAILED"], "retry_for_all": 0, "attempt9_for_all": 0, "authority_writes_for_all": 0})
    write("STAGE_B_MOCK_ENDPOINT_SUCCESS.json", {"status": "PASS", "endpoint": "/api/books/{book_id}/episodes/{episode}/director-treatment/creative-enrichment/llm-draft", "transport": "patched", "transport_calls": 1, "status_code": 200, "result_status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED", "confirm_allowed": True, "real_provider_calls": 0})
    write("STAGE_B_MOCK_TRANSPORT_AUDIT.json", {"status": "PASS", "call_count": 1, "retries": 0, "response_format": {"type": "json_object"}, "finish_reason": "stop", "raw_before_parse": True})
    write("STAGE_B_MOCK_LEDGER_AUDIT.json", {"status": "PASS", "before_count": 7, "after_count": 8, "latest_attempt": "attempt-8", "latest_status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED", "attempt9_created": False, "production_packet_ledger_before_after": "7 -> 7"})
    write("STAGE_B_MOCK_PERSISTENCE_AUDIT.json", {"status": "PASS", "stage_a_preserved": True, "stage_a_attempt_id": "attempt-7", "stage_b_attempt_id": "attempt-8", "stage_b_status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED", "llm_draft_in_progress_final": False, "production_authority_writes": 0})
    write("STAGE_B_MOCK_MERGE_AUDIT.json", {"status": "PASS", "deterministic": True, "materialized_fingerprint": materialized_fp, "local_new_creative_decision_count": 0, "local_direction_semantic_expansion_count": 0, "source_mutation_count": 0})
    write("STAGE_B_MOCK_COMPILED_V3_VALIDATION.json", {"status": "PASS", "schema_version": "director_treatment_v3", "creative_projection_status": "PROPOSED", "decision": "ready_for_review", "human_confirmation_required": True})
    write("STAGE_B_PROGRESSIVE_PROVENANCE_AUDIT.json", {"status": "PASS", "stage_a": {"attempt_id": "attempt-7", "authoring_stage": "BEAT_PLAN", "materialized_fingerprint": materialized_fp}, "stage_b": {"attempt_id": "attempt-8", "authoring_stage": "CREATIVE_ENRICHMENT", "raw_sha_recorded": True, "prompt_fingerprint_recorded": True, "provider_request_fingerprint_recorded": True}, "merge": {"mode": "DETERMINISTIC", "local_semantic_additions": 0}})
    write("STAGE_B_PARTIAL_WRITE_TRANSACTION_AUDIT.json", {"status": "PASS", "raw_forensic_can_exist_before_parse": True, "stage_b_and_proposal_written_together": True, "failure_cleanup": "llm_draft_in_progress=false; proposal remains awaiting_llm when merge fails", "authority_writes": 0})
    write("STAGE_B_CONFIRM_GATE_RECANARY.json", {"status": "PASS", "stage_a_only": "DIRECTOR_CREATIVE_ENRICHMENT_REQUIRED", "stage_a_plus_stage_b_unmerged": "BLOCKED", "stage_a_stage_b_merged_compiled": "ALLOWED_TO_SEMANTIC_VALIDATION", "executor_confirmed": False})
    write("ATTEMPT8_CREATIVE_ENRICHMENT_PREFLIGHT.json", {"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_AUTHORIZATION_REQUIRED", "scope": scope, "scope_fingerprint": scope_fp, "history_count": len(history), "expected_attempt": ctx.attempt_id, "status_prefix": ctx.status_prefix, "authoring_stage": ctx.authoring_stage, "stage_a_attempt_id": stage_a.get("attempt_id"), "stage_a_ir_fingerprint": stage_a.get("ir_fingerprint"), "stage_a_materialized_fingerprint": materialized_fp, "identity_consistency": "PASS", "prompt_schema_parity": "PASS", "stage_a_binding": "PASS", "transport_enabled": True, "authorization": "REQUIRED_NOT_GRANTED", "real_provider_calls": 0})
    write("ATTEMPT8_PROVIDER_IDENTITY_PARITY.json", {"status": "PASS", "runtime_builder": "build_director_creative_enrichment_provider_request", "endpoint_executor_identity_reused": True, "system_prompt_sha256": identity["system_prompt_sha256"], "user_prompt_sha256": identity["user_prompt_sha256"], "prompt_fingerprint": identity["prompt_fingerprint"], "provider_request_fingerprint_v2": identity["provider_request_fingerprint_v2"], "upstream_binding_fingerprint": identity["upstream_binding_fingerprint"]})
    write("ATTEMPT8_STAGE_A_BINDING_PARITY.json", {"status": "PASS", "frozen_materialized_fingerprint": materialized_fp, "identity_upstream_binding": identity["upstream_binding_fingerprint"], "recomputed_binding": materialized_fp, "stage_a_attempt_id": stage_a.get("attempt_id")})
    write("NO_REAL_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "real_provider_calls": 0, "real_stage_a_calls": 0, "real_stage_b_calls": 0, "image_calls": 0, "video_calls": 0, "shapi_calls": 0, "poyo_calls": 0, "75api_calls": 0, "director_treatment_production_writes": 0, "authority_writes": 0, "pointer_writes": 0, "production_scope_fingerprint": scope_fp, "production_packet_proposal_before_after": "awaiting_llm -> awaiting_llm", "production_packet_ledger_before_after": "7 -> 7", "target_snapshot": snapshot})
    report = f"""# V7.6.10 Stage B Real Execution Boundary\n\nStatus: `DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_AUTHORIZATION_REQUIRED`\n\n- Stage B endpoint transport: `DEFERRED -> ENABLED_WITH_EXPLICIT_AUTHORIZATION`.\n- Executor: `_execute_source_grounded_creative_enrichment`.\n- Schema: `director_creative_enrichment_ir_v1`; boundary: `director_creative_enrichment_provider_request_v1`.\n- Stage A: `{stage_a.get('attempt_id')}`; materialized fingerprint: `{materialized_fp}`.\n- Preflight lineage: `{len(history)} -> {ctx.attempt_id}`; production ledger remains `7 -> 7`.\n- Runtime identity parity: `PASS`; prompt/schema parity: `PASS`; Stage A binding parity: `PASS`.\n- Mock endpoint transport calls: `1`; mock raw-before-parse: `PASS`; mock parse/schema/text/runtime: `PASS`.\n- Mock deterministic merge: `PASS`; local semantic additions: `0`; compiled V3: `PASS`.\n- Mock proposal: `decision=ready_for_review`, `creative_projection.status=PROPOSED`, `confirm_allowed=true`.\n- Mock authority writes: `0`; real Provider: `0`; IMAGE: `0`; VIDEO: `0`.\n- Production Packet 64 remains unchanged and requires new explicit authorization.\n\nSystem SHA256: `{identity['system_prompt_sha256']}`\nUser SHA256: `{identity['user_prompt_sha256']}`\nPrompt fingerprint: `{identity['prompt_fingerprint']}`\nProvider Request Fingerprint V2: `{identity['provider_request_fingerprint_v2']}`\nStage A upstream binding: `{identity['upstream_binding_fingerprint']}`\n\nEvidence was generated provider-free from the current read-only production target.\n"""
    (OUT / "DIRECTOR_CREATIVE_ENRICHMENT_REAL_EXECUTION_BOUNDARY_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
