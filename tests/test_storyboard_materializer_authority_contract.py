import pytest

from core.storyboard_materializer import (
    MATERIALIZER_POLICY_VERSION,
    MATERIALIZER_VERSION,
    materialization_set_fingerprint,
    materialize_storyboard_from_shot_plan,
    projection_payload,
)


def _shot(**overrides):
    value = {
        "plan_shot_id": "S01",
        "beat_id": "B01",
        "purpose": "reveal",
        "event": "人物抬头",
        "duration_hint_seconds": 4,
        "camera": {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow"},
        "action_beats": [{"start_seconds": 0, "end_seconds": 2, "action": "抬头"}],
        "entry_state": {"position": "门口"},
        "exit_state": {"position": "门内"},
        "asset_bindings": {"characters": ["C1"]},
        "continuity_contract": {"screen_direction": "left_to_right"},
    }
    value.update(overrides)
    return value


def _plan(shots=None):
    return {"scene_id": "E01_SC01", "scene_name": "门厅", "shots": shots or [_shot()]}


@pytest.mark.parametrize("field", ["plan_shot_id", "purpose", "action_beats", "entry_state", "exit_state", "asset_bindings", "continuity_contract"])
def test_production_materializer_missing_contract_field_fails_closed(field):
    shot = _shot()
    shot.pop(field)
    with pytest.raises(ValueError) as exc:
        materialize_storyboard_from_shot_plan(_plan([shot]), production=True)
    assert "required" in str(exc.value).lower() or "invalid" in str(exc.value).lower()


def test_production_materializer_does_not_apply_camera_or_duration_defaults():
    shot = _shot(camera={"movement": "static"}, duration_hint_seconds=None)
    with pytest.raises(ValueError) as exc:
        materialize_storyboard_from_shot_plan(_plan([shot]), production=True)
    assert "SHOT_PLAN_CAMERA_REQUIRED" in str(exc.value) or "SHOT_PLAN_DURATION_REQUIRED" in str(exc.value)


def test_production_projection_is_exact_n_to_n_and_has_no_compiler_output():
    source = _plan([_shot(), _shot(plan_shot_id="S02", event="回头")])
    result = materialize_storyboard_from_shot_plan(source, production=True)
    assert [item["plan_shot_id"] for item in result] == ["S01", "S02"]
    assert len(result) == 2
    assert result[0]["meta_info"]["authority_classes"]["compiler_output"] == []
    assert result[0]["meta_info"]["authority_classes"]["media_state"] == []
    assert "visual_prompt_static" not in result[0]
    assert result[0]["duration"] == 4
    assert result[0]["meta_info"]["camera"]["shot_size"] == "MS"


def test_set_fingerprint_is_stable_and_detects_projection_tamper():
    result = materialize_storyboard_from_shot_plan(_plan(), production=True)
    authority = {"shot_plan": {"id": 1, "revision": 1, "authority_fingerprint": "a"}}
    first = materialization_set_fingerprint(authority_envelope=authority, projections=result)
    second = materialization_set_fingerprint(authority_envelope=authority, projections=result)
    assert first == second
    tampered = dict(result[0]); tampered["duration"] = 5
    assert materialization_set_fingerprint(authority_envelope=authority, projections=[tampered]) != first
    assert projection_payload(result[0])["plan_shot_id"] == "S01"


def test_materializer_versions_are_explicit():
    assert MATERIALIZER_VERSION.startswith("storyboard_materializer_")
    assert MATERIALIZER_POLICY_VERSION.startswith("storyboard_materializer_policy_")
