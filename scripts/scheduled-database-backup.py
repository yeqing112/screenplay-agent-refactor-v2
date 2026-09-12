"""Create a timestamped, verified SQLite backup for scheduled execution.

This wrapper is safe for cron/Task Scheduler: it never overwrites or deletes
an existing backup and never modifies the source database. Off-site upload is
deliberately out of scope and must be provided by the deployment environment.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config

_BACKUP_PATH = ROOT_DIR / "scripts" / "backup-database.py"
_BACKUP_SPEC = importlib.util.spec_from_file_location("backup_database", _BACKUP_PATH)
assert _BACKUP_SPEC and _BACKUP_SPEC.loader
_BACKUP_MODULE = importlib.util.module_from_spec(_BACKUP_SPEC)
_BACKUP_SPEC.loader.exec_module(_BACKUP_MODULE)

_RESTORE_PATH = ROOT_DIR / "scripts" / "restore-database-drill.py"
_RESTORE_SPEC = importlib.util.spec_from_file_location("restore_database_drill", _RESTORE_PATH)
assert _RESTORE_SPEC and _RESTORE_SPEC.loader
_RESTORE_MODULE = importlib.util.module_from_spec(_RESTORE_SPEC)
_RESTORE_SPEC.loader.exec_module(_RESTORE_MODULE)


def timestamped_output(directory: Path, *, prefix: str = "screenplay") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_prefix = "".join(character if character.isalnum() or character in "-_" else "-" for character in prefix).strip("-") or "screenplay"
    return directory.expanduser().resolve() / f"{safe_prefix}-{stamp}.sqlite"


def scheduled_backup(
    *,
    directory: Path,
    prefix: str,
    database_url: str,
    restore_drill: bool = False,
) -> dict[str, object]:
    output = timestamped_output(directory, prefix=prefix)
    source = _BACKUP_MODULE.sqlite_path_from_url(database_url)
    result = _BACKUP_MODULE.backup_database(source, output, overwrite=False)
    result["schedule_mode"] = True
    result["restore_drill_requested"] = restore_drill
    if restore_drill:
        result["restore_drill"] = _RESTORE_MODULE.restore_drill(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a timestamped, verified SQLite backup without deleting prior backups.")
    parser.add_argument("--directory", type=Path, default=ROOT_DIR / "artifacts" / "database-backups")
    parser.add_argument("--prefix", default="screenplay")
    parser.add_argument("--database-url", default=config.DATABASE_URL)
    parser.add_argument("--restore-drill", action="store_true", help="Run a non-destructive restore drill after backup verification.")
    args = parser.parse_args()
    try:
        result = scheduled_backup(
            directory=args.directory,
            prefix=args.prefix,
            database_url=args.database_url,
            restore_drill=bool(args.restore_drill),
        )
    except Exception as exc:  # noqa: BLE001 - CLI must return a useful failure payload.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
