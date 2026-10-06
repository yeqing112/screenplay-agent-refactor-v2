import json
from pathlib import Path

import pytest

from api import director_treatment_api as treatment_api
from core import llm
from core.director_progressive_authoring import (
    build_stage_a_persistence_patch,
    compile_progressive_director_proposal,
    materialize_director_beat_plan_ids,
    validate_director_beat_plan_ir,
    validate_director_beat_plan_ir_schema,
    validate_director_creative_enrichment_ir,
)
from core.prompt_cache import prompt_fingerprint, provider_request_fingerprint_v2, provider_request_payload_v2
from core.director_forensic import append_director_attempt


def _source_units(count=12):
    return [
        {"unit_id": f"SAU_E01_SC001_{index:03d}", "source_type": "SOURCE_DIALOGUE" if index == 8 else "SOURCE_ACTION", "text": f"source {index}"}
        for index in range(1, count + 1)
    ]


def _stage_a(units=None):
    units = units or _source_units()
    return {
        "version": "director_beat_plan_ir_v1",
        "scene_label": "暗房",
        "scene_objective": "把线索从物件推向不信任。",
        "dramatic_question": "谁在操控这场相遇？",
        "beats": [
            {"refs": [unit["unit_id"] for unit in units[index:index + 2]], "purpose": f"purpose {index // 2 + 1}", "objective": f"objective {index // 2 + 1}", "information_change": f"change {index // 2 + 1}", "hook": index == 0}
            for index in range(0, len(units), 2)
        ],
        "passthrough_refs": [],
        "unknowns": ["门外人物身份"],
        "confidence": 0.8,
        "note": "offline golden",
    }


def _stage_b(stage_a):
    materialized = materialize_director_beat_plan_ids(stage_a, scene_id="E01_SC001")
    return {
        "version": "director_creative_enrichment_ir_v1",
        "beat_enrichments": [
            {"beat_ref": beat["beat_ref"], "audience_effect": f"effect {index}", "performance": f"performance {index}", "transition": f"transition {index}", "character_effects": [{"character_ref": "顾沉", "effect": "withhold"}]}
            for index, beat in enumerate(materialized["beats"], 1)
        ],
        "character_directions": [{"character_ref": "顾沉", "direction": "试探而克制"}],
        "performance_arc": ["guarded"],
        "information_strategy": ["reveal object before motive"],
        "rhythm_strategy": {"tempo": "tightening"},
        "visual_priority": ["铁盒", "门缝"],
        "scene_exit_intent": "车票把关系推向分裂。",
        "prohibited_interpretations": ["不得确定门外人物身份"],
        "confidence": 0.75,
        "note": "offline enrichment",
    }


def _baseline(units):
    return {"schema_version": "director_treatment_v3", "scene_id": "E01_SC001", "source_constraints": {"source_authoring_units": units}}


def test_stage_a_schema_and_coverage_is_12_of_12():
    units = _source_units()
    value = _stage_a(units)
    assert validate_director_beat_plan_ir_schema(value)["status"] == "PASS"
    report = validate_director_beat_plan_ir(value, source_units=units)
    assert report["status"] == "qualified"
    assert report["source_unit_count"] == 12
    assert report["covered_source_unit_count"] == 12
    assert report["local_creative_completion_count"] == 0


def test_stage_a_missing_beat_field_fails_closed_without_default_text():
    units = _source_units()
    value = _stage_a(units)
    del value["beats"][0]["objective"]
    report = validate_director_beat_plan_ir(value, source_units=units)
    assert report["status"] == "blocked"
    assert any(error.get("field") == "objective" for error in report["errors"])


def test_stage_b_requires_exactly_one_enrichment_per_stage_a_beat():
    units = _source_units()
    stage_a = _stage_a(units)
    materialized = materialize_director_beat_plan_ids(stage_a, scene_id="E01_SC001")
    report = validate_director_creative_enrichment_ir(_stage_b(stage_a), beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    assert report["status"] == "qualified"
    assert report["beat_coverage"] == "PASS"
    bad = _stage_b(stage_a)
    bad["beat_enrichments"][0]["beat_ref"] = "DBP_UNKNOWN"
    assert validate_director_creative_enrichment_ir(bad, beat_plan=materialized, declared_participants=[{"id": "顾沉"}])["status"] == "blocked"
    missing = _stage_b(stage_a)
    missing["beat_enrichments"].pop()
    assert validate_director_creative_enrichment_ir(missing, beat_plan=materialized, declared_participants=[{"id": "顾沉"}])["status"] == "blocked"


def test_stage_b_cannot_invent_participant_or_replan_stage_a():
    units = _source_units()
    stage_a = _stage_a(units)
    materialized = materialize_director_beat_plan_ids(stage_a, scene_id="E01_SC001")
    bad = _stage_b(stage_a)
    bad["character_directions"] = [{"character_ref": "门外人", "direction": "神秘"}]
    bad["beat_enrichments"][0]["refs"] = ["SAU_INVENTED"]
    report = validate_director_creative_enrichment_ir(bad, beat_plan=materialized, declared_participants=[{"id": "顾沉"}])
    assert report["status"] == "blocked"
    assert any(error["code"] == "DIRECTOR_ENRICHMENT_PARTICIPANT_INVALID" for error in report["errors"])


def test_progressive_final_merge_is_proposed_without_local_semantic_synthesis():
    units = _source_units()
    stage_a = _stage_a(units)
    candidate = compile_progressive_director_proposal(
        beat_plan_ir=stage_a,
        enrichment_ir=_stage_b(stage_a),
        baseline_treatment=_baseline(units),
        source_scene={"scene_id": "E01_SC001", "participants": [{"id": "顾沉"}]},
    )
    assert candidate["schema_version"] == "director_treatment_v3"
    assert candidate["creative_projection"]["status"] == "PROPOSED"
    assert candidate["creative_projection"]["authority"] == "AUTHORIZED_CREATIVE_PROJECTION"
    assert candidate["human_confirmation_required"] is True
    assert candidate["compiler_report"]["local_new_creative_decision_count"] == 0
    assert candidate["compiler_report"]["local_direction_semantic_expansion_count"] == 0
    assert [beat["hook_intent"] for beat in candidate["creative_projection"]["creative_beats"]] == [beat["hook"] for beat in stage_a["beats"]]


def test_stage_a_persistence_patch_does_not_replace_packet_proposal():
    patch = build_stage_a_persistence_patch(ir=_stage_a(), fingerprint="stage-a-fp", authorization_id="auth-a", attempt_id="attempt-5")
    assert patch["progressive_director_authoring"]["stage_a"]["status"] == "VALIDATED"
    assert patch["progressive_director_authoring"]["stage_a"]["authoring_stage"] == "BEAT_PLAN"
    assert "proposal" not in patch


def test_historical_attempts_remain_original_and_are_not_salvaged():
    root = Path(__file__).resolve().parents[1]
    attempt3 = json.loads((root / "docs/canonical-canary/v7_5-real-director-proposal-ir/DIRECTOR_LLM_ATTEMPT_3_AUDIT.json").read_text(encoding="utf-8"))
    attempt4 = json.loads((root / "docs/canonical-canary/v7_6-real-director-proposal-ir-attempt4/DIRECTOR_ATTEMPT4_LEDGER_AUDIT.json").read_text(encoding="utf-8"))
    assert attempt3["status"] == "IR_INVALID"
    assert attempt4["attempt4"]["status"] == "SCHEMA_INVALID"
    completeness = json.loads((root / "docs/canonical-canary/v7_6_1-progressive-director-authoring/ATTEMPT3_ATTEMPT4_COMPLETENESS_AUDIT.json").read_text(encoding="utf-8"))
    assert len(completeness["attempt3"]["incomplete_semantic_strings"]) == 4
    assert completeness["attempt4"]["beat2_objective"] == "让"
    assert completeness["no_default_based_salvage"] is True
    assert completeness["offline_promotion"] is False


def test_future_attempt_ledger_can_record_authoring_stage_without_relabeling_history():
    info = {"director_llm_attempts": [{"attempt_id": "attempt-4", "status": "SCHEMA_INVALID"}]}
    updated = append_director_attempt(info, request_fingerprint="fp", raw_response_sha256="sha", authorization_id="auth", authoring_stage="BEAT_PLAN")
    assert updated["director_llm_attempts"][0]["attempt_id"] == "attempt-4"
    assert "authoring_stage" not in updated["director_llm_attempts"][0]
    assert updated["director_llm_attempts"][1]["authoring_stage"] == "BEAT_PLAN"


def test_provider_request_fingerprint_v2_is_distinct_and_policy_sensitive():
    base = dict(profile_id="p", provider="openai-compatible", model="mimo", base_host="https://example.test", system_prompt_sha256="s", user_prompt_sha256="u", temperature=0.0, max_tokens=4096, response_format={"type": "json_object"}, thinking={"type": "disabled"}, schema_version="director_beat_plan_ir_v1")
    first = provider_request_fingerprint_v2(**base)
    assert first != prompt_fingerprint("s", "u")
    assert first != provider_request_fingerprint_v2(**{**base, "max_tokens": 8192})
    assert first != provider_request_fingerprint_v2(**{**base, "model": "other"})
    assert first != provider_request_fingerprint_v2(**{**base, "response_format": {"type": "json_schema"}})
    payload = provider_request_payload_v2(**{**base, "response_format": {"type": "json_object", "api_key": "secret"}})
    assert "api_key" not in json.dumps(payload, ensure_ascii=False)


def test_director_provider_builder_returns_prompt_and_provider_identity():
    units = _source_units()
    treatment = {"scene_id": "E01_SC001", "source_authoring_units_fingerprint": "units", "source_constraints": {"scene_id": "E01_SC001", "source_authoring_units": units, "declared_participants": []}}
    profile = {"id": "p", "provider": "openai-compatible", "model_name": "mimo", "base_url": "https://example.test/v1", "default_params": {"max_tokens": 4096, "thinking": {"type": "disabled"}}}
    snapshot = {"profile_id": "p", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True, "key_configured": True}
    identity = treatment_api.build_source_grounded_director_provider_request(treatment, {"scene": {}, "characters": []}, profile=profile, profile_snapshot=snapshot)
    second = treatment_api.build_source_grounded_director_provider_request(json.loads(json.dumps(treatment)), {"scene": {}, "characters": []}, profile=json.loads(json.dumps(profile)), profile_snapshot=json.loads(json.dumps(snapshot)))
    assert identity["generation_policy"]["max_tokens"] == 4096
    assert identity["generation_policy"]["temperature"] == 0.0
    assert identity["provider_request_fingerprint_v2"]
    assert identity["provider_request_fingerprint_v2"] != identity["prompt_fingerprint"]
    assert identity["provider_request_fingerprint_v2"] == second["provider_request_fingerprint_v2"]
    assert identity["provider_request_payload_v2"] == second["provider_request_payload_v2"]


def test_llm_audit_records_finish_reason_policy_and_numeric_usage_details(monkeypatch):
    class Response:
        status_code = 200
        headers = {"x-request-id": "req-1"}
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"index": 0, "finish_reason": "length", "message": {"content": "{}"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "completion_tokens_details": {"reasoning_tokens": 2}, "prompt_tokens_details": {"cached_tokens": 4}}}

    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def post(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr(llm.httpx, "Client", Client)
    monkeypatch.setattr(llm._limiter, "wait_if_needed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(llm._limiter, "record", lambda *_args, **_kwargs: None)
    profile = {"id": "p", "provider": "openai-compatible", "model_name": "mimo", "base_url": "https://example.test/v1", "default_params": {"max_tokens": 4096, "thinking": {"type": "disabled"}}}
    audit = []
    result = llm.call_llm("user", system="system", model_profile=profile, retries=1, temperature=0.0, response_format={"type": "json_object"}, audit_callback=audit.append)
    assert result == "{}"
    record = audit[-1]
    assert record["finish_reason"] == "length"
    assert record["choice_index"] == 0
    assert record["resolved_max_tokens"] == 4096
    assert record["resolved_temperature"] == 0.0
    assert record["resolved_response_format"] == {"type": "json_object"}
    assert record["resolved_thinking"] == {"type": "disabled"}
    assert record["usage"]["reasoning_tokens"] == 2
    assert record["usage"]["completion_tokens_details"]["reasoning_tokens"] == 2
