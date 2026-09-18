"""Provider-free migration chain release-gate tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_migration_chain import audit_graph, fresh_replay, legacy_replay


def test_revision_graph_is_single_head_and_has_no_forbidden_runtime_shortcuts():
    report = audit_graph()
    assert report["root"] == ["bf85be21e043"]
    assert report["heads"] == ["w6f7g8h9i0j1"]
    assert not report["missing_predecessors"]
    assert report["status"] == "PASS"
    assert not report["forbidden_migration_patterns"]


def test_fresh_upgrade_and_repeat_are_idempotent_with_authority_schema():
    replay, schema = fresh_replay()
    assert replay["first_upgrade"] == "PASS"
    assert replay["second_upgrade"] == "PASS"
    assert replay["alembic_version"] == "w6f7g8h9i0j1"
    assert schema["status"] == "PASS"
    assert not schema["missing_authority_tables"]
    assert not schema["missing_authority_columns"]


def test_pre_f05_fixture_preserves_legacy_outline_payload():
    report = legacy_replay()
    assert report["status"] == "PASS"
    pre_f05 = next(item for item in report["fixtures"] if item["fixture"] == "pre-f05")
    assert pre_f05["row_preserved"] is True
    assert pre_f05["row"]["content"] == pre_f05["row"]["raw_content"]


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
