"""DirectorPlan shadow tests for the persistence layer.

These tests write to the same SQLite database as the rest of the test
suite. They only insert draft plans; they never advance plan status
beyond ``draft``.
"""
from core.director_plan import build_director_plan
from core.director_plan_shadow import persist_shadow_plan, bootstrap_shadow_state
from models import AgentPlan, Session


def _cleanup_plan(plan_id: int) -> None:
    with Session() as s:
        row = s.get(AgentPlan, plan_id)
        if row is not None:
            s.delete(row)
            s.commit()


def test_bootstrap_shadow_state_idempotent():
    bootstrap_shadow_state()
    bootstrap_shadow_state()


def test_persist_shadow_plan_only_draft():
    plan = build_director_plan(
        "obj",
        {"book_id": 1},
        {"items": []},
        [{"operation": "diagnose"}],
    )
    plan_id = persist_shadow_plan(plan)
    try:
        with Session() as s:
            row = s.get(AgentPlan, plan_id)
            assert row is not None
            assert row.status == "draft"
            assert row.plan_fingerprint == plan["plan_fingerprint"]
    finally:
        _cleanup_plan(plan_id)


def test_persist_rejects_non_draft_status():
    plan = build_director_plan(
        "obj", {"book_id": 1}, {"items": []}, [{"operation": "diagnose"}]
    )
    plan["status"] = "running"
    try:
        persist_shadow_plan(plan)
    except ValueError:
        return
    raise AssertionError("non-draft status should be rejected")