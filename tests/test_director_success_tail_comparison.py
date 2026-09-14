from core.director_success_tail_comparison import compare_success_tail


def _row(scene_id, score, *, latency, types):
    return {
        "scene_id": scene_id,
        "director_quality_score": score,
        "eligible_coverage": {"edit_strategy": 1.0 if score > 80 else 0.2},
        "patch_count": 4 if score > 80 else 1,
        "shot_count": 6 if score > 80 else 2,
        "telemetry": {"latency_ms": latency},
        "quality": {"dimensions": {"EDIT_RHYTHM": 8 if score > 80 else 2}},
        "opportunities": [{"type": item} for item in types],
    }


def test_success_tail_comparison_is_grouped_and_generates_generic_patterns():
    result = compare_success_tail([
        _row("success-1", 95, latency=100, types=["OPP_INFORMATION_REVEAL", "OPP_REACTION"]),
        _row("tail-1", 45, latency=300, types=["OPP_REACTION"]),
    ])
    assert result["status"] == "ready"
    assert result["success_count"] == 1
    assert result["tail_count"] == 1
    assert result["metrics"]["latency_ms"]["delta_success_minus_tail"] == -200.0
    assert result["metrics"]["dimension:EDIT_RHYTHM"]["delta_success_minus_tail"] == 6.0
    assert any(item["metric"] == "patch_count" for item in result["generalized_success_patterns"])
    assert result["opportunity_type_distribution"]["success"]["counts"]["OPP_INFORMATION_REVEAL"] == 1
