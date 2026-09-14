from pathlib import Path
import pytest

from scripts.build_director_quality_v2_3_phase_b2_evidence import build_evidence_pool
from scripts.run_director_quality_v2_3_phase_b2_pilot import CONFIRMATION_TOKEN, _rename_telemetry_stage, validate_real_authorization
from scripts.run_director_quality_v2_3_phase_b2_pilot import run_authorized_pilot as run_b2
import core.llm


ROOT = Path(__file__).resolve().parents[1]


def test_b2_evidence_pool_reaches_minimum_without_provider_calls():
    result = build_evidence_pool(minimum_scenes=24)
    assert result["scene_count"] >= 24
    assert result["deduplication"]["unique_scene_count"] == result["scene_count"]
    assert result["safety"] == {
        "llm_provider_calls": 0,
        "media_calls": 0,
        "object_storage_calls": 0,
        "production_writes": 0,
        "storyboard_writes": 0,
    }
    ids = [item["scene"]["scene_id"] for item in result["scenes"]]
    assert len(ids) == len(set(ids))
    assert all(item["evidence"]["contract"] for item in result["scenes"])


def test_b2_fixture_adapters_are_generic_and_provenanced():
    result = build_evidence_pool(minimum_scenes=24)
    fixture_rows = [item for item in result["scenes"] if item["scene"]["scene_type"] == "fixture_adapter"]
    assert len(fixture_rows) >= 5
    assert all(item["scene"]["source"] == "existing_test_fixture" for item in fixture_rows)
    assert all(item["evidence"]["treatment"]["source"] == "existing_test_fixture" for item in fixture_rows)


def test_b2_authorization_is_explicit_and_mimo_only():
    profile = {
        "id": "m",
        "provider": "openai-compatible",
        "capability": "llm",
        "model_name": "mimo-v2.5",
        "enabled": True,
        "api_key": "secret",
        "base_url": "https://example.invalid/v1",
    }
    assert validate_real_authorization(execute_real=True, confirmation_token=CONFIRMATION_TOKEN, profile=profile)["model_name"] == "mimo-v2.5"


def test_b2_wrong_confirmation_token_is_rejected():
    with pytest.raises(PermissionError):
        validate_real_authorization(
            execute_real=True,
            confirmation_token="CONFIRM_DIRECTOR_V23_PHASE_B1_REAL_MIMO_PILOT",
            profile={"id": "m", "provider": "openai-compatible", "capability": "llm", "model_name": "mimo-v2.5", "api_key": "secret", "base_url": "https://example.invalid/v1"},
        )


def test_b2_telemetry_stage_is_not_mislabeled_as_b1():
    telemetry = {
        "stages": {"director_patch_planner_v23_b1": {"total_calls": 1}},
        "records": [{"extra": {"stage": "director_patch_planner_v23_b1", "pilot_stage": "director_patch_planner_v23_b1"}}],
    }
    normalized = _rename_telemetry_stage(telemetry)
    assert "director_patch_planner_v23_b1" not in normalized["stages"]
    assert "director_patch_planner_v23_b2" in normalized["stages"]
    assert normalized["records"][0]["extra"]["stage"] == "director_patch_planner_v23_b2"
    assert normalized["records"][0]["extra"]["pilot_stage"] == "director_patch_planner_v23_b2"


def test_b2_engine_completes_24_scene_mock_without_side_effects(monkeypatch):
    calls = []
    monkeypatch.setattr(
        core.llm,
        "call_llm_json",
        lambda *args, **kwargs: (calls.append(1) or {
            "schema_version": "director_creative_patch_v1",
            "patches": [],
            "auxiliary_shot_proposals": [],
            "opportunity_decisions": [],
        }),
    )
    result = run_b2(
        profile={
            "id": "m",
            "provider": "openai-compatible",
            "capability": "llm",
            "model_name": "mimo-v2.5",
            "api_key": "secret",
            "base_url": "https://example.invalid/v1",
        },
        evidence_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json",
        scene_limit=24,
        confirmation_token=CONFIRMATION_TOKEN,
    )
    assert result["phase"] == "B2"
    assert result["scene_count"] == 24
    assert result["side_effects"] == {
        "production_rows_written": 0,
        "storyboard_shots_created": 0,
        "media_calls": 0,
        "object_storage_calls": 0,
    }
    assert result["production_shadow"]["enabled"] is False
    assert len(calls) == 24


def test_b2_library_runner_cannot_bypass_confirmation(monkeypatch):
    monkeypatch.setattr(core.llm, "call_llm_json", lambda *args, **kwargs: {})
    with pytest.raises(PermissionError):
        run_b2(
            profile={"id": "m", "provider": "openai-compatible", "capability": "llm", "model_name": "mimo-v2.5", "api_key": "secret", "base_url": "https://example.invalid/v1"},
            evidence_path=ROOT / "artifacts" / "director-quality-v2-3-phase-b2-evidence.json",
            scene_limit=24,
        )
