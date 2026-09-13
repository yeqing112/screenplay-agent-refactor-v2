import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_director_quality_v2_1_mimo_pilot_authorized.py"
SPEC = importlib.util.spec_from_file_location("director_quality_v21_mimo_pilot_authorized", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _profile(model_name="mimo-v2.5"):
    return {
        "id": "test-mimo-profile",
        "capability": "llm",
        "provider": "openai-compatible",
        "base_url": "https://api.xiaomimimo.com/v1",
        "model_name": model_name,
        "enabled": True,
        "api_key": "secret-for-test-only",
    }


def test_real_pilot_requires_explicit_execute_flag():
    with pytest.raises(PermissionError):
        MODULE.validate_real_authorization(
            execute_real=False,
            confirmation_token=MODULE.CONFIRMATION_TOKEN,
            profile=_profile(),
        )


def test_real_pilot_requires_exact_confirmation_token():
    with pytest.raises(PermissionError):
        MODULE.validate_real_authorization(
            execute_real=True,
            confirmation_token="wrong",
            profile=_profile(),
        )


def test_real_pilot_rejects_non_mimo_profile():
    with pytest.raises(ValueError, match="只允许.*MiMo"):
        MODULE.validate_real_authorization(
            execute_real=True,
            confirmation_token=MODULE.CONFIRMATION_TOKEN,
            profile=_profile("doubao-seed-2-0-lite-260428"),
        )


def test_real_pilot_accepts_explicit_mimo_profile_without_exposing_key():
    result = MODULE.validate_real_authorization(
        execute_real=True,
        confirmation_token=MODULE.CONFIRMATION_TOKEN,
        profile=_profile(),
    )
    assert result == {
        "profile_id": "test-mimo-profile",
        "provider": "openai-compatible",
        "model_name": "mimo-v2.5",
    }
    assert "api_key" not in result


def test_mocked_pilot_replays_twelve_frozen_scenes_without_production_side_effects():
    calls = []

    def fake_call(*_args, **_kwargs):
        calls.append(True)
        return {
            "schema_version": "director_creative_patch_v1",
            "patches": [],
            "auxiliary_shot_proposals": [],
        }

    with patch("core.llm.call_llm_json", side_effect=fake_call):
        result = MODULE.run_authorized_pilot(
            profile=_profile(),
            golden_path=Path(MODULE.GOLDEN_PATH),
            scene_limit=12,
        )

    assert result["scene_count"] == 12
    assert len(calls) == 12
    assert result["side_effects"] == {
        "production_rows_written": 0,
        "storyboard_shots_created": 0,
        "media_calls": 0,
        "object_storage_calls": 0,
    }
    assert result["blind_judge"]["status"] == "not_run"
    assert all("api_key" not in scene for scene in result["scenes"])
    assert all(
        scene["blind_review_packet"]["source_roles_hidden"] is True
        and scene["blind_review_packet"]["preferred_version"] is None
        and all("director_quality" not in version["payload"] for version in scene["blind_review_packet"]["versions"])
        for scene in result["scenes"]
    )


def test_pilot_repairs_only_rejected_patch_and_preserves_first_candidate(tmp_path):
    golden = json.loads(Path(MODULE.GOLDEN_PATH).read_text(encoding="utf-8"))
    golden["scenes"] = golden["scenes"][:1]
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps(golden, ensure_ascii=False), encoding="utf-8")
    calls = []

    def fake_call(_prompt, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            return {
                "schema_version": "director_creative_patch_v1",
                "patches": [{"plan_shot_id": "S01", "path": "/shots/0/event", "value": "must-be-rejected"}],
                "auxiliary_shot_proposals": [],
            }
        return {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}}

    with patch("core.llm.call_llm_json", side_effect=fake_call):
        result = MODULE.run_authorized_pilot(profile=_profile(), golden_path=golden_path, scene_limit=1)

    scene = result["scenes"][0]
    assert len(calls) == 2
    assert scene["repair_records"][0]["status"] == "repaired"
    assert scene["first_candidate"] != scene["final_candidate"]
    assert scene["metrics"]["contract_reliability"]["repair_success"] is True
    assert result["side_effects"]["production_rows_written"] == 0
