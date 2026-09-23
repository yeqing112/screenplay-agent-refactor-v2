"""Provider-free reproduction for the J2.3 media currentness fail-open bug."""

from __future__ import annotations

import pytest

from core.media_authority import MediaAuthorityError, _current_authority_snapshot, promote_media_candidate, validate_media_candidate
from models import GenerationExecutionRecord, MediaCandidateRecord, MediaValidationRecord, OfficialMediaVersion, PromptIRPointer, Session
from tests.test_media_validation_promotion_contract import _fixture


def test_missing_current_prompt_pointer_fails_closed():
    candidate_id, execution_id, _path, shot_id = _fixture(label="missing-current-prompt-pointer", shot_id=9801, with_prompt_ir=False)
    with Session() as session:
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one()
        snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
        assert snapshot["prompt_ir"]["pointer_present"] is False
        # This assertion intentionally fails on the pre-correction HEAD: the
        # old snapshot treated a missing pointer as a matching authority.
        assert snapshot["currentness_valid"] is False
        assert shot_id == execution.storyboard_shot_id


def test_missing_pointer_blocks_validation_and_promotion_rows():
    candidate_id, execution_id, _path, shot_id = _fixture(label="missing-pointer-validation", shot_id=9802, with_prompt_ir=False)
    with Session() as session:
        with pytest.raises(MediaAuthorityError) as exc:
            validate_media_candidate(session, candidate_id)
        assert exc.value.code == "MEDIA_CURRENT_PROMPT_IR_INVALID"
        assert session.query(MediaValidationRecord).filter_by(candidate_id=candidate_id).count() == 0
        assert session.query(OfficialMediaVersion).filter_by(storyboard_shot_id=shot_id).count() == 0


def test_deleting_current_pointer_stales_validation_before_promotion():
    candidate_id, execution_id, _path, shot_id = _fixture(label="delete-current-pointer", shot_id=9803)
    with Session() as session:
        validation = validate_media_candidate(session, candidate_id)
        pointer = session.query(PromptIRPointer).filter_by(book_id=990401, episode=1, storyboard_shot_id=shot_id, target_media="IMAGE").one()
        session.delete(pointer)
        session.commit()
        with pytest.raises(MediaAuthorityError) as exc:
            promote_media_candidate(session, candidate_id, validation["validation_id"], confirmation=True)
        assert exc.value.code == "MEDIA_PROMOTION_STALE"
        assert session.query(MediaValidationRecord).filter_by(validation_id=validation["validation_id"]).one().status == "STALE"
        assert session.query(OfficialMediaVersion).filter_by(storyboard_shot_id=shot_id).count() == 0


def test_video_execution_cannot_fallback_to_image_pointer():
    candidate_id, execution_id, _path, shot_id = _fixture(label="video-only-image-pointer", shot_id=9804)
    with Session() as session:
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one()
        candidate.media_type = execution.target_media = "VIDEO"
        session.commit()
        snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
        assert snapshot["prompt_ir"]["pointer_present"] is False
        assert snapshot["currentness_valid"] is False


def test_missing_generation_policy_fingerprint_fails_closed():
    candidate_id, execution_id, _path, _shot_id = _fixture(label="missing-policy-fingerprint", shot_id=9805)
    with Session() as session:
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one()
        execution.generation_policy_fingerprint = ""
        session.commit()
        snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
        assert snapshot["prompt_ir"]["generation_policy_matches"] is False
        assert snapshot["currentness_valid"] is False
