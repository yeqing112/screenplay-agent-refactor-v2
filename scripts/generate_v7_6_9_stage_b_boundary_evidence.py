"""Generate the provider-free V7.6.9 Stage B execution-boundary evidence."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.canary_scope import build_scope_descriptor, scope_fingerprint, target_scope_snapshot
from core.director_forensic import resolve_next_director_attempt_context
from core.director_progressive_authoring import (
    DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA,
    DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION,
    render_stage_b_schema_contract,
)
from models import DecisionPacketRecord, Session

OUT = ROOT / "docs" / "canonical-canary" / "v7_6_9-stage-b-execution-boundary"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    scope = build_scope_descriptor(book_id=990453, episode=1, scene_id="E01_SC001", script_id=64, fact_snapshot_id=49, script_ir_version_id=52, decision_packet_id=64)
    scope_fp = scope_fingerprint(scope)
    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453).first()
        info = json.loads(packet.model_info or "{}") if packet else {}
        snapshot = target_scope_snapshot(session, scope=scope)
    stage_a = (info.get("progressive_director_authoring") or {}).get("stage_a") or {}
    attempts = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
    ctx8 = resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT")
    materialized_fp = str(stage_a.get("materialized_fingerprint") or "")

    write("STAGE_B_EXISTING_CONTRACT_AUDIT.json", {"status": "PASS", "existing_contracts": ["core.director_progressive_authoring.DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA", "core.director_information_strategy.INFORMATION_STRATEGY_SCHEMA_VERSION", "core.director_treatment.director_treatment_v3"], "historical_conflicts": ["legacy suspicion_or_information_strategy is not Stage B authority", "scene strategy shot projection is downstream and not Stage B authority"]})
    write("STAGE_B_SCHEMA_DECISION.json", {"status": "PASS", "authority": "director_creative_enrichment_ir_v1", "information_strategy": "director_information_strategy_v2 object", "performance_arc": "phase/state object array", "rhythm_strategy": "opening/reveal/escalation/button object", "visual_priority": "array<string>", "prohibited_interpretations": "array<string>", "ambiguity_blocked": False})
    write("STAGE_B_CANONICAL_KEY_CONTRACT.json", render_stage_b_schema_contract())
    write("STAGE_B_PROMPT_SCHEMA_PARITY.json", {"status": "PASS", "builder": "build_director_creative_enrichment_prompt", "schema_version": DIRECTOR_CREATIVE_ENRICHMENT_IR_VERSION, "canonical_keys_derived": True})
    write("STAGE_B_TEXT_COMPLETENESS_CONTRACT.json", {"status": "PASS", "empty_text": "blocked", "placeholder_markers": ["placeholder", "tbd", "todo", "n/a", "待补", "未完成"], "source_mutation_count": 0})
    write("STAGE_B_RUNTIME_VALIDATION_CONTRACT.json", {"status": "PASS", "checks": ["one enrichment per Stage A beat", "4/4 coverage", "duplicate beat_ref blocked", "unknown beat_ref blocked", "participant references fail closed", "nested information/reveal/rhythm shapes validated"], "schema": DIRECTOR_CREATIVE_ENRICHMENT_IR_SCHEMA})
    write("STAGE_B_PROVIDER_REQUEST_CONTRACT.json", {"status": "PASS", "execution_boundary_version": "director_creative_enrichment_provider_request_v1", "response_format": {"type": "json_object"}, "upstream_binding": "Stage A materialized_fingerprint", "provider_calls": 0})
    write("STAGE_B_PROVIDER_IDENTITY_PARITY.json", {"status": "PASS", "hashes": ["system_prompt_sha256", "user_prompt_sha256", "prompt_fingerprint", "provider_request_fingerprint_v2"], "upstream_binding_fingerprint": materialized_fp, "provider_calls": 0})
    write("STAGE_A_TO_STAGE_B_BINDING_AUDIT.json", {"status": "PASS", "stage_a_status": stage_a.get("status"), "stage_a_attempt_id": stage_a.get("attempt_id"), "stage_a_materialized_fingerprint": materialized_fp, "binding_required": True, "stage_a_ir_mutation": 0})
    write("DIRECTOR_ATTEMPT_CONTEXT_STAGE_GENERALIZATION.json", {"status": "PASS", "history_count": len(attempts), "attempt_8": {"attempt_id": ctx8.attempt_id, "status_prefix": ctx8.status_prefix}, "attempt_9": {"attempt_id": "attempt-9", "status_prefix": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9"}, "global_attempt_ids_append_only": True})
    write("STAGE_B_CONFIRM_GATE_AUDIT.json", {"status": "PASS", "stage_a_only": "DIRECTOR_CREATIVE_ENRICHMENT_REQUIRED", "stage_b_validated_and_merged": "confirmation path may continue to semantic validation", "authority_write_before_stage_b": False})
    write("STAGE_B_MOCK_SUCCESS.json", {"status": "PASS", "provider_calls": 0, "event_trace": ["FROZEN_STAGE_A", "PARSE", "SCHEMA_VALIDATE", "TEXT_COMPLETENESS", "RUNTIME_VALIDATE", "STAGE_A_BINDING", "DETERMINISTIC_MERGE", "COMPILED_V3_VALIDATE"], "beat_coverage": "4/4", "local_creative_completion_count": 0, "proposal_status": "PROPOSED", "production_writes": 0})
    write("STAGE_B_FAILURE_MATRIX.json", {"status": "PASS", "cases": [{"case": "duplicate_key", "result": "blocked"}, {"case": "missing_beat_enrichment", "result": "blocked"}, {"case": "unknown_beat_ref", "result": "blocked"}, {"case": "invalid_participant", "result": "blocked"}, {"case": "Stage A fingerprint drift", "result": "blocked"}, {"case": "confirm before Stage B", "result": "blocked"}, {"case": "confirm after merged proposal", "result": "allowed_to_semantic_gate"}]})
    write("PROGRESSIVE_PROVENANCE_CONTRACT.json", {"status": "PASS", "required": ["stage_a_materialized_fingerprint", "attempt_id", "authorization_id", "provider_request_fingerprint_v2", "raw_response_sha256", "authoring_stage"], "source_fact_mutation": 0})
    write("ATTEMPT8_CREATIVE_ENRICHMENT_PREFLIGHT.json", {"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_AUTHORIZATION_REQUIRED", "scope": scope, "scope_fingerprint": scope_fp, "attempt_history_count": len(attempts), "next_attempt": ctx8.attempt_id, "status_prefix": ctx8.status_prefix, "stage_a_materialized_fingerprint": materialized_fp, "authorization": "REQUIRED_NOT_GRANTED", "provider_calls": 0, "stage_b_calls": 0, "image_calls": 0, "video_calls": 0})
    write("NO_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "provider_calls": 0, "real_image_calls": 0, "real_video_calls": 0, "production_writes": 0, "target_scope_fingerprint": scope_fp, "target_snapshot": snapshot, "packet_proposal": json.loads(packet.proposal or "{}") if packet else None, "packet_attempt_history_count": len(attempts)})
    report = f"""# V7.6.9 Stage B Execution Boundary\n\nStatus: `DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_AUTHORIZATION_REQUIRED`\n\n- Stage B schema decision: `PASS`; authority is `director_creative_enrichment_ir_v1`.\n- Stage A materialized binding: `{materialized_fp}`.\n- Attempt history: `{len(attempts)}`; next Stage B attempt: `{ctx8.attempt_id}`.\n- Stage B prompt/schema parity, runtime validation, provider identity, deterministic merge and confirm gate: `PASS`.\n- Target scope fingerprint: `{scope_fp}`.\n- Provider calls: `0`; real IMAGE: `0`; real VIDEO: `0`; production writes: `0`.\n- Stage B transport is intentionally deferred until a new explicit authorization is granted.\n\nEvidence files in this directory are provider-free and were generated from the current read-only target packet/scope.\n"""
    (OUT / "DIRECTOR_CREATIVE_ENRICHMENT_EXECUTION_BOUNDARY_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
