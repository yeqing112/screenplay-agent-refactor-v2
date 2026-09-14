from core.director_tail_repair_acceptance import evaluate_repair_acceptance


def _quality(edit_before=2, edit_after=4, overall_before=50, overall_after=52):
    return {"director_quality_score": overall_before, "dimensions": {"EDIT_RHYTHM": edit_before}}, {"director_quality_score": overall_after, "dimensions": {"EDIT_RHYTHM": edit_after}}


def test_acceptance_requires_target_dimension_improvement_and_clean_contract():
    before, after = _quality()
    result = evaluate_repair_acceptance(before_quality=before, after_quality=after, target_dimensions=["EDIT_RHYTHM"], contract_pass=True)
    assert result["accepted"] is True
    assert result["target_dimension_deltas"] == {"EDIT_RHYTHM": 2.0}


def test_acceptance_rolls_back_for_fact_override_or_unrelated_delta():
    before, after = _quality(edit_before=2, edit_after=2)
    result = evaluate_repair_acceptance(before_quality=before, after_quality=after, target_dimensions=["EDIT_RHYTHM"], contract_pass=False, fact_override_count=1)
    assert result["accepted"] is False
    assert "CONTRACT_BLOCK" in result["reasons"]
    assert "FACT_OVERRIDE" in result["reasons"]
    assert "TARGET_DIMENSION_NOT_IMPROVED" in result["reasons"]
