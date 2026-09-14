from core.director_opportunity_evaluation import build_eligibility_metrics, build_planner_outcome_metrics


def _item(opportunity_id, *, eligible=True, kind="OPP_REACTION"):
    return {
        "opportunity_id": opportunity_id,
        "type": kind,
        "scene_id": "SCENE_01",
        "beat_id": opportunity_id.replace("OPP_", "B"),
        "subjects": ["C1"],
        "reason": "证据显示该节拍存在导演决策窗口",
        "evidence_refs": ["treatment.beat_map"],
        "priority": "medium",
        "eligible": eligible,
        "recommended_directing_dimensions": ["performance_direction", "edit_strategy"],
    }


def test_eligibility_metrics_keep_non_applicable_out_of_the_denominator():
    metrics = build_eligibility_metrics([_item("OPP_B01_REACTION"), _item("OPP_B02_PROP", eligible=False, kind="OPP_PROP_EMPHASIS")])
    assert metrics["eligible_opportunity_count"] == 1
    assert metrics["non_applicable_opportunity_count"] == 1
    assert metrics["by_type"]["OPP_PROP_EMPHASIS"]["eligible_rate"] == 0.0


def test_planner_outcomes_report_valid_skip_and_silent_miss_separately():
    opportunities = [_item("OPP_B01_REACTION"), _item("OPP_B02_REACTION")]
    outcomes = [{
        "opportunity_id": "OPP_B01_REACTION",
        "eligible": True,
        "planner_decision": "SKIP_WITH_REASON",
        "decision_reason": "前一镜已完成同一反应覆盖",
        "accepted": False,
        "repaired": False,
        "fallback": False,
        "quality_delta": 0,
        "dimension_deltas": {},
        "final_status": "SKIPPED_VALID_REASON",
    }]
    metrics = build_planner_outcome_metrics(opportunities, outcomes)
    assert metrics["valid_skip_count"] == 1
    assert metrics["missed_opportunity_count"] == 1
    assert metrics["missed_opportunity_rate"] == 0.5
