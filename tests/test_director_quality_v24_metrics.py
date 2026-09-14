from core.director_quality_v24_metrics import build_director_quality_v24_metrics


def test_v24_metrics_reports_distribution_and_versioned_funnel_values():
    result = build_director_quality_v24_metrics(
        scenes=[{"scene_id": "S1", "director_quality_score": 95}, {"scene_id": "S2", "director_quality_score": 55}, {"scene_id": "S3", "director_quality_score": 75}],
        funnel={
            "trace_record_count": 4,
            "counts": {"eligible_opportunities": 4, "act": 3, "intervention_produced": 2, "contract_passed": 2, "applied": 2, "target_dimension_improved": 1, "useful_accepted": 1},
            "valid_skip_count": 1,
            "opportunity_detection_rate": 0.8,
        },
        contract_metrics={"patch_contract_first_pass_rate": 0.9, "patch_contract_final_pass_rate": 1.0},
        creative_value_metrics={"useful_creative_acceptance_rate": 0.25, "useful_creative_acceptance_v3_rate": 0.3333},
    )
    assert result["schema_version"] == "director-quality-v2-4-metrics-v1"
    assert result["quality_distribution"]["median"] == 75.0
    assert result["quality_distribution"]["buckets"] == {"<60": 1, "60-69": 0, "70-79": 1, "80-89": 0, ">=90": 1}
    assert result["eligibility_rate"] == 1.0
    assert result["act_rate"] == 0.75
    assert result["patch_contract_final_pass_rate"] == 1.0
    assert result["act_realization_rate"] == 0.3333
    assert result["opportunity_address_rate"] == 0.5
