"""Episode automatic production coordinator contracts."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.episode_production as production
from core.episode_rendering import create_episode_render_plan
from models import EpisodeOutline, GenerationExecutionRecord, StoryboardShot, TaskRun
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "episode-automatic-production.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _episode(session, *, episode_id: int = 99001, shot_count: int = 3):
    outline = EpisodeOutline(id=episode_id, book_id=9900, episode=1, title="Automatic production")
    session.add(outline)
    session.flush()
    shots = []
    for index in range(shot_count):
        shot = StoryboardShot(book_id=9900, episode=1, scene_name="scene", scene_id=f"scene-{index}", shot_id=index + 1, materialization_status="LEGACY")
        session.add(shot)
        session.flush()
        shots.append(shot)
    session.commit()
    return outline, shots


def test_dry_run_is_zero_production_writes_and_reports_blockers(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        outline, shots = _episode(session, shot_count=1)
        plan = create_episode_render_plan(session, episode_id=outline.id)
        session.commit()
        before = (session.query(GenerationExecutionRecord).count(), session.query(TaskRun).count())
        result = production.run_episode_production(session, episode_id=outline.id, plan_id=plan.id, dry_run=True)
        after = (session.query(GenerationExecutionRecord).count(), session.query(TaskRun).count())
        assert result["state"] == "BLOCKED"
        assert result["shots"][0]["state"] == "NOT_READY"
        assert result["shots"][0]["next_action"] == "WAIT_FOR_MATERIALIZATION"
        assert result["actions"] == []
        assert before == after
    finally:
        session.close()
        engine.dispose()


def test_dependency_projection_blocks_downstream_shots(monkeypatch, tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        outline, shots = _episode(session)
        plan = create_episode_render_plan(
            session,
            episode_id=outline.id,
            items=[
                {"shot_id": shots[0].id, "order": 0, "dependency": []},
                {"shot_id": shots[1].id, "order": 1, "dependency": [shots[0].id]},
                {"shot_id": shots[2].id, "order": 2, "dependency": [shots[1].id]},
            ],
        )
        session.commit()

        def fake_resolve(_session, *, shot_id):
            return {"shot_id": shot_id, "order": shot_id, "state": "COMPLETE" if shot_id == shots[0].id else "READY_FOR_VIDEO", "next_action": "GENERATE_VIDEO", "current_authorities": {}}

        monkeypatch.setattr(production, "resolve_shot_production_state", fake_resolve)
        result = production.run_episode_production(session, episode_id=outline.id, plan_id=plan.id, dry_run=True)
        assert result["shots"][0]["state"] == "COMPLETE"
        assert result["shots"][1]["state"] == "READY_FOR_VIDEO"
        assert result["shots"][2]["state"] == "BLOCKED_DEPENDENCY"
        assert result["shots"][2]["next_action"] == "WAIT_FOR_DEPENDENCY"
    finally:
        session.close()
        engine.dispose()


def test_episode_production_routes_are_registered():
    from api.server import app

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ("/episodes/{episode_id}/production/run", ("POST",)) in paths
    assert ("/episodes/{episode_id}/production-status", ("GET",)) in paths
    assert ("/api/episodes/{episode_id}/production/run", ("POST",)) in paths
    assert ("/api/episodes/{episode_id}/production-status", ("GET",)) in paths
