from core.director_creative_value import build_creative_value_score


def test_creative_value_score_uses_declared_weights_and_is_separate_from_director_quality():
    result = build_creative_value_score(
        opportunity_coverage=1.0,
        useful_creative_acceptance=0.8,
        edit_strategy=0.8,
        emotion_arc=0.8,
        information_strategy=0.8,
        tail_stability=0.8,
    )
    assert result["status"] == "ready"
    assert result["score"] == 85.0
    assert "director_quality_score" not in result


def test_creative_value_score_does_not_treat_missing_evidence_as_zero():
    result = build_creative_value_score(
        opportunity_coverage=1.0,
        useful_creative_acceptance=None,
        edit_strategy=1.0,
        emotion_arc=1.0,
        information_strategy=1.0,
        tail_stability=1.0,
    )
    assert result["status"] == "needs_information"
    assert result["score"] is None


def test_creative_value_score_rejects_out_of_range_component():
    result = build_creative_value_score(
        opportunity_coverage=1.2,
        useful_creative_acceptance=0.8,
        edit_strategy=0.8,
        emotion_arc=0.8,
        information_strategy=0.8,
        tail_stability=0.8,
    )
    assert result["status"] == "invalid"
