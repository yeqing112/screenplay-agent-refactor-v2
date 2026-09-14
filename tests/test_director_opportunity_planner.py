from core.director_opportunity_planner import validate_planner_decisions


def _opportunity(opportunity_id, *, eligible=True):
    return {
        "opportunity_id": opportunity_id,
        "type": "OPP_REACTION",
        "scene_id": "SCENE_01",
        "beat_id": opportunity_id.replace("OPP_", "B"),
        "subjects": ["C1"],
        "reason": "证据显示存在反应窗口",
        "evidence_refs": ["treatment.beat_map"],
        "priority": "high",
        "eligible": eligible,
        "recommended_directing_dimensions": ["performance_direction"],
    }


def test_planner_requires_explicit_decision_for_every_eligible_opportunity():
    result = validate_planner_decisions(
        [{"opportunity_id": "OPP_B01_REACTION", "decision": "ACT", "strategy": "反应完成后再切"}],
        [_opportunity("OPP_B01_REACTION"), _opportunity("OPP_B02_REACTION")],
    )
    assert result["status"] == "invalid"
    assert result["errors"][0]["code"] == "OPPORTUNITY_DECISION_MISSING"


def test_planner_accepts_act_and_valid_skip_and_orders_by_evidence():
    result = validate_planner_decisions(
        {
            "decisions": [
                {"opportunity_id": "OPP_B02_REACTION", "decision": "SKIP_WITH_REASON", "reason": "已有镜头覆盖同一反应"},
                {"opportunity_id": "OPP_B01_REACTION", "decision": "ACT", "strategy": "保留反应停顿 0.5 秒"},
            ]
        },
        [_opportunity("OPP_B01_REACTION"), _opportunity("OPP_B02_REACTION")],
    )
    assert result["status"] == "valid"
    assert [item["opportunity_id"] for item in result["decisions"]] == ["OPP_B01_REACTION", "OPP_B02_REACTION"]


def test_non_applicable_opportunity_can_be_explicitly_marked_not_applicable():
    result = validate_planner_decisions(
        [{"opportunity_id": "OPP_B01_REACTION", "decision": "NOT_APPLICABLE"}],
        [_opportunity("OPP_B01_REACTION", eligible=False)],
    )
    assert result["status"] == "valid"


def test_silent_skip_and_empty_act_are_rejected():
    missing_reason = validate_planner_decisions(
        [{"opportunity_id": "OPP_B01_REACTION", "decision": "SKIP_WITH_REASON"}],
        [_opportunity("OPP_B01_REACTION")],
    )
    empty_act = validate_planner_decisions(
        [{"opportunity_id": "OPP_B01_REACTION", "decision": "ACT"}],
        [_opportunity("OPP_B01_REACTION")],
    )
    assert missing_reason["status"] == "invalid"
    assert empty_act["status"] == "invalid"
