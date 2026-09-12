"""Validate the production sample registry against the current database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models import Book, Script, Session, StoryboardShot, init_db

DEFAULT_REGISTRY = ROOT_DIR / "production-sample-registry.json"


def validate_registry_payload(
    payload: dict[str, Any],
    *,
    books: Iterable[int],
    scripts_by_book: dict[int, int],
    shots_by_book: dict[int, int],
) -> dict[str, Any]:
    """Validate registry structure and evidence without applying changes."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "errors": ["registry must be a JSON object"],
            "warnings": [],
            "active": [],
            "available_candidates": [],
            "orphan_evidence": [],
        }
    raw_active = payload.get("active_book_ids", [])
    raw_retired = payload.get("retired_book_ids", [])
    if not isinstance(raw_active, list) or not isinstance(raw_retired, list):
        return {
            "ok": False,
            "errors": ["active_book_ids and retired_book_ids must be arrays"],
            "warnings": [],
            "active": [],
            "available_candidates": [],
            "orphan_evidence": [],
        }
    active = [int(value) for value in raw_active if str(value).isdigit() and int(value) > 0]
    retired = {int(value) for value in raw_retired if str(value).isdigit() and int(value) > 0}
    if len(active) != len(raw_active):
        errors.append("active_book_ids contains non-positive or non-integer IDs")
    if len(set(active)) != len(active):
        errors.append("active_book_ids contains duplicate IDs")
    overlap = sorted(set(active) & retired)
    if overlap:
        errors.append(f"active and retired sets overlap: {overlap}")
    existing_books = {int(value) for value in books}
    registered = set(active) | retired
    # Evidence rows can survive after a project record is removed (for
    # example, an interrupted fixture cleanup).  They must never become
    # production samples implicitly, but hiding them makes it impossible to
    # distinguish an empty candidate list from stale data.  Report the IDs
    # read-only and leave cleanup to an explicit, separately audited action.
    orphan_evidence = sorted((set(scripts_by_book) | set(shots_by_book)) - existing_books)
    for book_id in orphan_evidence:
        warnings.append(
            f"orphan evidence book {book_id}: script/shot rows exist but no books record; excluded from candidates"
        )
    available_candidates = [
        {
            "book_id": book_id,
            "scripts": int(scripts_by_book.get(book_id, 0) or 0),
            "shots": int(shots_by_book.get(book_id, 0) or 0),
        }
        for book_id in sorted(existing_books - registered)
        if int(scripts_by_book.get(book_id, 0) or 0) > 0
        and int(shots_by_book.get(book_id, 0) or 0) > 0
    ]
    for book_id in active:
        if book_id not in existing_books:
            errors.append(f"active book {book_id} does not exist in the database")
            continue
        script_count = int(scripts_by_book.get(book_id, 0) or 0)
        shot_count = int(shots_by_book.get(book_id, 0) or 0)
        if script_count <= 0:
            errors.append(f"active book {book_id} has no non-empty Script evidence")
        if shot_count <= 0:
            errors.append(f"active book {book_id} has no StoryboardShot evidence")
        warnings.append(f"active book {book_id}: scripts={script_count}, shots={shot_count}")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "active": active,
        "retired": sorted(retired),
        "available_candidates": available_candidates,
        "orphan_evidence": orphan_evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate production sample registry without modifying it.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    try:
        payload = json.loads(args.registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [f"cannot read registry: {exc}"], "warnings": []}, ensure_ascii=False))
        return 1
    init_db()
    with Session() as session:
        books = [int(row[0]) for row in session.query(Book.id).all()]
        scripts_by_book: dict[int, int] = {}
        for book_id, in session.query(Script.book_id).filter(Script.content.is_not(None), Script.content != "").all():
            scripts_by_book[int(book_id)] = scripts_by_book.get(int(book_id), 0) + 1
        shots_by_book: dict[int, int] = {}
        for book_id, in session.query(StoryboardShot.book_id).all():
            shots_by_book[int(book_id)] = shots_by_book.get(int(book_id), 0) + 1
    result = validate_registry_payload(
        payload,
        books=books,
        scripts_by_book=scripts_by_book,
        shots_by_book=shots_by_book,
    )
    result["registry"] = str(args.registry.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
