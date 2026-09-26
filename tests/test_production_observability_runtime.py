"""Production observability aggregation contracts over existing runtime rows."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.generation_execution_service import GenerationExecutionService
from core.production_batch import create_production_batch
from core.production_metrics import ProductionMetricsService
from models import (
    EpisodeOutline,
    MediaCandidateRecord,
    MediaPromotionRecord,
    PromptIRPointer,
    PromptIRVersion,
    StoryboardShot,
    ProductionBatchItem,
)
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "production-observability-runtime.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    return engine, sessionmaker(bind=engine)()


def _fixture(session):
    project_id = 981001
    episode = 1
    episode_id = project_id * 10 + episode
    session.add(EpisodeOutline(id=episode_id, book_id=project_id, episode=episode, title="Metrics fixture"))
    for business_shot_id in (601, 602):
        shot = StoryboardShot(
            book_id=project_id,
            episode=episode,
            scene_name="METRICS_SCENE",
            scene_id=f"metrics-scene-{business_shot_id}",
            plan_shot_id=f"metrics-plan-{business_shot_id}",
            shot_id=business_shot_id,
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
            schema_version="prompt_ir_metrics_test_v1",
            payload_json='{"generation_policy":{"target_media":"IMAGE"}}',
            payload_hash=f"sha256:metrics-{business_shot_id}",
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
                target_media="IMAGE",
                prompt_ir_version_id=version.id,
                payload_hash=version.payload_hash,
            )
        )
    session.commit()
    batch = create_production_batch(
        session,
        project_id=project_id,
        episode_id=episode_id,
        model_profile_id="shapi-image",
    )
    return batch


def _prepare_runtime_rows(session, batch):
    items = session.query(ProductionBatchItem).filter_by(batch_id=batch.id).order_by(ProductionBatchItem.id).all()
    executions = [item.execution_id for item in items]
    service = GenerationExecutionService(session)
    now = datetime.utcnow()
    rows = [service.get_execution(execution_id) for execution_id in executions]
    for index, row in enumerate(rows):
        service.transition(row.execution_id, "QUEUED")
        service.transition(row.execution_id, "RUNNING")
        if index == 0:
            service.transition(row.execution_id, "SUCCESS")
            row.provider = "shapi-openai-images"
            row.latency_ms = 100
            row.submitted_at = now
            row.completed_at = now + timedelta(seconds=1)
            row.candidate_id = "candidate-metrics-1"
            items[index].status = "SUCCEEDED"
            items[index].candidate_id = row.candidate_id
        else:
            service.transition(row.execution_id, "FAILED", error_message="provider failure")
            row.provider = "shapi-openai-images"
            row.latency_ms = 250
            row.transport_retry_count = 2
            row.submitted_at = now
            row.completed_at = now + timedelta(seconds=3)
            items[index].status = "FAILED"
            items[index].error = "provider failure"

    data = b"metrics-candidate"
    session.add(
        MediaCandidateRecord(
            candidate_id="candidate-metrics-1",
            execution_id=rows[0].execution_id,
            status="MEDIA_CANDIDATE",
            validation_status="TECHNICALLY_VALID",
            media_type="IMAGE",
            storage_identity="local://metrics-candidate-1",
            storage_reference_json="{}",
            metadata_json="{}",
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            mime_type="image/png",
            byte_size=len(data),
            width=1,
            height=1,
            prompt_ir_version_id=rows[0].prompt_ir_version_id,
            prompt_ir_payload_hash=rows[0].prompt_ir_payload_hash,
            generation_payload_fingerprint=rows[0].generation_payload_fingerprint,
            model_profile_id=rows[0].model_profile_id,
            model_profile_fingerprint=rows[0].model_profile_fingerprint,
            provider_request_fingerprint=rows[0].provider_request_fingerprint,
            provider_response_hash="sha256:metrics-response",
            provider_task_id="metrics-task",
        )
    )
    session.add(
        MediaPromotionRecord(
            promotion_id="promotion-metrics-1",
            candidate_id="candidate-metrics-1",
            validation_id="validation-metrics-1",
            execution_id=rows[0].execution_id,
            review_status="APPROVED",
            decision="APPROVE",
            official_media_version_id="official-metrics-1",
            authority_id="authority-metrics-1",
            promotion_fingerprint="sha256:promotion-metrics",
        )
    )
    batch.status = "FAILED"
    batch.completed_tasks = 1
    batch.failed_tasks = 1
    session.commit()
    return items, rows


def test_metrics_service_aggregates_batch_execution_provider_and_asset_facts(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        batch = _fixture(session)
        _prepare_runtime_rows(session, batch)
        metrics = ProductionMetricsService(session)

        assert metrics.batch_metrics(batch.batch_key) == {
            "total": 2,
            "completed": 1,
            "failed": 1,
            "running": 0,
            "pending": 0,
        }
        execution = metrics.execution_metrics(batch.batch_key)
        assert execution["success_count"] == 1
        assert execution["failed_count"] == 1
        assert execution["average_duration"] == 2000.0
        assert execution["retry_count"] == 2

        provider = metrics.provider_metrics(batch.batch_key)
        assert provider == [{
            "provider_name": "shapi-openai-images",
            "request_count": 2,
            "success_count": 1,
            "failure_count": 1,
            "success_rate": 0.5,
            "failure_rate": 0.5,
            "average_latency": 175.0,
            "average_latency_ms": 175.0,
        }]
        assert metrics.asset_metrics(batch.batch_key) == {
            "candidate_count": 1,
            "approved_count": 1,
            "rejected_count": 0,
            "promotion_rate": 1.0,
        }
    finally:
        session.close()
        engine.dispose()


def test_summary_and_batch_dashboard_are_read_only_and_do_not_create_metric_tables(tmp_path: Path):
    engine, session = _session(tmp_path)
    try:
        batch = _fixture(session)
        _prepare_runtime_rows(session, batch)
        service = ProductionMetricsService(session)
        summary = service.summary()
        dashboard = service.batch_dashboard(batch.batch_key)
        assert summary["schema_version"] == "production_observability_runtime_v1"
        assert summary["batch_metrics"]["total"] == 1
        assert summary["execution_metrics"]["total"] == 2
        assert dashboard["batch"]["batch_id"] == batch.batch_key
        assert dashboard["batch_metrics"]["failed"] == 1
        assert dashboard["provider_metrics"][0]["provider_name"] == "shapi-openai-images"
        tables = set(inspect(engine).get_table_names())
        assert not {table for table in tables if "metric" in table.lower() or "observability" in table.lower()}
    finally:
        session.close()
        engine.dispose()


def test_metrics_api_contract_and_missing_batch_error(tmp_path: Path, monkeypatch):
    engine, session = _session(tmp_path)
    try:
        batch = _fixture(session)
        _prepare_runtime_rows(session, batch)
        api_module = __import__("api.production_metrics_api", fromlist=["*"])
        monkeypatch.setattr(api_module, "Session", sessionmaker(bind=engine))
        summary = api_module.runtime_summary()
        dashboard = api_module.batch_dashboard(batch.batch_key)
        assert set(summary) == {"schema_version", "batch_metrics", "execution_metrics", "provider_metrics", "asset_metrics"}
        assert dashboard["batch"]["status"] == "FAILED"
        assert dashboard["asset_metrics"]["approved_count"] == 1
        with pytest.raises(Exception) as exc_info:
            api_module.batch_dashboard("missing-batch")
        assert getattr(exc_info.value, "status_code", None) == 404
    finally:
        session.close()
        engine.dispose()

    from api.server import app

    paths = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ("/production/metrics/batches/{batch_id}", ("GET",)) in paths
    assert ("/production/metrics/summary", ("GET",)) in paths
    assert ("/api/production/metrics/summary", ("GET",)) in paths
