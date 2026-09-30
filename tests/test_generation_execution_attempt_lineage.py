from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.canonical_generation import (
    canonical_request_fingerprint,
    derive_business_attempt_provider_request_fingerprint,
    ProductionGenerationSelection,
)
from core.generation_attempt_lineage import GenerationAttemptLineageError, GenerationAttemptLineageService
from models import Base, GenerationExecutionRecord, MediaCandidateRecord, OfficialMediaPointer, OfficialMediaVersion


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    value = factory()
    try:
        yield value
    finally:
        value.close()


def _execution(execution_id="exec-a", status="FAILED", media="IMAGE", book=1, shot=7):
    return GenerationExecutionRecord(
        execution_id=execution_id, schema_version="test", book_id=book, episode=1,
        storyboard_shot_id=shot, plan_shot_id="", execution_mode="FOUNDATION", status=status,
        target_media=media, prompt_ir_version_id=1, prompt_ir_authority_id=1,
        prompt_ir_payload_hash="prompt", generation_payload_fingerprint="payload",
        generation_policy_fingerprint="policy", model_profile_id="model",
        model_profile_fingerprint="model-fp", provider_adapter_id="adapter",
        provider_adapter_version="v1", reference_bindings_fingerprint="",
        provider_request_fingerprint=execution_id + "-request", request_snapshot_json="{}",
        provider="", model="", logical_provider_calls=0, transport_retry_count=4,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )


def test_retry_is_durable_idempotent_and_does_not_touch_transport_count(session):
    source = _execution()
    session.add(source)
    session.commit()
    service = GenerationAttemptLineageService(session)
    first = service.create_retry_intent(source_execution_id="exec-a", operation_idempotency_key="op-1", reason="provider timeout")
    session.commit()
    second = service.create_retry_intent(source_execution_id="exec-a", operation_idempotency_key="op-1", reason="provider timeout")
    assert first.attempt_lineage_id == second.attempt_lineage_id
    assert first.operation_kind == "RETRY"
    assert source.transport_retry_count == 4
    assert service.verify_confirmation(first.attempt_lineage_id, service.build_confirmation(first.attempt_lineage_id))


def test_retry_rejects_success_and_stale_sources(session):
    session.add_all([_execution("success", "SUCCESS"), _execution("stale", "STALE")])
    session.commit()
    service = GenerationAttemptLineageService(session)
    for execution_id in ("success", "stale"):
        with pytest.raises(GenerationAttemptLineageError) as error:
            service.create_retry_intent(source_execution_id=execution_id, operation_idempotency_key=execution_id)
        assert error.value.code == "GENERATION_RETRY_SOURCE_NOT_FAILED"


def test_regenerate_traces_current_official_to_candidate_and_execution(session):
    execution = _execution("image-exec", "SUCCESS")
    candidate = MediaCandidateRecord(
        candidate_id="candidate-image", execution_id="image-exec", status="MEDIA_CANDIDATE", media_type="IMAGE",
        storage_identity="fixture://image", storage_reference_json="{}", metadata_json="{}",
        checksum_sha256="checksum", mime_type="image/png", byte_size=1, width=1, height=1,
        duration_ms=None, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt",
        generation_payload_fingerprint="payload", model_profile_id="model", model_profile_fingerprint="model-fp",
        provider_request_fingerprint="image-exec-request", provider_response_hash="response",
    )
    official = OfficialMediaVersion(
        official_media_version_id="official-image", book_id=1, episode=1, storyboard_shot_id=7,
        plan_shot_id="", media_role="SHOT_PRIMARY_IMAGE", media_type="IMAGE", candidate_id="candidate-image",
        candidate_fingerprint="candidate-fp", storage_identity="fixture://image", checksum_sha256="checksum",
        mime_type="image/png", byte_size=1, width=1, height=1, duration_ms=None, prompt_ir_version_id=1,
        prompt_ir_payload_hash="prompt", generation_payload_fingerprint="payload",
        provider_request_fingerprint="image-exec-request", provider_response_hash="response",
        validation_id="validation", validation_fingerprint="validation-fp", revision=1, status="CURRENT",
        payload_hash="official-payload",
    )
    pointer = OfficialMediaPointer(
        book_id=1, episode=1, storyboard_shot_id=7, media_role="SHOT_PRIMARY_IMAGE",
        official_media_version_id="official-image", authority_id="authority", fingerprint="pointer-fp",
    )
    session.add_all([execution, candidate, official, pointer])
    session.commit()
    row = GenerationAttemptLineageService(session).create_regenerate_intent(source_official_media_version_id="official-image", operation_idempotency_key="reg-1")
    assert row.source_execution_id == "image-exec"
    assert row.source_candidate_id == "candidate-image"
    assert row.variant_index == 1
    assert row.target_media == "IMAGE"


def test_confirmation_and_attempt_fingerprint_are_operation_bound(session):
    session.add(_execution())
    session.commit()
    service = GenerationAttemptLineageService(session)
    row = service.create_retry_intent(source_execution_id="exec-a", operation_idempotency_key="op-1")
    with pytest.raises(GenerationAttemptLineageError) as error:
        service.verify_confirmation(row.attempt_lineage_id, "ordinary-generation-token")
    assert error.value.code == "GENERATION_ATTEMPT_CONFIRMATION_MISMATCH"
    selection = ProductionGenerationSelection(1, 1, 7, "IMAGE", "model", "TEXT_TO_IMAGE")
    kwargs = dict(selection=selection, prompt_ir_payload_hash="p", prompt_ir_version_id=1, generation_payload_fingerprint="g", generation_policy_fingerprint="policy", model_profile_fingerprint="m", adapter_id="a", adapter_version="v")
    base = canonical_request_fingerprint(**kwargs)
    assert canonical_request_fingerprint(**kwargs) == base
    assert derive_business_attempt_provider_request_fingerprint(base, row.operation_identity_fingerprint) != base

