"""Provider-free audit tests for the retry/regenerate contract boundary.

These tests freeze observed current behavior. They intentionally do not add
retry or regenerate implementation.
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint

from core.canonical_generation import ProductionGenerationSelection, canonical_request_fingerprint
from models import (
    GenerationExecutionRecord,
    MediaCandidateRecord,
    OfficialMediaPointer,
    OfficialMediaVersion,
    StoryboardVideoRetryAttempt,
)


def _unique_names(table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_generation_execution_foundation_has_no_business_retry_route():
    from api.generation_execution_api import router

    paths = {route.path for route in router.routes}
    assert "/generation/executions" in paths
    assert "/generation/executions/{execution_id}" in paths
    assert "/generation/executions/{execution_id}/run" in paths
    assert "/generation/executions/{execution_id}/retry" not in paths
    assert "/generation/executions/{execution_id}/regenerate" not in paths


def test_generation_execution_schema_has_transport_count_but_no_business_lineage():
    columns = GenerationExecutionRecord.__table__.c
    assert "transport_retry_count" in columns
    assert "parent_execution_id" not in columns
    assert "retry_root_execution_id" not in columns
    assert "retry_attempt_number" not in columns
    assert "retry_reason" not in columns
    assert "supersedes_execution_id" not in columns
    assert ("provider_request_fingerprint",) in _unique_names(GenerationExecutionRecord.__table__)


def test_canonical_request_identity_is_stable_without_attempt_identity():
    selection = ProductionGenerationSelection(
        book_id=1,
        episode=1,
        storyboard_shot_id=2,
        target_media="IMAGE",
        model_profile_id="image-profile",
        generation_mode="TEXT_TO_IMAGE",
    )
    kwargs = {
        "selection": selection,
        "prompt_ir_payload_hash": "prompt",
        "prompt_ir_version_id": 3,
        "generation_payload_fingerprint": "payload",
        "generation_policy_fingerprint": "policy",
        "model_profile_fingerprint": "profile",
        "adapter_id": "image",
        "adapter_version": "v1",
    }
    assert canonical_request_fingerprint(**kwargs) == canonical_request_fingerprint(**kwargs)


def test_legacy_video_retry_shape_is_task_and_video_specific():
    columns = StoryboardVideoRetryAttempt.__table__.c
    assert {"source_task_id", "retry_root_task_id", "attempt_number", "input_snapshot", "retry_task_id"} <= set(columns.keys())
    assert "generation_execution_id" not in columns
    assert "candidate_id" not in columns
    assert ("source_task_id",) in _unique_names(StoryboardVideoRetryAttempt.__table__)


def test_candidate_history_and_official_pointer_cardinality_are_distinct():
    assert ("execution_id",) in _unique_names(MediaCandidateRecord.__table__)
    assert ("book_id", "episode", "storyboard_shot_id", "media_role") in _unique_names(OfficialMediaPointer.__table__)
    assert ("book_id", "episode", "storyboard_shot_id", "media_role", "revision") in _unique_names(OfficialMediaVersion.__table__)


def test_generation_and_promotion_are_separate_domain_records():
    execution_columns = set(GenerationExecutionRecord.__table__.c.keys())
    candidate_columns = set(MediaCandidateRecord.__table__.c.keys())
    assert "official_promotion_count" in execution_columns
    assert "candidate_id" in execution_columns
    assert "official_media_version_id" not in execution_columns
    assert "official_media_version_id" not in candidate_columns


def test_audit_does_not_expose_a_regenerate_intent_field():
    columns = set(GenerationExecutionRecord.__table__.c.keys())
    assert "regeneration_reason" not in columns
    assert "creative_variant_index" not in columns
    assert "intent_id" not in columns
