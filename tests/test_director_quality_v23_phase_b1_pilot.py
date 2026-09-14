from pathlib import Path

import core.llm

from scripts.run_director_quality_v2_3_phase_b1_pilot import (
    CONFIRMATION_TOKEN,
    _eligible_dimension_coverage,
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
    assert result["scenes"][0]["tail_repair"]["triggered"] is True
    assert result["scenes"][0]["tail_repair"]["root_causes"]


def test_b1_patch_attribution_is_field_scoped_not_shot_scoped():
    patches = [
        {"plan_shot_id": "S01", "changes": {"camera.angle": "low_angle"}},
        {"plan_shot_id": "S01", "changes": {"information_strategy.reveals": ["钥匙"]}},
    ]
    dimensions = _patch_dimension_map(patches)
    assert dimensions["S01"] == {"camera_language", "shot_motivation", "information_strategy"}


def test_b1_strategy_coverage_uses_eligible_opportunity_denominator():
    opportunities = [
        {"opportunity_id": "O1", "type": "OPP_REACTION", "scene_id": "S", "beat_id": "B1", "subjects": [], "reason": "r", "evidence_refs": ["e"], "priority": "medium", "eligible": True, "recommended_directing_dimensions": ["edit_strategy"]},
        {"opportunity_id": "O2", "type": "OPP_REACTION", "scene_id": "S", "beat_id": "B2", "subjects": [], "reason": "r", "evidence_refs": ["e"], "priority": "medium", "eligible": True, "recommended_directing_dimensions": ["emotion_arc"]},
    ]
    outcomes = [
        {"opportunity_id": "O1", "eligible": True, "planner_decision": "SKIP_WITH_REASON", "decision_reason": "已有覆盖", "accepted": False, "repaired": False, "fallback": False, "quality_delta": 0, "dimension_deltas": {}, "final_status": "SKIPPED_VALID_REASON"},
        {"opportunity_id": "O2", "eligible": True, "planner_decision": "ACT", "decision_reason": "", "accepted": False, "repaired": False, "fallback": True, "quality_delta": 0, "dimension_deltas": {}, "final_status": "FALLBACK_BASELINE"},
    ]
    result = _eligible_dimension_coverage(opportunities, outcomes)
    assert result == {"edit_strategy": 1.0, "emotion_arc": 0.0, "information_strategy": None}
