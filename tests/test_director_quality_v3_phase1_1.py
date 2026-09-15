from __future__ import annotations

import copy

import pytest

from core.director_scene_strategy import build_strategy_contract
from core.director_scene_strategy_ir import validate_strategy_ir
from core.director_scene_strategy_ir_compiler import (
    compile_ir_to_canonical,
    creative_core_fingerprint,
    legacy_v1_to_ir,
)
from core.director_scene_strategy_semantic_spec import (
    IR_SCHEMA_VERSION,
    build_beat_alias_table,
    build_provider_skeleton,
    semantic_spec,
)
from core.director_strategy_format_repair import build_strategy_format_repair_packet
from core.director_strategy_prompt import build_scene_strategy_ir_prompt
from core.director_strategy_quality import compare_strategies, diagnose_directing_content


def contract():
    return build_strategy_contract(
        scene={"scene_id": "s1", "name": "测试", "beats": [{"beat_id": "B1", "event": "门响"}, {"beat_id": "B2", "event": "人物回头"}, {"beat_id": "B3", "event": "照片出现"}]},
        treatment={"scene_id": "s1", "character_intents": {"C1": {"goal": "隐藏照片"}, "C2": {"goal": "追问来源"}}},
        blocking={"scene_id": "s1", "participants": [{"character_id": "C1"}, {"character_id": "C2"}]},
        fact_snapshot={"records": [{"fact_id": "F1"}]},
    )


def phase(ids, power="NONE", ref=None):
    return {
        "phase_id": f"P{ids[0]}", "beat_ids": ids, "dramatic_function": "推进门与照片的怀疑",
        "audience_state": {"knows": ["门响"], "suspects": ["有人隐瞒"], "withholds": ["照片来源"], "question_shift": "从异常转向身份"},
        "emotion": {"state": "不安", "trigger": "门响", "transition_reason": "异常打破平静", "intensity_hint": 4},
        "power": {"center_type": power, "center_ref": ref, "description": "照片掌握信息" if power != "NONE" else "", "shift": "控制权改变"},
        "performance": [{"character_id": "C1", "objective": "隐藏", "tactic": "回避", "visible_behavior": "收手", "turning_point": False}],
        "edit": {"tempo": "缓慢", "hold_logic": "在门响后停留", "cut_logic": "动作完成时切换", "transition_motivation": "信息发生变化"},
        "visual": {"visual_grammar": "共享空间逐步隔离", "camera_rule": "认知变化才推进", "composition_rule": "门框切割关系", "movement_condition": "仅在照片出现时移动"},
        "information": {"reveal": ["门响"] if ids[0] == "B1" else ["照片出现"] if "B3" in ids else [], "hint": ["手部停顿"], "withhold": ["照片来源"], "source_refs": ["F1"]},
    }


def valid_ir(c=None):
    c = c or contract()
    return {"schema_version": IR_SCHEMA_VERSION, "scene_id": "s1", "dramatic_objective": "让观众从日常门响转向怀疑照片来源", "scene_question": "谁在隐藏照片的来源？", "strategy_summary": "以门响、回头和照片出现构成三段递进", "visual_thesis": "共享空间逐步被门框切割", "scene_phases": [phase(["B1"]), phase(["B2"]), phase(["B3"], "INFORMATION", None)], "spatial_expression": ["沿用 blocking"], "prop_visual_strategy": ["F1照片作为信息锚点"], "shot_architecture_guidance": {"required_functions": ["establishing", "reaction"]}, "must_preserve": ["门响顺序"], "must_avoid": ["提前展示照片来源"], "creative_risks": ["若反应缺失则信息跳跃"]}


def test_semantic_spec_and_skeleton_are_ssot():
    spec = semantic_spec()
    assert spec["schema_version"].endswith("_v1")
    skeleton = build_provider_skeleton(scene_id="s1", beat_ids=["B1", "B2"], character_ids=["C1"], fact_ids=["F1"])
    assert skeleton["schema_version"] == IR_SCHEMA_VERSION
    assert "strategy_fingerprint" in spec["forbidden_model_fields"]
    assert skeleton["beat_alias_table"]["aliases"]["1"] == "B1"


@pytest.mark.parametrize("mutator,code", [
    (lambda x: x["scene_phases"][0].update(beat_ids=["B9"]), "UNKNOWN_BEAT_REFERENCE"),
    (lambda x: x["scene_phases"][0]["performance"][0].update(character_id="C9"), "UNKNOWN_CHARACTER_REFERENCE"),
    (lambda x: x["scene_phases"][0]["information"].update(reveal=["未来结果"]), "FACT_INVENTION"),
    (lambda x: x.update(shots=[]), "FORBIDDEN_IR_FIELD"),
    (lambda x: x["scene_phases"][0]["power"].update(center_type="CHARACTER", center_ref="C9", description="x"), "INVALID_POWER_CONTROLLER"),
])
def test_ir_negative_cases(mutator, code):
    raw = valid_ir(); mutator(raw)
    result = validate_strategy_ir(raw, contract=contract())
    assert not result["valid"]
    assert any(e["code"] == code for e in result["errors"])


def test_ambiguous_alias_is_rejected():
    c = build_strategy_contract(scene={"scene_id": "s1", "beats": [{"beat_id": "B1", "event": "a"}, {"beat_id": "1", "event": "b"}]}, blocking={"scene_id": "s1"})
    raw = valid_ir(); raw["scene_phases"][0]["beat_ids"] = ["1"]
    result = validate_strategy_ir(raw, contract=c)
    assert any(e["code"] in {"AMBIGUOUS_BEAT_ALIAS", "UNKNOWN_BEAT_REFERENCE"} for e in result["errors"])


def test_future_reveal_is_rejected():
    raw = valid_ir(); raw["scene_phases"][0]["information"]["reveal"] = ["照片出现"]
    result = validate_strategy_ir(raw, contract=contract())
    assert any(e["code"] == "FUTURE_REVEAL" for e in result["errors"])


def test_beat_chronology_is_preserved():
    raw = valid_ir(); raw["scene_phases"][0]["beat_ids"], raw["scene_phases"][1]["beat_ids"] = ["B2"], ["B1"]
    result = validate_strategy_ir(raw, contract=contract())
    assert any(e["code"] == "BEAT_CHRONOLOGY_INVALID" for e in result["errors"])


def test_ir_positive_power_na_and_compiler_fingerprint():
    raw = valid_ir(); raw["scene_phases"][0]["power"] = {"center_type": "NONE", "center_ref": None, "description": "", "shift": "N/A"}
    checked = validate_strategy_ir(raw, contract=contract()); assert checked["valid"]
    canonical = compile_ir_to_canonical(ir=raw, contract=contract())
    assert canonical["schema_version"] == "director_scene_strategy_v2"
    assert canonical["normalized_beat_ids"] == ["B1", "B2", "B3"]
    assert canonical["strategy_fingerprint"]
    assert canonical["creative_core_fingerprint"]


def test_fingerprint_ignores_scene_identity_but_changes_creative_content():
    a = compile_ir_to_canonical(ir=valid_ir(), contract=contract())
    b = copy.deepcopy(a); b["scene_id"] = "other"; b["strategy_fingerprint"] = "x"; b["creative_core_fingerprint"] = "y"
    assert creative_core_fingerprint(a) == creative_core_fingerprint(b)
    b["visual_thesis"] = "完全不同的视觉命题"
    assert creative_core_fingerprint(a) != creative_core_fingerprint(b)


def test_fake_provider_fingerprint_does_not_trigger_distinctiveness():
    a = compile_ir_to_canonical(ir=valid_ir(), contract=contract()); b = copy.deepcopy(a); b["scene_id"] = "s2"; b["strategy_fingerprint"] = "a1b2c3d4"
    result = compare_strategies([a, b])
    assert result["hard_failure"] is True  # identical creative core is real reuse
    b["visual_thesis"] = "另一个场景特有的视觉命题"; b["strategy_fingerprint"] = "a1b2c3d4"
    assert compare_strategies([a, b])["hard_failure"] is False


def test_protocol_invalid_content_can_remain_usable():
    raw = valid_ir(); raw["shots"] = []
    result = diagnose_directing_content(strategy={"dramatic_objective": raw["dramatic_objective"], "scene_question": raw["scene_question"], "scene_phases": raw["scene_phases"], "visual_grammar": {"overall": "门框"}, "camera_principles": ["认知变化才推进"], "performance_arc": [{"objective": "x", "tactic_progression": ["a", "b"], "visible_behavior_progression": ["a", "b"], "turning_point": "B2"}], "edit_arc": {"tempo_progression": "x", "hold_points": ["x"], "cut_motivations": ["x"], "reveal_timing": "x"}, "information_reveal_plan": [{"reveal": ["门响"]}], "must_avoid": ["x", "y"], "creative_risks": ["x"]})
    assert result["directing_content_status"] != "DIRECTING_WEAK"


def test_format_repair_is_protocol_only_and_prompt_excludes_fingerprint():
    packet = build_strategy_format_repair_packet(errors=[{"code": "UNKNOWN_BEAT_REFERENCE", "path": "scene_phases[0].beat_ids[0]"}], contract=contract())
    assert packet["semantic_rewrite_allowed"] is False
    prompt = build_scene_strategy_ir_prompt(evidence={"strategy_contract": contract()})
    assert "strategy_fingerprint" in prompt["computed_fields_excluded"]
    assert "strategy_fingerprint" not in prompt["provider_contract"]["minimal_skeleton"]


def test_legacy_replay_preserves_non_provider_fingerprint():
    legacy = {"scene_id": "s1", "dramatic_objective": "objective", "scene_question": "question", "strategy_summary": "summary", "visual_grammar": "visual", "camera_principles": "camera", "composition_principles": "composition", "edit_arc": "edit", "must_avoid": ["avoid"], "creative_risks": ["risk"], "spatial_expression": ["space"], "prop_visual_strategy": ["N/A"], "shot_architecture_guidance": {"required_functions": ["reaction"]}, "must_preserve": ["facts"], "audience_experience": [{"beat_id": "1", "experience": "x"}, {"beat_id": "2", "experience": "y"}, {"beat_id": "3", "experience": "z"}], "performance_arc": {"C1": {"objective": "x", "tactic_progression": "a", "visible_behavior_progression": "b", "turning_point": "B2"}}}
    ir = legacy_v1_to_ir(raw=legacy, contract=contract())
    assert "strategy_fingerprint" not in ir
