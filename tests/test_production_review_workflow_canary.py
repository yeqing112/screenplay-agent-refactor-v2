"""Production Asset human review workflow contract tests."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.production_asset_authority import (
    AssetBindingInvalid,
    ingest_production_asset,
    switch_current_production_asset_version,
)
from core.production_asset_review import (
    ProductionAssetReviewError,
    ProductionAssetReviewGateError,
    create_production_asset_review,
    production_review_gate,
    review_history,
    transition_production_asset_review,
)
from core.production_review_workflow_canary import (
    build_production_review_workflow_fixture,
    build_review_workflow_truth_audit,
    reconcile_production_review_workflow_canary,
)
from models import (
    CharacterAssetAuthority,
    CharacterAssetVersion,
    ProductionAssetReview,
    ProductionAssetReviewHistory,
    SceneAssetVersion,
)
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "production-review-workflow.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _source(name: str, revision: int = 1) -> dict:
    return {
        "storage_identity": f"https://assets.example.invalid/review/{name}/v{revision}.png",
        "checksum": f"sha256:review:{name}:{revision}",
        "metadata": {
            "schema_version": "production_asset_media_metadata_v1",
            "source_kind": "production_review_test",
            "mime_type": "image/png",
            "width": 1024,
            "height": 1024,
            "provenance": {"source_reference": f"test://{name}/{revision}", "is_mock": False},
        },
    }


def _one_asset(tmp_path: Path):
    engine, session = _session(tmp_path)
    asset = ingest_production_asset(session, entity_type="CHARACTER", entity_id="REVIEW_CHARACTER", source=_source("character"))
    return engine, session, asset


def test_fixture_contains_approved_rejected_and_request_change_paths():
    fixture = build_production_review_workflow_fixture()
    assert fixture["episode"] == 1
    assert len(fixture["graph_fixture"]["shots"]) == 10
    assert len(fixture["graph_fixture"]["provider_response"]["assets"]) == 12
    assert {case["decision"] for case in fixture["review_cases"]} == {"APPROVE", "REJECT", "REQUEST_CHANGE"}
    assert fixture["provider_calls"] == 0


def test_valid_review_transition_records_append_only_history(tmp_path):
    engine, session, asset = _one_asset(tmp_path)
    try:
        review = create_production_asset_review(session, asset_type="CHARACTER", asset_id="REVIEW_CHARACTER", asset_version_id=asset["version_id"])
        for state in ("NORMALIZED", "AI_VALIDATED", "HUMAN_REVIEW_PENDING"):
            transition_production_asset_review(session, review_id=review["review_id"], to_state=state, reviewer_type="SYSTEM")
        transition_production_asset_review(session, review_id=review["review_id"], to_state="HUMAN_APPROVED", reviewer_type="DIRECTOR", decision="APPROVE")
        history = review_history(session, review["review_id"])
        assert [item["to"] for item in history] == ["GENERATED", "NORMALIZED", "AI_VALIDATED", "HUMAN_REVIEW_PENDING", "HUMAN_APPROVED"]
        assert len({item["history_id"] for item in history}) == len(history)
    finally:
        session.close(); engine.dispose()


def test_invalid_transition_cannot_bypass_human_review(tmp_path):
    engine, session, asset = _one_asset(tmp_path)
    try:
        review = create_production_asset_review(session, asset_type="CHARACTER", asset_id="REVIEW_CHARACTER", asset_version_id=asset["version_id"])
        with pytest.raises(ProductionAssetReviewError):
            transition_production_asset_review(session, review_id=review["review_id"], to_state="HUMAN_APPROVED", reviewer_type="SYSTEM", decision="APPROVE")
        with pytest.raises(ProductionAssetReviewError):
            transition_production_asset_review(session, review_id=review["review_id"], to_state="PRODUCTION_READY", reviewer_type="SYSTEM", decision="APPROVE")
        assert session.query(ProductionAssetReviewHistory).filter_by(review_id=review["review_id"]).count() == 1
    finally:
        session.close(); engine.dispose()


def test_public_pointer_switch_requires_review_id(tmp_path):
    engine, session, asset = _one_asset(tmp_path)
    try:
        authority = session.query(CharacterAssetAuthority).filter_by(character_id="REVIEW_CHARACTER").one()
        before = authority.current_version_id
        with pytest.raises(AssetBindingInvalid):
            switch_current_production_asset_version(session, entity_type="CHARACTER", entity_id="REVIEW_CHARACTER", version_id=asset["version_id"])
        assert authority.current_version_id == before
    finally:
        session.close(); engine.dispose()


def test_public_pointer_switch_requires_matching_review_target(tmp_path):
    engine, session, asset = _one_asset(tmp_path)
    try:
        review = create_production_asset_review(
            session,
            asset_type="CHARACTER",
            asset_id="REVIEW_CHARACTER",
            asset_version_id=asset["version_id"],
        )
        with pytest.raises(AssetBindingInvalid):
            switch_current_production_asset_version(
                session,
                entity_type="CHARACTER",
                entity_id="OTHER_CHARACTER",
                version_id=asset["version_id"],
                review_id=review["review_id"],
            )
    finally:
        session.close(); engine.dispose()


def test_canary_approved_path_activates_pointer_only_after_human_approval(tmp_path):
    engine, session = _session(tmp_path)
    try:
        result = reconcile_production_review_workflow_canary(session)
        assert result["stage"] == "PHASE_PRODUCTION_REVIEW_WORKFLOW_CANARY_COMPLETE"
        approved = next(item for item in result["promotion_attempts"] if item["case_id"] == "approved_character_a_v3")
        assert approved["allowed"] is True
        assert approved["before_pointer_version_id"] != approved["after_pointer_version_id"]
        assert result["review_counts"]["approved_asset_count"] == 2
    finally:
        session.close(); engine.dispose()


def test_rejected_asset_is_blocked_and_pointer_remains_unchanged(tmp_path):
    engine, session = _session(tmp_path)
    try:
        result = reconcile_production_review_workflow_canary(session)
        rejected = next(item for item in result["promotion_attempts"] if item["case_id"] == "rejected_character_b_v2")
        assert rejected["allowed"] is False
        assert rejected["before_pointer_version_id"] == rejected["after_pointer_version_id"]
        assert result["review_counts"]["blocked_promotion_count"] == 1
        assert result["review_counts"]["rejected_asset_count"] == 1
    finally:
        session.close(); engine.dispose()


def test_request_change_creates_new_version_and_preserves_old_history(tmp_path):
    engine, session = _session(tmp_path)
    try:
        result = reconcile_production_review_workflow_canary(session)
        change = result["request_change"]
        assert change["old_review_final_state"] == "ARCHIVED"
        assert change["old_version_id"] != change["new_version_id"]
        assert change["old_history_count"] >= 6
        assert change["new_history_count"] >= 6
        assert session.query(SceneAssetVersion).filter_by(version_id=change["old_version_id"]).count() == 1
        assert session.query(SceneAssetVersion).filter_by(version_id=change["new_version_id"]).count() == 1
    finally:
        session.close(); engine.dispose()


def test_history_is_append_only_and_approved_records_are_not_rewritten(tmp_path):
    engine, session = _session(tmp_path)
    try:
        result = reconcile_production_review_workflow_canary(session)
        before_ids = [row.history_id for row in session.query(ProductionAssetReviewHistory).order_by(ProductionAssetReviewHistory.id).all()]
        approved = next(row for row in session.query(ProductionAssetReview).all() if row.review_state == "PRODUCTION_READY")
        assert [item["to"] for item in review_history(session, approved.review_id)][-2:] == ["HUMAN_APPROVED", "PRODUCTION_READY"]
        session.flush()
        after_ids = [row.history_id for row in session.query(ProductionAssetReviewHistory).order_by(ProductionAssetReviewHistory.id).all()]
        assert after_ids == before_ids
        assert result["truth_checks"]["review_history_append_only"] is True
    finally:
        session.close(); engine.dispose()


def test_review_gate_reports_all_required_checks_and_source_boundary(tmp_path):
    engine, session, asset = _one_asset(tmp_path)
    try:
        gate = production_review_gate(session, asset_type="CHARACTER", asset_id="REVIEW_CHARACTER", asset_version_id=asset["version_id"])
        assert gate["allowed"] is False
        assert "human_review_exists" in gate["failed_checks"]
        audit = build_review_workflow_truth_audit(reconcile_production_review_workflow_canary(session))
        assert audit["complete"] is True
        assert audit["source_fact_mutations"] == 0
        assert audit["script_ir_mutations"] == 0
    finally:
        session.close(); engine.dispose()
