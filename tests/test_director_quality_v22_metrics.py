from core.director_quality_metrics import build_director_quality_v22_metrics, build_director_quality_metrics


def test_v22_staged_metrics_keep_each_gate_separate():
    result = build_director_quality_v22_metrics(
        stage_counts={
            "total_scenes": 4,
            "raw_parse_pass": 4,
            "normalized_parse_pass": 4,
            "first_pass_schema_pass": 3,
            "first_pass_contract_pass": 2,
            "post_normalization_contract_pass": 3,
            "post_deterministic_repair_pass": 4,
            "post_llm_repair_pass": 4,
            "final_contract_pass": 4,
            "fallback_patch_count": 1,
            "evaluated_patch_count": 20,
        },
        repair_cost={"llm_repair_calls": 2, "repair_token_cost": 100, "repair_latency_ms": 500},
        creative_patch_count=10,
        retained_creative_patch_count=9,
        fallback_free_scene_count=3,
        scene_count=4,
    )
    assert result["stages"]["first_pass_schema_pass"]["rate"] == 0.75
    assert result["stages"]["final_contract_pass"]["rate"] == 1.0
    assert result["fallback_patch_rate"] == 0.05
    assert result["creative_retention_rate"] == 0.9
    assert result["full_creative_scene_success_rate"] == 0.75
    assert result["repair_cost"]["llm_repair_calls_per_scene"] == 0.5


def test_legacy_quality_metrics_can_attach_v22_metrics_without_changing_old_fields():
    result = build_director_quality_metrics(
        baseline={"shots": []},
        v22_stage_counts={"total_scenes": 1, "final_contract_pass": 1},
        scene_count=1,
    )
    assert result["v22"]["stages"]["final_contract_pass"]["rate"] == 1.0
    assert set(result["dimensions"]) == {"baseline", "before_repair", "after_repair"}
