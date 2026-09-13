import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from core.director_creative_planner import (
    DirectorFactOverride,
    build_creative_shot_plan_candidate,
)
from core.director_local_repair import apply_director_local_repair, build_director_repair_options
from core.director_blind_review import prepare_blind_review, record_blind_preference
from core.director_quality_validator import (
    score_director_quality,
    validate_director_quality,
)
from core.shot_plan import build_shot_plan
from api.server import app


def _inputs():
    treatment = {
        "scene_name": "雨夜门厅",
        "scene_id": "E01_SC01",
        "status": "approved",
        "beat_map": [
            {"beat_id": "B01", "type": "setup", "event": "林晚推门进入"},
            {"beat_id": "B02", "type": "reveal", "event": "她发现桌上的照片", "information_change": "照片出现"},
            {"beat_id": "B03", "type": "decision", "event": "林晚决定隐瞒照片", "emotion_change": "从警惕到决绝"},
        ],
    }
    blocking = {
        "scene_name": "雨夜门厅",
        "scene_id": "E01_SC01",
        "status": "approved",
        "unknowns": [],
        "participants": [{"character_id": "CHAR_LIN", "name": "林晚"}, {"character_id": "CHAR_GUEST", "name": "来客"}],
        "source_spatial_facts": [{"fact_id": "F1", "subject_id": "CHAR_LIN", "predicate": "position", "value": "门口", "authority": "SOURCE_FACT"}],
    }
    baseline = build_shot_plan(treatment=treatment, blocking=blocking)
    return treatment, blocking, baseline


def test_creative_candidate_preserves_structural_facts_and_changes_only_creative_layer():
    treatment, blocking, baseline = _inputs()
    candidate = build_creative_shot_plan_candidate(structural_shot_plan=baseline, treatment=treatment, blocking=blocking)
    assert candidate["director_mode"] == "creative_planner_shadow"
    assert candidate["model_info"]["llm_called"] is False
    assert [item["plan_shot_id"] for item in candidate["shots"]] == [item["plan_shot_id"] for item in baseline["shots"]]
    assert candidate["shots"][0]["event"] == baseline["shots"][0]["event"]
    assert candidate["shots"][0]["asset_bindings"] == baseline["shots"][0]["asset_bindings"]
    assert candidate["shots"][0]["why_this_shot"]
    assert candidate["shots"][0]["camera"] != baseline["shots"][0]["camera"]


def test_llm_callable_requires_both_explicit_gates_and_is_injectable():
    _, _, baseline = _inputs()
    calls = []

    def fake_llm(evidence):
        calls.append(evidence)
        return {"shots": baseline["shots"]}

    blocked = build_creative_shot_plan_candidate(structural_shot_plan=baseline, llm_callable=fake_llm)
    assert calls == []
    assert blocked["director_mode"] == "deterministic_fallback"
    called = build_creative_shot_plan_candidate(structural_shot_plan=baseline, llm_callable=fake_llm, confirmed=True, allow_external_call=True)
    assert len(calls) == 1
    assert called["model_info"]["llm_called"] is True


def test_fact_override_is_fail_closed():
    _, _, baseline = _inputs()
    with pytest.raises(DirectorFactOverride):
        build_creative_shot_plan_candidate(
            structural_shot_plan=baseline,
            llm_output={"shots": [{"plan_shot_id": "S01", "event": "编造新的剧情"}]},
        )
    with pytest.raises(DirectorFactOverride):
        build_creative_shot_plan_candidate(
            structural_shot_plan=baseline,
            llm_output={"shots": [{"plan_shot_id": "S01", "source_beat_id": "B99"}]},
        )


def test_auxiliary_shot_requires_source_and_is_bounded():
    _, _, baseline = _inputs()
    candidate = build_creative_shot_plan_candidate(
        structural_shot_plan=baseline,
        llm_output={
            "shots": baseline["shots"] + [
                {"plan_shot_id": "S01-R01", "source_beat_id": "B01", "auxiliary_type": "reaction", "why_this_shot": "承接进入后的反应", "camera": {"shot_size": "CU", "angle": "eye_level", "movement": "static"}, "purpose": "reaction", "dramatic_function": "reaction"}
            ]
        },
    )
    assert len(candidate["shots"]) == len(baseline["shots"]) + 1
    assert candidate["shots"][-1]["source_beat_id"] == "B01"


def test_malformed_creative_proposal_falls_back_without_relaxing_fact_guard():
    _, _, baseline = _inputs()
    # An auxiliary shot without provenance is a creative contract error.  It
    # must not abort the whole pipeline or be admitted by weakening the
    # validator; the safe deterministic baseline is returned instead.
    candidate = build_creative_shot_plan_candidate(
        structural_shot_plan=baseline,
        llm_output={
            "shots": baseline["shots"] + [
                {
                    "plan_shot_id": "S01-R01",
                    "auxiliary_type": "reaction",
                    "why_this_shot": "承接进入后的反应",
                    "camera": {"shot_size": "CU", "angle": "eye_level", "movement": "static"},
                }
            ]
        },
    )
    assert candidate["director_mode"] == "deterministic_fallback"
    assert candidate["model_info"]["llm_called"] is False
    assert [item["plan_shot_id"] for item in candidate["shots"]] == [item["plan_shot_id"] for item in baseline["shots"]]


def test_quality_validator_detects_repetition_motivation_redundancy_and_flatline():
    plan = {"shots": []}
    for index in range(4):
        plan["shots"].append({"plan_shot_id": f"S{index+1:02d}", "purpose": "coverage", "camera": {"shot_size": "MS", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "center"}, "composition": {"dominant_subject": "c1"}, "emotion": {"intensity": 5}, "information_strategy": {}})
    issues = validate_director_quality(plan)
    codes = {item["code"] for item in issues}
    assert "CAMERA_REPETITION" in codes
    assert "UNMOTIVATED_SHOT" in codes
    assert "REDUNDANT_SHOT" in codes
    assert "EMOTIONAL_FLATLINE" in codes
    assert all(item["target_layer"] == "DIRECTOR_CREATIVE" for item in issues)


def test_quality_score_is_separate_from_structural_score_and_repair_is_bounded():
    treatment, blocking, baseline = _inputs()
    candidate = build_creative_shot_plan_candidate(structural_shot_plan=baseline, treatment=treatment, blocking=blocking)
    quality = score_director_quality(candidate, treatment=treatment, blocking=blocking)
    assert set(quality["dimensions"]) == {"DRAMATIC_CLARITY", "SHOT_MOTIVATION", "EMOTIONAL_PROGRESSION", "VISUAL_STORYTELLING", "SPATIAL_CLARITY", "PERFORMANCE_DIRECTION", "EDIT_RHYTHM", "INFORMATION_STRATEGY", "POWER_DYNAMICS", "SHOT_DIVERSITY"}
    assert 0 <= quality["director_quality_score"] <= 100
    options = build_director_repair_options(candidate, [{"code": "UNMOTIVATED_SHOT", "shot_id": "S01"}])
    assert options[0]["target_layer"] == "DIRECTOR_CREATIVE"
    repaired = apply_director_local_repair(candidate, {"code": "UNMOTIVATED_SHOT", "target_layer": "DIRECTOR_CREATIVE", "patch": [{"op": "add", "path": "/shots/0/why_this_shot", "value": "强调进入"}]})
    assert repaired["target_layer"] == "DIRECTOR_CREATIVE"
    with pytest.raises(ValueError):
        apply_director_local_repair(candidate, {"target_layer": "DIRECTOR_CREATIVE", "patch": [{"op": "replace", "path": "/shots/0/event", "value": "改事实"}]})


def test_blind_review_hides_source_roles_and_records_only_explicit_preference():
    treatment, blocking, baseline = _inputs()
    candidate = build_creative_shot_plan_candidate(structural_shot_plan=baseline, treatment=treatment, blocking=blocking)
    from core.director_benchmark import compare_director_plans
    comparison = compare_director_plans(baseline=baseline, planner=candidate, treatment=treatment, blocking=blocking)
    review = prepare_blind_review(comparison)
    assert review["source_roles_hidden"] is True
    assert {item["label"] for item in review["versions"]} == {"Version A", "Version B"}
    assert all("role" not in item for item in review["versions"])
    saved = record_blind_preference(review, preferred_version="Version A", reason="构图更清晰", judge_fingerprint="judge-test")
    assert saved["preferred_version"] == "Version A"


def test_creative_llm_api_fails_closed_before_reading_or_calling_provider():
    with patch("api.shot_plan_api.llm_client.call_llm_json") as call:
        response = TestClient(app).post("/api/books/999999/episodes/1/shot-plan/creative-llm-draft", json={})
    assert response.status_code == 409
    assert call.call_count == 0
