"""Phase H2.2 explicit asset ingestion and shot binding contract tests."""
from __future__ import annotations

from pathlib import Path

import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.production_asset_authority import (
    AssetBindingInvalid,
    ProductionAssetSchemaError,
    bind_shot_assets,
    ingest_production_asset,
    resolve_shot_assets,
    production_asset_media_readiness,
)
from core.production_workspace_projection_v2 import _asset_readiness
from models import CharacterAssetVersion, ShotAssetBinding, StoryboardShot
from scripts.verify_migration_chain import _upgrade


def _session(tmp_path: Path):
    db = tmp_path / "h2-2.sqlite"
    _upgrade(db)
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    session = sessionmaker(bind=engine)()
    session.add(
        StoryboardShot(
            book_id=990401,
            episode=1,
            scene_name="雨夜旧公寓门厅",
            scene_id="E01_SC001",
            shot_id=1,
            plan_shot_id="SH_E01_SC001_001",
            asset_links="{}",
            asset_status="pending",
        )
    )
    session.commit()
    return engine, session


def _source(token: str, revision: int = 1):
    return {
        "storage_identity": f"pilot://episode-01/{token}/v{revision}",
        "checksum": f"sha256:{token}:{revision}",
        "metadata": {"role": "production-reference", "token": token, "revision": revision},
    }


def test_ingestion_requires_explicit_storage_contract(tmp_path):
    engine, session = _session(tmp_path)
    try:
        with pytest.raises(ProductionAssetSchemaError):
            ingest_production_asset(session, entity_type="CHARACTER", entity_id="LIN_WAN", source={})
        with pytest.raises(ProductionAssetSchemaError):
            ingest_production_asset(
                session,
                entity_type="CHARACTER",
                entity_id="LIN_WAN",
                source={"storage_identity": "x", "checksum": "y", "metadata": {}, "image_url": "https://example.invalid"},
            )
    finally:
        session.close()
        engine.dispose()


def test_ingestion_is_idempotent_and_emits_authority_version_pointer(tmp_path):
    engine, session = _session(tmp_path)
    try:
        first = ingest_production_asset(session, entity_type="CHARACTER", entity_id="LIN_WAN", source=_source("lin-wan"))
        second = ingest_production_asset(session, entity_type="CHARACTER", entity_id="LIN_WAN", source=_source("lin-wan"))
        assert first["authority_id"] == second["authority_id"]
        assert first["version_id"] == second["version_id"]
        assert all(first[key] for key in ("authority_fingerprint", "version_fingerprint", "pointer_fingerprint"))
        session.commit()
    finally:
        session.close()
        engine.dispose()


def test_binding_resolves_and_version_rollover_stales_old_binding(tmp_path):
    engine, session = _session(tmp_path)
    try:
        character = ingest_production_asset(session, entity_type="CHARACTER", entity_id="LIN_WAN", source=_source("lin-wan"))
        scene = ingest_production_asset(session, entity_type="SCENE", entity_id="E01_SC001", source=_source("old-apartment-lobby"))
        prop = ingest_production_asset(session, entity_type="PROP", entity_id="RED_UMBRELLA", source=_source("red-umbrella"))
        shot = session.query(StoryboardShot).one()
        bound = bind_shot_assets(
            session,
            storyboard_shot_id=shot.id,
            characters=[{"authority_id": character["authority_id"], "version_id": character["version_id"]}],
            scene={"authority_id": scene["authority_id"], "version_id": scene["version_id"]},
            props=[{"authority_id": prop["authority_id"], "version_id": prop["version_id"]}],
        )
        assert len(bound) == 3
        resolved = resolve_shot_assets(session, storyboard_shot_id=shot.id)
        assert resolved["status"] == "PASS"
        assert resolved["scene"]["entity_id"] == "E01_SC001"

        replacement = ingest_production_asset(session, entity_type="SCENE", entity_id="E01_SC001", source=_source("old-apartment-lobby", revision=2))
        assert replacement["version_id"] != scene["version_id"]
        old = session.query(ShotAssetBinding).filter_by(storyboard_shot_id=shot.id, asset_type="SCENE").one()
        assert old.version_id == scene["version_id"]
        assert old.status == "STALE"
        with pytest.raises(AssetBindingInvalid) as exc:
            resolve_shot_assets(session, storyboard_shot_id=shot.id)
        assert exc.value.status_code == 409
        assert exc.value.code == "ASSET_BINDING_INVALID"
    finally:
        session.close()
        engine.dispose()


def test_resolver_rejects_missing_formal_binding(tmp_path):
    engine, session = _session(tmp_path)
    try:
        with pytest.raises(AssetBindingInvalid) as exc:
            resolve_shot_assets(session, storyboard_shot_id=session.query(StoryboardShot).one().id)
        assert exc.value.status_code == 409
        assert exc.value.code == "ASSET_BINDING_INVALID"
    finally:
        session.close()
        engine.dispose()


def test_v2_asset_readiness_rejects_fixture_media_and_missing_exact_entity(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = session.query(StoryboardShot).one()
        shot.asset_links = json.dumps({
            "canonical_asset_identity": {
                "scene": "E01_SC001",
                "characters": ["LIN_WAN", "GU_CHEN"],
                "props": ["RED_UMBRELLA"],
            }
        })
        lin_wan = ingest_production_asset(session, entity_type="CHARACTER", entity_id="LIN_WAN", source=_source("lin-wan"))
        scene = ingest_production_asset(session, entity_type="SCENE", entity_id="E01_SC001", source=_source("scene"))
        prop = ingest_production_asset(session, entity_type="PROP", entity_id="RED_UMBRELLA", source=_source("umbrella"))
        bind_shot_assets(
            session,
            storyboard_shot_id=shot.id,
            characters=[{"authority_id": lin_wan["authority_id"], "version_id": lin_wan["version_id"]}],
            scene={"authority_id": scene["authority_id"], "version_id": scene["version_id"]},
            props=[{"authority_id": prop["authority_id"], "version_id": prop["version_id"]}],
        )
        session.commit()

        readiness = _asset_readiness(session, shot_id=shot.id, book_id=990401)
        assert readiness["current"] is False
        assert readiness["state"] == "blocked"
        assert "CHARACTER:GU_CHEN" in readiness["missing"]
        assert "CHARACTER:LIN_WAN" in readiness["missing"]
        assert production_asset_media_readiness(
            storage_identity="pilot://episode-01/character/LIN_WAN/v1",
            checksum="sha256:fixture",
        ).present is False
    finally:
        session.close()
        engine.dispose()


def test_v2_asset_readiness_classifies_active_binding_with_missing_media_as_blocked(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = session.query(StoryboardShot).one()
        shot.asset_links = json.dumps({
            "production_asset_requirements": [{"asset_type": "CHARACTER", "entity_id": "LIN_WAN"}]
        })
        character = ingest_production_asset(session, entity_type="CHARACTER", entity_id="LIN_WAN", source=_source("lin-wan"))
        scene = ingest_production_asset(session, entity_type="SCENE", entity_id="E01_SC001", source=_source("scene"))
        version = session.query(CharacterAssetVersion).filter_by(version_id=character["version_id"]).one()
        version.storage_identity = None
        bind_shot_assets(
            session,
            storyboard_shot_id=shot.id,
            characters=[{"authority_id": character["authority_id"], "version_id": character["version_id"]}],
            scene={"authority_id": scene["authority_id"], "version_id": scene["version_id"]},
            props=[],
        )
        session.commit()
        readiness = _asset_readiness(session, shot_id=shot.id, book_id=990401)
        assert readiness["current"] is False
        assert readiness["state"] == "blocked"
        assert "CHARACTER:LIN_WAN" in readiness["missing"]
    finally:
        session.close()
        engine.dispose()


def test_v2_asset_readiness_accepts_list_requirement_contract_shape_and_exposes_exact_entities(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = session.query(StoryboardShot).one()
        shot.asset_links = json.dumps({
            "production_asset_requirements": [
                {"asset_type": "CHARACTER", "entity_id": "LIN_WAN"},
                "SCENE:E01_SC001",
            ]
        })
        readiness = _asset_readiness(session, shot_id=shot.id, book_id=990401)
        assert readiness["current"] is False
        assert readiness["required_entity_count"] == 2
        assert readiness["required_entities"] == ["CHARACTER:LIN_WAN", "SCENE:E01_SC001"]
        assert readiness["requirement_source"] == "production_asset_requirement_contract"
        assert readiness["missing"] == ["CHARACTER:LIN_WAN", "SCENE:E01_SC001"]
    finally:
        session.close()
        engine.dispose()


def test_v2_asset_readiness_rejects_version_without_metadata_hash(tmp_path):
    engine, session = _session(tmp_path)
    try:
        shot = session.query(StoryboardShot).one()
        shot.asset_links = json.dumps({"canonical_asset_identity": {"characters": ["LIN_WAN"]}})
        asset = ingest_production_asset(session, entity_type="CHARACTER", entity_id="LIN_WAN", source=_source("lin-wan"))
        scene = ingest_production_asset(session, entity_type="SCENE", entity_id="E01_SC001", source=_source("scene"))
        version = session.query(CharacterAssetVersion).filter_by(version_id=asset["version_id"]).one()
        version.metadata_hash = None
        bind_shot_assets(
            session,
            storyboard_shot_id=shot.id,
            characters=[{"authority_id": asset["authority_id"], "version_id": asset["version_id"]}],
            scene={"authority_id": scene["authority_id"], "version_id": scene["version_id"]},
            props=[],
        )
        session.commit()
        readiness = _asset_readiness(session, shot_id=shot.id, book_id=990401)
        assert readiness["current"] is False
        assert "CHARACTER:LIN_WAN" in readiness["missing"]
    finally:
        session.close()
        engine.dispose()
