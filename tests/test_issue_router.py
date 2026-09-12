from core.issue_router import route_issue


def test_issue_router_assigns_shot_plan_responsibility_for_action_overload():
    routed = route_issue({"code": "action_overloaded", "severity": "blocked"})
    assert routed["target_layer"] == "SHOT_PLAN"
    assert routed["blocking"] is True


def test_issue_router_does_not_route_unknown_creative_issue_to_prompt():
    assert route_issue({"code": "director_style_flat", "severity": "warning"})["target_layer"] == "DIRECTOR_QA"


def test_issue_router_routes_executability_to_executability_layer():
    assert route_issue({"code": "executability_blocked", "severity": "error"})["target_layer"] == "EXECUTABILITY"


def test_issue_router_cannot_relabel_action_overload_as_prompt_text():
    assert route_issue({"code": "action_overloaded", "severity": "blocked", "target_layer": "PROMPT_TEXT"})["target_layer"] == "SHOT_PLAN"
