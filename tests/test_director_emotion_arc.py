from core.director_emotion_arc import evaluate_emotion_arc, validate_emotion_arc


def test_emotion_arc_supports_non_monotonic_phases():
    value = validate_emotion_arc([
        {"beat_id": "B01", "state": "克制", "intensity": 3},
        {"beat_id": "B02", "state": "警觉", "intensity": 6},
        {"beat_id": "B03", "state": "震惊", "intensity": 9, "phase": "spike"},
        {"beat_id": "B04", "state": "压抑", "intensity": 5, "phase": "release"},
    ])
    assert value["status"] == "valid"
    assert value["scene_emotion_arc"][1]["phase"] == "rise"


def test_emotion_validator_detects_flatline_jump_and_missing_peak_support():
    result = evaluate_emotion_arc(
        [
            {"beat_id": "B01", "state": "平", "intensity": 2},
            {"beat_id": "B02", "state": "爆发", "intensity": 9},
        ],
        shots=[{"beat_id": "B02", "emotion": {"intensity": 9}, "performance_direction": []}],
        beat_map=[{"beat_id": "B01", "type": "setup"}, {"beat_id": "B02", "type": "setup"}],
    )
    codes = {item["code"] for item in result["issues"]}
    assert "EMOTION_JUMP_UNMOTIVATED" in codes
    assert "EMOTION_PEAK_UNVISUALIZED" in codes


def test_reaction_requires_visible_performance_support():
    result = evaluate_emotion_arc(
        [{"beat_id": "B01", "state": "紧张", "intensity": 5}],
        shots=[{"beat_id": "B01", "emotion": {"intensity": 5}, "performance_direction": []}],
        beat_map=[{"beat_id": "B01", "type": "reaction"}],
    )
    assert any(item["code"] == "REACTION_WITHOUT_PERFORMANCE_SUPPORT" for item in result["issues"])
