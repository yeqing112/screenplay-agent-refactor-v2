import copy

from core.director_tail_repair_ir import (
    REPAIR_IR_SCHEMA_VERSION,
    validate_repair_ir,
    validate_repair_ir_diagnostics,
)
from core.director_tail_repair_provider_contract import build_provider_output_contract, build_provider_system_prompt, provider_contract_fingerprint
from core.director_tail_repair_semantic_spec import (
    REPAIR_TYPE_SPECS,
    SEMANTIC_SPEC_VERSION,
    minimal_valid_skeleton,
)
from core.director_creative_contract import build_director_creative_contract
from core.director_tail_repair_executor import execute_tail_repair


def _base(kind, decision):
    roots = {"edit": "WEAK_EDIT_STRATEGY", "emotion": "WEAK_EMOTION_ARC", "information": "WEAK_INFORMATION_STRATEGY", "performance": "PERFORMANCE_DIRECTION_WEAK", "camera": "CAMERA_LANGUAGE_GENERIC"}
    dims = {"edit": ["EDIT_RHYTHM"], "emotion": ["EMOTIONAL_PROGRESSION"], "information": ["INFORMATION_STRATEGY"], "performance": ["PERFORMANCE_DIRECTION"], "camera": ["SHOT_DIVERSITY"]}
    return {"schema_version": REPAIR_IR_SCHEMA_VERSION, "repair_type": kind, "root_cause": roots[kind], "target_dimensions": dims[kind], "shot_decisions": [{"plan_shot_id": "S01", **decision}]}


def test_all_repair_types_have_valid_minimal_ir():
    values = {
        "edit": {"edit": {"cut_reason": "reaction"}},
        "emotion": {"emotion": {"intensity": 5}},
        "information": {"information_strategy": {"audience_focus": "subject"}},
        "performance": {"performance_direction": [{"character_id": "C1", "objective": "observe", "visible_behavior": "turns"}]},
        "camera": {"camera": {"shot_size": "MS"}},
    }
    for kind, decision in values.items():
        assert validate_repair_ir(_base(kind, decision), known_plan_shot_ids={"S01"}, allowed_character_ids={"C1"})["repair_type"] == kind


def test_emotion_collects_multiple_typed_errors():
    raw = _base("emotion", {"emotion": {"intensity": 15}, "performance_emphasis": ""})
    result = validate_repair_ir_diagnostics(raw, known_plan_shot_ids={"S01"})
    assert not result["valid"]
    assert {item["code"] for item in result["errors"]} >= {"VALUE_OUT_OF_RANGE", "EMPTY_STRING"}
    assert len(result["errors"]) >= 2
    assert all({"path", "code", "message", "expected", "actual_type"}.issubset(item) for item in result["errors"])


def test_performance_reports_empty_array_missing_fields_and_unknown_character():
    raw = _base("performance", {"performance_direction": [{"character_id": "C99", "objective": "", "visible_behavior": ""}]})
    result = validate_repair_ir_diagnostics(raw, known_plan_shot_ids={"S01"}, allowed_character_ids={"C1"})
    codes = {item["code"] for item in result["errors"]}
    assert {"EMPTY_STRING", "UNKNOWN_CHARACTER_ID"} <= codes
    empty = _base("performance", {"performance_direction": []})
    empty_result = validate_repair_ir_diagnostics(empty, known_plan_shot_ids={"S01"})
    assert any(item["code"] == "EMPTY_ARRAY" and item["path"].endswith("performance_direction") for item in empty_result["errors"])


def test_provider_contract_and_prompt_are_derived_from_spec():
    contract = build_provider_output_contract()
    assert contract["semantic_spec_version"] == SEMANTIC_SPEC_VERSION
    assert contract["typed_constraints"]["emotion"]["groups"]["emotion"]["fields"]["intensity"]["maximum"] == 10
    assert "minItems=1" in build_provider_system_prompt()
    assert "required fields: character_id, objective, visible_behavior" in build_provider_system_prompt()
    before = provider_contract_fingerprint()
    old = REPAIR_TYPE_SPECS["emotion"]["groups"]["emotion"]["fields"]["intensity"]["maximum"]
    REPAIR_TYPE_SPECS["emotion"]["groups"]["emotion"]["fields"]["intensity"]["maximum"] = 9
    try:
        assert provider_contract_fingerprint() != before
        assert "maximum=9" in build_provider_system_prompt()
        assert validate_repair_ir_diagnostics(_base("emotion", {"emotion": {"intensity": 10}}))["valid"] is False
    finally:
        REPAIR_TYPE_SPECS["emotion"]["groups"]["emotion"]["fields"]["intensity"]["maximum"] = old


def test_minimal_skeletons_are_typed_shapes_with_placeholders():
    for kind in REPAIR_TYPE_SPECS:
        skeleton = minimal_valid_skeleton(kind)
        assert skeleton["schema_version"] == REPAIR_IR_SCHEMA_VERSION
        assert skeleton["shot_decisions"][0]["plan_shot_id"].startswith("<")


def test_legacy_exception_contains_aggregate_errors():
    raw = _base("emotion", {"emotion": {"intensity": 15}, "performance_emphasis": ""})
    try:
        validate_repair_ir(raw)
    except Exception as exc:
        assert len(exc.errors) >= 2
    else:
        raise AssertionError("expected aggregate RepairIRSchemaError")


def test_executor_format_repair_packet_carries_structured_diagnostics_and_skeleton():
    plan = {"scene_id": "SCENE_01", "shots": [{"plan_shot_id": "S01", "participants": ["C1"]}]}
    contract = build_director_creative_contract(structural_shot_plan=plan, treatment={"scene_id": "SCENE_01", "beat_map": []})
    calls = []
    def provider(request):
        calls.append(request)
        if len(calls) == 1:
            return _base("emotion", {"emotion": {"intensity": 15}, "performance_emphasis": ""})
        return _base("emotion", {"emotion": {"intensity": 5}})
    result = execute_tail_repair(candidate=plan, record={"scene_id": "SCENE_01", "director_quality_score": 50, "eligible_coverage": {"emotion_arc": 0.1}}, contract=contract, repair_callable=provider, require_repair_ir=True, root_causes=["WEAK_EMOTION_ARC"])
    assert calls[1]["attempt"]["kind"] == "FORMAT_REPAIR"
    assert len(calls[1]["attempt"]["previous_validation_errors"]) >= 2
    assert calls[1]["attempt"]["typed_constraints_subset"]["repair_type"] == "emotion"
    assert calls[1]["attempt"]["repair_type_minimal_skeleton"]["repair_type"] == "emotion"
    assert result["attempts"][0]["attempts"][0]["ir_validation_errors_structured"]
