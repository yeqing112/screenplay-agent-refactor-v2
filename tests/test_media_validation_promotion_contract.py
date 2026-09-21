from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

import pytest

import config
from core.media_authority import (
    MediaAuthorityError,
    promote_media_candidate,
    resolve_current_official_media,
    validate_media_candidate,
)
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    MediaValidationRecord,
    OfficialMediaAuthority,
    OfficialMediaPointer,
    OfficialMediaVersion,
    PromptIRPointer,
    PromptIRVersion,
    Session,
    init_db,
)


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def _fixture(*, label: str | None = None, shot_id: int = 7001):
    init_db()
    token = label or uuid.uuid4().hex
    path = Path(config.UPLOAD_DIR) / f"media-authority-{token}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    execution_id = f"exec-{token}"
    candidate_id = f"candidate-{token}"
    with Session() as session:
        execution = GenerationExecutionRecord(
            execution_id=execution_id, schema_version="generation_execution_request_v1", book_id=990401,
            episode=1, storyboard_shot_id=shot_id, plan_shot_id=f"plan-{token}", execution_mode="EXECUTE",
            status="SUCCEEDED", target_media="IMAGE", prompt_ir_version_id=11, prompt_ir_authority_id=12,
            prompt_ir_payload_hash="prompt-hash", generation_payload_fingerprint=f"payload-{token}",
            generation_policy_fingerprint="policy-hash", model_profile_id="fake-image",
            model_profile_fingerprint="profile-hash", provider_adapter_id="fake", provider_adapter_version="v1",
            reference_bindings_fingerprint="", provider_request_fingerprint=f"request-{token}",
            request_snapshot_json=json.dumps({"media_role": "SHOT_PRIMARY_IMAGE"}), provider_response_hash=f"response-{token}",
            provider="phase-f-fake-image-provider", model="deterministic-image-v1", logical_provider_calls=1,
            transport_retry_count=0, official_promotion_count=0,
        )
        candidate = MediaCandidateRecord(
            candidate_id=candidate_id, execution_id=execution_id, status="MEDIA_CANDIDATE", media_type="IMAGE",
            storage_identity=str(path), storage_reference_json=json.dumps({"local_path": str(path)}),
            checksum_sha256=__import__("hashlib").sha256(PNG).hexdigest(), mime_type="image/png", byte_size=len(PNG),
            width=1, height=1, prompt_ir_version_id=11, prompt_ir_payload_hash="prompt-hash",
            generation_payload_fingerprint=f"payload-{token}", model_profile_id="fake-image",
            model_profile_fingerprint="profile-hash", provider_request_fingerprint=f"request-{token}",
            provider_response_hash=f"response-{token}", provider_task_id=f"task-{token}",
        )
        session.add(execution); session.add(candidate); session.commit()
    return candidate_id, execution_id, path, shot_id


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
        assert exc.value.code in {"MEDIA_VALIDATION_FAILED", "MEDIA_BYTES_INVALID", "MEDIA_MIME_UNDETECTABLE"}
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
    candidate_id, _execution_id, _path, shot_id = _fixture(shot_id=9101)
    with Session() as session:
        version = PromptIRVersion(id=11, book_id=990401, episode=1, scene_id="scene-1", storyboard_shot_id=shot_id, materialization_set_id=1, plan_shot_id="plan", schema_version="prompt_ir_v2", payload_json=json.dumps({"generation_policy": {"fingerprint": "policy-hash"}}), payload_hash="prompt-hash", compiler_version="test", compiler_policy_version="test", retention_policy_version="test", authority_envelope_json="{}", qualification_state="PROMPT_IR_QUALIFIED", asset_reference_state="READY", model_generation_ready="true", stale_status="FRESH", stale_reasons="[]")
        session.add(version)
        session.add(PromptIRPointer(book_id=990401, episode=1, storyboard_shot_id=shot_id, prompt_ir_version_id=11, payload_hash="prompt-hash", qualification_state="PROMPT_IR_QUALIFIED"))
        session.commit()
        validation = validate_media_candidate(session, candidate_id)
        version.payload_hash = "prompt-hash-drifted"
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_PROMOTION_STALE"
        assert session.query(OfficialMediaVersion).filter_by(candidate_id=candidate_id).count() == 0
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
