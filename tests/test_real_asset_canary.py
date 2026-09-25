"""Provider-free Real Asset Canary integration tests."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.real_asset_canary import (
    APPROVAL_SEQUENCE,
    build_canary_truth_audit,
    build_real_asset_canary_fixture,
    reconcile_real_asset_canary,
)
from models import (
    CharacterAssetAuthority,
    CharacterAssetPointer,
    CharacterAssetVersion,
    SceneAssetAuthority,
    SceneAssetPointer,
    SceneAssetVersion,
    ShotAssetBinding,
    StoryboardShot,
)
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "real-asset-canary.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine, sessionmaker(bind=engine)()


def _counts(session):
    return {
        "shots": session.query(StoryboardShot).count(),
        "bindings": session.query(ShotAssetBinding).count(),
        "character_authority": session.query(CharacterAssetAuthority).count(),
        "character_versions": session.query(CharacterAssetVersion).count(),
        "character_pointers": session.query(CharacterAssetPointer).count(),
        "scene_authority": session.query(SceneAssetAuthority).count(),
        "scene_versions": session.query(SceneAssetVersion).count(),
        "scene_pointers": session.query(SceneAssetPointer).count(),
    }


def test_fixture_is_one_episode_three_shots_and_provenance_complete():
    fixture = build_real_asset_canary_fixture()
    assert fixture["episode"] == 1
    assert len(fixture["shots"]) == 3
    assert len(fixture["provider_response"]["assets"]) == 2
    assert fixture["provider_response"]["provider_calls"] == 0
    for asset in fixture["provider_response"]["assets"]:
        provenance = asset["provenance"]
        assert provenance["source_reference"]
        assert provenance["provider_response_id"]
        assert provenance["provider_output_fingerprint"]
        assert provenance["is_mock"] is False


def test_reconcile_writes_only_after_constraints_and_closes_v2_asset_readiness(tmp_path):
    engine, session = _session(tmp_path)
    try:
        before = _counts(session)
        result = reconcile_real_asset_canary(session)
        after = _counts(session)
        assert result["provider_calls"] == 0
        assert result["approval_state"] == "CANARY_APPROVED"
        assert result["production_writes"]["only_after_reconcile"] is True
        assert result["production_writes"]["allowed"] is True
        assert all(row["state_history"] == list(APPROVAL_SEQUENCE) for row in result["assets"])
        assert before["shots"] == 0
        assert after["shots"] == 3
        assert after["bindings"] == 6
        assert all(item["current"] is True for item in result["v2_asset_readiness"])
        audit = build_canary_truth_audit(result)
        assert audit["stage"] == "PHASE_UI_V2_REAL_ASSET_CANARY_COMPLETE"
        assert audit["source_fact_mutations"] == 0
        assert audit["script_ir_mutations"] == 0
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_mock_provider_asset_is_rejected_before_any_production_write(tmp_path):
    engine, session = _session(tmp_path)
    try:
        fixture = build_real_asset_canary_fixture()
        fixture = copy.deepcopy(fixture)
        fixture["provider_response"]["assets"][0]["provenance"]["is_mock"] = True
        fixture["provider_response"]["assets"][0]["metadata"]["provenance"]["is_mock"] = True
        with pytest.raises(ValueError):
            reconcile_real_asset_canary(session, fixture)
        assert _counts(session) == {
            "shots": 0,
            "bindings": 0,
            "character_authority": 0,
            "character_versions": 0,
            "character_pointers": 0,
            "scene_authority": 0,
            "scene_versions": 0,
            "scene_pointers": 0,
        }
    finally:
        session.close()
        engine.dispose()
