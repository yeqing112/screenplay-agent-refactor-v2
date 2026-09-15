from __future__ import annotations

import copy

from core.director_scene_strategy_ir_v2 import validate_strategy_ir_v2
from core.director_scene_strategy_ir_compiler_v2 import compile_ir_v2_to_canonical_v3
from core.director_scene_strategy_semantic_spec_v2 import build_source_ref_contract
from core.director_strategy_quality import compare_canonical_strategies
from core.director_strategy_to_shot_contract import build_strategy_to_shot_contract
from core.director_strategy_renderer import render_director_brief_v3
from scripts.run_director_quality_v3_phase1_3 import _positive_fixture


def test_v2_scalar_shapes_normalize_and_compile_to_v3():
    raw, contract = _positive_fixture()
    checked = validate_strategy_ir_v2(raw, contract=contract)
    assert checked["valid"]
    canonical = compile_ir_v2_to_canonical_v3(ir=raw, contract=contract)
    assert canonical["schema_version"] == "director_scene_strategy_v3"
    assert canonical["prop_visual_strategy"] == []
    assert isinstance(canonical["spatial_expression"], list)
    assert canonical["source_trace"]["phases"][0]["reveal_refs"] == ["beat:1"]
    assert canonical["strategy_fingerprint"] and canonical["creative_core_fingerprint"]


def test_source_refs_and_epistemic_support_are_structural():
    raw, contract = _positive_fixture()
    raw = copy.deepcopy(raw); raw["scene_phases"][0]["information"]["reveal_refs"] = ["beat:999"]
    result = validate_strategy_ir_v2(raw, contract=contract)
    assert any(error["code"] == "UNKNOWN_SOURCE_REFERENCE" for error in result["errors"])
    raw, contract = _positive_fixture(); raw["scene_phases"][0]["information"]["audience_suspicions"] = [{"claim": "无依据猜测", "support_refs": []}]
    result = validate_strategy_ir_v2(raw, contract=contract)
    assert any(error["code"] == "UNSUPPORTED_INFERENCE" for error in result["errors"])


def test_future_reveal_and_hint_are_rejected_but_withhold_is_allowed():
    raw, contract = _positive_fixture(); raw["scene_phases"][0]["information"]["reveal_refs"] = ["beat:3"]
    assert any(error["code"] == "FUTURE_REVEAL" for error in validate_strategy_ir_v2(raw, contract=contract)["errors"])
    raw, contract = _positive_fixture(); raw["scene_phases"][0]["information"]["hint_refs"] = ["beat:3"]
    assert any(error["code"] == "FUTURE_HINT_EVIDENCE" for error in validate_strategy_ir_v2(raw, contract=contract)["errors"])


def test_distinctiveness_partial_cohort_is_not_evaluated():
    result = compare_canonical_strategies([])
    assert result["expected_scene_count"] == 3
    assert result["expected_pair_count"] == 3
    assert result["pair_count"] == 0
    assert result["all_pairs_checked"] is False
    assert result["status"] == "DISTINCTIVENESS_NOT_EVALUATED"


def test_strategy_to_shot_contract_accepts_canonical_v3_trace_source():
    raw, contract = _positive_fixture()
    canonical = compile_ir_v2_to_canonical_v3(ir=raw, contract=contract)
    draft = {"shots": [{"plan_shot_id": "S01", "beat_id": "1", "dramatic_function": "建立", "audience_information_state": "知道", "emotion_phase": "不安", "power_state": "C1", "edit_function": "建立", "camera_motivation": "认知变化", "performance_function": "停顿"}]}
    trace = build_strategy_to_shot_contract(strategy=canonical, draft_shot_plan=draft)
    assert trace["strategy_schema_version"] == "director_scene_strategy_v3"
    assert trace["strategy_schema_supported"] is True


def test_renderer_resolves_refs_for_display_without_validating_them():
    raw, contract = _positive_fixture()
    canonical = compile_ir_v2_to_canonical_v3(ir=raw, contract=contract)
    brief = render_director_brief_v3(strategy=canonical, contract={**contract, "beats": {"1": {"event": "门响"}}})
    assert "门响" in brief
    assert "Director Brief" in brief
