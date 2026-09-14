from core.director_tail_root_cause import classify_tail_root_cause, classify_tail_root_causes, rank_tail_root_causes_v2


def test_root_cause_prefers_structured_coverage_evidence():
    result = classify_tail_root_cause({"scene_id": "S1", "director_quality_score": 55, "coverage": {"edit_strategy_coverage": 0.2, "emotion_arc_coverage": 1.0, "information_strategy_coverage": 1.0, "useful_creative_acceptance_rate": 1.0}})
    assert result["root_cause"] == "WEAK_EDIT_STRATEGY"


def test_root_cause_prefers_eligible_coverage_over_legacy_fields():
    result = classify_tail_root_cause(
        {
            "scene_id": "S1",
            "director_quality_score": 90,
            "coverage": {"edit_strategy_coverage": 0.1},
            "eligible_coverage": {"edit_strategy": 1.0},
        }
    )
    assert result["root_cause"] == "UNKNOWN_ROOT_CAUSE"


def test_root_cause_classifies_over_directing_and_unknown_trace():
    result = classify_tail_root_cause({"scene_id": "S2", "director_quality_score": 40, "quality_trace": {"unknown_root_cause_count": 1}, "quality_issues": [{"code": "OVER_CUTTING"}]})
    assert result["root_cause"] == "UNKNOWN_ROOT_CAUSE"
    assert "OVER_DIRECTING" in result["candidate_causes"]


def test_root_cause_aggregator_returns_counts():
    result = classify_tail_root_causes([{"scene_id": "S1", "coverage": {"edit_strategy_coverage": 0.1}}])
    assert result["counts"]["WEAK_EDIT_STRATEGY"] == 1


def test_ranker_v2_uses_severity_and_is_not_order_biased():
    result = rank_tail_root_causes_v2(
        {
            "scene_id": "S1",
            "director_quality_score": 40,
            "eligible_coverage": {"edit_strategy": 0.7, "emotion_arc": 0.1, "information_strategy": 0.8},
            "priority": "high",
        }
    )
    assert result["root_cause"] == "WEAK_EMOTION_ARC"
    assert result["ranked_root_causes"][0]["score"] >= result["ranked_root_causes"][1]["score"]


def test_ranker_v2_marks_non_tail_as_not_applicable():
    result = rank_tail_root_causes_v2({"scene_id": "S2", "director_quality_score": 90, "eligible_coverage": {"edit_strategy": 1.0, "emotion_arc": 1.0, "information_strategy": 1.0}})
    assert result["root_cause"] == "NOT_APPLICABLE"
    assert result["ranked_root_causes"] == []
