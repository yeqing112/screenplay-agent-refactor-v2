"""Provider-free migration chain release-gate tests."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from scripts.verify_migration_chain import _upgrade, audit_graph, fresh_replay, legacy_replay


def test_revision_graph_is_single_head_and_has_no_forbidden_runtime_shortcuts():
    report = audit_graph()
    assert report["root"] == ["bf85be21e043"]
    assert report["heads"] == ["b2c3d4e5f6g7"]
    assert not report["missing_predecessors"]
    assert report["status"] == "PASS"
    assert not report["forbidden_migration_patterns"]


def test_fresh_upgrade_and_repeat_are_idempotent_with_authority_schema():
    replay, schema = fresh_replay()
    assert replay["first_upgrade"] == "PASS"
    assert replay["second_upgrade"] == "PASS"
    assert replay["alembic_version"] == "b2c3d4e5f6g7"
    assert schema["status"] == "PASS"
    assert not schema["missing_authority_tables"]
    assert not schema["missing_authority_columns"]


def test_pre_f05_fixture_preserves_legacy_outline_payload():
    report = legacy_replay()
    assert report["status"] == "PASS"
    pre_f05 = next(item for item in report["fixtures"] if item["fixture"] == "pre-f05")
    assert pre_f05["row_preserved"] is True
    assert pre_f05["row"]["content"] == pre_f05["row"]["raw_content"]


def test_historical_visual_canary_revision_upgrades_in_place_to_canonical_head(tmp_path):
    db = tmp_path / "historical-canary.sqlite"
    _upgrade(db, "n7h8i9j0k1l2")
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE visual_authoring_decision_requests (
          id INTEGER PRIMARY KEY, request_id VARCHAR(128) NOT NULL,
          book_id INTEGER NOT NULL, asset_key VARCHAR(255) NOT NULL,
          asset_type VARCHAR(32) NOT NULL, canonical_id VARCHAR(128) NOT NULL,
          scope TEXT NOT NULL DEFAULT '{}', source_constraints TEXT NOT NULL DEFAULT '{}',
          free_authoring_space TEXT NOT NULL DEFAULT '[]', forbidden_contradictions TEXT NOT NULL DEFAULT '[]',
          context_json TEXT NOT NULL DEFAULT '{}', status VARCHAR(32) NOT NULL DEFAULT 'PENDING'
        );
        CREATE TABLE visual_authoring_decisions (
          id INTEGER PRIMARY KEY, decision_id VARCHAR(128) NOT NULL,
          request_id VARCHAR(128) NOT NULL, book_id INTEGER NOT NULL,
          asset_key VARCHAR(255) NOT NULL, asset_type VARCHAR(32) NOT NULL,
          decision_json TEXT NOT NULL DEFAULT '{}', confirmed INTEGER NOT NULL DEFAULT 0,
          status VARCHAR(32) NOT NULL DEFAULT 'APPROVED'
        );
        CREATE TABLE visual_authoring_proposals (
          id INTEGER PRIMARY KEY, proposal_id VARCHAR(128) NOT NULL,
          request_id VARCHAR(128) NOT NULL, book_id INTEGER NOT NULL,
          asset_key VARCHAR(255) NOT NULL, asset_type VARCHAR(32) NOT NULL,
          scope TEXT NOT NULL DEFAULT '{}', proposed_fields_json TEXT NOT NULL DEFAULT '{}',
          explanation_summary TEXT NOT NULL DEFAULT '', source_constraint_refs TEXT NOT NULL DEFAULT '[]',
          provider_profile_id VARCHAR(128) NOT NULL, provider_model VARCHAR(255) NOT NULL DEFAULT '',
          provider_vendor_host VARCHAR(255) NOT NULL DEFAULT '', provider_request_fingerprint VARCHAR(128) NOT NULL,
          provider_response_hash VARCHAR(128) NOT NULL DEFAULT '', proposal_payload_hash VARCHAR(128) NOT NULL DEFAULT '',
          validator_status VARCHAR(32) NOT NULL DEFAULT 'PENDING', validator_diagnostics TEXT NOT NULL DEFAULT '{}',
          audit_json TEXT NOT NULL DEFAULT '{}', status VARCHAR(32) NOT NULL DEFAULT 'CANDIDATE'
        );
        CREATE TABLE visual_asset_versions (
          id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL, asset_key VARCHAR(255) NOT NULL,
          version INTEGER NOT NULL DEFAULT 1, payload_json TEXT NOT NULL DEFAULT '{}',
          status VARCHAR(32) NOT NULL DEFAULT 'DRAFT'
        );
        CREATE TABLE visual_asset_pointers (
          id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL, asset_key VARCHAR(255) NOT NULL,
          version_id INTEGER NOT NULL
        );
        CREATE TABLE visual_reference_authorities (
          id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL, asset_key VARCHAR(255) NOT NULL,
          reference_json TEXT NOT NULL DEFAULT '{}', status VARCHAR(32) NOT NULL DEFAULT 'CANDIDATE'
        );
        INSERT INTO visual_authoring_decision_requests (id, request_id, book_id, asset_key, asset_type, canonical_id)
          VALUES (1, 'legacy-request', 990401, 'character:legacy', 'character', 'legacy');
        UPDATE alembic_version SET version_num='p0q1r2s3t4u5';
        """
    )
    connection.commit()
    connection.close()
    _upgrade(db)
    check = sqlite3.connect(db)
    columns = {row[1] for row in check.execute("pragma table_info(visual_authoring_decision_requests)")}
    assert "source_constraints_json" in columns
    assert check.execute("select request_id from visual_authoring_decision_requests where id=1").fetchone()[0] == "legacy-request"
    assert check.execute("select version_num from alembic_version").fetchone()[0] == "b2c3d4e5f6g7"
    check.close()


def test_init_db_is_fail_closed_by_default(monkeypatch):
    import alembic.command
    import models.base as base

    monkeypatch.setattr(alembic.command, "upgrade", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broken migration")))
    monkeypatch.setattr(base.config, "ALLOW_DEV_CREATE_ALL_FALLBACK", False)
    monkeypatch.setattr(base.config, "DEPLOYMENT_ENV", "production")
    with pytest.raises(RuntimeError, match="broken migration"):
        base.init_db()


def test_create_all_fallback_requires_explicit_local_opt_in(monkeypatch):
    import alembic.command
    import models.base as base
    from sqlalchemy import create_engine

    monkeypatch.setattr(alembic.command, "upgrade", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broken migration")))
    local_engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(base, "engine", local_engine)
    monkeypatch.setattr(base.config, "ALLOW_DEV_CREATE_ALL_FALLBACK", True)
    monkeypatch.setattr(base.config, "DEPLOYMENT_ENV", "local")
    assert base.init_db() is local_engine
    local_engine.dispose()


def test_baseline_source_is_static_and_does_not_import_application_engine():
    source = Path("alembic/versions/bf85be21e043_v2_baseline.py").read_text(encoding="utf-8")
    assert "Base.metadata.create_all" not in source
    assert "from models import" not in source
    assert "engine" not in source
