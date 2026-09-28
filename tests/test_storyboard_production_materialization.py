"""Reviewed StoryboardPlan -> production materialization contract tests."""

from pathlib import Path
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.automatic_storyboard import (
    StoryboardCompileError,
    approve_storyboard,
    compile_storyboard,
    persist_storyboard,
    storyboard_from_reasoning,
)
from core.director_reasoning import director_reason, persist_reasoning
from core.storyboard_production_materialization import (
    StoryboardProductionMaterializationError,
    get_storyboard_materialization,
    materialize_storyboard_plan,
    rollback_storyboard_materialization,
)
from models import (
    DirectorReasoning,
    ProductionGenerationIntent,
    ProductionPromptVersion,
    ShotDirection,
    ShotPlan,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardPlan,
    StoryboardShot,
)
import api.automatic_storyboard_api as automatic_storyboard_api
from scripts.verify_migration_chain import _upgrade


def _context():
    script = {
        "episode_id": "mat-ep-1",
        "episode": 1,
        "scenes": [{"scene_id": "scene-1", "scene_name": "Station", "participants": ["char-1"], "shots": [{"shot_id": "shot-1"}] }],
    }
    episode = {
        "episode_id": "mat-ep-1",
        "book_id": 77,
        "episode": 1,
        "character_profiles": [{"character_id": "char-1"}],
        "visual_style_profiles": [{"visual_style_id": "style-1"}],
    }
    scene = {"scenes": script["scenes"], "visual_styles": [{"visual_style_id": "style-1"}]}
    return episode, script, scene


def _db(tmp_path: Path):
    path = tmp_path / "storyboard-materialization.sqlite"
    _upgrade(path)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    return engine, sessionmaker(bind=engine)


def _compiled_approved(factory, *, version: int = 1):
    episode, script, scene = _context()
    with factory() as session:
        reasoning = persist_reasoning(session, director_reason(episode, script, scene))
        payload = storyboard_from_reasoning(reasoning, context={"episode_id": "mat-ep-1", "scenes": script["scenes"]}, director_reasoning_id=reasoning["id"], director_reasoning_version=reasoning["version"])
        draft = persist_storyboard(session, payload)
        row = session.query(StoryboardPlan).filter_by(id=draft["id"]).one()
        assert row.version == version
        compile_storyboard(session, row, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
        session.commit()
        approved = approve_storyboard(session, "mat-ep-1", version, reviewer="reviewer-1")
        session.commit()
        return row.id, approved


def test_review_gate_and_valid_materialization(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        episode, script, scene = _context()
        with factory() as session:
            reasoning = persist_reasoning(session, director_reason(episode, script, scene))
            payload = storyboard_from_reasoning(reasoning, context={"episode_id": "mat-ep-1", "scenes": script["scenes"]}, director_reasoning_id=reasoning["id"], director_reasoning_version=reasoning["version"])
            draft = persist_storyboard(session, payload)
            row = session.query(StoryboardPlan).filter_by(id=draft["id"]).one()
            compile_storyboard(session, row, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
            session.commit()
            with pytest.raises(StoryboardProductionMaterializationError) as blocked:
                materialize_storyboard_plan(session, episode_id="mat-ep-1", storyboard_plan_id=row.id, storyboard_version=1, book_id=77, episode_number=1)
            assert blocked.value.diagnostics[0]["code"] == "STORYBOARD_REVIEW_REQUIRED"
            approve_storyboard(session, "mat-ep-1", 1, reviewer="reviewer-1")
            result = materialize_storyboard_plan(session, episode_id="mat-ep-1", storyboard_plan_id=row.id, storyboard_version=1, book_id=77, episode_number=1)
            session.commit()
            assert result["status"] == "MATERIALIZED"
            assert session.query(ShotPlan).count() == 1
            assert session.query(StoryboardShot).count() == 1
            assert session.query(StoryboardMaterializationSet).count() == 1
            assert session.query(StoryboardMaterializationPointer).count() == 1
            assert session.query(ShotDirection).count() == 1
            assert session.query(ProductionGenerationIntent).count() == 1
            assert session.query(ProductionPromptVersion).count() == 1
            shot = session.query(StoryboardShot).one()
            assert shot.storyboard_plan_id == row.id
            assert shot.storyboard_plan_version == 1
            assert session.query(DirectorReasoning).count() == 1
            assert session.query(DirectorReasoning).one().payload_hash
    finally:
        engine.dispose()


def test_materialization_is_idempotent_and_invalid_direction_fails_closed(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        plan_id, _ = _compiled_approved(factory)
        with factory() as session:
            first = materialize_storyboard_plan(session, episode_id="mat-ep-1", storyboard_plan_id=plan_id, storyboard_version=1, book_id=77, episode_number=1)
            session.commit()
            second = materialize_storyboard_plan(session, episode_id="mat-ep-1", storyboard_plan_id=plan_id, storyboard_version=1, book_id=77, episode_number=1)
            session.commit()
            assert first["materialization_set_ids"] == second["materialization_set_ids"]
            assert second["reused"] is True
            assert session.query(StoryboardShot).count() == 1
            assert session.query(StoryboardMaterializationSet).count() == 1
            assert session.query(ProductionPromptVersion).count() == 1
            episode, script, scene = _context()
            reasoning = session.query(DirectorReasoning).one()
            reasoning_payload = json.loads(reasoning.reasoning_json)
            invalid_payload = storyboard_from_reasoning(reasoning_payload, context={"episode_id": "mat-ep-1", "scenes": script["scenes"]}, director_reasoning_id=reasoning.id, director_reasoning_version=reasoning.version)
            invalid_payload["storyboard_json"]["shots"][0]["shot_direction"] = {}
            invalid_draft = persist_storyboard(session, invalid_payload)
            invalid_row = session.query(StoryboardPlan).filter_by(id=invalid_draft["id"]).one()
            compile_storyboard(session, invalid_row, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
            session.commit()
            approve_storyboard(session, "mat-ep-1", 2, reviewer="reviewer-2")
            with pytest.raises(StoryboardProductionMaterializationError) as blocked:
                materialize_storyboard_plan(session, episode_id="mat-ep-1", storyboard_plan_id=invalid_row.id, storyboard_version=2, book_id=77, episode_number=1)
            assert blocked.value.code == "SHOT_DIRECTION_INVALID"
    finally:
        engine.dispose()


def test_new_version_pointer_switch_and_rollback_preserve_history(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        plan_id, _ = _compiled_approved(factory)
        with factory() as session:
            v1 = materialize_storyboard_plan(session, episode_id="mat-ep-1", storyboard_plan_id=plan_id, storyboard_version=1, book_id=77, episode_number=1)
            session.commit()
            episode, script, scene = _context()
            reasoning = session.query(DirectorReasoning).one()
            reasoning_payload = json.loads(reasoning.reasoning_json)
            payload = storyboard_from_reasoning(reasoning_payload, context={"episode_id": "mat-ep-1", "scenes": script["scenes"]}, director_reasoning_id=reasoning.id, director_reasoning_version=reasoning.version)
            draft = persist_storyboard(session, payload)
            row = session.query(StoryboardPlan).filter_by(id=draft["id"]).one()
            compile_storyboard(session, row, episode_context=episode, script_ir=script, scene_context=scene, book_id=77, episode_number=1)
            session.commit()
            approve_storyboard(session, "mat-ep-1", 2, reviewer="reviewer-2")
            v2 = materialize_storyboard_plan(session, episode_id="mat-ep-1", storyboard_plan_id=row.id, storyboard_version=2, book_id=77, episode_number=1)
            session.commit()
            assert v2["materialization_set_ids"] != v1["materialization_set_ids"]
            assert session.query(StoryboardMaterializationSet).count() == 2
            assert session.query(StoryboardShot).count() == 2
            active_v2 = get_storyboard_materialization(session, episode_id="mat-ep-1", book_id=77, episode_number=1)
            assert active_v2["active_set"]["storyboard_plan_version"] == 2
            rollback = rollback_storyboard_materialization(session, episode_id="mat-ep-1", target_storyboard_version=1, book_id=77, episode_number=1)
            session.commit()
            assert rollback["status"] == "ROLLED_BACK"
            assert rollback["history_preserved"] is True
            active_v1 = get_storyboard_materialization(session, episode_id="mat-ep-1", book_id=77, episode_number=1)
            assert active_v1["active_set"]["storyboard_plan_version"] == 1
            assert session.query(StoryboardMaterializationSet).count() == 2
            assert session.query(StoryboardShot).count() == 2
    finally:
        engine.dispose()


def test_approval_requires_compile_pass(tmp_path: Path):
    engine, factory = _db(tmp_path)
    try:
        episode, script, scene = _context()
        with factory() as session:
            reasoning = persist_reasoning(session, director_reason(episode, script, scene))
            payload = storyboard_from_reasoning(reasoning, context={"episode_id": "mat-ep-1", "scenes": script["scenes"]}, director_reasoning_id=reasoning["id"], director_reasoning_version=reasoning["version"])
            draft = persist_storyboard(session, payload)
            with pytest.raises(StoryboardCompileError) as exc:
                approve_storyboard(session, "mat-ep-1", 1)
            assert exc.value.diagnostics[0]["code"] == "STORYBOARD_COMPILE_VALIDATION_REQUIRED"
            assert draft["status"] == "REVIEW_REQUIRED"
    finally:
        engine.dispose()


def test_materialization_api_contract(tmp_path: Path, monkeypatch):
    engine, factory = _db(tmp_path)
    try:
        monkeypatch.setattr(automatic_storyboard_api, "Session", factory)
        app = FastAPI()
        app.include_router(automatic_storyboard_api.router)
        client = TestClient(app)
        episode, script, scene = _context()
        request = {"episode_context": episode, "script_ir": script, "scene_context": scene, "visual_styles": episode["visual_style_profiles"]}
        created = client.post("/episodes/mat-ep-1/storyboard/generate", json=request)
        assert created.status_code == 201, created.text
        compiled = client.post("/episodes/mat-ep-1/storyboard/compile", json=request | {"version": 1, "book_id": 77, "episode_number": 1})
        assert compiled.status_code == 201, compiled.text
        approved = client.post("/episodes/mat-ep-1/storyboard/1/approve", json={"reviewer": "api-reviewer"})
        assert approved.status_code == 200, approved.text
        materialized = client.post("/episodes/mat-ep-1/storyboard/materialize", json={"storyboard_plan_id": 1, "storyboard_version": 1, "book_id": 77, "episode_number": 1})
        assert materialized.status_code == 201, materialized.text
        current = client.get("/episodes/mat-ep-1/storyboard/materialization", params={"book_id": 77, "episode_number": 1})
        assert current.status_code == 200, current.text
        assert current.json()["active_set"]["storyboard_plan_version"] == 1
    finally:
        engine.dispose()
