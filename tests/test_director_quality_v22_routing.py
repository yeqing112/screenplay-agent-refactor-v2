from core.issue_router import route_director_repair, route_director_repair_issues


def test_routing_assigns_levels_without_calling_an_llm():
    assert route_director_repair("DIRECTOR_PATCH_PATH_CANONICALIZATION")["repair_level"] == 0
    assert route_director_repair("DUPLICATE_IDENTICAL_PATCH")["repair_level"] == 1
    level2 = route_director_repair("UNMOTIVATED_SHOT")
    assert level2["repair_level"] == 2
    assert level2["llm_allowed"] is True


def test_authority_and_identity_issues_are_reject_only():
    for code in ("DIRECTOR_FACT_OVERRIDE", "IMMUTABLE_VIOLATION", "UNKNOWN_PLAN_SHOT_ID", "INVALID_SOURCE_BEAT", "AUXILIARY_BINDING_FAILURE"):
        result = route_director_repair(code)
        assert result["route"] == "REJECT"
        assert result["llm_allowed"] is False
        assert result["fail_closed"] is True


def test_unknown_issue_is_fail_closed():
    result = route_director_repair({"code": "SOMETHING_UNSPECIFIED"})
    assert result["route"] == "REJECT"
    assert result["repair_level"] is None


def test_issue_list_keeps_original_fields_and_adds_route_metadata():
    routed = route_director_repair_issues([{"code": "EMOTIONAL_FLATLINE", "target_id": "S01"}])
    assert routed[0]["target_id"] == "S01"
    assert routed[0]["repair_level"] == 2
