"""Episode rendering runtime contracts over ProductionBatch and TaskRun."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.episode_rendering import (
    EpisodeRenderingError,
    complete_episode_render_plan,
    create_episode_render_plan,
    render_episode,
    serialize_episode_render_plan,
)
from core.generation_execution_service import GenerationExecutionService
from models import EpisodeOutline, PromptIRPointer, PromptIRVersion, StoryboardShot, TaskRun
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "episode-rendering.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _fixture(session, *, project_id: int = 970001, episode_number: int = 2, shot_ids: tuple[int, ...] = (11, 12, 13)):
    outline = EpisodeOutline(id=project_id * 10 + episode_number, book_id=project_id, episode=episode_number, title="Render fixture")
    session.add(outline)
    for shot_id in shot_ids:
        shot = StoryboardShot(book_id=project_id, episode=episode_number, scene_name="render-scene", scene_id=f"render-scene-{shot_id}", plan_shot_id=f"render-plan-{shot_id}", shot_id=shot_id)
        session.add(shot)
        session.flush()
        version = PromptIRVersion(book_id=project_id, episode=episode_number, scene_id=shot.scene_id, storyboard_shot_id=shot.id, materialization_set_id=1, plan_shot_id=shot.plan_shot_id, schema_version="episode_render_test_v1", payload_json='{"generation_policy":{"target_media":"IMAGE"}}', payload_hash=f"sha256:episode-render-{shot_id}", compiler_version="test", compiler_policy_version="test", retention_policy_version="test")
        session.add(version)
        session.flush()
        session.add(PromptIRPointer(book_id=project_id, episode=episode_number, storyboard_shot_id=shot.id, target_media="IMAGE", prompt_ir_version_id=version.id, payload_hash=version.payload_hash))
    session.commit()
    return outline


def _success_runner(session, execution_id: str):
    service = GenerationExecutionService(session)
    service.transition(execution_id, "QUEUED")
    service.transition(execution_id, "RUNNING")
    return service.transition(execution_id, "SUCCESS", response_payload={"provider_calls": 0})


def test_migration_and_plan_materialize_ordered_dependency_graph(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        outline = _fixture(session)
        plan = create_episode_render_plan(session, episode_id=outline.id)
        payload = serialize_episode_render_plan(session, plan)
        assert {"episode_render_plans", "episode_render_items"}.issubset(inspect(engine).get_table_names())
        assert payload["status"] == "DRAFT"
        assert len(payload["items"]) == 3
        assert [item["order"] for item in payload["items"]] == [0, 1, 2]
        assert payload["items"][0]["dependency"] == []
        assert payload["items"][2]["dependency"] == [payload["items"][1]["shot_id"]]
    finally:
        session.close(); engine.dispose()


def test_dependency_cycle_and_invalid_order_fail_closed(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        outline = _fixture(session, shot_ids=(21, 22))
        shot_ids = [row.id for row in session.query(StoryboardShot).filter_by(book_id=outline.book_id, episode=outline.episode).order_by(StoryboardShot.id).all()]
        with pytest.raises(EpisodeRenderingError) as cycle:
            create_episode_render_plan(session, episode_id=outline.id, items=[{"shot_id": shot_ids[0], "order": 0, "dependency": [shot_ids[1]]}, {"shot_id": shot_ids[1], "order": 1, "dependency": [shot_ids[0]]}])
        assert cycle.value.code == "EPISODE_RENDER_DEPENDENCY_CYCLE"
        with pytest.raises(EpisodeRenderingError) as missing:
            create_episode_render_plan(session, episode_id=outline.id, items=[{"shot_id": shot_ids[0], "order": 0, "dependency": []}])
        assert missing.value.code == "EPISODE_RENDER_SHOT_SET_INVALID"
    finally:
        session.close(); engine.dispose()


def test_render_reuses_production_batch_task_and_enters_reviewing(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        outline = _fixture(session, shot_ids=(31, 32, 33))
        plan = create_episode_render_plan(session, episode_id=outline.id)
        result = render_episode(session, episode_id=outline.id, plan_id=plan.id, runner=_success_runner)
        session.commit()
        payload = serialize_episode_render_plan(session, result)
        assert payload["status"] == "REVIEWING"
        assert payload["production_batch"]["status"] == "COMPLETED"
        assert payload["production_batch"]["task_run"]["task_kind"] == "production_batch"
        assert all(item["status"] == "COMPLETED" for item in payload["items"])
        assert session.query(TaskRun).filter_by(task_id=payload["production_batch"]["task_id"]).count() == 1
    finally:
        session.close(); engine.dispose()


def test_completion_requires_explicit_review_and_transitions_to_completed(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        outline = _fixture(session, shot_ids=(41,))
        plan = create_episode_render_plan(session, episode_id=outline.id)
        render_episode(session, episode_id=outline.id, plan_id=plan.id, runner=_success_runner)
        with pytest.raises(EpisodeRenderingError) as exc:
            complete_episode_render_plan(session, episode_id=outline.id, plan_id=plan.id)
        assert exc.value.code == "EPISODE_RENDER_REVIEW_CONFIRMATION_REQUIRED"
        completed = complete_episode_render_plan(session, episode_id=outline.id, plan_id=plan.id, reviewed=True)
        assert completed.status == "COMPLETED"
    finally:
        session.close(); engine.dispose()


def test_episode_rendering_api_routes_are_registered(tmp_path: Path):
    engine, session = _session(tmp_path)
    session.close(); engine.dispose()
    from api.server import app

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ("/episodes/{episode_id}/render-plan", ("GET",)) in paths
    assert ("/episodes/{episode_id}/render-plan", ("POST",)) in paths
    assert ("/episodes/{episode_id}/render", ("POST",)) in paths
    assert ("/episodes/{episode_id}/render-status", ("GET",)) in paths
    assert ("/api/episodes/{episode_id}/render-plan", ("GET",)) in paths
