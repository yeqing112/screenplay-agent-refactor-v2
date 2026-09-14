from core.director_creative_value import evaluate_useful_creative_acceptance, evaluate_useful_creative_acceptance_v3


def _opp(opportunity_id="OPP_B01_REACTION"):
    return {
        "opportunity_id": opportunity_id,
        "type": "OPP_REACTION",
        "scene_id": "SCENE_01",
        "beat_id": "B01",
        "subjects": ["C1"],
        "reason": "存在反应窗口",
        "evidence_refs": ["treatment.beat_map.B01"],
        "priority": "high",
        "eligible": True,
        "recommended_directing_dimensions": ["performance_direction", "edit_strategy"],
    }


def _decision(decision="ACT", **extra):
    value = {"opportunity_id": "OPP_B01_REACTION", "decision": decision, "strategy": "反应完成后再切" if decision == "ACT" else "", "reason": ""}
    value.update(extra)
    return value


def test_useful_acceptance_requires_all_six_conditions():
    result = evaluate_useful_creative_acceptance(
        opportunities=[_opp()],
        decisions=[_decision()],
        interventions=[{"opportunity_id": "OPP_B01_REACTION", "patch_valid": True, "applied": True, "fact_contract_pass": True, "new_blocker": False, "quality_delta": 2.0, "dimension_deltas": {"edit_strategy": 2.0}}],
    )
    assert result["useful_accepted_count"] == 1
    assert result["useful_creative_acceptance_rate"] == 1.0
    assert result["outcomes"][0]["final_status"] == "USEFUL_ACCEPTED"


def test_accepted_but_no_positive_quality_delta_is_not_useful():
    result = evaluate_useful_creative_acceptance(
        opportunities=[_opp()], decisions=[_decision()],
        interventions=[{"opportunity_id": "OPP_B01_REACTION", "patch_valid": True, "applied": True, "fact_contract_pass": True, "new_blocker": False, "quality_delta": 0, "dimension_deltas": {}}],
    )
    assert result["useful_accepted_count"] == 0
    assert result["outcomes"][0]["final_status"] == "ACCEPTED_NO_MEASURABLE_VALUE"


def test_contract_failure_and_valid_skip_are_distinct_from_missed_opportunity():
    first = _opp("OPP_B01_REACTION")
    second = _opp("OPP_B02_REACTION")
    result = evaluate_useful_creative_acceptance(
        opportunities=[first, second],
        decisions=[_decision(), {"opportunity_id": "OPP_B02_REACTION", "decision": "SKIP_WITH_REASON", "reason": "已有镜头覆盖"}],
        interventions=[{"opportunity_id": "OPP_B01_REACTION", "patch_valid": False, "applied": False, "fact_contract_pass": False, "new_blocker": False}],
    )
    statuses = {item["opportunity_id"]: item["final_status"] for item in result["outcomes"]}
    assert statuses["OPP_B01_REACTION"] == "REJECTED_CONTRACT"
    assert statuses["OPP_B02_REACTION"] == "SKIPPED_VALID_REASON"
    assert result["missed_opportunity_count"] == 0


def test_unrelated_dimension_delta_cannot_credit_an_opportunity():
    opportunity = _opp()
    opportunity["recommended_directing_dimensions"] = ["emotion_arc"]
    result = evaluate_useful_creative_acceptance(
        opportunities=[opportunity],
        decisions=[_decision()],
        interventions=[{
            "opportunity_id": opportunity["opportunity_id"],
            "patch_valid": True,
            "applied": True,
            "fact_contract_pass": True,
            "new_blocker": False,
            "quality_delta": 4,
            "dimension_deltas": {"shot_diversity": 4},
        }],
    )
    assert result["useful_accepted_count"] == 0
    assert result["outcomes"][0]["final_status"] == "ACCEPTED_NO_MEASURABLE_VALUE"
    assert result["outcomes"][0]["causal_attribution"]["target_dimension_improved"] is False


def test_v3_uses_act_denominator_and_preserves_valid_skip_as_addressed():
    first = _opp("OPP_B01_REACTION")
    second = _opp("OPP_B02_REACTION")
    result = evaluate_useful_creative_acceptance_v3(
        opportunities=[first, second],
        decisions=[_decision(), {"opportunity_id": second["opportunity_id"], "decision": "SKIP_WITH_REASON", "reason": "已有覆盖"}],
        interventions=[{"opportunity_id": first["opportunity_id"], "patch_valid": True, "applied": True, "fact_contract_pass": True, "new_blocker": False, "quality_delta": 2, "dimension_deltas": {"EDIT_RHYTHM": 2}}],
    )
    assert result["schema_version"] == "director_useful_creative_acceptance_v3"
    assert result["act_realization_rate"] == 1.0
    assert result["opportunity_address_rate"] == 1.0
