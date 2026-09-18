import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core.visual_authoring_provider import validate_visual_authoring_proposal
from models import Session, VisualAuthoringDecision, VisualAuthoringProposal, VisualLocation, VisualMakeup, VisualProp, init_db


def _profile():
    return {
        "id": "llm-canary-test",
        "capability": "llm",
        "enabled": True,
        "key_configured": True,
        "model_name": "test-llm",
        "provider": "openai-compatible",
        "base_url": "https://provider.invalid/v1",
        "default_params": {"temperature": 0, "max_tokens": 1800},
        "api_key": "not-used-by-mock",
    }


def _valid(request_id="req-1", asset_key="character:1"):
    return {
        "schema_version": "visual_authoring_proposal_v1",
        "request_id": request_id,
        "asset_key": asset_key,
        "proposals": [{
            "field": "baseline_hairstyle", "value": "低束黑发", "scope": {},
            "design_intent": "保持轮廓简洁", "constraint_refs": ["source:hair"]
        }],
        "unknowns": ["原文未确定饰品"],
        "review_notes": ["需要人工确认"]
    }


def test_validator_preserves_unknowns_and_accepts_only_free_space():
    result = validate_visual_authoring_proposal(
        _valid(),
        request={
            "request_id": "req-1", "asset_key": "character:1", "asset_type": "character",
            "free_authoring_space": ["baseline_hairstyle"],
            "source_constraints": {"gender": "女"},
        },
    )
    assert result["ok"] is True
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["normalized"]["unknowns"] == ["原文未确定饰品"]


def test_validator_rejects_forbidden_and_source_conflict():
    payload = _valid()
    payload["approved"] = True
    payload["proposals"] = [{
        "field": "baseline_hairstyle", "value": "金色短发", "scope": {},
        "design_intent": "", "constraint_refs": []
    }]
    result = validate_visual_authoring_proposal(
        payload,
        request={
            "request_id": "req-1", "asset_key": "character:1", "asset_type": "character",
            "free_authoring_space": ["baseline_hairstyle"],
            "source_constraints": {"baseline_hairstyle": "黑色长发"},
        },
    )
    assert result["ok"] is False
    assert "PROVIDER_OUTPUT_FORBIDDEN_FIELD" in result["reason_codes"]
    assert "SOURCE_VISUAL_CONSTRAINT_CONFLICT" in result["reason_codes"]


def test_canary_requires_confirmation_and_does_not_call_provider():
    init_db()
    client = TestClient(app)
    book_id = 998801
    with Session() as session:
        asset_id = 198801
        session.query(VisualMakeup).filter_by(book_id=book_id, id=asset_id).delete()
        session.add(VisualMakeup(id=asset_id, book_id=book_id, episode=1, character_name="测试角色", hair_style="黑发"))
        session.commit()
    request = client.post(f"/api/books/{book_id}/visual-assets/authority/character/{asset_id}/authoring-requests", json={
        "requestId": "req-confirmation", "assetKey": f"character:{asset_id}", "freeAuthoringSpace": ["baseline_hairstyle"],
        "sourceConstraints": {"gender": "女"},
    })
    assert request.status_code == 200
    with patch("api.visual_authoring_provider_api.llm_client.call_llm_json") as call:
            response = client.post(f"/api/books/{book_id}/visual-assets/authority/character/{asset_id}/authoring-proposals/canary", json={
            "requestId": "req-confirmation", "modelProfileId": "llm-canary-test", "confirmedProviderCall": False,
        })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROVIDER_CALL_CONFIRMATION_REQUIRED"
    call.assert_not_called()


def test_canary_saves_only_review_required_proposal_and_dedupes():
    init_db()
    client = TestClient(app)
    book_id = 998802
    with Session() as session:
        asset_id = 198802
        session.query(VisualLocation).filter_by(book_id=book_id, id=asset_id).delete()
        session.query(VisualAuthoringProposal).filter_by(book_id=book_id).delete()
        session.add(VisualLocation(id=asset_id, book_id=book_id, name="门厅", style="写实", description="雨夜门厅"))
        session.commit()
    response = client.post(f"/api/books/{book_id}/visual-assets/authority/scene/{asset_id}/authoring-requests", json={
        "requestId": "req-valid", "assetKey": f"scene:{asset_id}", "freeAuthoringSpace": ["lighting_look", "atmosphere"],
        "sourceConstraints": {"style": "写实"},
    })
    assert response.status_code == 200
    with patch("api.visual_authoring_provider_api.get_profile", return_value=_profile()), patch(
        "api.visual_authoring_provider_api.llm_client.call_llm_json", return_value={
            "schema_version": "visual_authoring_proposal_v1", "request_id": "req-valid", "asset_key": "scene:198802",
            "proposals": [{"field": "lighting_look", "value": "冷色侧光", "scope": {}, "design_intent": "压低空间情绪", "constraint_refs": []}],
            "unknowns": [], "review_notes": ["请人工确认"],
        }) as call:
        first = client.post(f"/api/books/{book_id}/visual-assets/authority/scene/{asset_id}/authoring-proposals/canary", json={
            "requestId": "req-valid", "modelProfileId": "llm-canary-test", "confirmedProviderCall": True,
        })
        second = client.post(f"/api/books/{book_id}/visual-assets/authority/scene/{asset_id}/authoring-proposals/canary", json={
            "requestId": "req-valid", "modelProfileId": "llm-canary-test", "confirmedProviderCall": True,
        })
    assert first.status_code == 200
    assert first.json()["proposal"]["status"] == "REVIEW_REQUIRED"
    assert first.json()["provider_calls"] == 1
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["provider_calls"] == 0
    call.assert_called_once()
    with Session() as session:
        assert session.query(VisualAuthoringDecision).filter_by(book_id=book_id).count() == 0


def test_approve_requires_review_and_creates_decision_not_version():
    init_db()
    client = TestClient(app)
    book_id = 998803
    with Session() as session:
        asset_id = 198803
        session.query(VisualProp).filter_by(book_id=book_id, id=asset_id).delete()
        session.add(VisualProp(id=asset_id, book_id=book_id, name="旧钟", description="黄铜钟"))
        session.commit()
    assert client.post(f"/api/books/{book_id}/visual-assets/authority/prop/{asset_id}/authoring-requests", json={
        "requestId": "req-approve", "assetKey": f"prop:{asset_id}", "freeAuthoringSpace": ["finish"], "sourceConstraints": {}
    }).status_code == 200
    with patch("api.visual_authoring_provider_api.get_profile", return_value=_profile()), patch(
        "api.visual_authoring_provider_api.llm_client.call_llm_json", return_value={
            "schema_version": "visual_authoring_proposal_v1", "request_id": "req-approve", "asset_key": "prop:198803",
            "proposals": [{"field": "finish", "value": "轻微磨损", "scope": {}, "design_intent": "保留使用痕迹", "constraint_refs": []}],
            "unknowns": [], "review_notes": [],
        }):
        created = client.post(f"/api/books/{book_id}/visual-assets/authority/prop/{asset_id}/authoring-proposals/canary", json={
            "requestId": "req-approve", "modelProfileId": "llm-canary-test", "confirmedProviderCall": True,
        })
    proposal_id = created.json()["proposal"]["proposal_id"]
    approved = client.post(f"/api/books/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}/approve", json={"confirmed": True})
    assert approved.status_code == 200
    assert approved.json()["version_created"] is False
    assert approved.json()["pointer_moved"] is False
    with Session() as session:
        assert session.query(VisualAuthoringDecision).filter_by(book_id=book_id).count() == 1
