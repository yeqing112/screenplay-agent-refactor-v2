import json
from pathlib import Path

from core.director_repair_value_ceiling import (
    analyze_scene,
    build_sensitivity_map,
    immutable_projection,
    validate_ceiling_candidate,
)


def _candidate():
    return {
        "scene_id": "S1",
        "scene_name": "Test scene",
        "shots": [
            {
                "plan_shot_id": "S01",
                "beat_id": "B01",
                "event": "door opens",
                "participants": ["C1"],
                "action_beats": [{"action_id": "A1", "actor": "C1", "action": "door opens"}],
                "entry_state": {"door": "closed"},
                "exit_state": {"door": "open"},
                "asset_bindings": {"scene_asset_id": "SCENE", "character_asset_ids": ["C1"]},
                "continuity_contract": {"screen_direction": "maintain"},
                "continuity": "inherit",
                "camera": {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "center"},
                "purpose": "action",
            },
            {
                "plan_shot_id": "S02",
                "beat_id": "B02",
                "event": "character reacts",
                "participants": ["C1"],
                "action_beats": [{"action_id": "A2", "actor": "C1", "action": "reacts"}],
                "entry_state": {"door": "open"},
                "exit_state": {"door": "open"},
                "asset_bindings": {"scene_asset_id": "SCENE", "character_asset_ids": ["C1"]},
                "continuity_contract": {"screen_direction": "maintain"},
                "continuity": "inherit",
                "camera": {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "center"},
                "purpose": "action",
            },
        ],
    }


def _root(name, ids=("S01", "S02")):
    return {"root_cause": name, "relevant_plan_shot_ids": list(ids)}


def test_reachability_is_deterministic_and_preserves_topology_and_facts():
    candidate = _candidate()
    kwargs = {
        "scene_id": "S1",
        "baseline": candidate,
        "treatment": {"beat_map": []},
        "blocking": {},
        "contract": {"allowed_patch_paths": ["/shots/*/camera/*", "/shots/*/composition", "/shots/*/emotion", "/shots/*/performance_direction", "/shots/*/edit", "/shots/*/information_strategy"]},
        "frozen_roots": [_root("WEAK_EDIT_STRATEGY")],
        "all_known_roots": [_root("WEAK_EDIT_STRATEGY")],
        "actual": {"after_director_quality": 50},
    }
    first = analyze_scene(**kwargs)
    second = analyze_scene(**kwargs)
    assert first == second
    assert first["baseline"]["dq"] == 48.3
    assert first["top1_ceiling"]["validation"]["valid"] is True
    assert immutable_projection(candidate) == immutable_projection(candidate)


def test_validate_ceiling_candidate_rejects_fact_or_topology_change():
    baseline = _candidate()
    changed = json.loads(json.dumps(baseline))
    changed["shots"][0]["event"] = "different event"
    assert validate_ceiling_candidate(baseline=baseline, candidate=changed)["valid"] is False
    changed = json.loads(json.dumps(baseline))
    changed["shots"].append({"plan_shot_id": "S03"})
    assert validate_ceiling_candidate(baseline=baseline, candidate=changed)["valid"] is False


def test_sensitivity_map_covers_edit_emotion_information_performance_and_camera():
    result = build_sensitivity_map(baseline=_candidate())
    fields = {row["field"] for row in result["fields"]}
    assert {"edit.cut_reason", "emotion.intensity", "information_strategy.reveals", "performance_direction", "camera.signature"} <= fields
    assert not result["flags"]


def test_all_known_roots_counterfactual_can_exceed_historical_top2():
    baseline = _candidate()
    result = analyze_scene(
        scene_id="S1",
        baseline=baseline,
        treatment={"beat_map": []},
        blocking={},
        contract=None,
        frozen_roots=[_root("WEAK_EDIT_STRATEGY"), _root("WEAK_EMOTION_ARC")],
        all_known_roots=[_root("WEAK_EDIT_STRATEGY"), _root("WEAK_EMOTION_ARC"), _root("WEAK_INFORMATION_STRATEGY"), _root("PERFORMANCE_DIRECTION_WEAK"), _root("CAMERA_LANGUAGE_GENERIC")],
    )
    assert result["all_known_roots_ceiling"]["delta"] >= result["current_top2_ceiling"]["delta"]
    assert result["creative_value"]["status"] == "CV_CEILING_NOT_MEASURABLE"


def test_generated_artifacts_are_provider_free_and_complete():
    root = Path(__file__).resolve().parents[1] / "artifacts"
    required = [
        "director-quality-v2-4-4-gap-audit.md",
        "director-quality-v2-4-4-value-ceiling.json",
        "director-quality-v2-4-4-scorer-sensitivity.json",
        "director-quality-v2-4-4-approved-vs-fixture-gap.json",
        "director-quality-v2-4-4-root-cause-value.json",
        "director-quality-v2-4-4-counterfactuals.json",
        "director-quality-v2-4-4-report.md",
    ]
    assert all((root / name).exists() for name in required)
    payload = json.loads((root / "director-quality-v2-4-4-value-ceiling.json").read_text(encoding="utf-8"))
    assert payload["provider_calls"] == {"llm": 0, "mimo": 0, "image": 0, "video": 0, "storage": 0}
    assert payload["scene_count"] == 15
