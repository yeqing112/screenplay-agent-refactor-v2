import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core.visual_asset_authority import build_asset_key
from core.visual_authoring_provider import validate_visual_authoring_proposal
from models import Session, VisualAssetPointer, VisualAssetVersion, VisualAuthoringDecision, VisualAuthoringProposal, init_db


def _profile():
    return {
        "id": "canonical-provider-test",
        "capability": "llm",
        "enabled": True,
        "key_configured": True,
        "model_name": "test-llm",
        "provider": "openai-compatible",
        "base_url": "https://provider.invalid/v1",
        "default_params": {"temperature": 0, "max_tokens": 1800},
        "api_key": "not-used-by-test",
    }


def _payload(request_id, asset_key):
    return {
        "schema_version": "visual_authoring_proposal_v2",
        "request_id": request_id,
        "asset_key": asset_key,
        "proposals": [
            {"field": "baseline_hairstyle", "value": "low bun", "scope": {}, "design_intent": "stable silhouette", "constraint_refs": []},
            {"field": "wardrobe", "value": "dark coat", "scope": {"episode": 1}, "design_intent": "night variant", "constraint_refs": []},
        ],
        "unknowns": ["jewelry is unspecified"],
        "review_notes": ["human review required"],
    }


def test_provider_contract_requires_full_canonical_key_and_preserves_unknowns():
    result = validate_visual_authoring_proposal(
        _payload("r1", "book:7:character:C1"),
        request={
            "request_id": "r1",
            "asset_key": "book:7:character:C1",
            "asset_type": "character",
            "free_authoring_space": ["baseline_hairstyle", "wardrobe"],
            "source_constraints": [{"field": "gender", "value": "female"}],
        },
    )
    assert result["ok"] is True
    assert result["normalized"]["unknowns"] == ["jewelry is unspecified"]
    bad = validate_visual_authoring_proposal(_payload("r1", "character:C1"), request={"request_id": "r1", "asset_key": "book:7:character:C1", "asset_type": "character", "free_authoring_space": ["baseline_hairstyle"]})
    assert bad["ok"] is False
    assert "PROPOSAL_ASSET_MISMATCH" in bad["reason_codes"]


def test_provider_canary_is_confirmation_gated_and_deduplicated():
    init_db()
    client = TestClient(app)
    book_id = 999701
    asset_key = build_asset_key(book_id=book_id, asset_type="character", canonical_id="C1")
    with Session() as session:
        session.query(VisualAuthoringProposal).filter_by(book_id=book_id).delete(synchronize_session=False)
        session.query(VisualAuthoringDecision).filter_by(book_id=book_id).delete(synchronize_session=False)
        session.query(VisualAssetPointer).filter_by(book_id=book_id).delete(synchronize_session=False)
        session.query(VisualAssetVersion).filter_by(book_id=book_id).delete(synchronize_session=False)
        session.commit()
    request = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/authoring-requests", json={
        "missing_field": "baseline_hairstyle",
        "source_constraints": [{"field": "gender", "value": "female"}],
        "free_authoring_space": ["baseline_hairstyle", "wardrobe"],
    })
    assert request.status_code == 200, request.text
    request_id = request.json()["request_id"]
    with patch("api.visual_authoring_provider_api.get_profile", return_value=_profile()), patch(
        "api.visual_authoring_provider_api.llm_client.call_llm_json", return_value=_payload(request_id, asset_key)
    ) as call:
        denied = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/authoring-proposals/canary", json={"requestId": request_id, "modelProfileId": "canonical-provider-test", "confirmedProviderCall": False})
        assert denied.status_code == 409
        first = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/authoring-proposals/canary", json={"requestId": request_id, "modelProfileId": "canonical-provider-test", "confirmedProviderCall": True})
        second = client.post(f"/api/books/{book_id}/visual-assets/authority/character/C1/authoring-proposals/canary", json={"requestId": request_id, "modelProfileId": "canonical-provider-test", "confirmedProviderCall": True})
    assert first.status_code == 200, first.text
    assert first.json()["proposal"]["status"] == "REVIEW_REQUIRED"
    assert second.status_code == 200 and second.json()["deduplicated"] is True
    call.assert_called_once()
    proposal_id = first.json()["proposal"]["proposal_id"]
    approved = client.post(f"/api/books/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}/approve", json={"confirmed": True})
    assert approved.status_code == 200, approved.text
    assert len(approved.json()["decision_ids"]) == 2
    assert approved.json()["version_created"] is False
    with Session() as session:
        assert session.query(VisualAuthoringDecision).filter_by(book_id=book_id).count() == 2
        assert session.query(VisualAssetVersion).filter_by(book_id=book_id).count() == 0


def test_provider_approval_rejects_canonical_version_drift():
    init_db()
    client = TestClient(app)
    book_id = 999702
    asset_key = build_asset_key(book_id=book_id, asset_type="scene", canonical_id="S1")
    request = client.post(f"/api/books/{book_id}/visual-assets/authority/scene/S1/authoring-requests", json={
        "missing_field": "lighting_look",
        "source_constraints": [{"field": "material", "value": "brick"}],
        "free_authoring_space": ["lighting_look"],
    })
    assert request.status_code == 200
    request_id = request.json()["request_id"]
    payload = {**_payload(request_id, asset_key), "proposals": [{"field": "lighting_look", "value": "cold side light", "scope": {}, "design_intent": "preserve depth", "constraint_refs": []}]}
    with patch("api.visual_authoring_provider_api.get_profile", return_value=_profile()), patch(
        "api.visual_authoring_provider_api.llm_client.call_llm_json", return_value=payload
    ):
        created = client.post(f"/api/books/{book_id}/visual-assets/authority/scene/S1/authoring-proposals/canary", json={"requestId": request_id, "modelProfileId": "canonical-provider-test", "confirmedProviderCall": True})
    assert created.status_code == 200
    with Session() as session:
        session.add(VisualAssetVersion(book_id=book_id, asset_key=asset_key, asset_type="scene", canonical_id="S1", canonical_identity_json="{}", scope_json="{}", revision=1, payload_json="{}", payload_hash="drifted", source_constraints_json="[]", authoring_decisions_json="[]", variant_binding_json="{}", source_constraint_fingerprint="", authoring_decision_fingerprint="", variant_fingerprint="", authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]"))
        session.commit()
    proposal_id = created.json()["proposal"]["proposal_id"]
    rejected = client.post(f"/api/books/{book_id}/visual-assets/authority/authoring-proposals/{proposal_id}/approve", json={"confirmed": True})
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "AUTHORING_REQUEST_STALE"
