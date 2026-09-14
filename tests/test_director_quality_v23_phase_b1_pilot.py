from pathlib import Path

import core.llm

from scripts.run_director_quality_v2_3_phase_b1_pilot import (
    CONFIRMATION_TOKEN,
    _patch_dimension_map,
    run_authorized_pilot,
    validate_real_authorization,
)


def test_b1_authorization_is_explicit_and_mimo_only():
    profile = {"id": "m", "provider": "openai-compatible", "capability": "llm", "model_name": "mimo-v2.5", "enabled": True, "api_key": "secret", "base_url": "https://example.invalid/v1"}
    assert validate_real_authorization(execute_real=True, confirmation_token=CONFIRMATION_TOKEN, profile=profile)["model_name"] == "mimo-v2.5"


def test_b1_runner_with_incomplete_decisions_fails_closed_without_side_effects(monkeypatch):
    monkeypatch.setattr(core.llm, "call_llm_json", lambda *args, **kwargs: {"schema_version": "director_creative_patch_v1", "patches": [], "auxiliary_shot_proposals": [], "opportunity_decisions": []})
    result = run_authorized_pilot(
        profile={"id": "m", "provider": "openai-compatible", "capability": "llm", "model_name": "mimo-v2.5", "api_key": "secret", "base_url": "https://example.invalid/v1"},
        golden_path=Path("artifacts/director-quality-v2-1-golden-scenes.json"),
        scene_limit=1,
    )
    assert result["scene_count"] == 1
    assert result["side_effects"] == {"production_rows_written": 0, "storyboard_shots_created": 0, "media_calls": 0, "object_storage_calls": 0}
    assert result["production_shadow"]["enabled"] is False


def test_b1_patch_attribution_is_field_scoped_not_shot_scoped():
    patches = [
        {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}},
        {"plan_shot_id": "S01", "changes": {"information_strategy.reveals": ["钥匙"]}},
    ]
    dimensions = _patch_dimension_map(patches)
    assert dimensions["S01"] == {"camera_language", "shot_motivation", "information_strategy"}
