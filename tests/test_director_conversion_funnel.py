from core.director_conversion_funnel import build_conversion_funnel


def test_conversion_funnel_reports_each_drop_and_does_not_penalize_valid_skip():
    trace = {
        "records": [
            {"opportunity_id": "O1", "eligible": True, "planner_decision": "ACT", "patch_ids": ["p1"], "applied_patch_ids": ["p1"], "rejected_patch_ids": [], "dimension_delta_before": {"emotion_arc": 2}, "dimension_delta_after": {"emotion_arc": 4}, "final_status": "USEFUL_ACCEPTED"},
            {"opportunity_id": "O2", "eligible": True, "planner_decision": "SKIP_WITH_REASON", "patch_ids": [], "applied_patch_ids": [], "rejected_patch_ids": [], "dimension_delta_before": {}, "dimension_delta_after": {}, "final_status": "SKIPPED_VALID_REASON"},
            {"opportunity_id": "O3", "eligible": True, "planner_decision": "ACT", "patch_ids": [], "applied_patch_ids": [], "rejected_patch_ids": [], "dimension_delta_before": {}, "dimension_delta_after": {}, "final_status": "REJECTED_QUALITY"},
            {"opportunity_id": "O4", "eligible": False, "planner_decision": "NOT_APPLICABLE", "patch_ids": [], "applied_patch_ids": [], "rejected_patch_ids": [], "dimension_delta_before": {}, "dimension_delta_after": {}, "final_status": "NOT_APPLICABLE"},
        ]
    }
    result = build_conversion_funnel(trace)
    assert result["counts"] == {"eligible_opportunities": 3, "act": 2, "intervention_produced": 1, "contract_passed": 1, "applied": 1, "target_dimension_improved": 1, "useful_accepted": 1}
    assert result["valid_skip_count"] == 1
    assert result["opportunity_address_rate"] == 0.6667
    assert result["drop_reasons"]["no_intervention"] == 1
