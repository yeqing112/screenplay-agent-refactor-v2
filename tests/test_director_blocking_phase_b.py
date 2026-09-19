import copy

from core.director_treatment import build_director_treatment_v2, validate_director_treatment_v2
from core.scene_blocking import build_scene_blocking_phase_b, validate_scene_blocking_phase_b


def _scene():
    return {
        "scene_id": "E01_SC001",
        "name": "车站",
        "beats": [
            {"beat_id": "B01", "type": "REVEAL", "event": "红伞出现", "importance": "critical", "requires_reaction": True, "characters": ["林晚"]},
            {"beat_id": "B02", "type": "DECISION", "event": "林晚决定留下", "importance": "critical", "requires_reaction": True, "characters": ["林晚"]},
        ],
    }


def _treatment():
    scene = _scene()
    return build_director_treatment_v2(
        scene=scene,
        characters=[{"id": "LW", "name": "林晚"}],
        directives={
            "scene_objective": "让林晚从逃离转为主动调查红伞的来源。",
            "dramatic_question": "她能否在离开前确认谁动过她的包？",
            "audience_state_in": "观众只知道红伞出现。",
            "audience_state_out": "观众知道林晚选择留下。",
            "character_directions": [{"character": "林晚", "objective": "离开并隐藏恐惧", "obstacle": "顾沉知道断伞骨", "strategy": "先否认再试探", "strategy_shift": "发现伞骨消失后调查", "subtext": "我不能让他们知道我害怕", "performance_notes": "压住反应再行动", "avoid": "不要一开始就确定凶手"}],
            "suspicion_or_information_strategy": [{"order": 1, "beat_ref": "B01", "information": "红伞出现"}],
            "performance_arc": [{"phase": "IN", "state": "警惕"}, {"phase": "OUT", "state": "主动调查"}],
        },
    )


def test_placeholder_treatment_is_blocked():
    report = validate_director_treatment_v2({"scene_objective": "推进剧情"}, scene=_scene())
    codes = {item["code"] for item in report["errors"]}
    assert "DIRECTOR_TREATMENT_PLACEHOLDER" in codes
    assert "DIRECTOR_CHARACTER_DIRECTION_MISSING" in codes


def test_phase_b_treatment_covers_critical_beats_without_mutating_script():
    scene = _scene()
    before = copy.deepcopy(scene)
    treatment = _treatment()
    assert treatment["validation"]["status"] == "qualified"
    assert treatment["validation"]["covered_critical_beat_count"] == 2
    assert scene == before
    assert {item["beat_id"] for item in treatment["beat_map"]} == {"B01", "B02"}


def test_unmaterialized_blocking_is_fail_closed():
    report = validate_scene_blocking_phase_b({}, scene=_scene())
    assert report["status"] == "blocked"
    assert any(item["code"] == "BLOCKING_NOT_MATERIALIZED" for item in report["errors"])


def test_phase_b_blocking_materializes_spatial_states_and_rejects_camera_fields():
    treatment = _treatment()
    blocking = build_scene_blocking_phase_b(
        scene=_scene(),
        treatment=treatment,
        directives={
            "zones": [{"zone_id": "Z1", "name": "窗口", "spatial_relation": "固定锚点"}],
            "characters": [{"character": "林晚", "entry": "already_present", "initial_position": "Z1", "facing": "红伞", "movement_path": [{"beat_ref": "B02", "from": "Z1", "to": "Z1", "reason": "停下确认"}], "exit": "remains_in_scene"}],
            "critical_props": ["RED_UMBRELLA"],
            "prop_spatial_states": [{"prop_id": "RED_UMBRELLA", "beat_ref": "B01", "zone": "Z1", "state": "visible"}],
            "eyelines": [{"source": "林晚", "target": "RED_UMBRELLA", "beat_ref": "B01"}],
            "interactions": [{"beat_ref": "B02", "actor": "林晚", "target": "RED_UMBRELLA", "interaction": "stops_to_confirm", "spatial_effect": "holds_position"}],
            "interaction_axes": [{"axis_id": "AXIS_LW_UMBRELLA", "subjects": ["林晚", "RED_UMBRELLA"], "established_at_beat": "B01", "continuity_requirement": "PRESERVE"}],
        },
    )
    assert blocking["validation"]["status"] == "qualified"
    assert blocking["validation"]["camera_leakage_count"] == 0
    assert len(blocking["beat_spatial_states"]) == 2
    leaked = dict(blocking)
    leaked["lens"] = "50mm"
    assert any(x["code"] == "BLOCKING_CAMERA_DESIGN_LEAK" for x in validate_scene_blocking_phase_b(leaked, scene=_scene())["errors"])
