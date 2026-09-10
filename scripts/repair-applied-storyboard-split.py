"""Repair live relations after a split produced by an older server build.

The original split implementation only shifted ``storyboard_shots``.  This
one-off, idempotent repair shifts its live dependent records and marks both
new narrative units as requiring a fresh prompt compile.  It deliberately
does not edit TaskRun payloads: those are immutable execution audit records.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the repository package importable when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.server import _shift_storyboard_split_references, safe_json_loads
from models import AgentViolationLog, Session, StoryboardAcceptanceRecord, StoryboardPromptVersion, StoryboardShot


def _meta(raw: str | None) -> dict:
    value = safe_json_loads(raw) if raw else {}
    return value if isinstance(value, dict) else {}


def _is_repaired(shot: StoryboardShot) -> bool:
    return bool(_meta(shot.meta_info).get("split_reference_migration", {}).get("status") == "applied")


def _summary(session, book_id: int, episode: int, split_after: int) -> dict:
    return {
        "storyboard_shots": [row.shot_id for row in session.query(StoryboardShot).filter_by(book_id=book_id, episode=episode).order_by(StoryboardShot.shot_id)],
        "prompt_versions_to_shift": session.query(StoryboardPromptVersion).filter(
            StoryboardPromptVersion.book_id == book_id,
            StoryboardPromptVersion.episode == episode,
            StoryboardPromptVersion.shot_id > split_after,
        ).count(),
        "acceptance_records_to_shift": session.query(StoryboardAcceptanceRecord).filter(
            StoryboardAcceptanceRecord.book_id == book_id,
            StoryboardAcceptanceRecord.episode == episode,
            StoryboardAcceptanceRecord.shot_id > split_after,
        ).count(),
        "violation_logs_to_shift": session.query(AgentViolationLog).filter(
            AgentViolationLog.book_id == book_id,
            AgentViolationLog.episode == episode,
            AgentViolationLog.shot_id > split_after,
        ).count(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair dependent data after an already-applied storyboard split")
    parser.add_argument("--book-id", type=int, required=True)
    parser.add_argument("--episode", type=int, required=True)
    parser.add_argument("--split-after-shot", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="Commit the repair. Without this flag the command is read-only.")
    args = parser.parse_args()

    with Session() as session:
        source = session.query(StoryboardShot).filter_by(
            book_id=args.book_id, episode=args.episode, shot_id=args.split_after_shot
        ).first()
        created = session.query(StoryboardShot).filter_by(
            book_id=args.book_id, episode=args.episode, shot_id=args.split_after_shot + 1
        ).first()
        if not source or not created:
            raise SystemExit("The expected source and newly-created split shots were not found; no changes were made.")

        if _is_repaired(source) or _is_repaired(created):
            print(json.dumps({"status": "already_repaired", "book_id": args.book_id, "episode": args.episode}, ensure_ascii=False))
            return 0

        plan = _summary(session, args.book_id, args.episode, args.split_after_shot)
        plan.update({
            "book_id": args.book_id,
            "episode": args.episode,
            "split_after_shot": args.split_after_shot,
            "created_shot": args.split_after_shot + 1,
            "mode": "apply" if args.apply else "dry-run",
        })
        if not args.apply:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0

        _shift_storyboard_split_references(
            session,
            book_id=args.book_id,
            episode=args.episode,
            split_after_shot_id=args.split_after_shot,
        )
        for shot in (source, created):
            meta_info = _meta(shot.meta_info)
            compiler = meta_info.get("prompt_compiler", {}) if isinstance(meta_info.get("prompt_compiler", {}), dict) else {}
            compiler.update({
                "latest_version": None,
                "compile_reason": "split-reference-migration-recompile-required",
                "recompile_required": True,
                "locked": False,
                "locked_version": None,
            })
            meta_info["prompt_compiler"] = compiler
            meta_info["split_reference_migration"] = {
                "status": "applied",
                "split_after_shot": args.split_after_shot,
                "note": "Live relations were shifted; pre-split prompt versions remain audit-only until recompile.",
            }
            shot.visual_prompt_static = ""
            shot.visual_prompt_motion = ""
            shot.visual_prompt_final = ""
            shot.meta_info = json.dumps(meta_info, ensure_ascii=False)

        session.commit()
        plan["status"] = "applied"
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
