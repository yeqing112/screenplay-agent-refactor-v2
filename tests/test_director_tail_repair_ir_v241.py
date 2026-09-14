import copy

import pytest

from core.director_creative_contract import build_director_creative_contract
from core.director_tail_repair_ir import RepairIRSchemaError, validate_repair_ir
from core.director_tail_repair_ir_compiler import compile_repair_ir
from core.director_tail_repair_executor import execute_tail_repair


def _plan():
    return {"scene_id": "SCENE_01", "scene_name": "门厅", "shots": [
        {"plan_shot_id": "S01", "beat_id": "B01", "event": "发现照片", "participants": ["C1"], "duration_hint_seconds": 4},
        {"plan_shot_id": "S02", "beat_id": "B02", "event": "抬眼", "participants": ["C1"], "duration_hint_seconds": 2},
    ]}


def _contract():
    plan = _plan()
    return build_director_creative_contract(structural_shot_plan=plan, treatment={"scene_id": "SCENE_01", "scene_name": "门厅", "beat_map": [{"beat_id": "B01", "event": "发现照片"}, {"beat_id": "B02", "event": "抬眼"}]})


def _ir(repair_type="edit", decision=None):
    return {"schema_version": "director_tail_repair_ir_v1", "repair_type": repair_type, "root_cause": "WEAK_EDIT_STRATEGY" if repair_type == "edit" else "WEAK_EMOTION_ARC", "target_dimensions": ["EDIT_RHYTHM"] if repair_type == "edit" else ["EMOTIONAL_PROGRESSION"], "shot_decisions": [decision or {"plan_shot_id": "S01", repair_type: {"cut_reason": "reaction_complete"} if repair_type == "edit" else {"intensity": 8}}]}


def test_valid_edit_ir_compiles_without_model_paths():
    result = compile_repair_ir(_ir(), structural_shot_plan=_plan(), contract=_contract())
    assert result["schema_version"] == "director_creative_patch_v1"
    assert result["patches"][0]["changes"] == {"shots/S01/edit/cut_reason": "reaction_complete"}


def test_valid_emotion_ir_compiles_deterministically():
    ir = _ir("emotion")
    a = compile_repair_ir(ir, structural_shot_plan=_plan(), contract=_contract())
    b = compile_repair_ir(copy.deepcopy(ir), structural_shot_plan=_plan(), contract=_contract())
    assert a == b
    assert a["patches"][0]["changes"]["shots/S01/emotion/intensity"] == 8


def test_wrong_type_root_cause_and_unknown_shot_rejected():
    with pytest.raises(RepairIRSchemaError):
        validate_repair_ir(_ir("camera"), known_plan_shot_ids={"S01"})
    bad = _ir(); bad["shot_decisions"][0]["plan_shot_id"] = "S99"
    with pytest.raises(RepairIRSchemaError) as exc:
        validate_repair_ir(bad, known_plan_shot_ids={"S01"})
    assert exc.value.code == "UNKNOWN_PLAN_SHOT_ID"


def test_request_metadata_and_canonical_paths_are_not_ir_fields():
    bad = _ir(); bad["target_metric"] = {"EDIT_RHYTHM": 0.5}
    with pytest.raises(RepairIRSchemaError):
        validate_repair_ir(bad, known_plan_shot_ids={"S01"})
    bad = _ir(); bad["shot_decisions"][0]["path"] = "shots/S01/edit/cut_reason"
    with pytest.raises(RepairIRSchemaError):
        validate_repair_ir(bad, known_plan_shot_ids={"S01"})


def test_scope_escape_and_empty_decision_rejected():
    bad = _ir(); bad["shot_decisions"][0]["edit"] = {"scene_id": "override"}
    with pytest.raises(RepairIRSchemaError):
        validate_repair_ir(bad, known_plan_shot_ids={"S01"})


def test_executor_format_retry_receives_previous_output_and_errors():
    calls = []
    def repair(request):
        calls.append(request)
        if len(calls) == 1:
            return {"schema_version": "director_tail_repair_ir_v1", "repair_type": "edit", "root_cause": "WEAK_EDIT_STRATEGY", "target_dimensions": ["EDIT_RHYTHM"], "shot_decisions": [{"plan_shot_id": "S01", "edit": {"unknown": "x"}}]}
        return _ir()
    result = execute_tail_repair(candidate=_plan(), record={"scene_id": "SCENE_01", "director_quality_score": 50, "eligible_coverage": {"edit_strategy": 0.2}}, contract=_contract(), repair_callable=repair, require_repair_ir=True)
    assert result["status"] == "accepted"
    assert calls[1]["attempt_kind"] == "FORMAT_REPAIR"
    assert "previous_raw_output" in calls[1]
    assert calls[1]["previous_validation_errors"]


def test_executor_semantic_retry_is_bounded_to_two_attempts():
    calls = []
    def repair(request):
        calls.append(request)
        return {"schema_version": "director_tail_repair_ir_v1", "repair_type": "edit", "root_cause": "WEAK_EDIT_STRATEGY", "target_dimensions": ["EDIT_RHYTHM"], "shot_decisions": [{"plan_shot_id": "S01", "edit": {"duration_seconds": 4}}]}
    result = execute_tail_repair(candidate=_plan(), record={"scene_id": "SCENE_01", "director_quality_score": 50, "eligible_coverage": {"edit_strategy": 0.2}}, contract=_contract(), repair_callable=repair, require_repair_ir=True)
    assert result["status"] == "rolled_back"
    assert len(calls) == 2
    assert calls[1]["attempt_kind"] == "SEMANTIC_REPAIR"
    assert result["root_cause_attempt_coverage"] == 1.0


def test_authoritative_ir_to_patch_to_contract_to_quality_path():
    ir = _ir()
    canonical = compile_repair_ir(ir, structural_shot_plan=_plan(), contract=_contract())
    from core.director_patch_schema import parse_creative_patch
    from core.director_patch_compiler import compile_creative_patches
    from core.director_patch_validator import validate_compiled_patch_result
    from core.director_quality_validator import score_director_quality
    parsed = parse_creative_patch(canonical)
    compiled = compile_creative_patches(_plan(), parsed, _contract())
    validation = validate_compiled_patch_result(compiled, _plan(), _contract())
    before = score_director_quality(_plan())
    after = score_director_quality(compiled["candidate"])
    assert validation["contract_pass"] is True
    assert after["dimensions"]["EDIT_RHYTHM"] > before["dimensions"]["EDIT_RHYTHM"]
    bad = _ir(); bad["shot_decisions"][0].pop("edit")
    with pytest.raises(RepairIRSchemaError):
        validate_repair_ir(bad, known_plan_shot_ids={"S01"})
