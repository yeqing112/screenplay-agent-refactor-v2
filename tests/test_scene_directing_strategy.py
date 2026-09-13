import pytest

from core.director_creative_contract import build_director_creative_contract
from core.scene_directing_strategy import (
    SceneDirectingStrategyError,
    build_scene_directing_strategy,
    parse_scene_directing_strategy,
    validate_scene_directing_strategy,
    build_scene_directing_strategy_v2,
    parse_scene_directing_strategy_v2,
)
from core.shot_plan import build_shot_plan


def _inputs():
    treatment = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "visual_strategy": "用门口阻挡呈现关系变化",
        "beat_map": [
            {"beat_id": "B01", "type": "arrival", "event": "林晚进入"},
            {"beat_id": "B02", "type": "reveal", "event": "林晚发现照片"},
        ],
    }
    blocking = {
        "scene_id": "E01_SC01",
        "scene_name": "雨夜门厅",
        "participants": [{"character_id": "C1", "name": "林晚"}, {"character_id": "C2", "name": "神秘人"}],
    }
    plan = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=plan)
    return treatment, contract


def test_build_strategy_is_schema_first_and_bound_to_approved_beats():
    treatment, contract = _inputs()
    strategy = build_scene_directing_strategy(treatment=treatment, contract=contract)
    assert strategy["schema_version"] == "scene_directing_strategy_v1"
    assert [item["beat_id"] for item in strategy["emotional_curve"]] == ["B01", "B02"]
    assert strategy["strategy_fingerprint"]


def test_strategy_rejects_unknown_beat_and_character():
    _, contract = _inputs()
    strategy = build_scene_directing_strategy(contract=contract)
    invalid = dict(strategy)
    invalid["emotional_curve"] = [{"beat_id": "B99", "intensity": 5}]
    with pytest.raises(SceneDirectingStrategyError) as error:
        parse_scene_directing_strategy(invalid, contract)
    assert error.value.code == "DIRECTOR_STRATEGY_UNBOUND_BEAT"

    invalid = dict(strategy)
    invalid["power_curve"] = [{"beat_id": "B01", "dominant_character": "C99"}]
    with pytest.raises(SceneDirectingStrategyError) as error:
        parse_scene_directing_strategy(invalid, contract)
    assert error.value.code == "INVALID_CHARACTER_REFERENCE"


def test_strategy_rejects_authoritative_or_malformed_fields():
    _, contract = _inputs()
    strategy = build_scene_directing_strategy(contract=contract)
    invalid = dict(strategy)
    invalid["scene_name"] = "改写事实"
    report = validate_scene_directing_strategy(invalid, contract)
    assert report["status"] == "invalid"
    assert report["errors"][0]["code"] == "DIRECTOR_STRATEGY_FIELD_FORBIDDEN"

    invalid = dict(strategy)
    invalid["emotional_curve"] = [{"beat_id": "B01", "intensity": 11}, {"beat_id": "B02", "intensity": 5}]
    report = validate_scene_directing_strategy(invalid, contract)
    assert report["status"] == "invalid"


def test_strategy_v2_is_beat_bound_and_contains_four_director_curves():
    treatment, contract = _inputs()
    strategy = build_scene_directing_strategy_v2(treatment=treatment, contract=contract)
    assert strategy["schema_version"] == "scene_directing_strategy_v2"
    assert {item["beat_id"] for item in strategy["performance_arc"]} == {"B01", "B02"}
    assert {item["beat_id"] for item in strategy["rhythm_curve"]} == {"B01", "B02"}
    assert {item["beat_id"] for item in strategy["emotion_curve"]} == {"B01", "B02"}
    assert {item["beat_id"] for item in strategy["information_plan"]} == {"B01", "B02"}
    assert strategy["emotion_curve"][0]["intensity"] != strategy["emotion_curve"][1]["intensity"]
    assert strategy["strategy_fingerprint"]


def test_strategy_v2_rejects_unbound_beat_and_unknown_character():
    _, contract = _inputs()
    strategy = build_scene_directing_strategy_v2(contract=contract)
    invalid = dict(strategy)
    invalid["performance_arc"] = [dict(strategy["performance_arc"][0], beat_id="B99")]
    with pytest.raises(SceneDirectingStrategyError) as error:
        parse_scene_directing_strategy_v2(invalid, contract)
    assert error.value.code == "DIRECTOR_STRATEGY_UNBOUND_BEAT"

    invalid = dict(strategy)
    invalid["performance_arc"] = [dict(strategy["performance_arc"][0], character_id="C99"), strategy["performance_arc"][1]]
    with pytest.raises(SceneDirectingStrategyError) as error:
        parse_scene_directing_strategy_v2(invalid, contract)
    assert error.value.code == "INVALID_CHARACTER_REFERENCE"
