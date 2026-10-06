import json

import pytest

from api import director_treatment_api as api
from core.director_progressive_authoring import (
    DIRECTOR_BEAT_PLAN_IR_VERSION,
    build_director_beat_plan_prompt,
    materialize_director_beat_plan_ids,
    parse_director_beat_plan_ir,
    validate_director_beat_plan_ir,
    validate_director_beat_plan_ir_schema,
    validate_director_beat_plan_text_completeness,
)


def units():
    return [{"unit_id": f"SAU_E01_SC001_{i:03d}", "source_type": "SOURCE_DIALOGUE" if i == 8 else "SOURCE_ACTION", "source_order": i, "text": f"来源{i}。", **({"speaker": "林晚"} if i == 8 else {})} for i in range(1, 13)]


def ir():
    us = units()
    return {"version": DIRECTOR_BEAT_PLAN_IR_VERSION, "scene_label": "暗房", "scene_objective": "目标推进。", "dramatic_question": "谁在操控？", "beats": [{"refs": [u["unit_id"] for u in us[i:i + 2]], "purpose": "完成分组。", "objective": "推进目标。", "information_change": "增加信息。", "hook": i == 0} for i in range(0, 12, 2)], "passthrough_refs": [], "unknowns": [], "confidence": 0.8, "note": "测试。"}


def profile():
    return {"id": "p", "provider": "openai-compatible", "model_name": "mimo", "base_url": "https://example.test/v1", "default_params": {"max_tokens": 4096, "thinking": {"type": "disabled"}}}


def snapshot():
    return {"profile_id": "p", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test"}


def treatment():
    us = units()
    return {"scene_id": "E01_SC001", "source_authoring_units_fingerprint": "units", "source_constraints": {"scene_id": "E01_SC001", "source_authoring_units": us, "declared_participants": [{"id": "顾沉"}], "explicit_story_constraints": ["不可改写来源。"]}, "unknowns": ["未知事实"]}


def test_dedicated_endpoint_and_old_guard_are_declared():
    routes = {getattr(r, "path", "") for r in api.router.routes}
    assert "/api/books/{book_id}/episodes/{episode}/director-treatment/beat-plan/llm-draft" in routes
    assert "DIRECTOR_PROGRESSIVE_AUTHORING_REQUIRED" in open("api/director_treatment_api.py", encoding="utf-8").read()


def test_stage_a_prompt_is_minimized_and_excludes_stage_b():
    system, user = build_director_beat_plan_prompt(scene_id="E01_SC001", source_units=units(), declared_participants=[], explicit_story_constraints=["x"], unknown_source_facts=["y"])
    assert "EXPLICIT_STORY_CONSTRAINTS" in user and "UNKNOWN_SOURCE_FACTS" in user
    source_block = user.split("SOURCE_AUTHORING_UNITS=", 1)[1].split("DECLARED_PARTICIPANTS=", 1)[0]
    assert "source_evidence" not in source_block and "visual_priority" not in source_block
    assert "BEAT_PLAN_CONTRACT" in user


def test_parse_is_strict_json_object_and_version():
    assert parse_director_beat_plan_ir(json.dumps(ir(), ensure_ascii=False))["version"] == DIRECTOR_BEAT_PLAN_IR_VERSION
    with pytest.raises(ValueError): parse_director_beat_plan_ir("```json {} ```")
    with pytest.raises(ValueError): parse_director_beat_plan_ir(json.dumps({"version": "old"}))


def test_schema_and_runtime_require_exact_coverage():
    value = ir(); assert validate_director_beat_plan_ir_schema(value)["status"] == "PASS"
    report = validate_director_beat_plan_ir(value, source_units=units()); assert report["status"] == "qualified" and report["covered_source_unit_count"] == 12 and report["local_creative_completion_count"] == 0
    value["beats"][-1]["refs"].pop(); assert validate_director_beat_plan_ir(value, source_units=units())["status"] == "blocked"


def test_text_completeness_rejects_fragments_and_placeholders():
    assert validate_director_beat_plan_text_completeness(ir())["status"] == "PASS"
    bad = ir(); bad["beats"][0]["objective"] = "把悬疑从"; assert validate_director_beat_plan_text_completeness(bad)["status"] == "FAIL"
    bad = ir(); bad["scene_objective"] = "TBD。"; assert validate_director_beat_plan_text_completeness(bad)["status"] == "FAIL"


def test_materialized_ids_are_deterministic_and_separate():
    first = materialize_director_beat_plan_ids(ir(), scene_id="E01_SC001"); second = materialize_director_beat_plan_ids(ir(), scene_id="E01_SC001")
    assert [b["beat_ref"] for b in first["beats"]] == ["DBP_E01_SC001_001", "DBP_E01_SC001_002", "DBP_E01_SC001_003", "DBP_E01_SC001_004", "DBP_E01_SC001_005", "DBP_E01_SC001_006"]
    assert first == second and "beat_ref" not in ir()["beats"][0]


def test_provider_identity_parity_and_policy_sensitivity():
    one = api.build_director_beat_plan_provider_request(treatment(), {}, scene_id="E01_SC001", profile=profile(), profile_snapshot=snapshot())
    two = api.build_director_beat_plan_provider_request(json.loads(json.dumps(treatment())), {}, scene_id="E01_SC001", profile=json.loads(json.dumps(profile())), profile_snapshot=json.loads(json.dumps(snapshot())))
    assert one["prompt_fingerprint"] == two["prompt_fingerprint"] and one["provider_request_fingerprint_v2"] == two["provider_request_fingerprint_v2"]
    altered = json.loads(json.dumps(profile())); altered["default_params"]["max_tokens"] = 8192
    three = api.build_director_beat_plan_provider_request(treatment(), {}, scene_id="E01_SC001", profile=altered, profile_snapshot=snapshot())
    assert three["provider_request_fingerprint_v2"] != one["provider_request_fingerprint_v2"]


def test_provider_identity_contains_stage_a_boundary_and_both_hashes():
    value = api.build_director_beat_plan_provider_request(treatment(), {}, scene_id="E01_SC001", profile=profile(), profile_snapshot=snapshot())
    assert value["schema_version"] == "director_beat_plan_ir_v1" and value["authoring_stage"] == "BEAT_PLAN"
    assert value["system_prompt_sha256"] and value["user_prompt_sha256"] and value["prompt_fingerprint"] and value["provider_request_fingerprint_v2"]


def test_provider_identity_internal_consistency_rejects_top_level_payload_mismatch():
    value = api.build_director_beat_plan_provider_request(treatment(), {}, scene_id="E01_SC001", profile=profile(), profile_snapshot=snapshot())
    value["provider_request_payload_v2"]["user_prompt_sha256"] = "stale"
    assert api.validate_director_beat_plan_provider_identity(value)["status"] == "FAIL"


def test_provider_identity_internal_consistency_rejects_actual_prompt_mismatch():
    value = api.build_director_beat_plan_provider_request(treatment(), {}, scene_id="E01_SC001", profile=profile(), profile_snapshot=snapshot())
    value["user_prompt"] += "漂移"
    assert api.validate_director_beat_plan_provider_identity(value)["status"] == "FAIL"


def test_provider_identity_internal_consistency_rejects_stale_provider_fingerprint():
    value = api.build_director_beat_plan_provider_request(treatment(), {}, scene_id="E01_SC001", profile=profile(), profile_snapshot=snapshot())
    value["provider_request_fingerprint_v2"] = "stale"
    assert api.validate_director_beat_plan_provider_identity(value)["status"] == "FAIL"


def test_stage_a_contract_has_no_confirmation_or_stage_b_fields():
    prompt = api.build_director_beat_plan_provider_request(treatment(), {}, scene_id="E01_SC001", profile=profile(), profile_snapshot=snapshot())["user_prompt"]
    assert "REQUIRED_BEAT_FIELDS=refs,purpose,objective,information_change,hook" in prompt
    assert "BEAT_PLAN_CONTRACT=" in prompt and "HOOK_BOOLEAN_CONTRACT=" in prompt
