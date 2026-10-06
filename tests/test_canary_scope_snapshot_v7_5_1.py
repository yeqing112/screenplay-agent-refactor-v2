"""Provider-free target scope and lineage snapshot tests for V7.5.1."""
from __future__ import annotations

import json

import pytest

from core.canary_scope import assert_matching_scope, build_scope_descriptor, scope_fingerprint, target_scope_snapshot
from models import (
    Book, DecisionPacketRecord, DirectorTreatment, GenerationExecutionRecord,
    MediaCandidateRecord, SceneBlocking, Session, StoryboardShot, init_db,
)


def _scope(packet_id: int) -> dict:
    return build_scope_descriptor(book_id=990453, episode=1, scene_id="E01_SC001", script_id=64, fact_snapshot_id=49, script_ir_version_id=52, decision_packet_id=packet_id)


def _execution(*, book_id: int, storyboard_shot_id: int, suffix: str) -> GenerationExecutionRecord:
    return GenerationExecutionRecord(
        execution_id=f"exec-{suffix}", book_id=book_id, episode=1, storyboard_shot_id=storyboard_shot_id,
        plan_shot_id=f"shot-{suffix}", execution_mode="PREVIEW", status="PREVIEWED", target_media="IMAGE",
        prompt_ir_version_id=1, prompt_ir_authority_id=1, prompt_ir_payload_hash="prompt", generation_payload_fingerprint=f"payload-{suffix}",
        generation_policy_fingerprint="policy", model_profile_id="profile", model_profile_fingerprint="profile-fp",
        provider_adapter_id="adapter", provider_adapter_version="v1", reference_bindings_fingerprint="refs",
        provider_request_fingerprint=f"request-{suffix}", request_snapshot_json="{}", provider="", model="",
        provider_request_id="", provider_task_id="", provider_response_hash="", logical_provider_calls=0,
        transport_retry_count=0, official_promotion_count=0,
    )


def test_scope_fingerprint_and_mismatch_guard():
    before = {"scope_descriptor": _scope(64)}
    before["scope_fingerprint"] = scope_fingerprint(before["scope_descriptor"])
    after = {"scope_descriptor": _scope(64)}
    after["scope_fingerprint"] = scope_fingerprint(after["scope_descriptor"])
    assert assert_matching_scope(before, after)["status"] == "PASS"
    different = {"scope_descriptor": _scope(65)}
    different["scope_fingerprint"] = scope_fingerprint(different["scope_descriptor"])
    with pytest.raises(ValueError, match="DB_SNAPSHOT_SCOPE_MISMATCH"):
        assert_matching_scope(before, different)


def test_target_snapshot_excludes_unrelated_book_and_uses_lineage_joins():
    init_db()
    with Session() as session:
        target_book = Book(id=990453, title="target", filename="target", status="imported")
        other_book = Book(id=990454, title="other", filename="other", status="imported")
        session.add_all([target_book, other_book]); session.flush()
        target_packet = DecisionPacketRecord(id=64, book_id=990453, domain="director_treatment", scope="{}", packet_fingerprint="target-packet", evidence="[]", unknowns="[]", conflicts="[]", allowed_operations="[]", proposal=json.dumps({"decision": "awaiting_llm"}), model_info="{}")
        other_packet = DecisionPacketRecord(book_id=990454, domain="director_treatment", scope="{}", packet_fingerprint="other-packet", evidence="[]", unknowns="[]", conflicts="[]", allowed_operations="[]", proposal="{}", model_info="{}")
        target_treatment = DirectorTreatment(book_id=990453, episode=1, scene_id="E01_SC001")
        other_treatment = DirectorTreatment(book_id=990454, episode=1, scene_id="E01_SC001")
        other_blocking = SceneBlocking(book_id=990454, episode=1, scene_id="E01_SC001")
        target_shot = StoryboardShot(book_id=990453, episode=1, scene_name="", scene_id="E01_SC001", shot_id=101)
        other_shot = StoryboardShot(book_id=990454, episode=1, scene_name="", scene_id="E01_SC001", shot_id=202)
        session.add_all([target_packet, other_packet, target_treatment, other_treatment, other_blocking, target_shot, other_shot]); session.flush()
        target_exec = _execution(book_id=990453, storyboard_shot_id=target_shot.id, suffix="target")
        other_exec = _execution(book_id=990454, storyboard_shot_id=other_shot.id, suffix="other")
        session.add_all([target_exec, other_exec]); session.flush()
        session.add_all([
            MediaCandidateRecord(candidate_id="candidate-target", execution_id=target_exec.execution_id, status="MEDIA_CANDIDATE", validation_status="PENDING", media_type="IMAGE", storage_identity="target", storage_reference_json="{}", metadata_json="{}", checksum_sha256="sha-target", mime_type="image/png", byte_size=1, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt", generation_payload_fingerprint="payload-target", model_profile_id="profile", model_profile_fingerprint="profile-fp", provider_request_fingerprint="request-target", provider_response_hash=""),
            MediaCandidateRecord(candidate_id="candidate-other", execution_id=other_exec.execution_id, status="MEDIA_CANDIDATE", validation_status="PENDING", media_type="IMAGE", storage_identity="other", storage_reference_json="{}", metadata_json="{}", checksum_sha256="sha-other", mime_type="image/png", byte_size=1, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt", generation_payload_fingerprint="payload-other", model_profile_id="profile", model_profile_fingerprint="profile-fp", provider_request_fingerprint="request-other", provider_response_hash=""),
        ])
        session.commit()
        global_treatment_count = session.query(DirectorTreatment).count()
        snapshot = target_scope_snapshot(session, scope=_scope(64))
    tables = snapshot["tables"]
    assert tables["decision_packet_records"]["count"] == 1
    assert tables["director_treatments"]["count"] == 1
    assert global_treatment_count == 2
    assert global_treatment_count != tables["director_treatments"]["count"]
    assert tables["scene_blockings"]["count"] == 0
    assert tables["storyboard_shots"]["count"] == 1
    assert tables["generation_execution_records"]["count"] == 1
    assert tables["media_candidate_records"]["count"] == 1
    assert tables["generation_execution_records"]["scope_mode"] == "LINEAGE_JOIN"
    assert tables["media_candidate_records"]["scope_mode"] == "LINEAGE_JOIN"
