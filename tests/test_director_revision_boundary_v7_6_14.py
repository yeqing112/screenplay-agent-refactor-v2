import copy
import json
from pathlib import Path

import pytest

from core.director_revision import (
    archive_stage_b_attempt,
    build_revision_parent_identity,
    evaluate_stage_b_semantic_revision_eligibility,
    is_stage_b_semantic_revision_required,
    semantic_review_fingerprint,
    stage_b_revision_feedback,
)
from core.director_semantic_grounding import SEMANTIC_REVIEW_POLICY_V2, semantic_policy_v2_fingerprint, validate_director_creative_semantic_review_v2
from core.director_source_grounded import reconcile_source_authoring_units, source_authority_content_fingerprint
from api import director_treatment_api as api
from models import DecisionPacketRecord, DirectorTreatment, DirectorTreatmentAuthority, DirectorTreatmentPointer, Session, init_db

from tests.test_director_creative_enrichment_execution_v7_6_10 import _payloads, _profile, _seed_packet


ROOT = Path(__file__).resolve().parents[1]


def _canonical_units():
    return json.loads((ROOT / "docs/canonical-canary/v7_1-director-source-grounded-authoring-contract/SOURCE_AUTHORING_UNIT_CONTRACT.json").read_text(encoding="utf-8"))["units"]


def _alternate_units():
    return json.loads((ROOT / "docs/canonical-canary/v7_6_13-stage-b-semantic-grounding-review/ATTEMPT8_SOURCE_GROUNDING_AUDIT.json").read_text(encoding="utf-8"))["source_units"]


def _info():
    review = {"status": "BLOCKED", "source_grounding": {"findings": [{"classification": "UNSUPPORTED_FACT_ASSERTION", "path": "beat_enrichments[0].transition", "matched_term": "药水味"}]}, "downstream_leakage": {"violations": [{"category": "SHOT_SIZE", "path": "visual_priority[0]", "matched_term": "特写"}]}}
    stage_a = {"status": "DIRECTOR_BEAT_PLAN_ATTEMPT7_VALIDATED", "authoring_stage": "BEAT_PLAN", "attempt_id": "attempt-7", "ir_fingerprint": "a", "materialized_fingerprint": "m"}
    stage_b = {"status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED", "authoring_stage": "CREATIVE_ENRICHMENT", "attempt_id": "attempt-8", "ir": {"beat_enrichments": []}, "ir_fingerprint": "b", "fingerprint": "b", "stage_a_materialized_fingerprint": "m", "validation_state": "VALIDATED", "merge_state": "MERGED", "semantic_review": review, "authorization_id": "auth-8", "provider_provenance": {"called": True, "calls": 1}}
    return {"progressive_director_authoring": {"stage_a": stage_a, "stage_b": stage_b}, "semantic_review": review, "director_llm_attempts": [{"attempt_id": f"attempt-{i}", "authoring_stage": "CREATIVE_ENRICHMENT"} for i in range(1, 9)], "llm_draft_in_progress": False, "stage_b_provider_request": {"provider_request_fingerprint_v2": "p8"}, "stage_b_raw_response_forensic": {"raw_response_sha256": "r8"}, "stage_b_validation": {"status": "PASS"}}


def _proposal():
    return {"decision": "ready_for_review", "creative_projection": {"status": "PROPOSED"}}


def test_source_lineage_classifies_v713_projection_drift_and_same_content():
    result = reconcile_source_authoring_units(_canonical_units(), _alternate_units())
    assert result["status"] == "PASS"
    assert result["classification"] == "SOURCE_PROJECTION_VERSION_DRIFT"
    assert result["exact_projection_equality"] is False
    assert result["semantic_content_equality"] is True
    assert result["timeline_order_recovered_from_authority"] is True
    assert result["expected_content_fingerprint"] == result["canonicalized_candidate_content_fingerprint"]


def test_source_lineage_actual_content_change_is_stale():
    candidate = copy.deepcopy(_canonical_units())
    candidate[0]["text"] = "source changed"
    result = reconcile_source_authoring_units(_canonical_units(), candidate)
    assert result["status"] == "DIRECTOR_STAGE_A_SOURCE_AUTHORITY_STALE"
    assert result["semantic_content_equality"] is False


def test_stage_b_archive_is_idempotent_and_conflicts_fail_closed():
    info = _info()
    archived, first = archive_stage_b_attempt(info, proposal=_proposal(), attempt_id="attempt-8")
    assert first["archived"] is True
    archived_again, second = archive_stage_b_attempt(archived, proposal=_proposal(), attempt_id="attempt-8")
    assert second["changed"] is False
    assert len(archived_again["progressive_director_authoring"]["stage_b_attempts"]) == 1
    changed = copy.deepcopy(archived)
    changed["progressive_director_authoring"]["stage_b"]["ir_fingerprint"] = "changed"
    with pytest.raises(ValueError, match="DIRECTOR_STAGE_B_ARCHIVE_CONFLICT"):
        archive_stage_b_attempt(changed, proposal=_proposal(), attempt_id="attempt-8")


def test_revision_eligibility_requires_full_state_contract():
    info = _info()
    assert is_stage_b_semantic_revision_required(info, _proposal()) is True
    report = evaluate_stage_b_semantic_revision_eligibility(info, _proposal())
    assert all(report["checks"].values())
    blocked = copy.deepcopy(info)
    blocked["progressive_director_authoring"]["stage_b"]["merge_state"] = "PENDING"
    assert is_stage_b_semantic_revision_required(blocked, _proposal()) is False


def test_dynamic_attempt_lineage_and_revision_parent_identity():
    info = _info()
    assert len(info["director_llm_attempts"]) == 8
    parent = build_revision_parent_identity(parent_attempt_id="attempt-8", parent_ir_fingerprint="b", semantic_review=info["semantic_review"], stage_a_attempt_id="attempt-7", stage_a_materialized_fingerprint="m", source_authoring_unit_fingerprint="projection", source_authority_content_fingerprint=source_authority_content_fingerprint(_canonical_units()))
    assert parent["revision_parent_attempt_id"] == "attempt-8"
    assert parent["revision_parent_stage_b_ir_fingerprint"] == "b"
    assert parent["revision_parent_semantic_review_fingerprint"] == semantic_review_fingerprint(info["semantic_review"])


def test_revision_feedback_is_constraint_only_and_compact():
    feedback = stage_b_revision_feedback(_info()["semantic_review"])
    assert feedback["fresh_generation_required"] is True
    assert feedback["is_repair_instruction"] is False
    assert all(set(item) == {"category", "path", "matched_term", "constraint"} for item in feedback["constraints"])


def test_attempt_lineage_is_dynamic_for_8_9_10():
    from core.director_forensic import resolve_next_director_attempt_context
    for count, expected in [(8, "attempt-9"), (9, "attempt-10"), (10, "attempt-11")]:
        info = {"director_llm_attempts": [{"attempt_id": f"attempt-{i}"} for i in range(1, count + 1)]}
        assert resolve_next_director_attempt_context(info, authoring_stage="CREATIVE_ENRICHMENT").attempt_id == expected


def _seed_revision_packet(packet_fp: str = "revision-v7-6-14"):
    scene, treatment, stage_a, materialized, stage_b = _payloads()
    raw_stage_b = copy.deepcopy(stage_b)
    packet_id = _seed_packet(treatment, stage_a, materialized, packet_fp)
    review = {
        "status": "BLOCKED",
        "source_grounding": {"findings": [{"classification": "UNSUPPORTED_FACT_ASSERTION", "path": "beat_enrichments[0].transition", "matched_term": "药水味"}]},
        "downstream_leakage": {"violations": [{"category": "SHOT_SIZE", "path": "visual_priority[0]", "matched_term": "特写"}]},
    }
    stage_b = copy.deepcopy(stage_b)
    stage_b.update({
        "status": "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT8_VALIDATED",
        "authoring_stage": "CREATIVE_ENRICHMENT",
        "attempt_id": "attempt-8",
        "authorization_id": "mock-stage-b-auth-8",
        "ir_fingerprint": "stage-b-ir-8",
        "fingerprint": "stage-b-ir-8",
        "stage_a_materialized_fingerprint": "",
        "validation_state": "VALIDATED",
        "merge_state": "MERGED",
        "semantic_review": review,
        "provider_provenance": {"called": True, "calls": 1, "profile_id": "test-profile", "model": "mimo"},
    })
    # The stage-A binding must be the materialized plan fingerprint produced by
    # the shared execution fixture.
    stage_a_info = {
        "status": "DIRECTOR_BEAT_PLAN_ATTEMPT7_VALIDATED",
        "authoring_stage": "BEAT_PLAN",
        "attempt_id": "attempt-7",
        "ir": stage_a,
        "ir_fingerprint": "stage-a-ir",
        "materialized_beat_plan": materialized,
        "materialized_fingerprint": __import__("hashlib").sha256(json.dumps(materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    stage_b["stage_a_materialized_fingerprint"] = stage_a_info["materialized_fingerprint"]
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first()
        info = json.loads(row.model_info)
        info["progressive_director_authoring"]["stage_a"] = stage_a_info
        info["progressive_director_authoring"]["stage_b"] = stage_b
        info["semantic_review"] = review
        info["director_llm_attempts"].append({"attempt_id": "attempt-8", "authoring_stage": "CREATIVE_ENRICHMENT", "status": stage_b["status"]})
        info["stage_b_provider_request"] = {"provider_request_fingerprint_v2": "provider-8", "source_authoring_unit_fingerprint": treatment["source_authoring_units_fingerprint"]}
        info["stage_b_raw_response_forensic"] = {"raw_response_sha256": "raw-8"}
        info["stage_b_validation"] = {"status": "PASS"}
        row.model_info = json.dumps(info, ensure_ascii=False)
        row.proposal = json.dumps({"decision": "ready_for_review", "creative_projection": {"status": "PROPOSED"}}, ensure_ascii=False)
        row.status = "draft"
        session.commit()
    return scene, treatment, raw_stage_b, review, packet_id


def _revision_request(packet_fp: str, stage_b: dict, review: dict, **kwargs):
    attempt_id = kwargs.pop("revision_of_attempt_id", "attempt-8")
    ir_fingerprint = kwargs.pop("revision_of_stage_b_ir_fingerprint", "stage-b-ir-8")
    return api.DirectorCreativeEnrichmentRevisionLlmDraftRequest(
        scene_id="E01_SC001", packet_fingerprint=packet_fp,
        revision_of_attempt_id=attempt_id, revision_of_stage_b_ir_fingerprint=ir_fingerprint,
        semantic_review_fingerprint=semantic_review_fingerprint(review), **kwargs,
    )


def _patch_revision_runtime(monkeypatch, treatment, scene, packet_fp):
    monkeypatch.setattr(api, "_build_preview", lambda *_args, **_kwargs: (treatment, {"scene": scene}, None))
    monkeypatch.setattr(api, "_make_decision_packet", lambda *_args, **_kwargs: {"packet_fingerprint": packet_fp})
    monkeypatch.setattr(api, "_director_llm_profile_preflight", lambda: (_profile(), {"profile_id": "test-profile", "provider": "openai-compatible", "model": "mimo", "base_host": "https://example.test", "enabled": True}))


def test_revision_endpoint_requires_authorization_without_provider_or_mutation(monkeypatch):
    init_db(); packet_fp = "revision-no-auth"; scene, treatment, stage_b, review, packet_id = _seed_revision_packet(packet_fp)
    _patch_revision_runtime(monkeypatch, treatment, scene, packet_fp)
    calls = []
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **_kwargs: calls.append(1))
    req = _revision_request(packet_fp, stage_b, review)
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_AUTHORIZATION_REQUIRED"
    assert result["provider_calls"] == 0 and calls == []
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first()
        info = json.loads(row.model_info)
        assert len(info["director_llm_attempts"]) == 8
        assert "stage_b_attempts" not in info.get("progressive_director_authoring", {})
        assert json.loads(row.proposal)["decision"] == "ready_for_review"


def test_revision_mock_success_archives_attempt8_and_promotes_attempt9(monkeypatch):
    init_db(); packet_fp = "revision-success"; scene, treatment, stage_b, review, packet_id = _seed_revision_packet(packet_fp)
    _patch_revision_runtime(monkeypatch, treatment, scene, packet_fp)
    calls = []
    def mock_call(*_args, **kwargs):
        calls.append(1); kwargs["audit_callback"]({"finish_reason": "stop", "provider_request_id": "mock-revision"}); return json.dumps(stage_b, ensure_ascii=False)
    monkeypatch.setattr(api.llm_client, "call_llm", mock_call)
    req = _revision_request(packet_fp, stage_b, review, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth-9")
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED"
    assert result["confirm_allowed"] is True and len(calls) == 1
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first(); info = json.loads(row.model_info); proposal = json.loads(row.proposal)
        progressive = info["progressive_director_authoring"]
        assert progressive["stage_b"]["attempt_id"] == "attempt-9"
        assert [item["attempt_id"] for item in progressive["stage_b_attempts"]] == ["attempt-8", "attempt-9"]
        assert len(info["director_llm_attempts"]) == 9
        assert proposal["decision"] == "ready_for_review"
        assert info["llm_draft_in_progress"] is False
        assert session.query(DirectorTreatment).count() == 0
        assert session.query(DirectorTreatmentAuthority).count() == 0
        assert session.query(DirectorTreatmentPointer).count() == 0


def test_revision_mock_semantic_blocked_is_reviewable_and_next_attempt_is_dynamic(monkeypatch):
    init_db(); packet_fp = "revision-semantic-blocked"; scene, treatment, stage_b, review, packet_id = _seed_revision_packet(packet_fp)
    blocked = copy.deepcopy(stage_b)
    blocked["character_directions"][0]["direction"] = "他知道这不是第一次，药水味让他紧张。"
    blocked["visual_priority"] = ["特写"]
    _patch_revision_runtime(monkeypatch, treatment, scene, packet_fp)
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps(blocked, ensure_ascii=False))
    req = _revision_request(packet_fp, stage_b, review, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth-9")
    result = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert result["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED"
    assert result["confirm_allowed"] is False and result["semantic_review"]["status"] == "BLOCKED"
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first(); info = json.loads(row.model_info)
        assert info["progressive_director_authoring"]["stage_b"]["attempt_id"] == "attempt-9"
        assert len(info["director_llm_attempts"]) == 9
    v2_parent_review = validate_director_creative_semantic_review_v2(blocked, source_authoring_units=treatment["source_constraints"]["source_authoring_units"], declared_participants=treatment["source_constraints"].get("declared_participants", []))
    req2 = _revision_request(packet_fp, blocked, v2_parent_review, revision_of_attempt_id="attempt-9", revision_of_stage_b_ir_fingerprint=info["progressive_director_authoring"]["stage_b"]["ir_fingerprint"], semantic_review_policy=SEMANTIC_REVIEW_POLICY_V2, semantic_policy_fingerprint=semantic_policy_v2_fingerprint())
    preflight = api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req2)
    assert preflight["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED"


def test_revision_structural_failure_preserves_attempt8_active_and_archives_failed_attempt9(monkeypatch):
    init_db(); packet_fp = "revision-structural-failure"; scene, treatment, stage_b, review, packet_id = _seed_revision_packet(packet_fp)
    _patch_revision_runtime(monkeypatch, treatment, scene, packet_fp)
    monkeypatch.setattr(api.llm_client, "call_llm", lambda *_args, **kwargs: kwargs["audit_callback"]({"finish_reason": "stop"}) or json.dumps({"version": "director_creative_enrichment_ir_v1"}))
    req = _revision_request(packet_fp, stage_b, review, confirmed=True, allow_external_call=True, authorization_id="mock-stage-b-auth-9")
    with pytest.raises(api.HTTPException) as exc:
        api.generate_director_creative_enrichment_revision_llm_draft(990453, 1, req)
    assert exc.value.detail["code"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_SCHEMA_INVALID"
    with Session() as session:
        row = session.query(DecisionPacketRecord).filter_by(id=packet_id).first(); info = json.loads(row.model_info); proposal = json.loads(row.proposal)
        progressive = info["progressive_director_authoring"]
        assert progressive["stage_b"]["attempt_id"] == "attempt-8"
        assert [item["attempt_id"] for item in progressive["stage_b_attempts"]] == ["attempt-8", "attempt-9"]
        assert progressive["stage_b_attempts"][-1]["status"] == "DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_SCHEMA_INVALID"
        assert len(info["director_llm_attempts"]) == 9
        assert proposal["decision"] == "ready_for_review"
        assert info["llm_draft_in_progress"] is False
