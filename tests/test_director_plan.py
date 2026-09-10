"""Phase 0 director plan shadow tests.

These tests do not call any LLM, do not write to production tables, and
do not require the API to be running. They only verify that the
DirectorPlan builder classifies operations, derives a stable fingerprint,
and refuses to mark a plan as auto-executable when it contains C / D
tier operations.
"""
from core.director_plan import (
    build_director_plan,
    classify_tool_tier,
    director_plan_fingerprint,
    summarise_plan,
)


def test_classify_tool_tier():
    assert classify_tool_tier("diagnose") == "A"
    assert classify_tool_tier("continuity_check") == "A"
    assert classify_tool_tier("draft_prompt") == "B"
    assert classify_tool_tier("write_prompt_version") == "C"
    assert classify_tool_tier("adopt_script_revision") == "C"
    assert classify_tool_tier("image_generation") == "D"
    assert classify_tool_tier("video_generation") == "D"
    assert classify_tool_tier("totally_unknown_op") == "D"
    assert classify_tool_tier("") == "D"


def test_build_director_plan_only_reads():
    plan = build_director_plan(
        "diagnose storyboard 1",
        {"book_id": 75, "episode": 1, "shot_id": 3},
        {"items": [{"id": "shot-3", "tier": "locked_fact"}]},
        [
            {"operation": "diagnose", "description": "audit shot 3"},
            {"operation": "continuity_check", "description": "compare with shot 2"},
        ],
    )
    assert plan["tier_counts"] == {"A": 2, "B": 0, "C": 0, "D": 0}
    assert plan["auto_executable"] is True
    assert plan["status"] == "draft"
    assert all(not s["requires_confirmation"] for s in plan["steps"])
    assert plan["plan_fingerprint"]


def test_build_director_plan_with_confirmations():
    plan = build_director_plan(
        "repair and rewrite shot",
        {"book_id": 75, "shot_id": 3},
        {"items": []},
        [
            {"operation": "draft_repair", "description": "draft fix"},
            {"operation": "write_prompt_version", "description": "create new prompt version"},
            {"operation": "image_generation", "description": "produce a still"},
        ],
    )
    assert plan["tier_counts"] == {"A": 0, "B": 1, "C": 1, "D": 1}
    assert plan["auto_executable"] is False
    confirmation_steps = [s for s in plan["steps"] if s["requires_confirmation"]]
    assert len(confirmation_steps) == 2


def test_plan_fingerprint_stable():
    plan_a = build_director_plan(
        "obj",
        {"book_id": 1},
        {"items": [{"id": "a"}]},
        [{"operation": "diagnose"}],
        preconditions=["p1"],
        blocking_issues=["b1"],
    )
    plan_b = build_director_plan(
        "obj",
        {"book_id": 1},
        {"items": [{"id": "a"}]},
        [{"operation": "diagnose"}],
        preconditions=["p1"],
        blocking_issues=["b1"],
    )
    assert plan_a["plan_fingerprint"] == plan_b["plan_fingerprint"]


def test_plan_fingerprint_changes_on_steps():
    plan_a = build_director_plan(
        "obj", {"book_id": 1}, {"items": []}, [{"operation": "diagnose"}]
    )
    plan_b = build_director_plan(
        "obj", {"book_id": 1}, {"items": []}, [{"operation": "draft_prompt"}]
    )
    assert plan_a["plan_fingerprint"] != plan_b["plan_fingerprint"]


def test_summarise_plan_shape():
    plan = build_director_plan(
        "obj", {"book_id": 1}, {"items": []},
        [
            {"operation": "diagnose"},
            {"operation": "video_generation", "description": "submit"},
        ],
        blocking_issues=["missing asset"],
    )
    summary = summarise_plan(plan)
    assert summary["step_count"] == 2
    assert summary["tier_counts"] == {"A": 1, "B": 0, "C": 0, "D": 1}
    assert summary["blocking_issues"] == ["missing asset"]
    assert summary["auto_executable"] is False
    assert summary["status"] == "draft"


def test_plan_records_blocking_issues_and_preconditions():
    plan = build_director_plan(
        "obj", {"book_id": 1}, {"items": []},
        [{"operation": "diagnose"}],
        preconditions=["asset locked", "prompt version current"],
        blocking_issues=["prompt version expired"],
    )
    assert plan["preconditions"] == ["asset locked", "prompt version current"]
    assert plan["blocking_issues"] == ["prompt version expired"]