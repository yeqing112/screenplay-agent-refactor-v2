"""Controlled deterministic backfill for already-passing storyboard shots.

It never calls an LLM or changes director language/prompt text. By default it
only prints a plan. `--apply` is intentionally required for database writes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import safe_json_loads
from core.shot_executability import validate_shot_executability
from models import Session, StoryboardShot, init_db

_CORE_ACTION_SPLIT = re.compile(r"[。！？；]|随后|然后|接着|再将|再把|并将|并把|同时")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _beats(meta: dict[str, Any], action_process: str) -> list[dict[str, Any]]:
    structured = _as_dict(meta.get("structured_shot"))
    compiler = _as_dict(meta.get("prompt_compiler"))
    context = _as_dict(compiler.get("prompt_compile_context"))
    for candidate in (context.get("action_beats"), structured.get("action_beats")):
        if isinstance(candidate, list):
            beats = [item for item in candidate if isinstance(item, dict)]
            if beats:
                return beats
    text = str(action_process or "").strip()
    return [{"sequence": 1, "description": text}] if text else []


def _core_action(beats: list[dict[str, Any]], action_process: str) -> str:
    # Legacy rows often have one synthetic beat containing the whole action
    # chain, so derive the unique core action from the source prose first.
    first_unit = next((part.strip() for part in _CORE_ACTION_SPLIT.split(str(action_process or "")) if part.strip()), "")
    if first_unit:
        return first_unit
    for beat in beats:
        value = str(beat.get("description") or beat.get("action") or beat.get("text") or "").strip()
        if value:
            return value
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book-id", type=int, default=75)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--include-nonpass", action="store_true", help="Also persist warning/blocked findings as review-only metadata.")
    parser.add_argument("--revalidate-final-motion", action="store_true", help="Recompute existing results against the final video motion prompt.")
    args = parser.parse_args()
    init_db()
    changed: list[dict[str, Any]] = []
    with Session() as session:
        rows = session.query(StoryboardShot).filter(StoryboardShot.book_id == args.book_id).order_by(StoryboardShot.episode, StoryboardShot.shot_id).all()
        for row in rows:
            if len(changed) >= max(1, args.limit):
                break
            meta = safe_json_loads(row.meta_info, {}) if row.meta_info else {}
            meta = _as_dict(meta)
            beats = _beats(meta, str(row.action_process or ""))
            result = validate_shot_executability(
                duration=row.duration,
                action_process=str(row.action_process or ""),
                action_beats=beats,
                camera_movement=str(row.camera_movement or "static"),
                start_state=str(row.start_state or ""),
                end_state=str(row.end_state or ""),
                motion_prompt=str(row.visual_prompt_motion or ""),
            )
            if result["status"] != "pass" and not args.include_nonpass:
                continue
            structured = _as_dict(meta.get("structured_shot"))
            compiler = _as_dict(meta.get("prompt_compiler"))
            context = _as_dict(compiler.get("prompt_compile_context"))
            if context.get("executability") and not args.revalidate_final_motion:
                continue
            core_action = _core_action(beats, str(row.action_process or ""))
            payload = {
                "core_action": core_action,
                "action_beats": beats,
                "continuity_in": str(row.start_state or "").strip(),
                "continuity_out": str(row.end_state or "").strip(),
                "executability": result,
            }
            changed.append({"episode": row.episode, "shot_id": row.shot_id, "status": result["status"], "core_action": core_action})
            if args.apply:
                structured.update(payload)
                context.update(payload)
                shot_ir = _as_dict(context.get("shot_ir"))
                shot_ir.update(payload)
                context["shot_ir"] = shot_ir
                compiler["prompt_compile_context"] = context
                meta["structured_shot"] = structured
                meta["prompt_compiler"] = compiler
                migrations = meta.get("executability_backfills", [])
                if not isinstance(migrations, list):
                    migrations = []
                migrations.append({
                    "at": datetime.now(timezone.utc).isoformat(),
                    "source": "deterministic-final-motion-revalidation-v1" if args.revalidate_final_motion else "deterministic-executability-backfill-v1",
                    "status": result["status"],
                })
                meta["executability_backfills"] = migrations[-5:]
                row.meta_info = json.dumps(meta, ensure_ascii=False)
                row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if args.apply:
            session.commit()
    print(json.dumps({"book_id": args.book_id, "apply": args.apply, "include_nonpass": args.include_nonpass, "revalidate_final_motion": args.revalidate_final_motion, "eligible_shots": changed, "count": len(changed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
