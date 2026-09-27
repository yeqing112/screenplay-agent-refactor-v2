"""Provider-free automatic storyboard draft, review boundary and compiler tests."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import api.automatic_storyboard_api as storyboard_api
from core.automatic_storyboard import (
    StoryboardCompileError,
    StoryboardPlanPayload,
    compile_storyboard,
    persist_storyboard,
    storyboard_from_reasoning,
    validate_storyboard_for_compile,
)
from core.director_reasoning import director_reason, persist_reasoning
from models import ShotPlan, StoryboardPlan, StoryboardShot, Session
from scripts.verify_migration_chain import _upgrade


def _contexts():
    script = {
        "episode_id": "auto-ep-1",
        "episode": 1,
        "scenes": [{"scene_id": "scene-1", "scene_name": "Station", "participants": ["char-1"], "shots": [{"shot_id": "shot-1"}] }],
    }
    episode = {
        "episode_id": "auto-ep-1",
        "book_id": 77,
        "episode": 1,
        "character_profiles": [{"character_id": "char-1"}],
        "visual_style_profiles": [{"visual_style_id": "style-1"}],
    }
    scene = {"scenes": script["scenes"], "visual_styles": [{"visual_style_id": "style-1"}]}
    return episode, script, scene


def _db(tmp_path: Path):
    path = tmp_path / "automatic-storyboard.sqlite"
    _upgrade(path)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    return engine, sessionmaker(bind=engine)


def test_draft_schema_and_migration(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        assert {"director_storyboard_plans", "director_storyboard_shots"}.issubset(set(inspect(engine).get_table_names()))
        episode, script, scene = _contexts()
        reasoning = director_reason(episode, script, scene)
        payload = storyboard_from_reasoning(reasoning, context={"episode_id": "auto-ep-1", "scenes": script["scenes"]})
        assert StoryboardPlanPayload.model_validate(payload).status == "REVIEW_REQUIRED"
    finally:
        engine.dispose()


def test_generation_review_boundary_and_versioning(tmp_path: Path, monkeypatch):
    engine, factory = _db(tmp_path)
    monkeypatch.setattr(storyboard_api, "Session", factory)
    episode, script, scene = _contexts()
    app = FastAPI()
    app.include_router(storyboard_api.router)
    client = TestClient(app)
    request = {"episode_context": episode, "script_ir": script, "scene_context": scene, "visual_styles": episode["visual_style_profiles"]}
    first = client.post("/episodes/auto-ep-1/storyboard/generate", json=request)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["provider_calls"] == 1
    with factory() as session:
        assert session.query(StoryboardPlan).count() == 1
        assert session.query(ShotPlan).count() == 0
        assert session.query(StoryboardShot).count() == 0
    second = client.post("/episodes/auto-ep-1/storyboard/generate", json=request)
    assert second.status_code == 201, second.text
    assert second.json()["storyboard"]["version"] == 2
    engine.dispose()


def test_compile_lineage_fail_closed_and_rollback(tmp_path: Path):
    engine, factory = _db(tmp_path)
    episode, script, scene = _contexts()
    with factory() as session:
        reasoning = persist_reasoning(session, director_reason(episode, script, scene))
        payload = storyboard_from_reasoning(reasoning, context={"episode_id": "auto-ep-1", "scenes": script["scenes"]}, director_reasoning_id=reasoning["id"], director_reasoning_version=reasoning["version"])
        draft = persist_storyboard(session, payload)
        row = session.query(StoryboardPlan).filter_by(id=draft["id"]).one()
        compiled = compile_storyboard(session, row, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
        session.commit()
        assert compiled["status"] == "COMPILED"
        assert compiled["lineage"]["storyboard_plan_id"] == row.id
        assert session.query(ShotPlan).count() == 1
        assert session.query(ShotPlan).one().production_status == "blocked"
    with factory() as session:
        from core.automatic_storyboard import rollback_storyboard
        rolled = rollback_storyboard(session, "auto-ep-1", 1)
        session.commit()
        assert rolled["status"] == "ROLLED_BACK"
        assert session.query(ShotPlan).one().status == "superseded"
    engine.dispose()


def test_invalid_scene_style_camera_is_rejected():
    episode, script, scene = _contexts()
    reasoning = director_reason(episode, script, scene)
    payload = storyboard_from_reasoning(reasoning, context={"episode_id": "auto-ep-1", "scenes": script["scenes"]})
    shot = payload["storyboard_json"]["shots"][0]
    shot["scene_id"] = "missing"
    shot["visual_style_id"] = "missing"
    shot["camera"]["angle"] = "invalid"
    with pytest.raises(StoryboardCompileError) as exc:
        validate_storyboard_for_compile(payload, episode_context=episode, script_ir=script, scene_context=scene)
    codes = {item["code"] for item in exc.value.diagnostics}
    assert {"SCENE_NOT_FOUND", "VISUAL_STYLE_NOT_FOUND", "CAMERA_ANGLE_INVALID"}.issubset(codes)
