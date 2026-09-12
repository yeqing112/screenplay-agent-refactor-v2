from core.pilot_metrics import add_pipeline_completion, build_pilot_metrics


def test_metrics_keep_approval_and_manual_edit_rates_distinct():
    metrics = build_pilot_metrics(approval_gate_event_count=4, approval_gate_total=6, manual_shot_edit_count=2, shot_count=40, manual_scene_edit_count=1, scene_count=6, repair_yield={"overall_repair_yield": 0.8, "shot_plan_repair_yield": 1.0}, human_intervention_rate=0.3)
    assert metrics["approval_gate_rate"] == 0.6667
    assert metrics["manual_shot_edit_rate"] == 0.05
    assert metrics["manual_scene_edit_rate"] == 0.1667
    assert metrics["repair_yield"]["shot_plan_repair_yield"] == 1.0
    assert "human_intervention_rate" not in metrics


def test_pipeline_completion_metrics_are_explicit():
    result = add_pipeline_completion({}, approved_scenes=6, total_scenes=6, completed_episodes=3, total_episodes=3)
    assert result["scene_pipeline_completion_rate"] == 1.0
    assert result["episode_pipeline_completion_rate"] == 1.0
