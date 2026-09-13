import json
import sys

from scripts import run_director_quality_v2_2_1_mimo_pilot_authorized as pilot


def test_v221_runner_defaults_to_preflight(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["pilot"])
    pilot.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "preflight_only"
    assert payload["real_mimo_calls"] == 0


def test_v221_runner_compares_control_artifact_without_rerunning_v22(monkeypatch, tmp_path):
    control = {
        "scenes": [
            {"scene": {"scene_id": f"S{i}"}, "quality": {"dimensions": {"after_repair": {"DRAMATIC_CLARITY": 10}}}}
            for i in range(12)
        ],
        "comparison": {"v22_observed": {"repair_calls": 2, "fallback_patch_count": 1, "director_quality_average": 50}},
    }
    control_path = tmp_path / "control.json"
    control_path.write_text(json.dumps(control), encoding="utf-8")
    monkeypatch.setattr(pilot, "V22_ARTIFACT", control_path)

    observed = {
        "scene_count": 12,
        "scenes": [
            {"scene": {"scene_id": f"S{i}"}, "quality": {"dimensions": {"baseline": {"DRAMATIC_CLARITY": 9}, "after_repair": {"DRAMATIC_CLARITY": 11}}}}
            for i in range(12)
        ],
        "metrics": {"repair_cost": {"llm_repair_calls": 1}, "fallback_patch_count": 0},
        "comparison": {"v22_observed": {"director_quality_average": 51}, "v21_baseline": {}},
        "telemetry": {},
        "model": {},
        "side_effects": {},
    }
    monkeypatch.setattr(
        "scripts.run_director_quality_v2_2_mimo_pilot_authorized.run_authorized_pilot",
        lambda **_: observed,
    )
    result = pilot.run_v221_pilot(profile={}, scene_limit=12)
    assert result["comparison"]["v2_2_observed"]["fallback_patch_count"] == 1
    assert result["comparison"]["v2_2_1_observed"]["repair_calls"] == 1
    assert result["scenes"][0]["quality_dimensions_ab"]["baseline"]["DRAMATIC_CLARITY"] == 9
    assert result["production_shadow"]["enabled"] is False
