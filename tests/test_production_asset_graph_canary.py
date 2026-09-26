"""Production Asset Authority graph canary contract tests."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from core.production_asset_graph_canary import (
    build_graph_truth_audit,
    build_production_asset_graph_fixture,
    normalize_graph_provider_output,
    reconcile_production_asset_graph_canary,
    validate_production_asset_graph,
)
from models import (
    CharacterAssetAuthority,
    CharacterAssetPointer,
    CharacterAssetVersion,
    ProductionAssetVersionRegistry,
    SceneAssetAuthority,
    SceneAssetPointer,
    SceneAssetVersion,
    ShotAssetBinding,
    StoryboardShot,
)
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "production-asset-graph.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _reconcile(tmp_path: Path):
    engine, session = _session(tmp_path)
    result = reconcile_production_asset_graph_canary(session)
    return engine, session, result


def test_fixture_has_required_authority_version_and_shot_shape():
    fixture = build_production_asset_graph_fixture()
    rows = fixture["provider_response"]["assets"]
    assert fixture["episode"] == 1
    assert len(fixture["shots"]) == 10
    assert len(rows) == 12
    assert {(row["entity_id"], row["logical_version"]) for row in rows if row["asset_type"] == "CHARACTER"} == {
        ("CHARACTER_A", "v1"), ("CHARACTER_A", "v2"), ("CHARACTER_A", "v3"),
        ("CHARACTER_B", "v1"), ("CHARACTER_B", "v2"), ("CHARACTER_C", "v1"),
    }
    assert {(row["entity_id"], row["logical_version"]) for row in rows if row["asset_type"] == "SCENE"} == {
        ("SCENE_HOSPITAL", "v1_day"), ("SCENE_HOSPITAL", "v2_night"), ("SCENE_HOSPITAL", "v3_destroyed"),
        ("SCENE_OFFICE", "v1"), ("SCENE_OFFICE", "v2"), ("SCENE_STREET", "v1"),
    }


def test_normalization_rejects_mock_or_duplicate_provider_output():
    fixture = build_production_asset_graph_fixture()
    mocked = copy.deepcopy(fixture["provider_response"])
    mocked["assets"][0]["provenance"]["is_mock"] = True
    with pytest.raises(ValueError, match="invalid provenance"):
        normalize_graph_provider_output(mocked)
    duplicate = copy.deepcopy(fixture["provider_response"])
    duplicate["assets"].append(copy.deepcopy(duplicate["assets"][0]))
    with pytest.raises(ValueError, match="duplicate asset graph version"):
        normalize_graph_provider_output(duplicate)


def test_reconcile_has_unique_authorities_complete_graph_and_active_bindings(tmp_path):
    engine, session, result = _reconcile(tmp_path)
    try:
        assert result["stage"] == "PHASE_PRODUCTION_ASSET_GRAPH_CANARY_COMPLETE"
        assert result["approval_state"] == "GRAPH_CANARY_APPROVED"
        assert result["graph_validation"]["errors"] == []
        assert result["graph_counts"] == {
            "authority_registry": 6, "version_registry": 12,
            "character_authority": 3, "character_versions": 6,
            "scene_authority": 3, "scene_versions": 6,
            "shots": 10, "bindings": 25, "active_bindings": 20, "stale_bindings": 5,
        }
        assert session.query(CharacterAssetAuthority).count() == 3
        assert session.query(SceneAssetAuthority).count() == 3
        assert session.query(CharacterAssetVersion).count() == 6
        assert session.query(SceneAssetVersion).count() == 6
    finally:
        session.close(); engine.dispose()


def test_pointer_rollback_preserves_history_and_marks_old_bindings_stale(tmp_path):
    engine, session, result = _reconcile(tmp_path)
    try:
        rollback = result["rollback_simulation"]
        assert rollback["pointer_changed"] is True
        assert rollback["version_history_preserved"] is True
        assert rollback["authority_identity_mutations"] == 0
        assert rollback["shot_definitions_mutated"] is False
        pointer = session.query(CharacterAssetPointer).filter_by(character_id="CHARACTER_A").one()
        authority = session.query(CharacterAssetAuthority).filter_by(character_id="CHARACTER_A").one()
        current = session.query(CharacterAssetVersion).filter_by(version_id=pointer.version_id).one()
        assert authority.current_version_id == pointer.version_id == current.version_id
        assert current.metadata_hash
        assert session.query(CharacterAssetVersion).filter_by(authority_id=authority.authority_id).count() == 3
        assert session.query(ShotAssetBinding).filter_by(authority_id=authority.authority_id, status="STALE").count() == 5
    finally:
        session.close(); engine.dispose()


def test_every_shot_resolves_after_rollback_and_source_layers_are_untouched(tmp_path):
    engine, session, result = _reconcile(tmp_path)
    try:
        assert result["graph_validation"]["binding_resolution_complete"] is True
        assert result["source_gate_mutations"] == {"fact_snapshots": 0, "fact_records": 0, "script_ir_versions": 0}
        for shot in session.query(StoryboardShot).order_by(StoryboardShot.shot_id).all():
            active = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=shot.id, status="ACTIVE").all()
            assert len(active) == 2
    finally:
        session.close(); engine.dispose()


def test_validator_detects_orphaned_version_registry_edge(tmp_path):
    engine, session, result = _reconcile(tmp_path)
    try:
        version = session.query(CharacterAssetVersion).filter_by(character_id="CHARACTER_C").one()
        # Exercise the validator against a deliberately corrupted audit
        # database edge; production migrations keep this FK protected.
        session.connection().exec_driver_sql("PRAGMA foreign_keys=OFF")
        session.execute(text("DELETE FROM production_asset_version_registry WHERE version_id = :version_id"), {"version_id": version.version_id})
        session.flush()
        shots = session.query(StoryboardShot).order_by(StoryboardShot.shot_id).all()
        report = validate_production_asset_graph(
            session,
            shot_rows=shots,
            expected_entities=result["expected_entities"],
        )
        assert report["version_graph_integrity"] is False
        assert report["no_orphan_version"] is False
        assert any(error["code"] == "ORPHAN_VERSION" for error in report["errors"])
    finally:
        session.close(); engine.dispose()


def test_truth_audit_closes_graph_canary_without_ui_v2_completion_claim(tmp_path):
    engine, session, result = _reconcile(tmp_path)
    try:
        audit = build_graph_truth_audit(result)
        assert audit["stage"] == "PHASE_PRODUCTION_ASSET_GRAPH_CANARY_COMPLETE"
        assert audit["approval_state"] == "GRAPH_CANARY_APPROVED"
        assert all(audit["checks"][key] for key in (
            "asset_authority_integrity", "version_graph_integrity", "pointer_resolution_complete",
            "rollback_safe", "binding_resolution_complete", "no_orphan_version", "no_invalid_pointer",
            "provenance_metadata_complete",
        ))
        assert audit["checks"]["mock_asset_production_approved"] is False
        assert audit["source_fact_mutations"] == 0
        assert audit["script_ir_mutations"] == 0
    finally:
        session.close(); engine.dispose()
