"""Provider-free reproduction for the J2.3 media currentness fail-open bug."""

from __future__ import annotations

import pytest

from core.media_authority import MediaAuthorityError, _current_authority_snapshot, promote_media_candidate, validate_media_candidate
from core.prompt_ir_phase_e import _prompt_ir_payload_basis, fingerprint, validate_prompt_ir_current_scope
from models import GenerationExecutionRecord, MediaCandidateRecord, MediaValidationRecord, OfficialMediaVersion, PromptIRPointer, Session
from tests.test_media_validation_promotion_contract import _fixture


def test_live_lineage_drift_is_not_hidden_by_fresh_stored_prompt(monkeypatch):
    """Deterministically reproduce the pre-correction live-lineage fail-open."""
    from types import SimpleNamespace
    import json
    from tests.test_prompt_ir_phase_e_semantic_closure import _snapshots

    snapshots = _snapshots()
    snapshot = snapshots[0]
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models import Base
    from core.prompt_ir_phase_e import compile_storyboard_snapshot_to_prompt_ir
    from tests.test_prompt_ir_phase_e_semantic_closure import _persist_v2_for_resolver
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    ir = compile_storyboard_snapshot_to_prompt_ir(snapshot)[0]
    shot, _version, _authority, _pointer = _persist_v2_for_resolver(db, snapshot, ir)
    shot_id = shot.id
    source = snapshot["ordered_shots"][0]
    row = SimpleNamespace(
        id=shot_id,
        plan_shot_id="plan-live-lineage-drift",
        projection_fingerprint=source["projection_fingerprint"],
        meta_info=json.dumps({
            "visual_semantic_handoff": source["visual_semantic_handoff"],
            "projection_payload": source["projection_payload"],
            "prompt_compiler_handoff": source["prompt_compiler_handoff"],
        }),
    )
    current_set = SimpleNamespace(id=1, scene_id=snapshot["scene_id"], set_payload_fingerprint="set-current", status="MATERIALIZED", stale_status="FRESH")
    drifted = json.loads(json.dumps(snapshot))
    drifted["ordered_shots"][0]["visual_semantic_handoff"]["information_visibility"] = "UPSTREAM_REVISED"
    monkeypatch.setattr("core.storyboard_materializer.resolve_current_authoritative_materialization", lambda *args, **kwargs: (current_set, [row], drifted["authority_envelope"]))
    monkeypatch.setattr("core.storyboard_materializer.build_storyboard_production_snapshot", lambda **kwargs: drifted)
    monkeypatch.setattr("core.prompt_ir_phase_e.validate_prompt_ir_historical_integrity", lambda *args, **kwargs: {"integrity_valid": True})
    # Use the isolated resolver database so the reproduction has a real
    # StoryboardShot and persisted source authority lineage.
    result = validate_prompt_ir_current_scope(db, book_id=77, episode=1, storyboard_shot_id=shot_id, target_media="IMAGE")
    # This assertion is expected to fail on the pre-correction HEAD: the
    # current-scope wrapper promoted historical integrity to live currentness.
    assert result["current_lineage_valid"] is False
    db.close()
    engine.dispose()


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


def test_unmarked_prompt_without_source_lineage_fails_closed_even_when_fresh():
    candidate_id, _execution_id, _path, shot_id = _fixture(label="missing-source-lineage", shot_id=9808)
    with Session() as session:
        version = session.query(__import__("models", fromlist=["PromptIRVersion"]).PromptIRVersion).filter_by(storyboard_shot_id=shot_id).one()
        pointer = session.query(PromptIRPointer).filter_by(storyboard_shot_id=shot_id, target_media="IMAGE").one()
        authority = session.query(__import__("models", fromlist=["PromptIRAuthority"]).PromptIRAuthority).filter_by(prompt_ir_version_id=version.id).one()
        payload = __import__("json").loads(version.payload_json)
        payload.pop("legacy_fixture_contract", None)
        payload_hash = fingerprint(_prompt_ir_payload_basis(payload))
        payload["prompt_ir_payload_fingerprint"] = payload_hash
        payload["payload_hash"] = payload_hash
        version.payload_json = __import__("json").dumps(payload, ensure_ascii=False, sort_keys=True)
        version.payload_hash = payload_hash
        pointer.payload_hash = payload_hash
        envelope = __import__("json").loads(authority.envelope_json)
        envelope["prompt_ir_payload_hash"] = payload_hash
        envelope.pop("envelope_fingerprint", None)
        envelope["envelope_fingerprint"] = fingerprint(envelope)
        authority.envelope_json = __import__("json").dumps(envelope, ensure_ascii=False, sort_keys=True)
        authority.envelope_fingerprint = envelope["envelope_fingerprint"]
        session.commit()
        result = validate_prompt_ir_current_scope(session, book_id=990401, episode=1, storyboard_shot_id=shot_id, target_media="IMAGE")
        assert result["integrity_valid"] is True
        assert result["current_lineage_valid"] is False
        assert result["obsolete_due_to_upstream_change"] is True
        assert version.stale_status == "FRESH" and authority.stale_status == "FRESH"


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


def test_persisted_lowercase_media_scope_fails_closed():
    candidate_id, execution_id, _path, _shot_id = _fixture(label="lowercase-media-scope", shot_id=9806)
    with Session() as session:
        candidate = session.query(MediaCandidateRecord).filter_by(candidate_id=candidate_id).one()
        execution = session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one()
        candidate.media_type = execution.target_media = "image"
        session.commit()
        snapshot = _current_authority_snapshot(session, candidate=candidate, execution=execution)
        assert snapshot["currentness_valid"] is False
