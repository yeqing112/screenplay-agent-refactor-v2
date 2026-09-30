import asyncio

import api.generation_canary_api as canary
import api.server as server
from core.generation_compatibility_telemetry import (
    generation_compatibility_telemetry_snapshot,
    record_generation_compatibility_response,
    reset_generation_compatibility_telemetry,
)


def test_storyboard_alias_records_real_endpoint_response_shape(monkeypatch):
    reset_generation_compatibility_telemetry()

    monkeypatch.setattr(
        canary,
        "preview_canonical_generation",
        lambda *_args, **_kwargs: {
            "confirmation_token": "token",
            "execution": {"execution_id": "preview", "status": "READY"},
        },
    )

    async def execute(*_args, **_kwargs):
        return {
            "execution": {"execution_id": "exec-telemetry", "status": "SUCCEEDED"},
            "candidate": {"candidate_id": "candidate-telemetry", "status": "MEDIA_CANDIDATE"},
        }

    monkeypatch.setattr(canary, "execute_canonical_generation", execute)
    response = asyncio.run(
        server.generate_storyboard_frame(
            1,
            1,
            "101",
            server.StoryboardGenerationRequest(model_profile_id="fixture-image-profile", confirmed=True),
            server.BackgroundTasks(),
        )
    )
    assert response["execution"]["execution_id"] == "exec-telemetry"
    snapshot = generation_compatibility_telemetry_snapshot()
    assert snapshot["response_count"] == 1
    assert snapshot["canonical_execution_response_count"] == 1
    assert snapshot["canonical_candidate_response_count"] == 1
    assert snapshot["task_id_only_fallback_count"] == 0


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
