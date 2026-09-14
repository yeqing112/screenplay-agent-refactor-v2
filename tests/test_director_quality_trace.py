from core.director_quality_trace import (
    classify_missing_stage,
    scorer_field_present,
    trace_quality_signals,
)
from core.director_quality_validator import score_director_quality
from core.director_creative_contract import build_director_creative_contract
from core.director_creative_planner import build_creative_patch_candidate
from core.shot_plan import build_shot_plan
from core.director_creative_planner import build_creative_shot_plan_candidate
from core.scene_directing_strategy import build_scene_directing_strategy_v2
from core.director_quality_metrics import build_director_quality_v23_coverage_metrics


def _shot(**overrides):
    shot = {
        "plan_shot_id": "S01",
        "beat_id": "B01",
        "purpose": "reaction",
        "dramatic_function": "承接反应",
        "why_this_shot": "让观众看到反应完成后再切",
        "camera": {"shot_size": "CU", "angle": "eye_level", "movement": "static", "speed": "slow", "camera_side": "center"},
        "composition": {"frame_relationship": "isolated"},
        "continuity_contract": {"screen_direction": "maintain"},
        "emotion": {"intensity": 6, "start": "平静", "end": "警觉"},
        "performance_direction": [{"character_id": "C1", "objective": "确认声音来源", "visible_behavior": "先停顿半秒再抬眼"}],
        "edit": {"duration_seconds": 3.5, "cut_reason": "reaction_complete", "hold_after_action_seconds": 0.4},
        "information_strategy": {"reveals": ["反应"], "withholds": ["来源"], "audience_focus": "角色视线"},
    }
    shot.update(overrides)
    return shot


def test_valid_performance_direction_shape_is_visible_to_scorer():
    shot = _shot()
    assert scorer_field_present("PERFORMANCE_DIRECTION", shot) is True
    quality = score_director_quality({"shots": [shot]})
    assert quality["dimensions"]["PERFORMANCE_DIRECTION"] > 0


def test_provider_keyed_performance_shape_is_traced_as_path_mismatch():
    final = {"shots": [_shot(performance_direction={"C1": "抬眼确认声音来源"})]}
    trace = trace_quality_signals(
        scene_id="E01_SC01",
        planner_output=final,
        accepted_patch=final,
        final_candidate=final,
        scorer_input=final,
    )
    record = next(item for item in trace["records"] if item["dimension"] == "PERFORMANCE_DIRECTION")
    assert record["final_candidate_field_present"] is True
    assert record["scorer_field_present"] is False
    assert record["missing_stage"] == "SCORER_PATH_MISMATCH"


def test_four_dimension_strategy_evidence_and_scores_are_traced():
    shot = _shot()
    strategy = {
        "performance_arc": [{"beat_id": "B01", "character_id": "C1", "objective": "确认", "visible_behavior": "抬眼"}],
        "rhythm_curve": [{"beat_id": "B01", "pace": "hold", "cut_strategy": "反应完成后切", "target_duration_range": [3, 4]}],
        "emotion_curve": [{"beat_id": "B01", "character_id": "C1", "state": "警觉", "intensity": 6}],
        "information_plan": [{"beat_id": "B01", "audience_should_know": ["反应"], "audience_should_not_know_yet": ["来源"], "reveal_trigger": "抬眼", "reaction_priority": "人物"}],
    }
    scores = score_director_quality({"shots": [shot]})["dimensions"]
    trace = trace_quality_signals(
        scene_id="E01_SC01",
        strategy=strategy,
        planner_output={"shots": [shot]},
        accepted_patch={"shots": [shot]},
        final_candidate={"shots": [shot]},
        dimension_scores=scores,
    )
    by_dim = {item["dimension"]: item for item in trace["records"] if item["plan_shot_id"] == "S01"}
    for dimension in ("PERFORMANCE_DIRECTION", "EDIT_RHYTHM", "EMOTIONAL_PROGRESSION", "INFORMATION_STRATEGY"):
        assert by_dim[dimension]["strategy_evidence"] is True
        assert by_dim[dimension]["scorer_field_present"] is True
        assert by_dim[dimension]["dimension_score"] > 0


def test_missing_stage_taxonomy_is_fail_closed_and_ordered():
    assert classify_missing_stage(
        dimension="PERFORMANCE_DIRECTION",
        strategy_present=False,
        planner_output_present=False,
        patch_accepted=False,
        patch_rejected=False,
        patch_fallback=False,
        final_candidate_field_present=False,
        scorer_field_present=False,
        dimension_score=0,
    ) == "STRATEGY_MISSING"
    assert classify_missing_stage(
        dimension="PERFORMANCE_DIRECTION",
        strategy_present=True,
        planner_output_present=True,
        patch_accepted=True,
        patch_rejected=False,
        patch_fallback=False,
        final_candidate_field_present=True,
        scorer_field_present=False,
        dimension_score=0,
    ) == "SCORER_PATH_MISMATCH"


def test_v2_patch_planner_binds_strategy_refs_without_changing_patch_values():
    treatment = {"scene_id": "E", "scene_name": "门厅", "beat_map": [{"beat_id": "B01", "type": "reveal", "event": "发现照片"}]}
    blocking = {"scene_id": "E", "scene_name": "门厅", "participants": [{"character_id": "C1", "name": "林晚"}]}
    structural = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=structural)
    strategy = build_scene_directing_strategy_v2(treatment=treatment, contract=contract)
    result = build_creative_patch_candidate(
        structural_shot_plan=structural,
        contract=contract,
        strategy=strategy,
        llm_output={"schema_version": "director_creative_patch_v1", "patches": [{"plan_shot_id": "S01", "changes": {"emotion.intensity": 8}}], "auxiliary_shot_proposals": []},
    )
    patch = result["patch_document"]["patches"][0]
    assert patch["changes"]["emotion.intensity"] == 8
    assert patch["strategy_refs"] == ["emotion:B01:C1"]


def test_shot_planner_executes_v2_strategy_entries():
    treatment = {"scene_id": "E", "scene_name": "门厅", "beat_map": [{"beat_id": "B01", "type": "reveal", "event": "发现照片"}, {"beat_id": "B02", "type": "decision", "event": "决定离开"}]}
    blocking = {"scene_id": "E", "scene_name": "门厅", "participants": [{"character_id": "C1", "name": "林晚"}]}
    structural = build_shot_plan(treatment=treatment, blocking=blocking)
    contract = build_director_creative_contract(treatment=treatment, blocking=blocking, structural_shot_plan=structural)
    strategy = build_scene_directing_strategy_v2(treatment=treatment, contract=contract)
    candidate = build_creative_shot_plan_candidate(structural_shot_plan=structural, treatment=treatment, blocking=blocking, strategy=strategy)
    assert candidate["shots"][0]["performance_direction"][0]["visible_behavior"]
    assert candidate["shots"][0]["edit"]["cut_reason"] == strategy["rhythm_curve"][0]["cut_strategy"]
    assert candidate["shots"][0]["emotion"]["intensity"] == strategy["emotion_curve"][0]["intensity"]


def test_v23_coverage_metrics_are_explicit_and_do_not_treat_rejected_patch_as_useful():
    shot = _shot()
    strategy = {
        "emotion_curve": [{"beat_id": "B01", "character_id": "C1", "state": "警觉", "intensity": 6}],
        "information_plan": [{"beat_id": "B01", "audience_should_know": ["反应"], "audience_should_not_know_yet": [], "reveal_trigger": "抬眼", "reaction_priority": "人物"}],
    }
    metrics = build_director_quality_v23_coverage_metrics(
        candidate={"shots": [shot]},
        strategy=strategy,
        treatment={"beat_map": [{"beat_id": "B01", "type": "reveal"}]},
        proposed_patch_document={"patches": [{"plan_shot_id": "S01", "changes": {"emotion.intensity": 8}}]},
        accepted_patch_document={"patches": []},
    )
    assert metrics["performance_direction_coverage"] == 1.0
    assert metrics["edit_strategy_coverage"] == 1.0
    assert metrics["emotion_arc_coverage"] == 1.0
    assert metrics["information_strategy_coverage"] == 1.0
    assert metrics["useful_creative_acceptance_rate"] == 0.0


def test_v23_coverage_flags_mechanical_equal_duration_and_checks_emotion_execution():
    shots = [
        _shot(plan_shot_id="S01", beat_id="B01", edit={"duration_seconds": 4, "cut_reason": "beat_change"}, emotion={"intensity": 3}),
        _shot(plan_shot_id="S02", beat_id="B02", edit={"duration_seconds": 4, "cut_reason": "beat_change"}, emotion={"intensity": 8}),
        _shot(plan_shot_id="S03", beat_id="B03", edit={"duration_seconds": 4, "cut_reason": "beat_change"}, emotion={"intensity": 8}),
    ]
    strategy = {
        "emotion_curve": [
            {"beat_id": "B01", "character_id": "C1", "state": "平静", "intensity": 3},
            {"beat_id": "B02", "character_id": "C1", "state": "警觉", "intensity": 8},
            {"beat_id": "B03", "character_id": "C1", "state": "警觉", "intensity": 8},
        ]
    }
    metrics = build_director_quality_v23_coverage_metrics(candidate={"shots": shots}, strategy=strategy)
    assert metrics["mechanical_equal_duration_ratio"] == 1.0
    assert metrics["mechanical_duration_warning"] is True
    assert metrics["emotion_progression_consistency"] == 1.0

    flat = build_director_quality_v23_coverage_metrics(
        candidate={"shots": [shot | {"emotion": {"intensity": 3}} for shot in shots]},
        strategy=strategy,
    )
    assert flat["emotion_progression_consistency"] == 0.1667
