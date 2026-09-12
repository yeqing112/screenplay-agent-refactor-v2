import importlib.util
import sqlite3
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "backup-database.py"
_SPEC = importlib.util.spec_from_file_location("backup_database", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

_DRILL_PATH = Path(__file__).parents[1] / "scripts" / "restore-database-drill.py"
_DRILL_SPEC = importlib.util.spec_from_file_location("restore_database_drill", _DRILL_PATH)
assert _DRILL_SPEC and _DRILL_SPEC.loader
_DRILL_MODULE = importlib.util.module_from_spec(_DRILL_SPEC)
_DRILL_SPEC.loader.exec_module(_DRILL_MODULE)


def _make_source(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE shots (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("INSERT INTO shots(name) VALUES ('real sample')")
        connection.commit()


def test_backup_is_integrity_checked_and_source_is_not_mutated(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "backup" / "source.db"
    _make_source(source)
    before = source.read_bytes()

    result = _MODULE.backup_database(source, output)

    assert result["source_mutated"] is False
    assert result["source_integrity"] == "ok"
    assert result["backup_integrity"] == "ok"
    assert output.is_file()
    assert source.read_bytes() == before
    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT name FROM shots").fetchone() == ("real sample",)


def test_backup_refuses_overwrite_without_explicit_flag(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "backup.db"
    _make_source(source)
    output.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        _MODULE.backup_database(source, output)


def test_sqlite_path_from_url_rejects_non_sqlite_and_memory_urls():
    with pytest.raises(ValueError):
        _MODULE.sqlite_path_from_url("postgresql://localhost/screenplay")
    with pytest.raises(ValueError):
        _MODULE.sqlite_path_from_url("sqlite:///:memory:")


def test_restore_drill_restores_to_temporary_database_without_touching_backup(tmp_path):
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    _make_source(source)
    _MODULE.backup_database(source, backup)
    before = backup.read_bytes()

    result = _DRILL_MODULE.restore_drill(backup)

    assert result["source_integrity"] == "ok"
    assert result["restored_integrity"] == "ok"
    assert result["source_table_count"] == result["restored_table_count"] == 1
    assert result["source_untouched"] is True
    assert result["temporary_restore_removed"] is True
    assert backup.read_bytes() == before
