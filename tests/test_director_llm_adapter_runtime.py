"""Director LLM adapter context, contract, validation and review-boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import api.director_reasoning_api as reasoning_api
from api.director_reasoning_api import router
from core.director_llm_adapter import (
    AnthropicCompatibleDirectorAdapter,
    CustomDirectorLLMAdapter,
    DirectorContextBuilder,
    DirectorLLMAdapterError,
    OpenAICompatibleDirectorAdapter,
    add_adapter_lineage,
    director_reasoning_json_schema,
    validate_llm_reasoning_output,
)
from core.director_reasoning import director_reason
from models import DirectorReasoning, DirectorReasoningGeneration, ShotPlan
from scripts.verify_migration_chain import _upgrade


def _contexts():
    script = {
        "episode_id": "ep-llm-1",
        "episode": 1,
        "scenes": [{
            "scene_id": "scene-1",
            "scene_name": "Station",
            "participants": ["char-1"],
            "shots": [{"shot_id": "shot-1"}],
        }],
    }
    episode = {
        "episode_id": "ep-llm-1",
        "book_id": 77,
        "episode": 1,
        "character_profiles": [{"character_id": "char-1", "name": "A"}],
        "visual_style_profiles": [{"visual_style_id": "style-1"}],
        "source_fact_snapshot_hash": "sha256:fact",
    }
    return episode, script


def _db(tmp_path: Path):
    path = tmp_path / "director-llm.sqlite"
    _upgrade(path)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    return engine, sessionmaker(bind=engine)


def test_context_builder_snapshots_all_required_inputs_without_mutating_sources():
    episode, script = _contexts()
    context = DirectorContextBuilder().build(episode=episode, script_ir=script)
    assert context.schema_version == "director_context_v1"
    assert context.characters[0]["character_id"] == "char-1"
    assert context.scenes[0]["scene_id"] == "scene-1"
    assert context.visual_styles[0]["visual_style_id"] == "style-1"
    assert context.existing_shots[0]["shot_id"] == "shot-1"
    assert context.constraints["direct_database_write"] is False
    assert context.constraints["media_generation_allowed"] is False
    context.to_payload()["script_ir"]["scenes"][0]["scene_id"] = "mutated-copy"
    assert script["scenes"][0]["scene_id"] == "scene-1"


def test_provider_adapter_contracts_are_transport_injected_and_provider_neutral():
    episode, script = _contexts()
    context = DirectorContextBuilder().build(episode=episode, script_ir=script)
    payload = director_reason(episode, script, {"scenes": context.scenes, "visual_styles": context.visual_styles})
    seen = []

    def openai_transport(value):
        seen.append(value)
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    result = OpenAICompatibleDirectorAdapter(openai_transport).generate_reasoning(context)
    assert isinstance(result, dict) and result["choices"]
    assert seen[0]["schema_version"] == "director_context_v1"

    anthropic = AnthropicCompatibleDirectorAdapter(lambda value: {"content": [{"text": json.dumps(payload)}]})
    assert anthropic.generate_reasoning(context)["content"]
    custom = CustomDirectorLLMAdapter(lambda value: payload)
    assert custom.generate_reasoning(context)["episode_id"] == "ep-llm-1"


def test_schema_validation_and_invalid_output_rejection():
    episode, script = _contexts()
    context = DirectorContextBuilder().build(episode=episode, script_ir=script)
    payload = director_reason(episode, script, {"scenes": context.scenes, "visual_styles": context.visual_styles})
    schema = director_reasoning_json_schema()
    assert "beats" in schema["properties"]
    validated = validate_llm_reasoning_output(json.dumps(payload), context)
    assert validated["episode_id"] == "ep-llm-1"
    with pytest.raises(DirectorLLMAdapterError) as exc:
        validate_llm_reasoning_output({"episode_id": "ep-llm-1", "beats": "invalid"}, context)
    assert exc.value.code == "DIRECTOR_LLM_OUTPUT_SCHEMA_INVALID"
    with pytest.raises(DirectorLLMAdapterError) as exc:
        validate_llm_reasoning_output({**payload, "episode_id": "other-episode"}, context)
    assert exc.value.code == "DIRECTOR_LLM_OUTPUT_EPISODE_MISMATCH"


def test_lineage_creation_forces_review_and_preserves_immutability_flags():
    episode, script = _contexts()
    context = DirectorContextBuilder().build(episode=episode, script_ir=script)
    payload = director_reason(episode, script, {"scenes": context.scenes, "visual_styles": context.visual_styles})
    adapter = CustomDirectorLLMAdapter(lambda value: payload)
    lineage = add_adapter_lineage(payload, context=context, adapter=adapter)
    assert lineage["status"] == "REVIEW_REQUIRED"
    assert lineage["reasoning_trace"]["direct_database_write"] is False
    assert lineage["lineage"]["context_hash"] == context.context_hash
    assert lineage["lineage"]["source_fact_mutated"] is False
    assert lineage["lineage"]["script_ir_mutated"] is False


def test_generation_api_persists_only_review_required_draft_and_status(tmp_path: Path, monkeypatch):
    episode, script = _contexts()
    engine, SessionLocal = _db(tmp_path)
    monkeypatch.setattr(reasoning_api, "Session", SessionLocal)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    request = {"episode_context": episode, "script_ir": script, "provider": "mock"}
    generated = client.post("/episodes/ep-llm-1/director-reasoning/generate", json=request)
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["human_review_required"] is True
    assert body["direct_database_write"] is False
    assert body["source_fact_mutated"] is False
    assert body["script_ir_mutated"] is False
    assert body["reasoning"]["status"] == "REVIEW_REQUIRED"
    with SessionLocal() as session:
        assert session.query(DirectorReasoning).count() == 1
        assert session.query(DirectorReasoningGeneration).one().status == "REVIEW_REQUIRED"
        assert session.query(ShotPlan).count() == 0
    status = client.get("/episodes/ep-llm-1/director-reasoning/generation-status")
    assert status.status_code == 200
    assert status.json()["generation"]["status"] == "REVIEW_REQUIRED"
    engine.dispose()


def test_generation_api_rejects_invalid_provider_output_and_records_failed_status(tmp_path: Path, monkeypatch):
    episode, script = _contexts()
    engine, SessionLocal = _db(tmp_path)
    monkeypatch.setattr(reasoning_api, "Session", SessionLocal)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    failed = client.post(
        "/episodes/ep-llm-invalid/director-reasoning/generate",
        json={
            "episode_context": {**episode, "episode_id": "ep-llm-invalid"},
            "script_ir": {**script, "episode_id": "ep-llm-invalid"},
            "provider": "mock",
            "mock_response": {"episode_id": "ep-llm-invalid", "beats": "not-a-list"},
        },
    )
    assert failed.status_code == 409
    assert failed.json()["detail"]["code"] == "DIRECTOR_LLM_OUTPUT_SCHEMA_INVALID"
    with SessionLocal() as session:
        generation = session.query(DirectorReasoningGeneration).one()
        assert generation.status == "FAILED"
        assert session.query(DirectorReasoning).count() == 0
    engine.dispose()


def test_real_provider_transport_is_disabled_without_injected_mock():
    episode, script = _contexts()
    context = DirectorContextBuilder().build(episode=episode, script_ir=script)
    with pytest.raises(DirectorLLMAdapterError) as exc:
        OpenAICompatibleDirectorAdapter().generate_reasoning(context)
    assert exc.value.code == "DIRECTOR_LLM_PROVIDER_CALL_DISABLED"
