from scripts.finalize_director_quality_v2_3_report import build_metrics, render_report


def test_report_keeps_offline_only_results_not_ready_for_shadow():
    offline = {"quality": {"variant_b": {"mean": 88.0}}}
    aggregate = {
        "quality": {"B": {"mean": 88.0, "median": 88.0, "stddev": 0.0, "p25": 88.0, "p75": 88.0}},
        "coverage": {"B": {key: {"mean": 1.0} for key in (
            "performance_direction_coverage", "edit_strategy_coverage", "emotion_arc_coverage", "information_strategy_coverage", "useful_creative_acceptance_rate"
        )}},
        "paired_delta": {"mean": 30.0, "median": 30.0, "stddev": 0.0, "p25": 30.0, "p75": 30.0},
        "independent_run_count": 1,
        "improved_run_count": 1,
        "degraded_run_count": 0,
        "run_comparisons": [],
        "per_scene_paired_delta": {},
        "variance": {},
        "safety": {"final_contract_pass_rate": 1.0, "fact_override_accepted": 0, "side_effects": {}},
        "cost": {},
    }
    metrics = build_metrics(offline=offline, aggregate=aggregate, sources={"offline": "offline.json"})
    assert metrics["gates"]["safe_to_shadow"] is True
    assert metrics["gates"]["valuable_enough_to_shadow"] is False
    assert metrics["status"] == "NOT_READY"
    assert "offline deterministic results are not treated" in render_report(metrics)
