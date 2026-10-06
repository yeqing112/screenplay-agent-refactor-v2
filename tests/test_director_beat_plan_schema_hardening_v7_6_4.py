import copy
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


def _units():
    return [{"unit_id": f"SAU_E01_SC001_{i:03d}", "source_type": "SOURCE_ACTION", "source_order": i, "text": f"来源动作{i}。"} for i in range(1, 13)]


def _ir(hook=True):
    units = _units()
    return {"version": DIRECTOR_BEAT_PLAN_IR_VERSION, "scene_label": "场景", "scene_objective": "推进目标。", "dramatic_question": "谁在推动事件？", "beats": [{"refs": [u["unit_id"] for u in units[i:i + 2]], "purpose": "完成结构分组。", "objective": "推进导演目标。", "information_change": "增加来源信息。", "hook": hook if i == 0 else False} for i in range(0, 12, 2)], "passthrough_refs": [], "unknowns": [], "confidence": 0.8, "note": "测试。"}


def _treatment():
    units = _units()
    return {"scene_id": "E01_SC001", "source_authoring_units_fingerprint": "units", "source_constraints": {"source_authoring_units": units, "declared_participants": [], "explicit_story_constraints": []}, "unknowns": []}


def test_prompt_declares_hook_boolean_semantics_and_type_boundary():
    system, user = build_director_beat_plan_prompt(scene_id="E01_SC001", source_units=_units())
    contract = "beats[].hook:boolean"
    assert contract in user
    assert "MUST be a JSON boolean literal true or false" in user
    assert "NEVER output a string for hook" in user
    assert "hook=true means" in user and "hook=false means" in user
    assert "hook is only a classification flag" in user
    assert "beats[].hook 是 boolean" in system


@pytest.mark.parametrize("bad", ["true", "false", "制造悬念。", 1, None])
def test_hook_wrong_types_fail_schema_without_coercion_or_repair(bad):
    value = _ir(); original = copy.deepcopy(value); value["beats"][0]["hook"] = bad
    assert parse_director_beat_plan_ir(json.dumps(value, ensure_ascii=False)) == value
    report = validate_director_beat_plan_ir_schema(value)
    assert report["status"] == "FAIL"
    assert any(error.get("path") == "$.beats[0].hook" and error.get("code") == "SCHEMA_TYPE_INVALID" for error in report["errors"])
    assert value == {**original, "beats": [{**original["beats"][0], "hook": bad}, *original["beats"][1:]]}


@pytest.mark.parametrize("hook", [True, False])
def test_boolean_hooks_pass_schema_runtime_and_materialize_without_semantic_change(hook):
    value = _ir(hook)
    assert validate_director_beat_plan_ir_schema(value)["status"] == "PASS"
    runtime = validate_director_beat_plan_ir(value, source_units=_units())
    assert runtime["status"] == "qualified" and runtime["covered_source_unit_count"] == 12 and runtime["local_creative_completion_count"] == 0
    materialized = materialize_director_beat_plan_ids(value, scene_id="E01_SC001")
    assert materialized["beats"][0]["hook"] is hook


def test_attempt5_shape_is_read_only_schema_diagnostic_with_only_hook_errors():
    # The persisted raw is inspected without rewriting or repairing it.
    from pathlib import Path
    forensic = json.loads((Path("docs/canonical-canary/v7_6_3-attempt5-stage-a-canary/ATTEMPT5_RAW_FORENSIC.json")).read_text(encoding="utf-8"))
    raw = parse_director_beat_plan_ir(forensic["raw_response"])
    report = validate_director_beat_plan_ir_schema(raw)
    assert report["status"] == "FAIL"
    assert len(report["errors"]) == 6
    assert {error["path"] for error in report["errors"]} == {f"$.beats[{i}].hook" for i in range(6)}
    assert raw["confidence"] == "high"  # explicitly allowed by the contract


def test_attempt6_identity_changes_and_remains_internally_consistent():
    value = api.build_director_beat_plan_provider_request(_treatment(), {}, scene_id="E01_SC001", profile={"id": "p", "provider": "openai-compatible", "model_name": "mimo", "base_url": "https://example.test/v1", "default_params": {"max_tokens": 4096, "thinking": {"type": "disabled"}}}, profile_snapshot={"profile_id": "p", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test"})
    assert api.validate_director_beat_plan_provider_identity(value)["status"] == "PASS"
    assert value["prompt_fingerprint"]
    assert value["provider_request_fingerprint_v2"]
