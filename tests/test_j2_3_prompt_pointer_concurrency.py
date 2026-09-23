"""Provider-free concurrency contracts for media-scoped PromptIR pointers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


ROOT = Path(__file__).resolve().parents[1]


def _upgrade(db: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db.as_posix()}")
    command.upgrade(config, "head")


def _insert_pointer(db: Path, pointer_id: int, target_media: str, barrier: Barrier) -> str:
    engine = create_engine(f"sqlite:///{db.as_posix()}", connect_args={"timeout": 10})
    connection = engine.connect()
    transaction = connection.begin()
    try:
        barrier.wait(timeout=10)
        connection.execute(
            text(
                "INSERT INTO prompt_ir_pointers "
                "(id, book_id, episode, storyboard_shot_id, target_media, "
                "prompt_ir_version_id, payload_hash, qualification_state) "
                "VALUES (:id, 1, 1, 7, :target_media, 11, 'hash', 'PROMPT_IR_QUALIFIED')"
            ),
            {"id": pointer_id, "target_media": target_media},
        )
        transaction.commit()
        return "committed"
    except IntegrityError:
        transaction.rollback()
        return "unique_conflict"
    finally:
        connection.close()
        engine.dispose()


def _run_pair(db: Path, targets: tuple[str, str]) -> tuple[list[str], list[tuple[int, str]]]:
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: _insert_pointer(db, item[0], item[1], barrier), enumerate(targets, start=1)))
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, target_media FROM prompt_ir_pointers WHERE book_id=1 AND episode=1 AND storyboard_shot_id=7 ORDER BY id")
        ).all()
    engine.dispose()
    return results, [(int(row[0]), str(row[1])) for row in rows]


def test_concurrent_same_scope_has_one_commit_and_deterministic_unique_conflict(tmp_path):
    db = tmp_path / "same-scope.sqlite"
    _upgrade(db)
    results, rows = _run_pair(db, ("IMAGE", "IMAGE"))
    assert sorted(results) == ["committed", "unique_conflict"]
    assert len(rows) == 1
    assert rows[0][1] == "IMAGE"


def test_concurrent_cross_scope_retains_both_media_pointers(tmp_path):
    db = tmp_path / "cross-scope.sqlite"
    _upgrade(db)
    results, rows = _run_pair(db, ("IMAGE", "VIDEO"))
    assert results == ["committed", "committed"]
    assert rows == [(1, "IMAGE"), (2, "VIDEO")]
