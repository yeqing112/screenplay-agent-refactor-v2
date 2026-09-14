import copy

import pytest

from core.director_overdirecting import detect_over_directing
from core.director_patch_validator import compile_and_validate_creative_patches
from core.director_scene_repair_contract import build_scene_repair_contract
from core.director_scene_repair_ir_compiler import compile_scene_repair_ir
from core.director_scene_repair_semantic_spec import SceneRepairIRSchemaError, validate_scene_repair_ir
from core.director_scene_repair_value_ceiling import execute_bounded_scene_repair


def candidate(count=4):
    return {"scene_id": "SCENE", "scene_name": "Scene", "shots": [{
        "plan_shot_id": f"S{i:02d}", "beat_id": f"B{i:02d}", "event": f"beat {i}", "dialogue": f"line {i}", "participants": ["C1"],
        "action_beats": [], "entry_state": {"n": i - 1}, "exit_state": {"n": i}, "asset_bindings": {"scene_asset_id": "A1"},
        "continuity_contract": {"screen_direction": "maintain"}, "continuity": "inherit", "purpose": "action",
        "camera": {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "center"},
    } for i in range(1, count + 1)]}


def contract(c):
    return build_scene_repair_contract(candidate=c, scene_id="SCENE")


def test_scene_scope_freezes_required_authority_fields():
    c = contract(candidate())
    for field in ("event", "dialogue", "participants", "character_id", "asset_bindings", "entry_state", "exit_state", "continuity_contract", "plan_shot_id", "shot_count", "shot_order"):
        assert field in c["immutable_fields"]


def test_scene_contract_has_dimension_and_shot_budgets():
    c = contract(candidate(10))
    assert c["dimension_budget"]["max_dimensions"] == 5
    assert c["shot_budget"]["max_shots"] == 8


def test_multi_shot_multi_dimension_repair_compiles():
    result = execute_bounded_scene_repair(candidate=candidate())
    assert result["validation"]["contract_pass"] is True
    assert result["compiled"]["patch_count"] >= 1
    assert len(result["candidate"]["shots"]) == 4


def test_ir_rejects_canonical_paths():
    with pytest.raises(SceneRepairIRSchemaError):
        validate_scene_repair_ir({"schema_version": "director_scene_repair_ir_v1", "scene_id": "S", "strategy_summary": "x", "target_dimensions": ["EDIT_RHYTHM"], "scene_level_intent": "x", "shot_decisions": [{"plan_shot_id": "S01", "edit": {"/shots/0/edit/cut_reason": "x"}}]})


def test_ir_rejects_unknown_shot_id():
    with pytest.raises(SceneRepairIRSchemaError):
        validate_scene_repair_ir({"schema_version": "director_scene_repair_ir_v1", "scene_id": "S", "strategy_summary": "x", "target_dimensions": ["EDIT_RHYTHM"], "scene_level_intent": "x", "shot_decisions": [{"plan_shot_id": "S99", "edit": {"cut_reason": "x"}}]}, known_plan_shot_ids={"S01"})


def test_ir_rejects_unknown_character_id():
    with pytest.raises(SceneRepairIRSchemaError):
        validate_scene_repair_ir({"schema_version": "director_scene_repair_ir_v1", "scene_id": "S", "strategy_summary": "x", "target_dimensions": ["PERFORMANCE_DIRECTION"], "scene_level_intent": "x", "shot_decisions": [{"plan_shot_id": "S01", "performance_direction": [{"character_id": "C9", "objective": "x", "visible_behavior": "x"}]}]}, known_plan_shot_ids={"S01"}, allowed_character_ids={"C1"})


def test_compiler_enforces_scene_dimension_and_affected_shot_budgets():
    c = contract(candidate(10))
    too_many_dimensions = {
        "schema_version": "director_scene_repair_ir_v1", "scene_id": "SCENE", "strategy_summary": "x",
        "target_dimensions": ["DRAMATIC_CLARITY", "SHOT_MOTIVATION", "EMOTIONAL_PROGRESSION", "VISUAL_STORYTELLING", "PERFORMANCE_DIRECTION", "EDIT_RHYTHM"],
        "scene_level_intent": "x", "shot_decisions": [{"plan_shot_id": "S01", "purpose": "x"}],
    }
    with pytest.raises(SceneRepairIRSchemaError):
        compile_scene_repair_ir(too_many_dimensions, contract=c)
    too_many_shots = {
        "schema_version": "director_scene_repair_ir_v1", "scene_id": "SCENE", "strategy_summary": "x",
        "target_dimensions": ["SHOT_MOTIVATION"], "scene_level_intent": "x",
        "shot_decisions": [{"plan_shot_id": f"S{i:02d}", "purpose": "x"} for i in range(1, 9)],
    }
    with pytest.raises(SceneRepairIRSchemaError):
        compile_scene_repair_ir(too_many_shots, contract=c)


def test_contract_publishes_id_rules():
    rules = contract(candidate())["id_rules"]
    assert rules["plan_shot_id_required"] is True
    assert rules["duplicate_shot_ids_rejected"] is True


def test_compiler_generates_canonical_patch_paths():
    c = contract(candidate())
    ir = {"schema_version": "director_scene_repair_ir_v1", "scene_id": "SCENE", "strategy_summary": "x", "target_dimensions": ["EDIT_RHYTHM"], "scene_level_intent": "x", "shot_decisions": [{"plan_shot_id": "S01", "edit": {"cut_reason": "on action", "duration_seconds": 2.0}}]}
    result = compile_scene_repair_ir(ir, contract=c)
    assert result["patch_document"]["patches"][0]["changes"]["edit.cut_reason"] == "on action"
    assert all("/shots/" not in path for path in result["source_ir"]["shot_decisions"][0].get("edit", {}))


@pytest.mark.parametrize("field", ["event", "dialogue", "participants", "asset_bindings", "entry_state", "exit_state", "continuity_contract", "scene_id"])
def test_fact_and_identity_changes_rejected(field):
    c = candidate()
    patch_value = {"schema_version": "director_creative_patch_v1", "patches": [{"plan_shot_id": "S01", "changes": {field: "bad"}}], "auxiliary_shot_proposals": []}
    result = compile_and_validate_creative_patches(c, patch_value, contract(c))
    assert result["contract_pass"] is False


def test_topology_add_delete_reorder_rejected_by_scene_contract_validation():
    c = candidate()
    result = execute_bounded_scene_repair(candidate=c)
    mutated = copy.deepcopy(result["candidate"])
    mutated["shots"].append({"plan_shot_id": "S99"})
    assert result["contract"]["topology_fingerprint"] != build_scene_repair_contract(candidate=mutated, scene_id="SCENE")["topology_fingerprint"]
    mutated = copy.deepcopy(result["candidate"])
    mutated["shots"][0], mutated["shots"][1] = mutated["shots"][1], mutated["shots"][0]
    assert result["contract"]["topology_fingerprint"] != build_scene_repair_contract(candidate=mutated, scene_id="SCENE")["topology_fingerprint"]


def test_over_directing_policy_and_shot_inflation_zero():
    result = execute_bounded_scene_repair(candidate=candidate())
    over = result["validation"]["quality_issues"]
    assert result["candidate"]["shots"]
    assert result["contract"]["topology_rules"]["auxiliary_shots_allowed"] is False
    assert not any(item.get("code") == "SHOT_INFLATION" for item in over)


def test_camera_coherence_reason_is_present():
    result = execute_bounded_scene_repair(candidate=candidate())
    camera_decisions = [item for item in result["ir"]["shot_decisions"] if "camera" in item]
    assert camera_decisions and all(item.get("reason") for item in camera_decisions)


def test_emotion_values_are_bounded_and_progressive():
    result = execute_bounded_scene_repair(candidate=candidate())
    values = [item["emotion"]["intensity"] for item in result["ir"]["shot_decisions"] if "emotion" in item]
    assert values and all(0 <= value <= 10 for value in values) and len(set(values)) > 1


def test_edit_values_have_cut_reason_and_positive_duration():
    result = execute_bounded_scene_repair(candidate=candidate())
    edits = [item["edit"] for item in result["ir"]["shot_decisions"] if "edit" in item]
    assert edits and all(edit["cut_reason"] and edit["duration_seconds"] > 0 for edit in edits)


def test_information_strategy_uses_current_beat_only():
    result = execute_bounded_scene_repair(candidate=candidate())
    for decision in result["ir"]["shot_decisions"]:
        if "information_strategy" in decision:
            assert decision["information_strategy"]["reveals"]
            assert "what follows" in decision["information_strategy"]["withholds"][0]


def test_performance_ids_stay_within_contract():
    result = execute_bounded_scene_repair(candidate=candidate())
    allowed = set(result["contract"]["allowed_character_ids"])
    for decision in result["ir"]["shot_decisions"]:
        for row in decision.get("performance_direction", []):
            assert row["character_id"] in allowed


def test_scene_repair_is_deterministic():
    first = execute_bounded_scene_repair(candidate=candidate())
    second = execute_bounded_scene_repair(candidate=candidate())
    assert first["ir"] == second["ir"]
    assert first["validation"]["compilation"]["candidate"] == second["validation"]["compilation"]["candidate"]


def test_direct_over_directing_detector_remains_non_blocking():
    result = detect_over_directing(candidate()["shots"], baseline_shot_count=4, allowed_auxiliary_count=0)
    assert result["blocking"] is False


def test_phase1_does_not_create_auxiliary_shots():
    result = execute_bounded_scene_repair(candidate=candidate())
    assert result["compiled"]["patch_document"]["auxiliary_shot_proposals"] == []
