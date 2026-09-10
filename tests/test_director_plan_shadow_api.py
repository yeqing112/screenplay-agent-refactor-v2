"""Phase 0 director plan shadow API tests."""
from fastapi.testclient import TestClient

from api.director_plan_shadow_api import router
from models import AgentPlan, Session


def _cleanup(plan_id: int) -> None:
    with Session() as s:
        row = s.get(AgentPlan, plan_id)
        if row is not None:
            s.delete(row)
            s.commit()


def _client() -> TestClient:
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_shadow_plan_does_not_persist_by_default():
    client = _client()
    resp = client.post(
        "/api/agent/plan",
        json={
            "objective": "diagnose",
            "scope": {"book_id": 1},
            "evidence_snapshot": {"items": []},
            "candidate_operations": [{"operation": "diagnose"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "draft"
    assert body["plan_id"] is None
    assert body["plan"]["tier_counts"] == {"A": 1, "B": 0, "C": 0, "D": 0}


def test_shadow_plan_persists_only_as_draft():
    client = _client()
    resp = client.post(
        "/api/agent/plan",
        json={
            "objective": "diagnose and submit",
            "scope": {"book_id": 1},
            "evidence_snapshot": {"items": []},
            "candidate_operations": [
                {"operation": "diagnose"},
                {"operation": "image_generation"},
            ],
            "persist": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    plan_id = body["plan_id"]
    assert plan_id is not None
    try:
        with Session() as s:
            row = s.get(AgentPlan, plan_id)
            assert row is not None
            assert row.status == "draft"
    finally:
        _cleanup(plan_id)


def test_shadow_plan_flags_confirmations():
    client = _client()
    resp = client.post(
        "/api/agent/plan",
        json={
            "objective": "x",
            "scope": {"book_id": 1},
            "evidence_snapshot": {"items": []},
            "candidate_operations": [
                {"operation": "write_prompt_version"},
                {"operation": "video_generation"},
            ],
        },
    )
    body = resp.json()
    steps = body["plan"]["steps"]
    assert all(s["requires_confirmation"] for s in steps)
    assert body["summary"]["auto_executable"] is False