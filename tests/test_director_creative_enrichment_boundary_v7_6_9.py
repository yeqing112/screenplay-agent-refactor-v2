import copy
import hashlib
import json

import pytest

from api import director_treatment_api as api
from core.director_forensic import append_director_attempt, resolve_next_director_attempt_context
from core.director_progressive_authoring import (
    build_director_creative_enrichment_prompt,
    build_stage_b_persistence_patch,
    compile_progressive_director_proposal,
    is_progressive_stage_validated,
    materialize_director_beat_plan_ids,
    parse_director_creative_enrichment_ir,
    render_stage_b_schema_contract,
    validate_director_creative_enrichment_ir,
    validate_director_creative_enrichment_ir_schema,
    validate_director_creative_enrichment_text_completeness,
    validate_stage_b_prompt_schema_key_parity,
)


def stage_a():
    units = [{"unit_id": f"SAU_{i:03d}", "source_type": "SOURCE_ACTION", "text": f"动作{i}"} for i in range(1, 5)]
    return {
        "version": "director_beat_plan_ir_v1", "scene_label": "暗房", "scene_objective": "线索把关系推向不信任。",
        "dramatic_question": "谁在操控这场相遇？", "beats": [
            {"refs": ["SAU_001", "SAU_002"], "purpose": "建立戒备。", "objective": "确认铁盒来源。", "information_change": "观众知道铁盒已被调包。", "hook": True},
            {"refs": ["SAU_003", "SAU_004"], "purpose": "把冲突推向门口。", "objective": "逼出下一步反应。", "information_change": "观众仍不知道门外身份。", "hook": False},
        ], "passthrough_refs": [], "unknowns": ["门外身份"], "confidence": 0.8, "note": "离线固定夹具。",
    }, units


def stage_b(materialized):
    return {
        "version": "director_creative_enrichment_ir_v1",
        "beat_enrichments": [{"beat_ref": beat["beat_ref"], "audience_effect": "观众先感到不安。", "performance": "人物压住情绪。", "transition": "视线切向门缝。", "character_effects": [{"character_ref": "顾沉", "effect": "保持试探。"}]} for beat in materialized["beats"]],
        "character_directions": [{"character_ref": "顾沉", "direction": "克制地试探。"}],
        "performance_arc": [{"phase": "IN", "state": "戒备。"}, {"phase": "TURN", "state": "失控边缘。"}, {"phase": "OUT", "state": "保留退路。"}],
        "information_strategy": {"schema_version": "director_information_strategy_v2", "known_to_audience": ["铁盒出现。"], "withheld_from_audience": ["门外身份。"], "reveal_plan": [{"beat_id": materialized["beats"][0]["beat_ref"], "reveals": ["铁盒"], "withholds": ["动机"], "audience_should_notice": "铁盒被反复确认。", "audience_should_not_yet_know": "门外身份。"}], "reaction_priority": ["顾沉"], "audience_focus": ["铁盒"]},
        "rhythm_strategy": {"opening": "收紧。", "reveal": "延迟。", "escalation": "压缩。", "button": "停在门缝。"},
        "visual_priority": ["铁盒", "门缝"], "scene_exit_intent": "车票把关系推向分裂。", "prohibited_interpretations": ["不得确定门外身份。"], "confidence": 0.75, "note": "离线固定夹具。",
    }


def test_stage_b_contract_prompt_and_schema_parity():
    materialized = materialize_director_beat_plan_ids(stage_a()[0], scene_id="E01_SC001")
    system, prompt = build_director_creative_enrichment_prompt(scene_id="E01_SC001", beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    assert system and validate_stage_b_prompt_schema_key_parity(prompt)["status"] == "PASS"
    assert render_stage_b_schema_contract()["information_strategy_keys"]
    assert validate_director_creative_enrichment_ir_schema(stage_b(materialized))["status"] == "PASS"


def test_stage_b_validates_coverage_participants_and_text():
    raw, units = stage_a()
    materialized = materialize_director_beat_plan_ids(raw, scene_id="E01_SC001")
    valid = stage_b(materialized)
    report = validate_director_creative_enrichment_ir(valid, beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    assert report["status"] == "qualified" and report["beat_coverage"] == "PASS"
    assert validate_director_creative_enrichment_text_completeness(valid)["status"] == "PASS"
    invalid = copy.deepcopy(valid)
    invalid["character_directions"][0]["character_ref"] = "不存在"
    assert validate_director_creative_enrichment_ir(invalid, beat_plan=materialized, declared_participants=[{"id": "顾沉"}])["status"] == "blocked"
    invalid = copy.deepcopy(valid)
    invalid["beat_enrichments"].pop()
    assert validate_director_creative_enrichment_ir(invalid, beat_plan=materialized, declared_participants=[{"id": "顾沉"}])["status"] == "blocked"


def test_duplicate_key_and_stage_a_binding_are_fail_closed():
    with pytest.raises(ValueError, match="DIRECTOR_CREATIVE_ENRICHMENT_DUPLICATE_JSON_KEY|DIRECTOR_BEAT_PLAN_DUPLICATE_JSON_KEY"):
        parse_director_creative_enrichment_ir('{"version":"director_creative_enrichment_ir_v1","version":"director_creative_enrichment_ir_v1"}')
    raw, _ = stage_a(); materialized = materialize_director_beat_plan_ids(raw, scene_id="E01_SC001")
    fp = hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert build_stage_b_persistence_patch(ir=stage_b(materialized), fingerprint="b", authorization_id="auth", attempt_id="attempt-8", stage_a_materialized_fingerprint=fp)["progressive_director_authoring"]["stage_b"]["status"] == "VALIDATED"
    with pytest.raises(ValueError):
        compile_progressive_director_proposal(beat_plan_ir=raw, enrichment_ir=stage_b(materialized), baseline_treatment={"source_constraints": {"source_authoring_units": []}}, source_scene={"scene_id": "E01_SC001", "participants": [{"id": "顾沉"}]}, materialized_beat_plan=materialized, materialized_fingerprint="wrong")


def test_attempt_context_generalizes_stage_b_without_relabeling_history():
    info = {"director_llm_attempts": [{"attempt_id": f"attempt-{i}", "status": "OLD"} for i in range(1, 8)]}
    ctx = resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT")
    assert ctx.attempt_id == "attempt-8" and ctx.status("AUTHORIZATION_REQUIRED") == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_AUTHORIZATION_REQUIRED"
    updated = append_director_attempt(info, request_fingerprint="fp", raw_response_sha256="sha", authorization_id="auth", authoring_stage="CREATIVE_ENRICHMENT", attempt_context=ctx)
    assert updated["director_llm_attempts"][-1]["attempt_id"] == "attempt-8"
    assert resolve_next_director_attempt_context(updated, authoring_stage="CREATIVE_ENRICHMENT").attempt_id == "attempt-9"


def test_provider_identity_binds_stage_a_and_has_no_transport():
    raw, _ = stage_a(); materialized = materialize_director_beat_plan_ids(raw, scene_id="E01_SC001")
    fp = hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    identity = api.build_director_creative_enrichment_provider_request(scene_id="E01_SC001", materialized_beat_plan=materialized, stage_a_materialized_fingerprint=fp, declared_participants=[{"id": "顾沉"}], profile={"id": "p", "provider": "openai-compatible", "model_name": "mimo", "base_url": "https://example.test/v1", "default_params": {"max_tokens": 4096, "thinking": {"type": "disabled"}}}, profile_snapshot={"profile_id": "p", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True})
    assert identity["authoring_stage"] == "CREATIVE_ENRICHMENT"
    assert identity["provider_request_payload_v2"]["upstream_binding_fingerprint"] == fp
    assert api.validate_director_creative_enrichment_provider_identity(identity)["status"] == "PASS"
    assert is_progressive_stage_validated({"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED", "authoring_stage": "CREATIVE_ENRICHMENT"}, authoring_stage="CREATIVE_ENRICHMENT")
