"""Phase H2.2 explicit asset ingestion and shot binding contract tests."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.production_asset_authority import (
    AssetBindingInvalid,
    ProductionAssetSchemaError,
    bind_shot_assets,
    ingest_production_asset,
    resolve_shot_assets,
)
from models import ShotAssetBinding, StoryboardShot
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
