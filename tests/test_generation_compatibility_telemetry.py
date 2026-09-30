from core.generation_compatibility_telemetry import (
    generation_compatibility_telemetry_snapshot,
    record_generation_compatibility_response,
    reset_generation_compatibility_telemetry,
)


def test_generation_compatibility_telemetry_classifies_canonical_legacy_and_mixed_shapes():
    reset_generation_compatibility_telemetry()
    record_generation_compatibility_response({"execution": {"execution_id": "e1"}, "candidate": {"candidate_id": "c1"}})
    record_generation_compatibility_response({"task_id": "legacy-1"})
    record_generation_compatibility_response({"execution": {"execution_id": "e2"}, "task_id": "legacy-diagnostic"})
    snapshot = generation_compatibility_telemetry_snapshot()
    assert snapshot["canonical_execution_response_count"] == 2
    assert snapshot["canonical_candidate_response_count"] == 1
    assert snapshot["task_id_only_fallback_count"] == 1
    assert snapshot["mixed_execution_task_id_response_count"] == 1
    assert snapshot["provider_calls"] == snapshot["llm_calls"] == 0
