from core.director_tail_analysis import build_tail_analysis


def test_tail_analysis_reports_required_distribution_and_buckets():
    result = build_tail_analysis([{"scene_id": f"S{i}", "director_quality_score": score} for i, score in enumerate([29, 52, 65, 72, 81, 90, 95, 99, 60, 88])])
    stats = result["statistics"]
    assert stats["min"] == 29.0
    assert stats["p10"] == 29.0
    assert stats["median"] == 72.0
    assert stats["max"] == 99.0
    assert result["buckets"]["<60"] == 2
    assert len(result["bottom_3_scenes"]) == 3
    assert len(result["bottom_20_percent"]) == 2


def test_tail_analysis_reads_nested_quality_scores_and_keeps_missing_records_out():
    result = build_tail_analysis([
        {"scene_id": "S1", "quality": {"overall_director_quality": {"after_repair": 75}}},
        {"scene_id": "S2"},
    ])
    assert result["statistics"]["count"] == 1
    assert result["bottom_3_scenes"][0]["scene_id"] == "S1"
