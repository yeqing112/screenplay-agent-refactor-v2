"""Create and verify a safe SQLite backup for production recovery.

The command is deliberately explicit: an output path is required, existing
files are never overwritten unless ``--overwrite`` is supplied, and the
backup is integrity-checked before it is moved into place.  It never deletes
or mutates the source database.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config


def sqlite_path_from_url(database_url: str) -> Path:
    """Resolve a SQLite SQLAlchemy URL to an absolute filesystem path."""
    parsed = make_url(str(database_url or ""))
    if parsed.drivername not in {"sqlite", "sqlite+pysqlite"}:
        raise ValueError("database backup currently supports SQLite only")
    database = str(parsed.database or "").strip()
    if not database or database == ":memory:":
        raise ValueError("an on-disk SQLite database is required for backup")
    return Path(database).expanduser().resolve()


def _integrity_check(path: Path) -> str:
    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    result = str(row[0] if row else "").strip().lower()
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed for {path}: {result or 'empty result'}")
    return result


def verify_backup(path: Path) -> dict[str, object]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"backup file not found: {resolved}")
    integrity = _integrity_check(resolved)
    connection = sqlite3.connect(str(resolved))
    try:
        table_count = int(connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])
    finally:
        connection.close()
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "integrity": integrity,
        "table_count": table_count,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def backup_database(source: Path, output: Path, *, overwrite: bool = False) -> dict[str, object]:
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"source database not found: {source}")
    if source == output:
        raise ValueError("backup output must differ from the source database")
    if output.exists() and not overwrite:
        raise FileExistsError(f"backup output already exists; pass --overwrite explicitly: {output}")

    # Validate the source before copying so a corrupted source cannot be
    # silently promoted as a recovery artifact.
    source_integrity = _integrity_check(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    try:
        source_connection = sqlite3.connect(str(source))
        target_connection = sqlite3.connect(str(temporary))
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()
        verify_backup(temporary)
        if output.exists() and not overwrite:
            raise FileExistsError(f"backup output already exists; pass --overwrite explicitly: {output}")
        os.replace(str(temporary), str(output))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    result = verify_backup(output)
    return {
        "source": str(source),
        "output": result["path"],
        "source_integrity": source_integrity,
        "backup_integrity": result["integrity"],
        "bytes": result["bytes"],
        "table_count": result["table_count"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or verify a SQLite recovery backup.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path, help="Explicit backup output path.")
    group.add_argument("--verify", type=Path, help="Verify an existing SQLite backup without writing.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing output file.")
    parser.add_argument("--database-url", default=config.DATABASE_URL, help="SQLite URL; defaults to DATABASE_URL.")
    args = parser.parse_args()

    if args.verify:
        if args.overwrite:
            parser.error("--overwrite cannot be used with --verify")
        result = verify_backup(args.verify)
    else:
        source = sqlite_path_from_url(args.database_url)
        result = backup_database(source, args.output, overwrite=bool(args.overwrite))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
