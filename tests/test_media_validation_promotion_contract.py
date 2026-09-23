from __future__ import annotations

import base64
import hashlib
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

import pytest

import config
from core.media_authority import (
    MediaAuthorityError,
    promote_media_candidate,
    resolve_current_official_media,
    validate_media_candidate,
)
from core.prompt_ir_phase_e import build_generation_policy, fingerprint
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    MediaValidationRecord,
    OfficialMediaAuthority,
    OfficialMediaPointer,
    OfficialMediaVersion,
    PromptIRPointer,
    PromptIRAuthority,
    PromptIRVersion,
    Session,
    VisualAssetPointer,
    VisualAssetVersion,
    VisualReferenceAuthority,
    init_db,
)


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def _fixture(*, label: str | None = None, shot_id: int = 7001, with_prompt_ir: bool = True):
    init_db()
    token = label or uuid.uuid4().hex
    if label is None and shot_id == 7001:
        shot_id = 100000 + (uuid.uuid5(uuid.NAMESPACE_URL, token).int % 900000000)
    path = Path(config.UPLOAD_DIR) / f"media-authority-{token}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    execution_id = f"exec-{token}"
    candidate_id = f"candidate-{token}"
    with Session() as session:
        policy = build_generation_policy({"mode": "TEXT_TO_IMAGE", "target_media": "IMAGE"}, allow_default=False)
        prompt_payload = {"schema_version": "prompt_ir_v2", "legacy_fixture_contract": "deterministic_media_fixture_v1", "generation_policy": policy, "asset_authority_bindings": {"resolved": []}}
        prompt_hash = fingerprint(prompt_payload)
        prompt_payload["prompt_ir_payload_fingerprint"] = prompt_hash
        prompt_payload["payload_hash"] = prompt_hash
        envelope = {"schema_version": "prompt_ir_authority_envelope_v2", "storyboard_shot_id": shot_id, "fixture_token": token, "generation_policy": policy, "asset_authority_bindings": {"resolved": []}, "prompt_ir_payload_hash": prompt_hash, "qualification_state": "PROMPT_IR_QUALIFIED", "model_generation_ready": False, "stale_status": "FRESH"}
        envelope["envelope_fingerprint"] = fingerprint(envelope)
        execution_prompt_id = (100000 + (uuid.uuid5(uuid.NAMESPACE_URL, token).int % 900000000)) if with_prompt_ir else 11
        execution_prompt_hash = prompt_hash if with_prompt_ir else "prompt-hash"
        execution = GenerationExecutionRecord(
            execution_id=execution_id, schema_version="generation_execution_request_v1", book_id=990401,
            episode=1, storyboard_shot_id=shot_id, plan_shot_id=f"plan-{token}", execution_mode="EXECUTE",
            status="SUCCEEDED", target_media="IMAGE", prompt_ir_version_id=execution_prompt_id, prompt_ir_authority_id=12,
            prompt_ir_payload_hash=execution_prompt_hash, generation_payload_fingerprint=f"payload-{token}",
            generation_policy_fingerprint=policy["fingerprint"] if with_prompt_ir else "policy-hash", model_profile_id="fake-image",
            model_profile_fingerprint="profile-hash", provider_adapter_id="fake", provider_adapter_version="v1",
            reference_bindings_fingerprint="", provider_request_fingerprint=f"request-{token}",
            request_snapshot_json=json.dumps({"media_role": "SHOT_PRIMARY_IMAGE", "generation_policy": policy}), provider_response_hash=f"response-{token}",
            provider="phase-f-fake-image-provider", model="deterministic-image-v1", logical_provider_calls=1,
            transport_retry_count=0, official_promotion_count=0,
        )
        candidate = MediaCandidateRecord(
            candidate_id=candidate_id, execution_id=execution_id, status="MEDIA_CANDIDATE", media_type="IMAGE",
            storage_identity=str(path), storage_reference_json=json.dumps({"local_path": str(path)}),
            checksum_sha256=hashlib.sha256(PNG).hexdigest(), mime_type="image/png", byte_size=len(PNG),
            width=1, height=1, prompt_ir_version_id=execution_prompt_id, prompt_ir_payload_hash=execution_prompt_hash,
            generation_payload_fingerprint=f"payload-{token}", model_profile_id="fake-image",
            model_profile_fingerprint="profile-hash", provider_request_fingerprint=f"request-{token}",
            provider_response_hash=f"response-{token}", provider_task_id=f"task-{token}",
        )
        session.add(execution); session.add(candidate)
        if with_prompt_ir:
            now = datetime.now()
            session.add(PromptIRVersion(id=execution_prompt_id, book_id=990401, episode=1, scene_id="scene-fixture", storyboard_shot_id=shot_id, materialization_set_id=1, plan_shot_id=f"plan-{token}", schema_version="prompt_ir_v2", payload_json=json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True), payload_hash=prompt_hash, compiler_version="test", compiler_policy_version="test", retention_policy_version="test", authority_envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="READY", model_generation_ready="true", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now))
            session.add(PromptIRAuthority(prompt_ir_version_id=execution_prompt_id, book_id=990401, episode=1, storyboard_shot_id=shot_id, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PROMPT_IR_QUALIFIED", stale_status="FRESH", stale_reasons="[]", created_at=now, updated_at=now))
            current_pointer = session.query(PromptIRPointer).filter_by(book_id=990401, episode=1, storyboard_shot_id=shot_id, target_media="IMAGE").first()
            if current_pointer is None:
                session.add(PromptIRPointer(book_id=990401, episode=1, storyboard_shot_id=shot_id, target_media="IMAGE", prompt_ir_version_id=execution_prompt_id, payload_hash=prompt_hash, qualification_state="PROMPT_IR_QUALIFIED", created_at=now, updated_at=now))
            else:
                current_pointer.prompt_ir_version_id = execution_prompt_id
                current_pointer.payload_hash = prompt_hash
        session.commit()
    return candidate_id, execution_id, path, shot_id


def _install_manual_prompt_ir(session, *, version_id: int, shot_id: int, policy_fingerprint: str = "policy-hash", asset_bindings: dict | None = None):
    policy = {"schema_version": "generation_policy_v1", "mode": "TEXT_TO_IMAGE", "target_media": "IMAGE", "required_asset_classes": [], "optional_asset_classes": [], "style_profile_id": "", "language": "", "source": "explicit_request", "fingerprint": policy_fingerprint}
    payload = {"schema_version": "prompt_ir_v2", "legacy_fixture_contract": "deterministic_media_fixture_v1", "generation_policy": policy, "asset_authority_bindings": asset_bindings or {"resolved": []}}
    payload_hash = fingerprint(payload)
    payload["prompt_ir_payload_fingerprint"] = payload_hash
    payload["payload_hash"] = payload_hash
    envelope = {"schema_version": "prompt_ir_authority_envelope_v2", "storyboard_shot_id": shot_id, "generation_policy": policy, "asset_authority_bindings": asset_bindings or {"resolved": []}, "prompt_ir_payload_hash": payload_hash, "qualification_state": "PROMPT_IR_QUALIFIED", "model_generation_ready": False, "stale_status": "FRESH"}
    envelope["envelope_fingerprint"] = fingerprint(envelope)
    version = session.query(PromptIRVersion).filter_by(id=version_id).one()
    version.payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    version.payload_hash = payload_hash
    version.authority_envelope_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    session.add(PromptIRAuthority(prompt_ir_version_id=version_id, book_id=990401, episode=1, storyboard_shot_id=shot_id, envelope_fingerprint=envelope["envelope_fingerprint"], envelope_json=json.dumps(envelope, ensure_ascii=False, sort_keys=True), qualification_state="PROMPT_IR_QUALIFIED", stale_status="FRESH", stale_reasons="[]"))
    session.add(PromptIRPointer(book_id=990401, episode=1, storyboard_shot_id=shot_id, target_media="IMAGE", prompt_ir_version_id=version_id, payload_hash=payload_hash, qualification_state="PROMPT_IR_QUALIFIED"))
    candidate = session.query(MediaCandidateRecord).filter_by(prompt_ir_version_id=version_id).first()
    if candidate:
        candidate.prompt_ir_payload_hash = payload_hash
    execution = session.query(GenerationExecutionRecord).filter_by(prompt_ir_version_id=version_id).first()
    if execution:
        execution.prompt_ir_payload_hash = payload_hash
        execution.generation_policy_fingerprint = policy_fingerprint


def test_validation_promotion_and_exact_resolver_are_explicit_and_idempotent():
    candidate_id, _execution_id, _path, shot_id = _fixture()
    with Session() as session:
        first = validate_media_candidate(session, candidate_id)
        second = validate_media_candidate(session, candidate_id)
        assert first["reused"] is False
        assert second["reused"] is True
        promoted = promote_media_candidate(session, candidate_id, first["validation_id"], confirmation=True)
        replay = promote_media_candidate(session, candidate_id, first["validation_id"], confirmation=True)
        resolved = resolve_current_official_media(session, book_id=990401, episode=1, storyboard_shot_id=shot_id)
        assert promoted["reused"] is False
        assert replay["reused"] is True
        assert resolved["version"].official_media_version_id == promoted["version"].official_media_version_id
        assert session.query(MediaValidationRecord).filter_by(candidate_id=candidate_id).count() == 1
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 1
        assert session.query(OfficialMediaAuthority).filter_by(official_media_version_id=promoted["version"].official_media_version_id).count() == 1
        assert session.query(OfficialMediaPointer).filter_by(book_id=990401, episode=1, storyboard_shot_id=shot_id).count() == 1
        assert session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one().status == "MEDIA_CANDIDATE"


def test_storage_tamper_fails_validation_without_a_validation_row():
    candidate_id, _execution_id, path, _shot_id = _fixture()
    path.write_bytes(PNG + b"tampered")
    with Session() as session:
        with pytest.raises(MediaAuthorityError) as exc:
            validate_media_candidate(session, candidate_id)
        assert exc.value.code == "MEDIA_VALIDATION_FAILED"
        assert session.query(MediaValidationRecord).filter_by(candidate_id=candidate_id).count() == 0


def test_media_candidate_checksum_tamper_fails_promotion_closed():
    candidate_id, _execution_id, _path, _shot_id = _fixture()
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        candidate.checksum_sha256 = "tampered-checksum"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_VALIDATION_TAMPERED"
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0


def test_media_candidate_storage_tamper_after_validation_fails_promotion_closed():
    candidate_id, _execution_id, path, _shot_id = _fixture()
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        path.write_bytes(PNG + b"tampered")
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_PROMOTION_STALE"
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0


def test_candidate_official_status_is_rejected_without_mutation():
    candidate_id, _execution_id, _path, _shot_id = _fixture()
    with Session() as session:
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        candidate.status = "OFFICIAL"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            validate_media_candidate(session, candidate_id)
        assert exc.value.code == "MEDIA_CANDIDATE_IMMUTABLE_STATUS"
        assert session.query(MediaValidationRecord).filter_by(candidate_id=candidate_id).count() == 0


def test_validation_tamper_and_pointer_tamper_fail_closed():
    candidate_id, _execution_id, _path, _shot_id = _fixture()
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        validation_row = session.query(MediaValidationRecord).filter_by(validation_id=validation["validation_id"]).one()
        validation_row.technical_validation_fingerprint = "tampered"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_VALIDATION_TAMPERED"
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0


def test_validation_authority_snapshot_tamper_fails_closed():
    candidate_id, _execution_id, _path, _shot_id = _fixture()
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        row = session.query(MediaValidationRecord).filter_by(validation_id=validation["validation_id"]).one()
        row.authority_snapshot_json = "{\"tampered\":true}"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_VALIDATION_TAMPERED"
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0


def test_two_different_candidates_create_explicit_revisions_and_one_pointer():
    first_id, _first_exec, _first_path, shot_id = _fixture(shot_id=9001)
    with Session() as session:
        first_validation = validate_media_candidate(session, first_id)
        first = promote_media_candidate(session, first_id, first_validation["validation_id"], confirmation=True)
        first_revision = first["version"].revision
    second_id, _second_exec, _second_path, _ = _fixture(shot_id=shot_id)
    # The fixture uses a new execution id but the same deterministic shot scope.
    with Session() as session:
        second_validation = validate_media_candidate(session, second_id)
        second = promote_media_candidate(session, second_id, second_validation["validation_id"], confirmation=True)
        versions = session.query(OfficialMediaVersion).filter_by(book_id=990401, episode=1, storyboard_shot_id=shot_id, media_role="SHOT_PRIMARY_IMAGE").order_by(OfficialMediaVersion.revision).all()
        pointer = session.query(OfficialMediaPointer).filter_by(book_id=990401, episode=1, storyboard_shot_id=shot_id, media_role="SHOT_PRIMARY_IMAGE").one()
        assert first_revision == 1
        assert second["version"].revision == 2
        assert [row.status for row in versions] == ["SUPERSEDED", "CURRENT"]
        assert pointer.official_media_version_id == second["version"].official_media_version_id


def test_prompt_ir_revision_makes_validation_stale_before_promotion():
    candidate_id, _execution_id, _path, shot_id = _fixture(shot_id=9101, with_prompt_ir=False)
    with Session() as session:
        version = PromptIRVersion(id=9101001, book_id=990401, episode=1, scene_id="scene-1", storyboard_shot_id=shot_id, materialization_set_id=1, plan_shot_id="plan", schema_version="prompt_ir_v2", payload_json=json.dumps({"generation_policy": {"fingerprint": "policy-hash"}}), payload_hash="prompt-hash", compiler_version="test", compiler_policy_version="test", retention_policy_version="test", authority_envelope_json="{}", qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="READY", model_generation_ready="true", stale_status="FRESH", stale_reasons="[]")
        session.add(version)
        session.flush()
        _install_manual_prompt_ir(session, version_id=9101001, shot_id=shot_id)
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=candidate.execution_id).one()
        candidate.prompt_ir_version_id = execution.prompt_ir_version_id = 9101001
        candidate.prompt_ir_payload_hash = execution.prompt_ir_payload_hash = version.payload_hash
        execution.generation_policy_fingerprint = "policy-hash"
        session.commit()
        validation = validate_media_candidate(session, candidate_id)
        version.payload_hash = "prompt-hash-drifted"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_PROMOTION_STALE"
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0
        assert session.query(MediaValidationRecord).filter_by(validation_id=validation["validation_id"]).one().status == "STALE"


def test_generation_policy_revision_makes_validation_stale_before_promotion():
    candidate_id, _execution_id, _path, shot_id = _fixture(shot_id=9111, with_prompt_ir=False)
    with Session() as session:
        version = PromptIRVersion(id=9111001, book_id=990401, episode=1, scene_id="scene-policy", storyboard_shot_id=shot_id, materialization_set_id=1, plan_shot_id="plan-policy", schema_version="prompt_ir_v2", payload_json=json.dumps({"generation_policy": {"fingerprint": "policy-hash"}}), payload_hash="prompt-hash", compiler_version="test", compiler_policy_version="test", retention_policy_version="test", authority_envelope_json="{}", qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="READY", model_generation_ready="true", stale_status="FRESH", stale_reasons="[]")
        session.add(version)
        session.flush()
        _install_manual_prompt_ir(session, version_id=9111001, shot_id=shot_id)
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=candidate.execution_id).one()
        candidate.prompt_ir_version_id = execution.prompt_ir_version_id = 9111001
        candidate.prompt_ir_payload_hash = execution.prompt_ir_payload_hash = version.payload_hash
        execution.generation_policy_fingerprint = "policy-hash"
        session.commit()
        validation = validate_media_candidate(session, candidate_id)
        version.payload_json = json.dumps({"generation_policy": {"fingerprint": "policy-drifted"}})
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_PROMOTION_STALE"
        assert session.query(MediaValidationRecord).filter_by(validation_id=validation["validation_id"]).one().status == "STALE"


def test_asset_revision_makes_validation_stale_before_promotion():
    candidate_id, execution_id, _path, shot_id = _fixture(shot_id=9151, with_prompt_ir=False)
    asset_key = "book:990401:prop:PHASE_G2_ASSET"
    with Session() as session:
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one()
        candidate.prompt_ir_version_id = execution.prompt_ir_version_id = 9151001
        version = PromptIRVersion(
            id=9151001, book_id=990401, episode=1, scene_id="scene-asset", storyboard_shot_id=shot_id,
            materialization_set_id=1, plan_shot_id="plan-asset", schema_version="prompt_ir_v2",
            payload_json=json.dumps({"generation_policy": {"fingerprint": "policy-hash"}, "asset_authority_bindings": {"resolved": [{"identity_ref": "PROP:PHASE_G2_ASSET", "asset_authority_ref": asset_key, "asset_version_id": 910001, "asset_version_fingerprint": "asset-hash", "authority_fingerprint": "asset-hash"}]}}),
            payload_hash="prompt-hash", compiler_version="test", compiler_policy_version="test", retention_policy_version="test",
            authority_envelope_json="{}", qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="READY", model_generation_ready="true", stale_status="FRESH", stale_reasons="[]",
        )
        asset = VisualAssetVersion(id=910001, book_id=990401, asset_key=asset_key, asset_type="prop", canonical_id="PHASE_G2_ASSET", canonical_identity_json="{}", scope_json="{}", revision=1, payload_json="{}", payload_hash="asset-hash", authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]")
        asset_pointer = VisualAssetPointer(book_id=990401, asset_key=asset_key, asset_type="prop", scope_key="phase-g2", current_version_id=910001, payload_hash="asset-hash", authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]")
        session.add_all([version, asset, asset_pointer]); session.flush()
        _install_manual_prompt_ir(session, version_id=9151001, shot_id=shot_id, asset_bindings={"resolved": [{"identity_ref": "PROP:PHASE_G2_ASSET", "asset_authority_ref": asset_key, "asset_version_id": 910001, "asset_version_fingerprint": "asset-hash", "authority_fingerprint": "asset-hash"}]})
        session.commit()
        validation = validate_media_candidate(session, candidate_id)
        asset_pointer.current_version_id = 9999999
        asset_pointer.payload_hash = "asset-hash-drifted"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_PROMOTION_STALE"
        assert session.query(MediaValidationRecord).filter_by(validation_id=validation["validation_id"]).one().status == "STALE"


def test_reference_revision_makes_validation_stale_before_promotion():
    candidate_id, execution_id, _path, shot_id = _fixture(shot_id=9161)
    asset_key = "book:990401:prop:PHASE_G2_REFERENCE"
    with Session() as session:
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one()
        execution.request_snapshot_json = json.dumps({"media_role": "SHOT_PRIMARY_IMAGE", "reference_bindings": [{"reference_authority_fingerprint": "phase-g2-reference-fp"}]})
        pointer = VisualAssetPointer(book_id=990401, asset_key=asset_key, asset_type="prop", scope_key="phase-g2-ref", current_version_id=920001, payload_hash="reference-asset-hash", authority_status="SPEC_APPROVED", stale_status="FRESH", stale_reasons="[]")
        authority = VisualReferenceAuthority(visual_reference_asset_id=1, asset_key=asset_key, asset_version_id=920001, asset_version_fingerprint="reference-asset-hash", reference_scope_json="{}", image_identity="reference", checksum="reference", storage_reference_json="{}", generation_provenance_json="{}", reference_token_mapping_json="{}", lock_revision=1, status="LOCKED", authority_fingerprint="phase-g2-reference-fp", stale_status="FRESH", stale_reasons="[]")
        session.add_all([pointer, authority]); session.commit()
        validation = validate_media_candidate(session, candidate_id)
        authority.asset_version_id = 920002
        authority.asset_version_fingerprint = "reference-asset-hash-drifted"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_PROMOTION_STALE"
        assert session.query(MediaValidationRecord).filter_by(validation_id=validation["validation_id"]).one().status == "STALE"


def test_authority_and_pointer_tamper_fail_closed():
    candidate_id, _execution_id, _path, shot_id = _fixture(shot_id=9201)
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        promoted = promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        promoted["authority"].lineage_hash = "tampered"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            resolve_current_official_media(session, book_id=990401, episode=1, storyboard_shot_id=shot_id)
        assert exc.value.code == "MEDIA_OFFICIAL_RESOLUTION_FAILED"

    candidate_id, _execution_id, _path, shot_id = _fixture(shot_id=9202)
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        promoted = promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        promoted["version"].checksum_sha256 = "tampered-version-checksum"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            resolve_current_official_media(session, book_id=990401, episode=1, storyboard_shot_id=shot_id)
        assert exc.value.code == "MEDIA_OFFICIAL_RESOLUTION_FAILED"


def test_promotion_requires_explicit_positive_confirmation_and_preserves_candidate():
    candidate_id, _execution_id, _path, _shot_id = _fixture()
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        for value in (False, "false", "", "0"):
            with pytest.raises(MediaAuthorityError) as exc:
                promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=value)
            assert exc.value.code == "MEDIA_PROMOTION_CONFIRMATION_REQUIRED"
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0
        assert session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one().status == "MEDIA_CANDIDATE"


def test_second_session_replays_same_promotion_without_duplicate_rows():
    candidate_id, _execution_id, _path, shot_id = _fixture()
    with Session() as first_session:
        validation = validate_media_candidate(first_session, candidate_id)
        first = promote_media_candidate(first_session, candidate_id, validation["validation_id"], confirmation=True)
        version_id = first["version"].official_media_version_id
    with Session() as second_session:
        replay = promote_media_candidate(second_session, candidate_id, validation["validation_id"], confirmation="confirmed")
        assert replay["reused"] is True
        assert replay["version"].official_media_version_id == version_id
        assert second_session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id, book_id=990401, episode=1, storyboard_shot_id=shot_id).count() == 1


def test_same_candidate_concurrent_promotions_commit_one_official_chain():
    candidate_id, _execution_id, _path, shot_id = _fixture(shot_id=9401)
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        validation_id = validation["validation_id"]
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        try:
            with Session() as session:
                barrier.wait(timeout=10)
                results.append(promote_media_candidate(session, candidate_id, validation_id, confirmation=True))
        except Exception as exc:  # pragma: no cover - assertion below reports unexpected races
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not errors
    assert len(results) == 2
    with Session() as session:
        versions = session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id, book_id=990401, episode=1, storyboard_shot_id=shot_id).all()
        pointers = session.query(OfficialMediaPointer).filter_by(book_id=990401, episode=1, storyboard_shot_id=shot_id, media_role="SHOT_PRIMARY_IMAGE").all()
        assert len(versions) == 1
        assert len(pointers) == 1

    candidate_id, _execution_id, _path, shot_id = _fixture(shot_id=9301)
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        pointer = session.query(OfficialMediaPointer).filter_by(book_id=990401, episode=1, storyboard_shot_id=shot_id).one()
        pointer.fingerprint = "tampered"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            resolve_current_official_media(session, book_id=990401, episode=1, storyboard_shot_id=shot_id)
        assert exc.value.code == "MEDIA_OFFICIAL_RESOLUTION_FAILED"
