from core.director_opportunity_model import (
    OPPORTUNITY_SCHEMA_VERSION,
    build_opportunity_outcome,
    normalize_opportunity,
    validate_opportunity,
    validate_opportunity_outcome,
)


def _opportunity(**overrides):
    value = {
        "opportunity_id": "OPP_B03_REACTION",
        "type": "OPP_REACTION",
        "scene_id": "SCENE_01",
        "beat_id": "B03",
        "subjects": ["CHAR_002"],
        "reason": "角色获知关键信息后存在明显反应窗口",
        "evidence_refs": [{"source": "treatment", "path": "beat_map.B03"}],
        "priority": "high",
        "eligible": True,
        "recommended_directing_dimensions": ["performance_direction", "edit_strategy", "shot_motivation"],
    }
    value.update(overrides)
    return value


def test_opportunity_normalization_requires_evidence_and_preserves_schema():
    normalized = normalize_opportunity(_opportunity())
    assert normalized["schema_version"] == OPPORTUNITY_SCHEMA_VERSION
    assert normalized["evidence_refs"][0]["path"] == "beat_map.B03"
    assert validate_opportunity({**_opportunity(), "evidence_refs": []})["status"] == "invalid"


def test_non_applicable_opportunity_can_be_recorded_without_planner_action():
    opportunity = normalize_opportunity(_opportunity(eligible=False, priority="low"))
    outcome = build_opportunity_outcome(
        opportunity=opportunity,
        planner_decision="NOT_APPLICABLE",
        final_status="SKIPPED_VALID_REASON",
        decision_reason="证据不足以形成可执行导演机会",
    )
    assert outcome["eligible"] is False
    assert outcome["planner_decision"] == "NOT_APPLICABLE"


def test_eligible_skip_requires_explicit_reason_and_accepted_requires_act():
    opportunity = normalize_opportunity(_opportunity())
    invalid_skip = validate_opportunity_outcome({
        "opportunity_id": opportunity["opportunity_id"],
        "eligible": True,
        "planner_decision": "SKIP_WITH_REASON",
        "accepted": False,
        "repaired": False,
        "fallback": False,
        "quality_delta": 0,
        "dimension_deltas": {},
        "final_status": "SKIPPED_VALID_REASON",
    })
    assert invalid_skip["status"] == "invalid"
    outcome = build_opportunity_outcome(
        opportunity=opportunity,
        planner_decision="ACT",
        accepted=True,
        quality_delta=2.5,
        dimension_deltas={"edit_strategy": 2.5},
        final_status="USEFUL_ACCEPTED",
    )
    assert validate_opportunity_outcome(outcome)["status"] == "valid"


def test_opportunity_fingerprint_is_stable_for_equivalent_input():
    first = normalize_opportunity(_opportunity())
    second = normalize_opportunity({**_opportunity(), "schema_version": OPPORTUNITY_SCHEMA_VERSION})
    from core.director_opportunity_model import opportunity_fingerprint

    assert opportunity_fingerprint(first) == opportunity_fingerprint(second)
