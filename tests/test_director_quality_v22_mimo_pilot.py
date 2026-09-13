from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.run_director_quality_v2_2_mimo_pilot_authorized import (
    CONFIRMATION_TOKEN,
    run_authorized_pilot,
    validate_real_authorization,
)


ROOT = Path(__file__).resolve().parents[1]


def _profile(model_name: str = "mimo-v2.5"):
    return {
        "id": "offline-v22-profile",
        "provider": "openai-compatible",
        "capability": "llm",
        "model_name": model_name,
        "enabled": True,
        "api_key": "offline-test-key",
        "base_url": "https://offline.invalid/v1",
    }


def test_v22_real_authorization_is_fail_closed():
    with pytest.raises(PermissionError):
        validate_real_authorization(execute_real=False, confirmation_token=CONFIRMATION_TOKEN, profile=_profile())
    with pytest.raises(PermissionError):
        validate_real_authorization(execute_real=True, confirmation_token="wrong", profile=_profile())
    with pytest.raises(ValueError):
        validate_real_authorization(execute_real=True, confirmation_token=CONFIRMATION_TOKEN, profile=_profile("qwen3-max"))


def test_mocked_v22_pilot_is_benchmark_only_and_has_no_side_effects():
    def fake_call(*_args, **_kwargs):
        return {"schema_version": "director_creative_patch_v1", "patches": [], "auxiliary_shot_proposals": []}

    with patch("core.llm.call_llm_json", side_effect=fake_call):
        result = run_authorized_pilot(
            profile=_profile(),
            golden_path=ROOT / "artifacts" / "director-quality-v2-1-golden-scenes.json",
            scene_limit=1,
        )

    assert result["pilot_mode"] == "real_mimo_benchmark_only"
    assert result["scene_count"] == 1
    assert result["side_effects"] == {
        "production_rows_written": 0,
        "storyboard_shots_created": 0,
        "media_calls": 0,
        "object_storage_calls": 0,
    }
    assert result["production_shadow"]["enabled"] is False

