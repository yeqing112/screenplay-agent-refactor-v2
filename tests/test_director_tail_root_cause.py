from core.director_tail_root_cause import classify_tail_root_cause, classify_tail_root_causes


def test_root_cause_prefers_structured_coverage_evidence():
    result = classify_tail_root_cause({"scene_id": "S1", "director_quality_score": 55, "coverage": {"edit_strategy_coverage": 0.2, "emotion_arc_coverage": 1.0, "information_strategy_coverage": 1.0, "useful_creative_acceptance_rate": 1.0}})
    assert result["root_cause"] == "WEAK_EDIT_STRATEGY"


def test_root_cause_classifies_over_directing_and_unknown_trace():
    result = classify_tail_root_cause({"scene_id": "S2", "director_quality_score": 40, "quality_trace": {"unknown_root_cause_count": 1}, "quality_issues": [{"code": "OVER_CUTTING"}]})
    assert result["root_cause"] == "UNKNOWN_ROOT_CAUSE"
    assert "OVER_DIRECTING" in result["candidate_causes"]


def test_root_cause_aggregator_returns_counts():
    result = classify_tail_root_causes([{"scene_id": "S1", "coverage": {"edit_strategy_coverage": 0.1}}])
    assert result["counts"]["WEAK_EDIT_STRATEGY"] == 1
