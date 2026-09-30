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
    produced = _execution("exec-b", "FAILED")
    other_root = _execution("exec-other-root", "FAILED", book=2, shot=8)
    session.add_all([source, produced, other_root])
    session.commit()
    before_candidate_count = session.query(MediaCandidateRecord).count()
    service = GenerationAttemptLineageService(session)
    first = service.create_retry_intent(source_execution_id="exec-a", operation_idempotency_key="op-1", reason="provider timeout")
    session.commit()
    second = service.create_retry_intent(source_execution_id="exec-a", operation_idempotency_key="op-1", reason="provider timeout")
    assert first.attempt_lineage_id == second.attempt_lineage_id
    with pytest.raises(GenerationAttemptLineageError) as error:
        service.create_retry_intent(source_execution_id="exec-a", operation_idempotency_key="op-1", reason="operator requested another variant")
    assert error.value.code == "GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT"
    assert first.operation_kind == "RETRY"
    assert source.status == "FAILED"
    assert first.attempt_number == 1
    assert first.variant_index == 0
    assert first.retry_attempt_key
    assert source.transport_retry_count == 4
    assert session.query(MediaCandidateRecord).count() == before_candidate_count
    assert service.verify_confirmation(first.attempt_lineage_id, service.build_confirmation(first.attempt_lineage_id))
    sibling = service.create_retry_intent(source_execution_id="exec-a", operation_idempotency_key="op-2", reason="second explicit retry")
    assert sibling.attempt_number == 2
    service.bind_produced_execution(first.attempt_lineage_id, "exec-b")
    chained = service.create_retry_intent(source_execution_id="exec-b", operation_idempotency_key="op-3")
    assert chained.root_execution_id == "exec-a"
    assert chained.attempt_number == 3
    independent = service.create_retry_intent(source_execution_id="exec-other-root", operation_idempotency_key="op-other")
    assert independent.attempt_number == 1
    assert independent.variant_index == 0


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
    before_candidate_count = session.query(MediaCandidateRecord).count()
    before_pointer_version = session.query(OfficialMediaPointer).one().official_media_version_id
    row = GenerationAttemptLineageService(session).create_regenerate_intent(source_official_media_version_id="official-image", operation_idempotency_key="reg-1")
    assert row.source_execution_id == "image-exec"
    assert row.source_candidate_id == "candidate-image"
    assert row.variant_index == 1
    assert row.attempt_number == 1
    assert row.regenerate_variant_key
    assert row.retry_attempt_key is None
    assert row.target_media == "IMAGE"
    assert session.query(MediaCandidateRecord).count() == before_candidate_count
    assert session.query(OfficialMediaPointer).one().official_media_version_id == before_pointer_version


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


def test_regenerate_variant_two_and_idempotency_conflict(session):
    execution = _execution("image-exec", "SUCCESS")
    candidate = MediaCandidateRecord(
        candidate_id="candidate-image", execution_id="image-exec", status="MEDIA_CANDIDATE", media_type="IMAGE",
        storage_identity="fixture://image", storage_reference_json="{}", metadata_json="{}", checksum_sha256="checksum",
        mime_type="image/png", byte_size=1, width=1, height=1, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt",
        generation_payload_fingerprint="payload", model_profile_id="model", model_profile_fingerprint="model-fp",
        provider_request_fingerprint="image-exec-request", provider_response_hash="response",
    )
    official = OfficialMediaVersion(
        official_media_version_id="official-image", book_id=1, episode=1, storyboard_shot_id=7, plan_shot_id="",
        media_role="SHOT_PRIMARY_IMAGE", media_type="IMAGE", candidate_id="candidate-image", candidate_fingerprint="fp",
        storage_identity="fixture://image", checksum_sha256="checksum", mime_type="image/png", byte_size=1,
        width=1, height=1, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt", generation_payload_fingerprint="payload",
        provider_request_fingerprint="image-exec-request", provider_response_hash="response", validation_id="validation",
        validation_fingerprint="validation-fp", revision=1, status="CURRENT", payload_hash="official-payload",
    )
    pointer = OfficialMediaPointer(book_id=1, episode=1, storyboard_shot_id=7, media_role="SHOT_PRIMARY_IMAGE", official_media_version_id="official-image", authority_id="authority", fingerprint="pointer-fp")
    session.add_all([execution, candidate, official, pointer])
    session.commit()
    service = GenerationAttemptLineageService(session)
    first = service.create_regenerate_intent(source_official_media_version_id="official-image", operation_idempotency_key="reg-a")
    second = service.create_regenerate_intent(source_official_media_version_id="official-image", operation_idempotency_key="reg-b")
    assert first.variant_index == 1
    assert second.variant_index == 2
    video_execution = _execution("video-exec", "SUCCESS", media="VIDEO")
    video_candidate = MediaCandidateRecord(
        candidate_id="candidate-video", execution_id="video-exec", status="MEDIA_CANDIDATE", media_type="VIDEO",
        storage_identity="fixture://video", storage_reference_json="{}", metadata_json="{}", checksum_sha256="video-checksum",
        mime_type="video/mp4", byte_size=1, width=1, height=1, duration_ms=1000, prompt_ir_version_id=1,
        prompt_ir_payload_hash="prompt", generation_payload_fingerprint="payload", model_profile_id="model",
        model_profile_fingerprint="model-fp", provider_request_fingerprint="video-exec-request", provider_response_hash="response",
    )
    video_official = OfficialMediaVersion(
        official_media_version_id="official-video", book_id=1, episode=1, storyboard_shot_id=7, plan_shot_id="",
        media_role="SHOT_PRIMARY_VIDEO", media_type="VIDEO", candidate_id="candidate-video", candidate_fingerprint="video-fp",
        storage_identity="fixture://video", checksum_sha256="video-checksum", mime_type="video/mp4", byte_size=1,
        width=1, height=1, duration_ms=1000, prompt_ir_version_id=1, prompt_ir_payload_hash="prompt",
        generation_payload_fingerprint="payload", provider_request_fingerprint="video-exec-request", provider_response_hash="response",
        validation_id="video-validation", validation_fingerprint="video-validation-fp", revision=1, status="CURRENT", payload_hash="video-official-payload",
    )
    video_pointer = OfficialMediaPointer(book_id=1, episode=1, storyboard_shot_id=7, media_role="SHOT_PRIMARY_VIDEO", official_media_version_id="official-video", authority_id="video-authority", fingerprint="video-pointer-fp")
    session.add_all([video_execution, video_candidate, video_official, video_pointer])
    session.commit()
    video_row = service.create_regenerate_intent(source_official_media_version_id="official-video", operation_idempotency_key="reg-video")
    assert video_row.variant_index == 1
    with pytest.raises(GenerationAttemptLineageError) as error:
        service.create_retry_intent(source_execution_id="image-exec", operation_idempotency_key="reg-a")
    assert error.value.code == "GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT"


def test_produced_execution_binding_is_once_only_and_scope_checked(session):
    source = _execution("source", "FAILED")
    produced = _execution("produced", "CREATED")
    other = _execution("other", "CREATED", shot=8)
    session.add_all([source, produced, other])
    session.commit()
    service = GenerationAttemptLineageService(session)
    row = service.create_retry_intent(source_execution_id="source", operation_idempotency_key="bind-1")
    bound = service.bind_produced_execution(row.attempt_lineage_id, "produced")
    assert bound.status == "BOUND"
    assert service.bind_produced_execution(row.attempt_lineage_id, "produced").produced_execution_id == "produced"
    with pytest.raises(GenerationAttemptLineageError) as error:
        service.bind_produced_execution(row.attempt_lineage_id, "other")
    assert error.value.code == "GENERATION_ATTEMPT_ALREADY_BOUND"
    with pytest.raises(GenerationAttemptLineageError) as error:
        service.bind_produced_execution(row.attempt_lineage_id, "source")
    assert error.value.code == "GENERATION_ATTEMPT_ALREADY_BOUND"
    fresh = service.create_retry_intent(source_execution_id="source", operation_idempotency_key="bind-2")
    with pytest.raises(GenerationAttemptLineageError) as error:
        service.bind_produced_execution(fresh.attempt_lineage_id, "source")
    assert error.value.code == "GENERATION_ATTEMPT_SCOPE_MISMATCH"
