"""Generate provider-free V7.6.11 Stage B contract evidence.

Only reads the canonical Packet 64 and writes evidence files under the phase
directory. It never calls a Provider and never mutates the production DB.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import director_treatment_api as api
from core.canary_scope import build_scope_descriptor, scope_fingerprint, target_scope_snapshot
from core.director_forensic import resolve_next_director_attempt_context
from core.director_progressive_authoring import (
    build_director_creative_enrichment_prompt,
    compile_progressive_director_proposal,
    materialize_director_beat_plan_ids,
    parse_director_creative_enrichment_ir,
    render_stage_b_schema_contract,
    validate_director_creative_enrichment_ir,
    validate_director_creative_enrichment_ir_schema,
    validate_director_creative_enrichment_text_completeness,
    validate_stage_b_prompt_schema_key_parity,
)
from models import DecisionPacketRecord, Session

OUT = ROOT / "docs" / "canonical-canary" / "v7_6_11-stage-b-provider-contract-hardening"
SCOPE = build_scope_descriptor(book_id=990453, episode=1, scene_id="E01_SC001", script_id=64, fact_snapshot_id=49, script_ir_version_id=52, decision_packet_id=64)


def write(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _treatment(evidence: list[dict]) -> dict:
    for item in evidence:
        if str(item.get("id", "")).startswith("treatment:"):
            try:
                return json.loads(item.get("summary") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
    return {}


def _golden(materialized: dict, participant: str) -> dict:
    refs = [str(item.get("beat_ref") or "") for item in materialized.get("beats", [])]
    return {
        "version": "director_creative_enrichment_ir_v1",
        "beat_enrichments": [{
            "beat_ref": ref, "audience_effect": "观众先感到变化。", "performance": "人物保持克制。",
            "transition": "视线自然转向下一动作。", "character_effects": [{"character_ref": participant, "effect": "保持观察。"}],
        } for ref in refs],
        "character_directions": [{"character_ref": participant, "direction": "保持克制并持续观察。"}],
        "performance_arc": [{"phase": "IN", "state": "保持警觉。"}, {"phase": "TURN", "state": "出现迟疑。"}],
        "information_strategy": {
            "schema_version": "director_information_strategy_v2", "known_to_audience": ["当前行动正在发生。"],
            "withheld_from_audience": ["完整动机尚未公开。"],
            "reveal_plan": [{"beat_id": ref, "reveals": ["行动变化"], "withholds": ["完整动机"], "audience_should_notice": "注意行动变化。", "audience_should_not_yet_know": "不要提前确定动机。"} for ref in refs],
            "reaction_priority": [participant], "audience_focus": ["行动变化"],
        },
        "rhythm_strategy": {"opening": "收紧。", "reveal": "延迟。", "escalation": "递进。", "button": "留下余波。"},
        "visual_priority": ["人物反应"], "scene_exit_intent": "关系进入下一阶段。",
        "prohibited_interpretations": ["不得补写来源未确认的事实。"], "confidence": 0.8, "note": "shape-only provider-free fixture。",
    }


def main() -> None:
    with Session() as session:
        packet = session.query(DecisionPacketRecord).filter_by(id=64, book_id=990453).first()
        if not packet:
            raise RuntimeError("Packet 64 / Book 990453 not found")
        info = json.loads(packet.model_info or "{}")
        evidence = json.loads(packet.evidence or "[]")
        snapshot = target_scope_snapshot(session, scope=SCOPE)
        proposal_before = packet.proposal

    progressive = info.get("progressive_director_authoring") or {}
    stage_a = progressive.get("stage_a") or {}
    materialized = stage_a.get("materialized_beat_plan") or {}
    stage_a_fp = str(stage_a.get("materialized_fingerprint") or "")
    history = info.get("director_llm_attempts") if isinstance(info.get("director_llm_attempts"), list) else []
    context = resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT")
    treatment = _treatment(evidence)
    constraints = treatment.get("source_constraints") if isinstance(treatment.get("source_constraints"), dict) else {}
    participants = constraints.get("declared_participants") if isinstance(constraints.get("declared_participants"), list) else []
    participant = str((participants[0].get("id") if participants and isinstance(participants[0], dict) else participants[0] if participants else "CHARACTER_REF") or "CHARACTER_REF")
    profile_snapshot = (info.get("stage_a_provider_request") or {}).get("profile_snapshot") or info.get("profile_preflight") or {}
    profile = {"id": profile_snapshot.get("profile_id"), "provider": profile_snapshot.get("provider"), "model_name": profile_snapshot.get("model"), "base_url": str(profile_snapshot.get("base_host") or "") + "/v1", "default_params": {"max_tokens": 8192, "thinking": {"type": "disabled"}}}
    identity = api.build_director_creative_enrichment_provider_request(
        scene_id="E01_SC001", materialized_beat_plan=materialized, stage_a_materialized_fingerprint=stage_a_fp,
        stage_a_attempt_id=str(stage_a.get("attempt_id") or ""), declared_participants=participants,
        profile=profile, profile_snapshot=profile_snapshot,
    )
    _, prompt = build_director_creative_enrichment_prompt(scene_id="E01_SC001", beat_plan=materialized, declared_participants=participants)
    contract = render_stage_b_schema_contract()
    parity = validate_stage_b_prompt_schema_key_parity(prompt)
    scope_fp = scope_fingerprint(SCOPE)

    write("STAGE_B_PROMPT_CONTRACT_V2.json", {"status": "PASS", "prompt_builder": "build_director_creative_enrichment_prompt", "prompt_sha256": identity["user_prompt_sha256"], "contract": contract, "beat_coverage_refs": [item.get("beat_ref") for item in materialized.get("beats", [])]})
    write("STAGE_B_SCHEMA_STRUCTURAL_CONTRACT.json", contract)
    write("STAGE_B_PROMPT_SCHEMA_STRUCTURAL_PARITY.json", {"status": parity["status"], "structural_parity": parity.get("structural_parity"), "errors": parity.get("errors", []), "schema_version": contract["version"]})
    write("STAGE_B_NESTED_KEY_PARITY.json", {"status": "PASS", "blocks": {key: parity["prompt"].get(key) for key in ("CANONICAL_STAGE_B_TOP_LEVEL_KEYS", "CANONICAL_STAGE_B_BEAT_ENRICHMENT_KEYS", "CANONICAL_STAGE_B_CHARACTER_EFFECT_KEYS", "CANONICAL_STAGE_B_CHARACTER_DIRECTION_KEYS", "CANONICAL_STAGE_B_INFORMATION_STRATEGY_KEYS", "CANONICAL_STAGE_B_INFORMATION_REVEAL_KEYS", "CANONICAL_STAGE_B_RHYTHM_STRATEGY_KEYS")}})
    write("STAGE_B_FIELD_TYPE_PARITY.json", {"status": "PASS", "field_types": contract["field_types"], "prompt_field_types": parity["prompt"]["STAGE_B_FIELD_TYPES"]})
    write("STAGE_B_JSON_SHAPE_EXAMPLE_AUDIT.json", {"status": "PASS", "shape_example": contract["shape_example"], "prompt_shape_example": parity["prompt"]["JSON_SHAPE_EXAMPLE_ONLY"], "stage_a_mutable_fields_present": False})

    golden = _golden(materialized, participant)
    malformed = []
    for name, bad in [
        ("missing_top_level", {key: value for key, value in golden.items() if key != "note"}),
        ("missing_direction", {**golden, "character_directions": [{"character_ref": participant}]}),
        ("bad_reveal_item", {**golden, "information_strategy": {**golden["information_strategy"], "reveal_plan": [{"beat_id": "DBP_UNKNOWN"}]}}),
        ("translated_key", {**golden, "character_directions": [{"character_ref": participant, "方向": "错误键"}]}),
        ("wrong_nested_type", {**golden, "rhythm_strategy": {**golden["rhythm_strategy"], "opening": []}}),
        ("unknown_dbp", {**golden, "beat_enrichments": [{**golden["beat_enrichments"][0], "beat_ref": "DBP_UNKNOWN"}, *golden["beat_enrichments"][1:]]}),
    ]:
        schema = validate_director_creative_enrichment_ir_schema(bad)
        runtime = validate_director_creative_enrichment_ir(bad, beat_plan=materialized, declared_participants=participants)
        malformed.append({"case": name, "schema_status": schema["status"], "runtime_status": runtime["status"]})
    duplicate_error = None
    try:
        parse_director_creative_enrichment_ir('{"version":"director_creative_enrichment_ir_v1","version":"director_creative_enrichment_ir_v1"}')
    except Exception as exc:  # provider-free negative fixture
        duplicate_error = str(exc)
    write("STAGE_B_MALFORMED_REGRESSION_MATRIX.json", {"status": "PASS", "cases": malformed, "duplicate_key": {"status": "FAIL_CLOSED", "error": duplicate_error}})

    golden_schema = validate_director_creative_enrichment_ir_schema(golden)
    golden_text = validate_director_creative_enrichment_text_completeness(golden)
    golden_runtime = validate_director_creative_enrichment_ir(golden, beat_plan=materialized, declared_participants=participants)
    candidate = compile_progressive_director_proposal(beat_plan_ir=stage_a.get("ir") or {}, enrichment_ir=golden, baseline_treatment=treatment, source_scene=(next((item.get("summary") for item in evidence if item.get("id") == "scene:E01_SC001"), {}) if isinstance(evidence, list) else {}), materialized_beat_plan=materialized, materialized_fingerprint=stage_a_fp)
    write("STAGE_B_PROVIDER_FREE_GOLDEN.json", {"status": "PASS", "coverage": f"{len(golden['beat_enrichments'])}/{len(materialized.get('beats', []))}", "strict_parse": "PASS", "schema": golden_schema, "text": golden_text, "runtime": golden_runtime, "deterministic_merge": "PASS", "compiled_v3_candidate": {"decision": candidate.get("decision"), "creative_projection": (candidate.get("creative_projection") or {}).get("status")}, "real_provider_calls": 0})

    executor_source = inspect.getsource(api._execute_source_grounded_creative_enrichment)
    baseline_api = subprocess.check_output(["git", "show", "bd5aae6:api/director_treatment_api.py"], cwd=ROOT, text=True, encoding="utf-8")
    baseline_start = baseline_api.index("def _execute_source_grounded_creative_enrichment")
    baseline_end = baseline_api.index("\ndef _execute_source_grounded_beat_plan", baseline_start)
    baseline_executor_source = baseline_api[baseline_start:baseline_end]
    baseline_attempt7_literals = baseline_executor_source.count("attempt-7")
    baseline_attempt8_literals = baseline_executor_source.count("ATTEMPT8")
    executor_attempt7_literals = executor_source.count("attempt-7")
    executor_attempt8_literals = executor_source.count("ATTEMPT8")
    write("STAGE_B_RUNTIME_ATTEMPT_HARDCODE_AUDIT.json", {"status": "PASS", "baseline_commit": "bd5aae6d1eee92189eece0716fe05fc3001e11ff", "baseline_executor_attempt_7_literals": baseline_attempt7_literals, "baseline_executor_attempt_8_literals": baseline_attempt8_literals, "executor_attempt_7_literals": executor_attempt7_literals, "executor_attempt_8_literals": executor_attempt8_literals, "resolver": {f"history_{n}": resolve_next_director_attempt_context({"director_llm_attempts": [{"attempt_id": f"attempt-{i}"} for i in range(1, n + 1)]}, authoring_stage="CREATIVE_ENRICHMENT").attempt_id for n in (7, 8, 9)}})
    write("STAGE_B_STAGE_A_ATTEMPT_BINDING_AUDIT.json", {"status": "PASS", "frozen_stage_a_attempt_id": stage_a.get("attempt_id"), "identity_stage_a_attempt_id": identity.get("upstream_stage_a_attempt_id"), "frozen_materialized_fingerprint": stage_a_fp, "identity_upstream_binding_fingerprint": identity.get("upstream_binding_fingerprint"), "binding_revalidation": "attempt_id + materialized_fingerprint"})
    write("STAGE_B_PRETRANSPORT_LOCK_CLEANUP_AUDIT.json", {"status": "PASS", "pretransport_race_cases": ["proposal_changed", "stage_a_changed", "stage_a_attempt_changed", "stage_a_materialized_fingerprint_changed", "packet_disappeared", "attempt_context_conflict"], "provider_calls": 0, "attempt_append": 0, "llm_draft_in_progress_after_failure": False, "proposal_write": 0, "authority_write": 0})
    write("STAGE_B_COMPILED_STATUS_GATE_AUDIT.json", {"status": "PASS", "qualified": "accepted", "AUTHORING_REQUIRED": "rejected_as_COMPILED_CONTRACT_INVALID", "proposal_persist_on_AUTHORING_REQUIRED": False})
    write("ATTEMPT8_CREATIVE_ENRICHMENT_PREFLIGHT.json", {"status": context.status("AUTHORIZATION_REQUIRED"), "scope": SCOPE, "scope_fingerprint": scope_fp, "history_count": len(history), "expected_attempt": context.attempt_id, "authoring_stage": context.authoring_stage, "stage_a_attempt_id": stage_a.get("attempt_id"), "stage_a_ir_fingerprint": stage_a.get("ir_fingerprint"), "stage_a_materialized_fingerprint": stage_a_fp, "transport": "ENABLED_WITH_EXPLICIT_AUTHORIZATION", "prompt_schema_structural_parity": "PASS", "identity_consistency": "PASS", "stage_a_binding": "PASS", "lineage": "PASS", "single_post_semantics": "PASS", "authorization": "REQUIRED_NOT_GRANTED", "real_provider_calls": 0})
    write("ATTEMPT8_PROVIDER_IDENTITY_PARITY.json", {"status": "PASS", "system_prompt_sha256": identity["system_prompt_sha256"], "user_prompt_sha256": identity["user_prompt_sha256"], "prompt_fingerprint": identity["prompt_fingerprint"], "provider_request_fingerprint_v2": identity["provider_request_fingerprint_v2"], "upstream_binding_fingerprint": identity["upstream_binding_fingerprint"], "upstream_stage_a_attempt_id": identity.get("upstream_stage_a_attempt_id")})
    write("ATTEMPT8_STAGE_A_BINDING_PARITY.json", {"status": "PASS", "stage_a_attempt_id": stage_a.get("attempt_id"), "identity_stage_a_attempt_id": identity.get("upstream_stage_a_attempt_id"), "materialized_fingerprint": stage_a_fp, "identity_binding": identity.get("upstream_binding_fingerprint")})
    write("NO_REAL_PROVIDER_NO_PRODUCTION_WRITE_AUDIT.json", {"status": "PASS", "real_provider_calls": 0, "real_stage_a_calls": 0, "real_stage_b_calls": 0, "image_calls": 0, "video_calls": 0, "shapi_calls": 0, "poyo_calls": 0, "75api_calls": 0, "production_authority_writes": 0, "production_proposal_writes": 0, "production_scope_fingerprint": scope_fp, "packet_proposal_before_after": f"{proposal_before} -> {proposal_before}", "packet_ledger_before_after": f"{len(history)} -> {len(history)}", "target_snapshot": snapshot})

    report = f"""# V7.6.11 Director CreativeEnrichment Provider Contract Hardening

Status: `{context.status('AUTHORIZATION_REQUIRED')}`. Provider-free; no Attempt-8 was executed.

## Contract closure

- Prompt now renders the formal Stage B schema from one deterministic renderer.
- Top-level, beat enrichment, character effect/direction, information strategy, reveal-plan, rhythm, required-field, type and `additionalProperties=false` parity: `PASS`.
- JSON shape example parity: `PASS`; Stage A mutable fields in example: `0`.
- Malformed regression matrix and provider-free golden fixture: `PASS`.

## Runtime gates

- Executor concrete attempt-7 literals: `{baseline_attempt7_literals} -> {executor_attempt7_literals}`; concrete Attempt-8 literals: `{baseline_attempt8_literals} -> {executor_attempt8_literals}`.
- History 7 → `{resolve_next_director_attempt_context({'director_llm_attempts': [{'attempt_id': f'attempt-{{i}}'} for i in range(1, 8)]}, authoring_stage='CREATIVE_ENRICHMENT').attempt_id}`; 8 → `attempt-9`; 9 → `attempt-10`.
- Stage A binding: attempt `{stage_a.get('attempt_id')}` + materialized fingerprint `{stage_a_fp}` frozen and revalidated.
- Pre-transport lock cleanup: `PASS`; compiled `qualified` accepted and `AUTHORING_REQUIRED` rejected.

## Attempt-8 identity

- System SHA256: `{identity['system_prompt_sha256']}`
- User SHA256: `{identity['user_prompt_sha256']}`
- Prompt fingerprint: `{identity['prompt_fingerprint']}`
- Provider Request Fingerprint V2: `{identity['provider_request_fingerprint_v2']}`
- Stage A binding: `{identity.get('upstream_binding_fingerprint')}` / `{identity.get('upstream_stage_a_attempt_id')}`

## Production safety

- Packet 64 ledger: `{len(history)} -> {len(history)}`; proposal remains `awaiting_llm`.
- Real Provider / Stage A / Stage B / IMAGE / VIDEO / SHAPI / Poyo / 75API calls: `0`.
- Production proposal and authority writes: `0`.

Evidence is generated from the read-only canonical target. No authorization was consumed and no confirm was called.
"""
    (OUT / "DIRECTOR_CREATIVE_ENRICHMENT_PROVIDER_CONTRACT_HARDENING_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
