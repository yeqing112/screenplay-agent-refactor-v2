"""Run a non-destructive SQLite restore drill.

The drill restores a backup into a temporary database, runs integrity checks,
and compares its table inventory with the backup.  It never opens the live
database and never writes outside the operating system temporary directory.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import importlib.util

_BACKUP_PATH = ROOT_DIR / "scripts" / "backup-database.py"
_BACKUP_SPEC = importlib.util.spec_from_file_location("backup_database", _BACKUP_PATH)
assert _BACKUP_SPEC and _BACKUP_SPEC.loader
_BACKUP_MODULE = importlib.util.module_from_spec(_BACKUP_SPEC)
_BACKUP_SPEC.loader.exec_module(_BACKUP_MODULE)


def _inventory(connection: sqlite3.Connection) -> tuple[int, tuple[str, ...]]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = tuple(str(row[0]) for row in rows)
    return len(names), names


def restore_drill(backup: Path) -> dict[str, object]:
    resolved = Path(backup).expanduser().resolve()
    source_info = _BACKUP_MODULE.verify_backup(resolved)
    with tempfile.TemporaryDirectory(prefix="screenplay-restore-drill-") as directory:
        restored_path = Path(directory) / "restored.sqlite"
        source_connection = sqlite3.connect(str(resolved))
        target_connection = sqlite3.connect(str(restored_path))
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()

        restored_connection = sqlite3.connect(str(restored_path))
        try:
            integrity_row = restored_connection.execute("PRAGMA integrity_check").fetchone()
            integrity = str(integrity_row[0] if integrity_row else "").strip().lower()
            table_count, table_names = _inventory(restored_connection)
        finally:
            restored_connection.close()

    if integrity != "ok":
        raise RuntimeError(f"restored SQLite integrity check failed: {integrity or 'empty result'}")
    source_table_count = int(source_info["table_count"])
    if table_count != source_table_count:
        raise RuntimeError(
            f"restored table inventory differs: source={source_table_count}, restored={table_count}"
        )
    return {
        "backup": str(resolved),
        "source_integrity": source_info["integrity"],
        "restored_integrity": integrity,
        "source_table_count": source_table_count,
        "restored_table_count": table_count,
        "restored_table_names": list(table_names),
        "source_untouched": True,
        "temporary_restore_removed": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a non-destructive SQLite restore drill.")
    parser.add_argument("--backup", type=Path, required=True, help="Existing SQLite backup to restore.")
    args = parser.parse_args()
    print(json.dumps(restore_drill(args.backup), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
