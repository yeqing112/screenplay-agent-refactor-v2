import copy
import hashlib
import json

import pytest

from api import director_treatment_api as api
from core.director_revision import semantic_review_fingerprint
from core.director_semantic_grounding import (
    SEMANTIC_REVIEW_POLICY_V2,
    semantic_policy_v2_fingerprint,
    validate_director_creative_semantic_review_v2,
    validate_semantic_review_assessment_binding,
    resolve_required_semantic_review_policy,
)
from core.director_progressive_authoring import materialize_director_beat_plan_ids
from models import DecisionPacketRecord, Session, init_db

from tests.test_director_creative_enrichment_execution_v7_6_10 import _payloads, _profile, _seed_packet


def _seed_attempt9(packet_fp: str, *, blocked_parent: bool = True):
    scene, treatment, stage_a, materialized, clean_stage_b = _payloads()
    packet_id = _seed_packet(treatment, stage_a, materialized, packet_fp)
    stage_a_fp = hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    stage_b = copy.deepcopy(clean_stage_b)
    if blocked_parent:
        stage_b["beat_enrichments"][0]["character_effects"][0]["effect"] = "林晚打开铁盒。"
    stage_b_fp = hashlib.sha256(json.dumps(stage_b, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    v1 = {"schema_version": "director_creative_semantic_review_v1", "status": "BLOCKED", "source_grounding": {"findings": []}, "downstream_leakage": {"violations": []}}
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first()
        info = json.loads(row.model_info)
        progressive = info["progressive_director_authoring"]
        progressive["stage_a"]["materialized_fingerprint"] = stage_a_fp
        progressive["stage_b"] = {
            "status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED",
            "authoring_stage": "CREATIVE_ENRICHMENT",
            "attempt_id": "attempt-9",
            "ir": stage_b,
            "ir_fingerprint": stage_b_fp,
            "fingerprint": stage_b_fp,
            "stage_a_materialized_fingerprint": stage_a_fp,
            "validation_state": "VALIDATED",
            "merge_state": "MERGED",
            "semantic_review": v1,
            "authorization_id": "mock-attempt-9",
            "provider_provenance": {"called": True, "calls": 1},
        }
        info["semantic_review"] = v1
        info["director_llm_attempts"] = [{"attempt_id": f"attempt-{i}", "authoring_stage": "CREATIVE_ENRICHMENT", "status": "OLD"} for i in range(1, 10)]
        row.model_info = json.dumps(info, ensure_ascii=False)
        row.proposal = json.dumps({"decision": "ready_for_review", "creative_projection": {"status": "PROPOSED"}, "source_constraints": treatment["source_constraints"]}, ensure_ascii=False)
        row.status = "draft"
        session.commit()
    return scene, treatment, clean_stage_b, stage_b, packet_id


def _patch_runtime(monkeypatch, treatment, scene, packet_fp):
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))


def _request(packet_fp, stage_b, review, **kwargs):
    review_fp = kwargs.pop("semantic_review_fingerprint", semantic_review_fingerprint(review))
    policy = kwargs.pop("semantic_review_policy", SEMANTIC_REVIEW_POLICY_V2)
    policy_fp = kwargs.pop("semantic_policy_fingerprint", semantic_policy_v2_fingerprint())
    return api.DirectorCreativeEnrichmentRevisionLlmDraftRequest(
        scene_id="E01_SC001",
        packet_fingerprint=packet_fp,
        revision_of_attempt_id="attempt-9",
        revision_of_stage_b_ir_fingerprint=hashlib.sha256(json.dumps(stage_b, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        semantic_review_fingerprint=review_fp,
        semantic_review_policy=policy,
        semantic_policy_fingerprint=policy_fp,
        **kwargs,
    )


def test_attempt9_v2_server_recompute_and_provider_free_preflight(monkeypatch):
    init_db()
    scene, treatment, clean_stage_b, parent_stage_b, packet_id = _seed_attempt9("v7617-preflight")
    _patch_runtime(monkeypatch, treatment, scene, "v7617-preflight")
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first()
        info = json.loads(row.model_info); proposal = json.loads(row.proposal)
        review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=proposal["source_constraints"]["source_authoring_units"], declared_participants=proposal["source_constraints"].get("declared_participants", []))
        before = (row.packet_fingerprint, row.proposal, row.model_info)
        req = _request("v7617-preflight", parent_stage_b, review)
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1))
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED"
    assert result["provider_calls"] == 0 and calls == []
    assert result["execution_manifest"]["semantic_review_policy"] == SEMANTIC_REVIEW_POLICY_V2
    assert result["execution_manifest"]["semantic_policy_fingerprint"] == semantic_policy_v2_fingerprint()
    assert result["execution_manifest"]["revision_feedback"]["constraint_count"] == 1
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first()
        assert (row.packet_fingerprint, row.proposal, row.model_info) == before


def test_attempt10_mock_pass_persists_v2_and_future_revision_is_not_eligible(monkeypatch):
    init_db()
    scene, treatment, clean_stage_b, parent_stage_b, packet_id = _seed_attempt9("v7617-pass")
    _patch_runtime(monkeypatch, treatment, scene, "v7617-pass")
    parent_review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop", "provider_request_id": "mock-v2-pass"}) or json.dumps(clean_stage_b, ensure_ascii=False))
    req = _request("v7617-pass", parent_stage_b, parent_review, confirmed=True, allow_external_call=True, authorization_id="mock-attempt-10")
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_VALIDATED"
    assert result["semantic_review"]["policy_version"] == SEMANTIC_REVIEW_POLICY_V2
    assert result["confirm_allowed"] is True
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first(); info = json.loads(row.model_info)
        stage_b = info["progressive_director_authoring"]["stage_b"]
        assert stage_b["attempt_id"] == "attempt-10"
        assert stage_b["semantic_review_policy"] == SEMANTIC_REVIEW_POLICY_V2
        assert stage_b["semantic_review_v2"]["status"] == "PASS"
        assert len(info["semantic_review_assessments"]) == 1
        assert info["semantic_review_assessments"][0]["attempt_id"] == "attempt-10"
        assert info["semantic_review_assessments"][0]["status"] == "PASS"


def test_attempt10_mock_blocked_uses_v2_and_preflights_attempt11(monkeypatch):
    init_db()
    scene, treatment, clean_stage_b, parent_stage_b, packet_id = _seed_attempt9("v7617-blocked")
    _patch_runtime(monkeypatch, treatment, scene, "v7617-blocked")
    parent_review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
    blocked = copy.deepcopy(clean_stage_b)
    blocked["beat_enrichments"][0]["character_effects"][0]["effect"] = "林晚打开铁盒。"
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(blocked, ensure_ascii=False))
    req = _request("v7617-blocked", parent_stage_b, parent_review, confirmed=True, allow_external_call=True, authorization_id="mock-attempt-10")
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_VALIDATED"
    assert result["semantic_review"]["status"] == "BLOCKED"
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first(); info = json.loads(row.model_info); active = info["progressive_director_authoring"]["stage_b"]
        assert active["attempt_id"] == "attempt-10"
        attempt10_review = active["semantic_review_v2"]
        attempt10_fp = active["ir_fingerprint"]
    req11 = api.DirectorCreativeEnrichmentRevisionLlmDraftRequest(
        scene_id="E01_SC001", packet_fingerprint="v7617-blocked", revision_of_attempt_id="attempt-10", revision_of_stage_b_ir_fingerprint=attempt10_fp,
        semantic_review_fingerprint=semantic_review_fingerprint(attempt10_review), semantic_review_policy=SEMANTIC_REVIEW_POLICY_V2, semantic_policy_fingerprint=semantic_policy_v2_fingerprint(),
    )
    preflight = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req11)
    assert preflight["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED"
    assert preflight["execution_manifest"]["history_count"] == 10


def test_attempt10_structural_failure_archives_failure_and_keeps_attempt9_active(monkeypatch):
    init_db()
    scene, treatment, clean_stage_b, parent_stage_b, packet_id = _seed_attempt9("v7617-structural")
    _patch_runtime(monkeypatch, treatment, scene, "v7617-structural")
    parent_review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps({"version": "director_creative_enrichment_ir_v1"}))
    req = _request("v7617-structural", parent_stage_b, parent_review, confirmed=True, allow_external_call=True, authorization_id="mock-attempt-10")
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert exc.value.detail["code"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID"
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first(); info = json.loads(row.model_info); progressive = info["progressive_director_authoring"]
        assert progressive["stage_b"]["attempt_id"] == "attempt-9"
        assert progressive["stage_b_attempts"][-1]["attempt_id"] == "attempt-10"
        assert len([item for item in info["director_llm_attempts"] if item.get("attempt_id") == "attempt-11"]) == 0


def test_v2_request_policy_drift_and_confirm_binding_fail_closed(monkeypatch):
    init_db()
    scene, treatment, clean_stage_b, parent_stage_b, packet_id = _seed_attempt9("v7617-drift")
    _patch_runtime(monkeypatch, treatment, scene, "v7617-drift")
    parent_review = validate_director_creative_semantic_review_v2(parent_stage_b, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1))
    for override in (
        {"semantic_review_policy": "director_creative_semantic_review_v1"},
        {"semantic_policy_fingerprint": "wrong"},
        {"semantic_review_fingerprint": "old-v1"},
    ):
        kwargs = {"semantic_review_policy": SEMANTIC_REVIEW_POLICY_V2, "semantic_policy_fingerprint": semantic_policy_v2_fingerprint()}
        kwargs.update(override)
        req = _request("v7617-drift", parent_stage_b, parent_review, **kwargs)
        with pytest.raises(api.HTTPException) as exc:
            api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
        assert exc.value.status_code == 409
    assert calls == []
    good = {"policy_version": SEMANTIC_REVIEW_POLICY_V2, "semantic_policy_fingerprint": semantic_policy_v2_fingerprint(), "attempt_id": "attempt-10", "ir_fingerprint": "ir", "status": "PASS"}
    assert validate_semantic_review_assessment_binding(good, attempt_id="attempt-10", ir_fingerprint="ir")["status"] == "PASS"
    assert validate_semantic_review_assessment_binding({**good, "semantic_policy_fingerprint": "wrong"}, attempt_id="attempt-10", ir_fingerprint="ir")["status"] == "BLOCKED"
    assert validate_semantic_review_assessment_binding({**good, "attempt_id": "attempt-9"}, attempt_id="attempt-10", ir_fingerprint="ir")["status"] == "BLOCKED"


def test_policy_resolver_preserves_history_and_generalizes_future_revision_boundary():
    assert resolve_required_semantic_review_policy(attempt_id="attempt-8", revision_context=True) != SEMANTIC_REVIEW_POLICY_V2
    assert resolve_required_semantic_review_policy(attempt_id="attempt-9", revision_context=True) == SEMANTIC_REVIEW_POLICY_V2
    assert resolve_required_semantic_review_policy(attempt_id="attempt-10", revision_context=True) == SEMANTIC_REVIEW_POLICY_V2
    assert resolve_required_semantic_review_policy(attempt_id="attempt-11", revision_context=True) == SEMANTIC_REVIEW_POLICY_V2


def test_attempt10_prompt_and_provider_identity_bind_v2_boundary():
    scene, treatment, stage_a, materialized, stage_b = _payloads()
    identity = api.build_director_creative_enrichment_provider_request(
        scene_id="E01_SC001",
        materialized_beat_plan=materialized,
        stage_a_materialized_fingerprint=hashlib.sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        stage_a_attempt_id="attempt-7",
        declared_participants=treatment["source_constraints"].get("declared_participants", []),
        source_authoring_units=treatment["source_constraints"]["source_authoring_units"],
        source_authoring_unit_fingerprint=treatment["source_authoring_units_fingerprint"],
        source_authority_content_fingerprint="content-fp",
        revision_feedback={"schema_version": "director_revision_feedback_v2", "constraints": []},
        revision_parent={"revision_parent_attempt_id": "attempt-9", "revision_parent_fingerprint": "parent-fp", "revision_parent_semantic_review_fingerprint": "review-fp"},
        semantic_review_policy=SEMANTIC_REVIEW_POLICY_V2,
        semantic_policy_fingerprint=semantic_policy_v2_fingerprint(),
        profile=_profile(),
        profile_snapshot={"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True},
    )
    prompt = identity["user_prompt"]
    for marker in ("SOURCE_AUTHORING_UNITS", "REVISION_PARENT", "REVISION_FEEDBACK", "UNCERTAINTY_PRESERVATION_RULE", "STORY_ACTION_BOUNDARY", "SCENEBLOCKING_BOUNDARY", "V2_SHOTPLAN_BOUNDARY", "REVISION_GENERATION_CONTRACT"):
        assert marker in prompt
    assert "Attempt-9 raw response" not in prompt
    assert identity["semantic_review_policy"] == SEMANTIC_REVIEW_POLICY_V2
    assert identity["provider_request_payload_v2"]["semantic_policy_fingerprint"] == semantic_policy_v2_fingerprint()
