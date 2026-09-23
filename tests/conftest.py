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

import pytest


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


@pytest.fixture(autouse=True)
def _purge_orphan_fact_snapshots():
    """Keep test order from reusing an id with stale fact authority rows.

    A few negative fixtures intentionally use a synthetic book id that is not
    present in ``books``.  If that row survives its test, SQLite can later
    reuse the same integer id for a real fixture and make a read-only API test
    observe another test's snapshot.  Purge only rows with no owning Book;
    valid book-scoped authority data remains untouched.
    """
    yield
    try:
        from models import Book, FactRecord, FactSnapshot, Session

        with Session() as session:
            book_ids = session.query(Book.id)
            orphan_ids = [row[0] for row in session.query(FactSnapshot.id).filter(~FactSnapshot.book_id.in_(book_ids)).all()]
            if orphan_ids:
                session.query(FactRecord).filter(FactRecord.snapshot_id.in_(orphan_ids)).delete(synchronize_session=False)
                session.query(FactSnapshot).filter(FactSnapshot.id.in_(orphan_ids)).delete(synchronize_session=False)
                session.commit()
    except Exception:
        # A test that failed before migrations/bootstrap must still report its
        # own failure; cleanup is best effort during interpreter teardown.
        pass
