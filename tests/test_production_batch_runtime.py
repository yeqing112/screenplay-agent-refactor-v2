"""Production batch runtime contracts over the existing execution/task surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.generation_execution_service import GenerationExecutionService
from core.production_batch import (
    ProductionBatchError,
    create_production_batch,
    run_production_batch,
    serialize_production_batch,
)
from models import (
    EpisodeOutline,
    GenerationExecutionRecord,
    PromptIRPointer,
    PromptIRVersion,
    ProductionBatch,
    ProductionBatchItem,
    StoryboardShot,
    TaskRun,
)
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "production-batch-runtime.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _fixture(session, *, project_id: int = 980001, episode: int = 1, shot_ids: tuple[int, ...] = (101, 102), target_media: str = "IMAGE"):
    session.add(EpisodeOutline(id=project_id * 10 + episode, book_id=project_id, episode=episode, title="Batch fixture"))
    for shot_id in shot_ids:
        shot = StoryboardShot(
            book_id=project_id,
            episode=episode,
            scene_name="BATCH_SCENE",
            scene_id=f"batch-scene-{shot_id}",
            plan_shot_id=f"batch-plan-{shot_id}",
            shot_id=shot_id,
        )
        session.add(shot)
        session.flush()
        version = PromptIRVersion(
            book_id=project_id,
            episode=episode,
            scene_id=shot.scene_id,
            storyboard_shot_id=shot.id,
            materialization_set_id=1,
            plan_shot_id=shot.plan_shot_id,
            schema_version="prompt_ir_batch_test_v1",
            payload_json='{"generation_policy":{"target_media":"%s"}}' % target_media,
            payload_hash=f"sha256:batch-{shot_id}",
            compiler_version="test",
            compiler_policy_version="test",
            retention_policy_version="test",
        )
        session.add(version)
        session.flush()
        session.add(
            PromptIRPointer(
                book_id=project_id,
                episode=episode,
                storyboard_shot_id=shot.id,
                target_media=target_media,
                prompt_ir_version_id=version.id,
                payload_hash=version.payload_hash,
            )
        )
    session.commit()
    return project_id, episode


def _success_runner(session, execution_id: str):
    service = GenerationExecutionService(session)
    service.transition(execution_id, "QUEUED")
    service.transition(execution_id, "RUNNING")
    return service.transition(execution_id, "SUCCESS", response_payload={"provider_calls": 0})


def test_batch_entity_task_run_reuse_and_priority_order(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        project_id, episode = _fixture(session, shot_ids=(201, 202, 203))
        batch = create_production_batch(session, project_id=project_id, episode_id=project_id * 10 + episode, model_profile_id="shapi-image", priority=0)
        items = session.query(ProductionBatchItem).filter_by(batch_id=batch.id).order_by(ProductionBatchItem.id).all()
        items[0].priority = 1
        items[1].priority = 10
        items[2].priority = 5
        session.commit()
        seen: list[int] = []

        def runner(db, execution_id):
            item = db.query(ProductionBatchItem).filter_by(execution_id=execution_id).one()
            seen.append(item.shot_id)
            return _success_runner(db, execution_id)

        result = run_production_batch(session, batch.batch_key, runner=runner)
        session.commit()
        assert result.status == "COMPLETED"
        assert seen == [items[1].shot_id, items[2].shot_id, items[0].shot_id]
        assert session.query(TaskRun).filter_by(task_id=batch.task_id).count() == 1
        task = session.query(TaskRun).filter_by(task_id=batch.task_id).one()
        assert task.task_kind == "production_batch"
        assert task.status == "completed"
        assert task.progress == 100
        assert session.query(GenerationExecutionRecord).count() == 3
        assert session.query(ProductionBatchItem).filter_by(batch_id=batch.id, status="SUCCEEDED").count() == 3
    finally:
        session.close()
        engine.dispose()


def test_batch_failure_recovery_reuses_execution_and_counts_retry(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        project_id, episode = _fixture(session, shot_ids=(301,))
        batch = create_production_batch(session, project_id=project_id, episode_id=project_id * 10 + episode, model_profile_id="shapi-image")
        calls = {"count": 0}

        def flaky_runner(db, execution_id):
            calls["count"] += 1
            service = GenerationExecutionService(db)
            service.transition(execution_id, "QUEUED")
            service.transition(execution_id, "RUNNING")
            if calls["count"] == 1:
                service.transition(execution_id, "FAILED", error_message="provider unavailable")
                raise RuntimeError("provider unavailable")
            return service.transition(execution_id, "SUCCESS", response_payload={"provider_calls": 0})

        first = run_production_batch(session, batch.batch_key, runner=flaky_runner)
        assert first.status == "FAILED"
        item = session.query(ProductionBatchItem).filter_by(batch_id=batch.id).one()
        execution_id = item.execution_id
        assert item.retry_count == 0
        assert session.query(GenerationExecutionRecord).filter_by(execution_id=execution_id).one().execution_status == "FAILED"

        second = run_production_batch(session, batch.batch_key, retry_failed=True, max_retries=1, runner=flaky_runner)
        session.commit()
        assert second.status == "COMPLETED"
        assert calls["count"] == 2
        item = session.query(ProductionBatchItem).filter_by(batch_id=batch.id).one()
        assert item.retry_count == 1
        assert item.status == "SUCCEEDED"
        assert item.execution_id == execution_id
    finally:
        session.close()
        engine.dispose()


def test_video_pointer_fails_closed_and_api_routes_are_registered(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        project_id, episode = _fixture(session, shot_ids=(401,), target_media="VIDEO")
        with pytest.raises(ProductionBatchError) as exc_info:
            create_production_batch(session, project_id=project_id, episode_id=project_id * 10 + episode, model_profile_id="shapi-image")
        assert exc_info.value.code == "PRODUCTION_BATCH_PROMPT_POINTER_MISSING"
    finally:
        session.close()
        engine.dispose()

    from api.server import app

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ("/production/batches", ("POST",)) in paths
    assert ("/production/batches/{batch_id}", ("GET",)) in paths
    assert ("/production/batches/{batch_id}/run", ("POST",)) in paths
    assert ("/api/production/batches", ("POST",)) in paths


def test_batch_serialization_exposes_review_boundary_without_auto_promotion(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        project_id, episode = _fixture(session, shot_ids=(501,))
        batch = create_production_batch(session, project_id=project_id, episode_id=project_id * 10 + episode, model_profile_id="shapi-image")
        payload = serialize_production_batch(session, batch)
        assert payload["status"] == "CREATED"
        assert payload["task_run"]["task_id"] == batch.task_id
        assert payload["items"][0]["promotion_id"] is None
        assert payload["items"][0]["candidate_id"] is None
    finally:
        session.close()
        engine.dispose()
