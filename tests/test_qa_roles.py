from core.qa_roles import DIRECTOR_QA, HUMAN_REVIEW, VALIDATOR, build_production_pass_metrics, classify_qa_role


def test_qa_roles_keep_structural_and_creative_questions_separate():
    assert classify_qa_role({"code": "executability_blocked", "severity": "blocked"}) == VALIDATOR
    assert classify_qa_role({"code": "director_style_flat", "severity": "warning"}) == DIRECTOR_QA
    assert classify_qa_role({"code": "creative_approval_required", "severity": "warning"}) == HUMAN_REVIEW


def test_production_pass_metrics_are_fail_closed_and_keep_source_issues():
    result = build_production_pass_metrics({"issues": [
        {"code": "executability_blocked", "severity": "blocked", "shot_id": "SH1"},
        {"code": "missing_required_asset", "severity": "warning", "shot_id": "SH1"},
        {"code": "director_style_flat", "severity": "warning", "shot_id": "SH1"},
    ]})
    assert result["production_pass"] is False
    assert result["production_blocker_count"] == 1
    assert result["executability_blocked_count"] == 1
    assert result["missing_required_asset_count"] == 1
    assert len(result["issues"]) == 3
