"""DirectorReasoningIR schema, compile, lineage, version and rollback tests."""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.director_reasoning import (
    DirectorReasoningCompileError,
    DirectorReasoningPayload,
    compile_reasoning,
    director_reason,
    persist_reasoning,
    rollback_reasoning,
    validate_reasoning_for_compile,
)
from models import DirectorReasoning, ShotPlan, init_db
from api.director_reasoning_api import router
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "director-reasoning.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _contexts():
    script = {"episode_id": "ep-1", "episode": 1, "scenes": [{"scene_id": "scene-1", "scene_name": "Station", "participants": ["char-1"], "shots": [{"shot_id": "shot-1"}]}]}
    episode = {"episode_id": "ep-1", "book_id": 77, "episode": 1, "character_profiles": [{"character_id": "char-1"}], "visual_style_profiles": [{"visual_style_id": "style-1"}]}
    scene = {"scenes": script["scenes"], "visual_styles": [{"id": "style-1"}]}
    return episode, script, scene


def test_reasoning_schema_and_provider_free_adapter():
    episode, script, scene = _contexts()
    payload = director_reason(episode, script, scene)
    validated = DirectorReasoningPayload.model_validate(payload)
    assert validated.beats[0].sequence == 1
    assert validated.visual_decisions[0].visual_style_id == "style-1"
    assert payload["reasoning_trace"]["llm_called"] is False
    assert payload["lineage"]["source_fact_mutated"] is False


def test_reasoning_migration_exposes_authority_tables(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"director_reasonings", "director_story_beats", "director_visual_decisions"}.issubset(tables)
        assert {"director_reasoning_id", "director_reasoning_version", "reasoning_lineage"}.issubset({item["name"] for item in inspect(engine).get_columns("shot_plans")})
    finally:
        session.close(); engine.dispose()


def test_compile_validation_fails_closed_for_scene_character_style_and_shot():
    episode, script, scene = _contexts()
    payload = director_reason(episode, script, scene)
    payload["beats"][0]["scene_id"] = "missing-scene"
    payload["beats"][0]["character_refs"] = ["missing-character"]
    payload["beats"][0]["shot_refs"] = ["missing-shot"]
    payload["visual_decisions"][0]["visual_style_id"] = "missing-style"
    with pytest.raises(DirectorReasoningCompileError) as exc:
        validate_reasoning_for_compile(payload, episode_context=episode, script_ir=script, scene_context=scene)
    codes = {item["code"] for item in exc.value.diagnostics}
    assert {"SCENE_NOT_FOUND", "CHARACTER_NOT_FOUND", "VISUAL_STYLE_NOT_FOUND", "SHOT_REFERENCE_INVALID"}.issubset(codes)


def test_compile_lineage_version_and_rollback(tmp_path: Path):
    episode, script, scene = _contexts()
    engine, session = _session(tmp_path)
    try:
        first = persist_reasoning(session, director_reason(episode, script, scene))
        row = session.query(DirectorReasoning).filter_by(id=first["id"]).one()
        compiled = compile_reasoning(session, row, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
        session.commit()
        assert compiled["status"] == "COMPILED"
        assert compiled["shot_plans"][0]["reasoning_lineage"]["director_reasoning_id"] == row.id
        assert compiled["generation_intents"][0]["prompt_version_id"] in compiled["lineage"]["prompt_version_ids"]
        assert session.query(ShotPlan).filter_by(director_reasoning_id=row.id).count() == 1

        second = persist_reasoning(session, director_reason(episode, script, scene))
        session.commit()
        assert second["version"] == 2
        rolled = rollback_reasoning(session, "ep-1", 1)
        session.commit()
        assert rolled["status"] == "ROLLED_BACK"
        assert session.get(DirectorReasoning, row.id).status == "ROLLED_BACK"
        assert session.query(ShotPlan).filter_by(director_reasoning_id=row.id).one().status == "superseded"
    finally:
        session.close(); engine.dispose()


def test_reasoning_api_create_query_compile_and_rollback():
    init_db()
    episode, script, scene = _contexts()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    request = {"episode_context": episode, "script_ir": script, "scene_context": scene}
    created = client.post("/episodes/api-reasoning/director-reasoning", json=request)
    assert created.status_code == 201
    assert created.json()["reasoning"]["reasoning_trace"]["llm_called"] is False
    queried = client.get("/episodes/api-reasoning/director-reasoning")
    assert queried.status_code == 200
    compiled = client.post("/episodes/api-reasoning/director-reasoning/compile", json=request)
    assert compiled.status_code == 201
    body = compiled.json()
    assert body["status"] == "COMPILED"
    assert body["lineage"]["director_reasoning_id"]
    rolled = client.post("/episodes/api-reasoning/director-reasoning/1/rollback")
    assert rolled.status_code == 200
    assert rolled.json()["status"] == "ROLLED_BACK"
