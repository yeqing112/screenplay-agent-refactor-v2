"""Read-only audit of layered scene semantic lint on real project data.

The command deliberately does not mutate assets, references, prompts, or
versions. It samples the current database and reports warning/blocking rates
so the team can calibrate release gates from evidence instead of intuition.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.server import _build_scene_semantic_layers, _lint_scene_asset_layers
from models import Book, Session, VisualLocation, init_db


def audit(book_ids: list[int] | None = None, sample_limit: int = 20) -> dict:
    init_db()
    with Session() as session:
        query = session.query(VisualLocation).order_by(VisualLocation.book_id.asc(), VisualLocation.id.asc())
        if book_ids:
            query = query.filter(VisualLocation.book_id.in_(book_ids))
        rows = query.all()
        books = {book.id: book.title for book in session.query(Book).all()}

    counts = Counter()
    book_stats: dict[str, dict] = {}
    samples: list[dict] = []
    for row in rows:
        layers = _build_scene_semantic_layers(row)
        lint = _lint_scene_asset_layers(layers)
        key = str(row.book_id)
        stats = book_stats.setdefault(key, {"book_id": row.book_id, "book_title": books.get(row.book_id, ""), "assets": 0, "pass": 0, "warning": 0, "blocked": 0, "warning_codes": {}})
        stats["assets"] += 1
        status = str(lint.get("status") or "pass")
        stats[status] = stats.get(status, 0) + 1
        counts[status] += 1
        for warning in lint.get("warnings", []):
            code = str(warning.get("code") or "unknown")
            counts[f"warning:{code}"] += 1
            stats["warning_codes"][code] = stats["warning_codes"].get(code, 0) + 1
        if len(samples) < sample_limit and (lint.get("warnings") or lint.get("blocking")):
            samples.append({"book_id": row.book_id, "book_title": books.get(row.book_id, ""), "asset_id": row.id, "name": row.name, "lint": lint, "sources": layers.get("source", {})})

    return {
        "mode": "readonly-scene-semantic-lint-audit",
        "generated_at": datetime.utcnow().isoformat(),
        "filters": {"book_ids": book_ids or [], "sample_limit": sample_limit},
        "summary": {"assets": len(rows), "books": len(book_stats), "pass": counts["pass"], "warning": counts["warning"], "blocked": counts["blocked"], "warning_codes": {key.split(":", 1)[1]: value for key, value in counts.items() if key.startswith("warning:")}},
        "books": list(book_stats.values()),
        "samples": samples,
        "writes_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-id", action="append", type=int, dest="book_ids")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = audit(args.book_ids, max(0, args.sample_limit))
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
        print(f"[scene-semantic-lint] report written: {args.out}")
    else:
        print(output)
    print(f"[scene-semantic-lint] assets={report['summary']['assets']} warning={report['summary']['warning']} blocked={report['summary']['blocked']} writes_performed={report['writes_performed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

