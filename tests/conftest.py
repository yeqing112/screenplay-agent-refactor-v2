"""Hermetic pytest runtime for the screenplay project.

The application uses a module-level SQLAlchemy engine, so the database URL
must be isolated before any test imports ``models`` or ``api.server``.  This
prevents regression tests from mutating the developer database and makes a
purged/empty working tree a valid starting point.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path


_runtime_dir = Path(tempfile.mkdtemp(prefix="screenplay-pytest-"))
_database_path = _runtime_dir / "screenplay.db"
_upload_dir = _runtime_dir / "uploads"
_chroma_dir = _runtime_dir / "chroma"

# An explicit opt-out is available for local debugging, but the default is
# always isolated.  CI never needs to opt out.
if os.getenv("SCREENPLAY_TEST_USE_EXISTING_DB", "").strip().lower() not in {"1", "true", "yes"}:
    os.environ["DATABASE_URL"] = f"sqlite:///{_database_path}?timeout=30"
    os.environ["UPLOAD_DIR"] = str(_upload_dir)
    os.environ["CHROMA_PERSIST_DIR"] = str(_chroma_dir)


def _cleanup_runtime():  # pragma: no cover - process shutdown hook
    """Dispose the app engine, then remove the isolated runtime directory.

    Deferring removal until interpreter exit avoids deleting files while
    pytest's capture teardown is still active.
    """
    if os.getenv("SCREENPLAY_TEST_USE_EXISTING_DB", "").strip().lower() in {"1", "true", "yes"}:
        return
    try:
        from models import engine

        engine.dispose()
    except Exception:
        pass
    shutil.rmtree(_runtime_dir, ignore_errors=True)


atexit.register(_cleanup_runtime)
