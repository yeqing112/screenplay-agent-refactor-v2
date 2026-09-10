"""Deterministic, no-LLM preservation backfill for storyboard prompts.

The compiler's non-lossy preservation pass (:func:`_preserve_locked_asset_anchor_contract`)
restores a child character's authoritative gender (and any dropped locked-resource
anchor) into the static prompt when the stored prompt predates that pass.  This
script applies the same deterministic rule to every storyboard shot that still
carries a missing authority fact, so the zero-error production gate stops raising
``character_gender_authority`` blocking errors.

It is intentionally generic: it derives inputs entirely from the current shot
graph (bound_assets) and never calls a model, never creates a media task, and
never changes prose that is already correct.  Run without ``--apply`` for a
dry-run manifest, then with ``--apply`` to persist.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.server import _build_storyboard_prompt_compile_evidence, _preserve_locked_asset_anchor_contract
from api.server import _gender_authority_presence
from models import Session, StoryboardPromptVersion, StoryboardShot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="persist changes (default is dry-run)")
    parser.add_argument("--out", default="artifacts/storyboard-gender-backfill-manifest.json", help="manifest output path")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    changes: list[dict] = []
    conflicts: list[dict] = []
    scanned = 0

    with Session() as s:
        shots = s.query(StoryboardShot).order_by(StoryboardShot.book_id, StoryboardShot.episode, StoryboardShot.shot_id).all()
        for shot in shots:
            scanned += 1
            try:
                context, _compiler, _packet = _build_storyboard_prompt_compile_evidence(shot.book_id, shot)
            except Exception as exc:  # noqa: BLE001 - record and continue
                changes.append({"book_id": shot.book_id, "episode": shot.episode, "shot_id": shot.shot_id, "error": str(exc)[:200]})
                continue
            bound_assets = context.get("bound_assets", []) if isinstance(context.get("bound_assets", []), list) else []
            used_assets = [item for item in bound_assets if isinstance(item, dict)]
            original_static = str(shot.visual_prompt_static or "").strip()
            if not original_static:
                continue
            authority_genders = []
            any_conflict = False
            for item in bound_assets:
                if not isinstance(item, dict) or str(item.get("asset_type") or "").strip() != "character":
                    continue
                g = str(item.get("gender") or "").strip()
                if g in {"", "人物", "未识别", "未知"} or g in authority_genders:
                    continue
                authority_genders.append(g)
                if _gender_authority_presence(g, original_static) == "conflict":
                    any_conflict = True
            if any_conflict:
                # A contradictory gender assertion cannot be safely auto-fixed
                # without risk of mangling prose.  Route these to human/QA review.
                conflicts.append({
                    "book_id": shot.book_id,
                    "episode": shot.episode,
                    "shot_id": shot.shot_id,
                    "scene_name": str(shot.scene_name or "").strip(),
                    "authority_genders": authority_genders,
                    "action": "need_qa_gender_correction",
                })
                continue
            preserved = _preserve_locked_asset_anchor_contract(original_static, used_assets, bound_assets)
            if preserved == original_static:
                continue
            record = {
                "book_id": shot.book_id,
                "episode": shot.episode,
                "shot_id": shot.shot_id,
                "scene_name": str(shot.scene_name or "").strip(),
                "authority_genders": authority_genders,
                "original_static": original_static,
                "new_static": preserved,
            }
            changes.append(record)
            if args.apply:
                # Keep the version trail coherent with a deterministic version row,
                # mirroring the confirm path but without any LLM call.
                latest = (
                    s.query(StoryboardPromptVersion)
                    .filter_by(book_id=shot.book_id, episode=shot.episode, shot_id=shot.shot_id)
                    .order_by(StoryboardPromptVersion.version.desc())
                    .first()
                )
                version_no = (latest.version if latest else 0) + 1
                meta = safe_json_loads(shot.meta_info, {}) if shot.meta_info else {}
                meta = meta if isinstance(meta, dict) else {}
                version = StoryboardPromptVersion(
                    book_id=shot.book_id,
                    episode=shot.episode,
                    shot_id=shot.shot_id,
                    version=version_no,
                    compile_reason="deterministic-gender-preservation-backfill",
                    prompt_static=preserved,
                    prompt_motion=str(shot.visual_prompt_motion or "").strip(),
                    negative_prompt=str(shot.visual_prompt_final or "").strip(),
                    meta_info=json.dumps({"backfill": {"kind": "gender_preservation", "applied_at": datetime.utcnow().isoformat()}}, ensure_ascii=False),
                )
                s.add(version)
                shot.visual_prompt_static = preserved
                compiler = meta.get("prompt_compiler", {}) if isinstance(meta.get("prompt_compiler"), dict) else {}
                compiler["latest_version"] = version_no
                compiler["compile_reason"] = "deterministic-gender-preservation-backfill"
                meta["prompt_compiler"] = compiler
                shot.meta_info = json.dumps(meta, ensure_ascii=False)
                shot.updated_at = datetime.utcnow()

        if args.apply:
            s.commit()

    out_path.write_text(json.dumps({"scanned": scanned, "applied_changes": len(changes), "conflicts": len(conflicts), "applied": bool(args.apply), "changes": changes, "conflicts": conflicts}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[gender-backfill] scanned={scanned} changed={len(changes)} applied={args.apply}")
    for record in changes:
        if "error" in record:
            print(f"  book {record['book_id']}/{record['episode']}/{record['shot_id']} ERROR {record['error']}")
        else:
            print(f"  APPLY book {record['book_id']}/{record['episode']}/{record['shot_id']} ({record['scene_name']}) authority={record.get('authority_genders')}")
    for record in conflicts:
        print(f"  QA book {record['book_id']}/{record['episode']}/{record['shot_id']} ({record['scene_name']}) authority={record.get('authority_genders')} need_qa_gender_correction")
    return 0


def safe_json_loads(text, fallback):
    try:
        return json.loads(text) if text else fallback
    except (TypeError, ValueError):
        return fallback


if __name__ == "__main__":
    raise SystemExit(main())
