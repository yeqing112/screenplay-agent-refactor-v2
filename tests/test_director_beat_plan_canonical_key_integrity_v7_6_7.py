import copy
import json

import pytest

from core.director_progressive_authoring import (
    CANONICAL_BEAT_KEYS,
    CANONICAL_TOP_LEVEL_KEYS,
    DIRECTOR_BEAT_PLAN_IR_VERSION,
    DuplicateJSONKeyError,
    audit_duplicate_json_keys,
    build_director_beat_plan_prompt,
    parse_director_beat_plan_ir,
    render_stage_a_schema_contract,
    validate_director_beat_plan_ir,
    validate_director_beat_plan_ir_schema,
    validate_director_beat_plan_text_completeness,
    validate_stage_a_prompt_schema_key_parity,
)


def _units():
    return [{"unit_id": f"SAU_E01_SC001_{i:03d}", "source_type": "SOURCE_ACTION", "source_order": i, "text": f"来源单元{i}。"} for i in range(1, 13)]


def _golden():
    units = _units()
    return {
        "version": DIRECTOR_BEAT_PLAN_IR_VERSION,
        "scene_label": "暗房。",
        "scene_objective": "建立封闭空间中的不安并推动线索进入下一阶段。",
        "dramatic_question": "林晚是否能够确认谁先动过铁盒？",
        "beats": [
            {"refs": [u["unit_id"] for u in units[index:index + 2]], "purpose": "交代当前空间和人物关系。", "objective": "让观众理解这一组来源动作的戏剧功能。", "information_change": "新的来源信息被观众清楚看见。", "hook": index in {2, 4, 6, 8, 10}}
            for index in range(0, 12, 2)
        ],
        "passthrough_refs": [],
        "unknowns": [],
        "confidence": 0.8,
        "note": "所有来源单元均被覆盖。",
    }


def test_prompt_schema_contract_is_derived_and_has_set_parity():
    _, prompt = build_director_beat_plan_prompt(scene_id="E01_SC001", source_units=_units())
    report = validate_stage_a_prompt_schema_key_parity(prompt)
    assert report["status"] == "PASS", report
    assert report["prompt"]["CANONICAL_TOP_LEVEL_KEYS"] == list(CANONICAL_TOP_LEVEL_KEYS)
    assert report["prompt"]["CANONICAL_BEAT_KEYS"] == list(CANONICAL_BEAT_KEYS)
    for phrase in ("byte-for-byte", "do not translate", "Chinese only in values", "never in keys"):
        assert phrase in prompt
    shape = json.loads(prompt.split("JSON_SHAPE_EXAMPLE_ONLY=", 1)[1].split("; this example", 1)[0])
    assert set(shape) == set(CANONICAL_TOP_LEVEL_KEYS)
    assert set(shape["beats"][0]) == set(CANONICAL_BEAT_KEYS)


def test_schema_contract_is_single_source_for_allowlist_and_additional_properties():
    contract = render_stage_a_schema_contract()
    assert contract["top_level_keys"] == list(CANONICAL_TOP_LEVEL_KEYS)
    assert contract["beat_keys"] == list(CANONICAL_BEAT_KEYS)
    assert contract["top_level_additional_properties"] is False
    assert contract["beat_additional_properties"] is False


def test_attempt6_invalid_alias_forms_fail_without_rename_repair():
    valid = _golden()
    invalid_a = copy.deepcopy(valid)
    invalid_a["beats"][0]["信息_change"] = invalid_a["beats"][0]["information_change"]
    report_a = validate_director_beat_plan_ir_schema(invalid_a)
    assert report_a["status"] == "FAIL"
    assert any(error.get("code") == "SCHEMA_ADDITIONAL_PROPERTY" and error.get("field") == "信息_change" for error in report_a["errors"])
    invalid_b = copy.deepcopy(valid)
    invalid_b["beats"][0]["信息_change"] = invalid_b["beats"][0].pop("information_change")
    report_b = validate_director_beat_plan_ir_schema(invalid_b)
    codes = {(error.get("code"), error.get("field")) for error in report_b["errors"]}
    assert ("SCHEMA_REQUIRED_FIELD_MISSING", "information_change") in codes
    assert ("SCHEMA_ADDITIONAL_PROPERTY", "信息_change") in codes
    assert "information_change" not in invalid_b["beats"][0]


@pytest.mark.parametrize(("canonical", "alias"), [
    ("scene_label", "scene_标签"), ("scene_objective", "scene_目标"),
    ("dramatic_question", "dramatic_问题"), ("passthrough_refs", "passthrough_引用"),
    ("information_change", "信息_change"), ("purpose", "目的"),
    ("objective", "目标"), ("hook", "钩子"), ("refs", "引用"),
    ("confidence", "置信度"), ("note", "备注"),
    ("scene_objective", "sceneObjective"), ("dramatic_question", "dramaticQuestion"),
    ("information_change", "informationChange"), ("passthrough_refs", "passThroughRefs"),
    ("information_change", "info_change"), ("objective", "obj"), ("refs", "ref"),
])
def test_all_translated_camelcase_and_abbreviated_keys_fail(canonical, alias):
    value = _golden()
    if canonical in CANONICAL_TOP_LEVEL_KEYS:
        value[alias] = value.pop(canonical)
    else:
        value["beats"][0][alias] = value["beats"][0].pop(canonical)
    assert validate_director_beat_plan_ir_schema(value)["status"] == "FAIL"


def test_golden_response_passes_all_provider_free_stage_a_gates():
    value = _golden()
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    assert audit_duplicate_json_keys(raw)["status"] == "PASS"
    parsed = parse_director_beat_plan_ir(raw)
    assert validate_director_beat_plan_ir_schema(parsed)["status"] == "PASS"
    runtime = validate_director_beat_plan_ir(parsed, source_units=_units())
    assert runtime["status"] == "qualified"
    assert runtime["covered_source_unit_count"] == 12
    assert runtime["creative_beat_count"] == 6
    assert runtime["local_creative_completion_count"] == 0
    assert validate_director_beat_plan_text_completeness(parsed)["status"] == "PASS"
    assert all(isinstance(beat["hook"], bool) for beat in parsed["beats"])


def test_duplicate_exact_json_key_fails_closed_without_last_value_wins():
    raw = '{"version":"director_beat_plan_ir_v1","information_change":"A","information_change":"B"}'
    audit = audit_duplicate_json_keys(raw)
    assert audit["status"] == "FAIL"
    assert audit["duplicate_keys"] == ["information_change"]
    with pytest.raises(DuplicateJSONKeyError, match="DIRECTOR_BEAT_PLAN_DUPLICATE_JSON_KEY"):
        parse_director_beat_plan_ir(raw)

