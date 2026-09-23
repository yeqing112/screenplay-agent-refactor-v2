"""Phase H2 Production Asset Authority schema migration tests."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from scripts.verify_migration_chain import _upgrade
from core.production_asset_authority import validate_asset_authority_schema


ROOT = Path(__file__).resolve().parents[1]
H2_HEAD = "b2c3d4e5f6g7"
H2_TABLES = {
    "production_asset_authority_registry",
    "production_asset_version_registry",
    "character_asset_authorities",
    "character_asset_versions",
    "character_asset_pointers",
    "scene_asset_authorities",
    "scene_asset_versions",
    "scene_asset_pointers",
    "prop_asset_authorities",
    "prop_asset_versions",
    "prop_asset_pointers",
    "shot_asset_bindings",
}


def _cfg(db: Path) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    return cfg


def _foreign_key_engine(db: Path):
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return engine


def test_upgrade_downgrade_upgrade_cycle_and_empty_asset_data(tmp_path):
    db = tmp_path / "h2-cycle.sqlite"
    _upgrade(db)
    engine = _foreign_key_engine(db)
    try:
        inspector = inspect(engine)
        assert H2_TABLES <= set(inspector.get_table_names())
        with engine.connect() as connection:
            assert connection.execute(text("select version_num from alembic_version")).scalar() == H2_HEAD
            assert sum(connection.execute(text(f"select count(*) from {table}")).scalar() for table in H2_TABLES) == 0
        command.downgrade(_cfg(db), "z0a1b2c3d4e5")
        with engine.connect() as connection:
            assert not H2_TABLES.intersection(inspect(engine).get_table_names())
        command.upgrade(_cfg(db), "head")
        with engine.connect() as connection:
            assert connection.execute(text("select version_num from alembic_version")).scalar() == H2_HEAD
    finally:
        engine.dispose()


def test_unique_pointer_invalid_fk_and_status_constraints(tmp_path):
    db = tmp_path / "h2-constraints.sqlite"
    _upgrade(db)
    engine = _foreign_key_engine(db)
    try:
        with engine.begin() as connection:
            connection.execute(text("insert into production_asset_authority_registry(authority_id, asset_type, source_table) values ('char-auth', 'CHARACTER', 'character_asset_authorities')"))
            connection.execute(text("insert into production_asset_version_registry(version_id, authority_id, asset_type) values ('char-v1', 'char-auth', 'CHARACTER')"))
            connection.execute(text("insert into character_asset_versions(version_id, authority_id, character_id, revision, status) values ('char-v1', 'char-auth', 'char-1', 1, 'CURRENT')"))
            connection.execute(text("insert into character_asset_authorities(authority_id, character_id, current_version_id, fingerprint, status) values ('char-auth', 'char-1', 'char-v1', 'char-auth-fp', 'ACTIVE')"))
            connection.execute(text("insert into character_asset_pointers(character_id, authority_id, version_id, fingerprint) values ('char-1', 'char-auth', 'char-v1', 'char-pointer-fp')"))
            with pytest.raises(IntegrityError):
                connection.execute(text("insert into character_asset_pointers(character_id, authority_id, version_id, fingerprint) values ('char-1', 'char-auth', 'char-v1', 'char-pointer-fp-2')"))
            with pytest.raises(IntegrityError):
                connection.execute(text("insert into shot_asset_bindings(storyboard_shot_id, asset_type, authority_id, version_id, binding_fingerprint, status) values (999, 'CHARACTER', 'missing-auth', 'missing-version', 'binding-fp', 'ACTIVE')"))
            connection.execute(text("insert into production_asset_authority_registry(authority_id, asset_type, source_table) values ('bad-auth', 'CHARACTER', 'character_asset_authorities')"))
            with pytest.raises(IntegrityError):
                connection.execute(text("insert into character_asset_authorities(authority_id, character_id, fingerprint, status) values ('bad-auth', 'char-bad', 'bad-fp', 'INVALID')"))
    finally:
        engine.dispose()


def test_existing_ag2_counts_and_reference_isolation(tmp_path):
    """A pre-H2 A-G2 database keeps all existing rows and gains no assets."""
    db = tmp_path / "ag2.sqlite"
    _upgrade(db, "z0a1b2c3d4e5")
    engine = _foreign_key_engine(db)
    existing_tables = (
        "script_ir_versions",
        "director_treatment_authorities",
        "scene_blocking_authorities",
        "shot_plan_authorities",
        "storyboard_shots",
        "prompt_ir_versions",
        "media_candidate_records",
        "official_media_versions",
        "visual_reference_authorities",
    )
    try:
        with engine.connect() as connection:
            before = {table: connection.execute(text(f"select count(*) from {table}")).scalar() for table in existing_tables}
        command.upgrade(_cfg(db), "head")
        with engine.connect() as connection:
            after = {table: connection.execute(text(f"select count(*) from {table}")).scalar() for table in existing_tables}
            h2_counts = {table: connection.execute(text(f"select count(*) from {table}")).scalar() for table in H2_TABLES}
        assert after == before
        assert all(value == 0 for value in h2_counts.values())
    finally:
        engine.dispose()


def test_schema_validator_accepts_empty_h2_tables_without_resolver(tmp_path):
    db = tmp_path / "h2-validator.sqlite"
    _upgrade(db)
    engine = _foreign_key_engine(db)
    try:
        session = sessionmaker(bind=engine)()
        try:
            report = validate_asset_authority_schema(session)
            assert report["status"] == "PASS"
            assert report["resolver_created"] is False
            assert report["provider_calls"] == 0
            assert report["prompt_ir_mutated"] is False
        finally:
            session.close()
    finally:
        engine.dispose()
