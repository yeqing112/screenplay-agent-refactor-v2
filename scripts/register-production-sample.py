"""Safely register an existing, evidence-backed book as a production sample.

The command is intentionally dry-run by default. It never creates or copies
shots and never changes the database; an explicit confirmation string is
required before atomically updating the JSON sample registry.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models import Book, Script, Session, StoryboardShot, init_db

DEFAULT_REGISTRY = ROOT_DIR / "production-sample-registry.json"
CONFIRMATION = "REGISTER_PRODUCTION_SAMPLE"


def _parse_ids(values: Any, label: str, errors: list[str]) -> list[int]:
    if not isinstance(values, list):
        errors.append(f"{label} must be an array")
        return []
    parsed: list[int] = []
    for value in values:
        if not str(value).isdigit() or int(value) <= 0:
            errors.append(f"{label} contains non-positive or non-integer IDs")
            continue
        parsed.append(int(value))
    if len(set(parsed)) != len(parsed):
        errors.append(f"{label} contains duplicate IDs")
    return parsed


def build_registration_plan(
    payload: dict[str, Any],
    *,
    book_id: int,
    book_exists: bool,
    script_count: int,
    shot_count: int,
    confirmed: bool,
    unretire: bool = False,
) -> dict[str, Any]:
    """Build a safe registration plan without writing any file or database."""
    errors: list[str] = []
    active = payload.get("active_book_ids", []) if isinstance(payload, dict) else []
    retired = payload.get("retired_book_ids", []) if isinstance(payload, dict) else []
    active_ids = _parse_ids(active, "active_book_ids", errors)
    retired_list = _parse_ids(retired, "retired_book_ids", errors)
    retired_ids = set(retired_list)
    overlap = sorted(set(active_ids) & retired_ids)
    if overlap:
        errors.append(f"active and retired sets overlap: {overlap}")
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "would_write": False,
        }
    if book_id <= 0:
        errors.append("book_id must be a positive integer")
    if not book_exists:
        errors.append(f"book {book_id} does not exist in the database")
    if script_count <= 0:
        errors.append(f"book {book_id} has no non-empty Script evidence")
    if shot_count <= 0:
        errors.append(f"book {book_id} has no StoryboardShot evidence")
    if book_id in active_ids:
        return {
            "ok": not errors,
            "errors": errors,
            "book_id": book_id,
            "already_active": True,
            "would_write": False,
            "confirmed": confirmed,
            "scripts": script_count,
            "shots": shot_count,
        }
    if book_id in retired_ids and not unretire:
        errors.append("book is retired; pass --unretire after reviewing its evidence")
    if errors:
        return {
            "ok": False,
            "errors": errors,
            "book_id": book_id,
            "would_write": False,
            "confirmed": confirmed,
            "scripts": script_count,
            "shots": shot_count,
        }

    next_active = list(active_ids)
    next_active.append(book_id)
    next_active.sort()
    next_retired = sorted(retired_ids - ({book_id} if unretire else set()))
    return {
        "ok": True,
        "errors": [],
        "book_id": book_id,
        "already_active": False,
        "would_write": confirmed,
        "requires_confirmation": not confirmed,
        "confirmed": confirmed,
        "scripts": script_count,
        "shots": shot_count,
        "next_active_book_ids": next_active,
        "next_retired_book_ids": next_retired,
    }


def build_batch_registration_plan(
    payload: dict[str, Any],
    *,
    candidates: list[dict[str, Any]],
    confirmed: bool,
    unretire: bool = False,
) -> dict[str, Any]:
    """Validate and plan several sample registrations as one atomic change.

    ``candidates`` is read-only evidence collected by the CLI.  No candidate
    can be promoted when another candidate fails validation, preventing a
    partially updated registry after a typo or stale project is encountered.
    """
    errors: list[str] = []
    active = payload.get("active_book_ids", []) if isinstance(payload, dict) else []
    retired = payload.get("retired_book_ids", []) if isinstance(payload, dict) else []
    active_ids = _parse_ids(active, "active_book_ids", errors)
    retired_list = _parse_ids(retired, "retired_book_ids", errors)
    retired_ids = set(retired_list)
    overlap = sorted(set(active_ids) & retired_ids)
    if overlap:
        errors.append(f"active and retired sets overlap: {overlap}")

    seen: set[int] = set()
    sample_plans: list[dict[str, Any]] = []
    next_active = set(active_ids)
    next_retired = set(retired_ids)
    for candidate in candidates:
        try:
            book_id = int(candidate.get("book_id"))
        except (TypeError, ValueError):
            book_id = 0
        if book_id in seen:
            errors.append(f"book {book_id} is listed more than once")
            continue
        seen.add(book_id)
        book_exists = bool(candidate.get("book_exists"))
        script_count = int(candidate.get("script_count", 0) or 0)
        shot_count = int(candidate.get("shot_count", 0) or 0)
        item_errors: list[str] = []
        if book_id <= 0:
            item_errors.append("book_id must be a positive integer")
        if not book_exists:
            item_errors.append(f"book {book_id} does not exist in the database")
        if script_count <= 0:
            item_errors.append(f"book {book_id} has no non-empty Script evidence")
        if shot_count <= 0:
            item_errors.append(f"book {book_id} has no StoryboardShot evidence")
        already_active = book_id in next_active
        if book_id in next_retired and not already_active and not unretire:
            item_errors.append("book is retired; pass --unretire after reviewing its evidence")
        errors.extend(item_errors)
        sample_plans.append({
            "book_id": book_id,
            "scripts": script_count,
            "shots": shot_count,
            "already_active": already_active,
            "errors": item_errors,
        })
        if not item_errors and not already_active:
            next_active.add(book_id)
            if unretire:
                next_retired.discard(book_id)

    changed = next_active != set(active_ids) or next_retired != retired_ids
    return {
        "ok": not errors,
        "errors": errors,
        "samples": sample_plans,
        "already_active": [item["book_id"] for item in sample_plans if item["already_active"]],
        "would_write": bool(confirmed and not errors and changed),
        "requires_confirmation": bool(not confirmed and not errors and changed),
        "confirmed": confirmed,
        "next_active_book_ids": sorted(next_active),
        "next_retired_book_ids": sorted(next_retired),
    }


def atomically_write_registry(path: Path, payload: dict[str, Any]) -> None:
    """Replace a registry atomically without leaving a partial JSON file."""
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{resolved.name}.", suffix=".tmp", dir=str(resolved.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, resolved)
    finally:
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Register an existing evidence-backed production sample.")
    parser.add_argument("--book-id", type=int, action="append", required=True, help="Book ID to register; repeat for an atomic batch.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--confirm", default="", help=f"Required to write: {CONFIRMATION}")
    parser.add_argument("--unretire", action="store_true", help="Allow an explicitly reviewed retired book to re-enter active samples.")
    args = parser.parse_args()

    try:
        payload = json.loads(args.registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [f"cannot read registry: {exc}"]}, ensure_ascii=False))
        return 1
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "errors": ["registry must be a JSON object"]}, ensure_ascii=False))
        return 1

    if not args.book_id:
        print(json.dumps({"ok": False, "errors": ["at least one --book-id is required"]}, ensure_ascii=False))
        return 1

    init_db()
    with Session() as session:
        requested_ids = [int(value) for value in args.book_id]
        existing_ids = {
            int(value)
            for value, in session.query(Book.id).filter(Book.id.in_(requested_ids)).all()
        }
        scripts_by_book: dict[int, int] = {}
        for book_id, in session.query(Script.book_id).filter(
            Script.book_id.in_(requested_ids), Script.content.is_not(None), Script.content != ""
        ).all():
            scripts_by_book[int(book_id)] = scripts_by_book.get(int(book_id), 0) + 1
        shots_by_book: dict[int, int] = {}
        for book_id, in session.query(StoryboardShot.book_id).filter(StoryboardShot.book_id.in_(requested_ids)).all():
            shots_by_book[int(book_id)] = shots_by_book.get(int(book_id), 0) + 1

    confirmed = args.confirm == CONFIRMATION
    candidates = [
        {
            "book_id": book_id,
            "book_exists": book_id in existing_ids,
            "script_count": scripts_by_book.get(book_id, 0),
            "shot_count": shots_by_book.get(book_id, 0),
        }
        for book_id in requested_ids
    ]
    plan = build_batch_registration_plan(
        payload,
        candidates=candidates,
        confirmed=confirmed,
        unretire=bool(args.unretire),
    )
    if plan.get("ok") and plan.get("would_write"):
        payload["active_book_ids"] = plan["next_active_book_ids"]
        payload["retired_book_ids"] = plan["next_retired_book_ids"]
        if isinstance(payload.get("retired"), dict):
            for book_id in requested_ids:
                payload["retired"].pop(str(book_id), None)
        atomically_write_registry(args.registry, payload)
        plan["written"] = True
    else:
        plan["written"] = False
    plan["registry"] = str(args.registry.expanduser().resolve())
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not plan.get("ok"):
        return 1
    if plan.get("requires_confirmation"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
