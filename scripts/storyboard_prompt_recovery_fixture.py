import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.server import (
    _build_storyboard_prompt_version_audit,
    _build_storyboard_prompt_version_payloads,
    _coerce_storyboard_shot_id,
    _create_storyboard_prompt_rollback,
    _recommend_storyboard_restore_version,
)
from models import Session, StoryboardPromptVersion, StoryboardShot, init_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage a repeatable storyboard prompt recovery acceptance fixture.",
    )
    parser.add_argument("mode", choices=["status", "degrade", "restore"])
    parser.add_argument("--book-id", type=int, required=True)
    parser.add_argument("--episode", type=int, required=True)
    parser.add_argument("--shot-id", required=True)
    parser.add_argument("--restore-version", type=int, default=None)
    parser.add_argument("--reason", default="")
    parser.add_argument(
        "--snapshot-dir",
        default="artifacts/prompt-recovery-fixtures",
        help="Directory used to store before/after snapshots.",
    )
    return parser.parse_args()


def load_shot(session, book_id: int, episode: int, shot_id: int) -> StoryboardShot:
    shot = (
        session.query(StoryboardShot)
        .filter(
            StoryboardShot.book_id == book_id,
            StoryboardShot.episode == episode,
            StoryboardShot.shot_id == shot_id,
        )
        .first()
    )
    if not shot:
        raise SystemExit(f"Storyboard shot not found: book={book_id}, episode={episode}, shot={shot_id}")
    return shot


def json_load(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def ensure_snapshot_dir(path_str: str) -> Path:
    path = Path(path_str)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_snapshot(snapshot_dir: Path, name: str, payload: dict) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = snapshot_dir / f"{name}-{timestamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def summarize_status(version_payloads: list[dict], current_version: int | None) -> dict:
    recommendation = _recommend_storyboard_restore_version(version_payloads, current_version)
    current = next((item for item in version_payloads if item.get("version") == current_version), None)
    return {
        "current_version": current_version,
        "current_audit": current.get("version_audit") if isinstance(current, dict) else None,
        "recommended_restore_version": recommendation,
        "versions": [
            {
                "id": item.get("id"),
                "version": item.get("version"),
                "compile_reason": item.get("compile_reason"),
                "is_current": item.get("is_current"),
                "version_audit": item.get("version_audit"),
            }
            for item in version_payloads
        ],
    }


def build_scene_only_degraded_version(source: dict, shot: StoryboardShot) -> tuple[dict, str, str]:
    degraded = copy.deepcopy(source)
    used_assets = degraded.get("used_assets", []) if isinstance(degraded.get("used_assets", []), list) else []
    prompt_context = (
        degraded.get("prompt_compile_context", {})
        if isinstance(degraded.get("prompt_compile_context", {}), dict)
        else {}
    )
    bound_assets = prompt_context.get("bound_assets", []) if isinstance(prompt_context.get("bound_assets", []), list) else []
    scene_binding = (
        prompt_context.get("asset_bindings", {}).get("scene", {})
        if isinstance(prompt_context.get("asset_bindings", {}), dict)
        else {}
    )

    scene_asset = next(
        (
            item
            for item in used_assets
            if isinstance(item, dict) and str(item.get("asset_type") or "").strip() == "scene"
        ),
        None,
    )
    if not scene_asset:
        scene_asset = next(
            (
                item
                for item in bound_assets
                if isinstance(item, dict) and str(item.get("asset_type") or "").strip() == "scene"
            ),
            None,
        )
    if not scene_asset and isinstance(scene_binding, dict) and scene_binding:
        scene_asset = {
            "asset_type": "scene",
            "asset_id": str(scene_binding.get("asset_id") or "").strip(),
            "asset_name": str(scene_binding.get("asset_name") or shot.scene_name or "").strip(),
            "reference_token": str(scene_binding.get("reference_token") or "").strip(),
            "reference_status": str(scene_binding.get("reference_status") or "selected").strip(),
            "has_reference": True,
            "locked_reference": bool(scene_binding.get("locked_reference")),
            "image_url": str(scene_binding.get("image_url") or "").strip(),
            "reference_asset_id": str(scene_binding.get("reference_asset_id") or "").strip(),
        }

    degraded["used_assets"] = [scene_asset] if scene_asset else []

    reference_images = degraded.get("reference_images", []) if isinstance(degraded.get("reference_images", []), list) else []
    scene_images = [
        item for item in reference_images
        if isinstance(item, dict) and str(item.get("asset_type") or "").strip() == "scene"
    ]
    degraded["reference_images"] = scene_images[:1] if scene_images else reference_images[:1]
    degraded["reference_asset_ids"] = [
        str(item.get("reference_asset_id") or item.get("id") or "").strip()
        for item in degraded["reference_images"]
        if isinstance(item, dict) and str(item.get("reference_asset_id") or item.get("id") or "").strip()
    ]
    degraded["compiler_warnings"] = ["fixture_scene_only_recovery_validation"]
    degraded["compiler_diagnostics"] = {}

    scene_name = (
        str((scene_asset or {}).get("asset_name") or "").strip()
        or str(scene_binding.get("asset_name") or "").strip()
        or str(shot.scene_name or "").strip()
        or "scene"
    )
    scene_token = str((scene_asset or {}).get("reference_token") or scene_binding.get("reference_token") or "").strip()
    scene_ref = f" {scene_token}" if scene_token else ""
    prompt_static = f"{scene_name}，仅保留场景参考{scene_ref}，人物与关键道具引用缺失的验收样本。"
    prompt_motion = f"镜头缓慢推进至{scene_name}内部，仅保留场景连续性，不带入人物和关键道具动作。"
    return degraded, prompt_static, prompt_motion


def cmd_status(session, args: argparse.Namespace) -> dict:
    shot_id = _coerce_storyboard_shot_id(args.shot_id)
    shot = load_shot(session, args.book_id, args.episode, shot_id)
    shot_meta = json_load(shot.meta_info)
    prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
    version_payloads = _build_storyboard_prompt_version_payloads(
        session,
        args.book_id,
        shot,
        prompt_compiler_meta.get("latest_version"),
        prompt_compiler_meta.get("locked_version"),
    )
    return summarize_status(version_payloads, prompt_compiler_meta.get("latest_version"))


def cmd_degrade(session, args: argparse.Namespace, snapshot_dir: Path) -> dict:
    shot_id = _coerce_storyboard_shot_id(args.shot_id)
    shot = load_shot(session, args.book_id, args.episode, shot_id)
    latest = (
        session.query(StoryboardPromptVersion)
        .filter(
            StoryboardPromptVersion.book_id == args.book_id,
            StoryboardPromptVersion.episode == args.episode,
            StoryboardPromptVersion.shot_id == shot_id,
        )
        .order_by(StoryboardPromptVersion.version.desc())
        .first()
    )
    if not latest:
        raise SystemExit("No prompt version found for this shot. Compile prompts once before creating a recovery fixture.")

    shot_meta = json_load(shot.meta_info)
    prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
    latest_meta = json_load(latest.meta_info)

    write_snapshot(
        snapshot_dir,
        f"book-{args.book_id}-ep-{args.episode}-shot-{shot_id}-before-degrade",
        {
            "shot": {
                "book_id": args.book_id,
                "episode": args.episode,
                "shot_id": shot_id,
                "visual_prompt_static": shot.visual_prompt_static,
                "visual_prompt_motion": shot.visual_prompt_motion,
                "visual_prompt_final": shot.visual_prompt_final,
                "meta_info": shot_meta,
            },
            "latest_version": {
                "id": latest.id,
                "version": latest.version,
                "compile_reason": latest.compile_reason,
                "meta_info": latest_meta,
            },
        },
    )

    degraded_meta, prompt_static, prompt_motion = build_scene_only_degraded_version(latest_meta, shot)
    latest_version = int(latest.version or 0)
    degraded_version = latest_version + 1
    compile_reason = str(args.reason or "").strip() or f"acceptance-scene-only-v{latest_version}"
    degraded_row = StoryboardPromptVersion(
        book_id=args.book_id,
        episode=args.episode,
        shot_id=shot_id,
        version=degraded_version,
        compile_reason=compile_reason,
        prompt_static=prompt_static,
        prompt_motion=prompt_motion,
        negative_prompt=latest.negative_prompt,
        meta_info=json.dumps(degraded_meta, ensure_ascii=False),
    )
    session.add(degraded_row)

    prompt_compiler_meta["latest_version"] = degraded_version
    prompt_compiler_meta["compile_reason"] = compile_reason
    prompt_compiler_meta["negative_prompt"] = latest.negative_prompt
    prompt_compiler_meta["used_assets"] = degraded_meta.get("used_assets", [])
    prompt_compiler_meta["reference_images"] = degraded_meta.get("reference_images", [])
    prompt_compiler_meta["reference_asset_ids"] = degraded_meta.get("reference_asset_ids", [])
    prompt_compiler_meta["compiler_warnings"] = degraded_meta.get("compiler_warnings", [])
    prompt_compiler_meta["compiler_diagnostics"] = degraded_meta.get("compiler_diagnostics", {})
    prompt_compiler_meta["prompt_compile_context"] = degraded_meta.get("prompt_compile_context", {})
    prompt_compiler_meta["locked_reference_summary"] = degraded_meta.get("locked_reference_summary", {})

    shot.visual_prompt_static = prompt_static
    shot.visual_prompt_motion = prompt_motion
    shot.visual_prompt_final = latest.negative_prompt
    shot_meta["prompt_compiler"] = prompt_compiler_meta
    shot.meta_info = json.dumps(shot_meta, ensure_ascii=False)
    session.commit()

    version_payloads = _build_storyboard_prompt_version_payloads(
        session,
        args.book_id,
        shot,
        degraded_version,
        prompt_compiler_meta.get("locked_version"),
    )
    return {
        "action": "degrade",
        "book_id": args.book_id,
        "episode": args.episode,
        "shot_id": shot_id,
        "new_version": degraded_version,
        "current_audit": _build_storyboard_prompt_version_audit(degraded_meta),
        "recommended_restore_version": _recommend_storyboard_restore_version(version_payloads, degraded_version),
    }


def cmd_restore(session, args: argparse.Namespace, snapshot_dir: Path) -> dict:
    shot_id = _coerce_storyboard_shot_id(args.shot_id)
    shot = load_shot(session, args.book_id, args.episode, shot_id)
    shot_meta = json_load(shot.meta_info)
    prompt_compiler_meta = shot_meta.get("prompt_compiler", {}) if isinstance(shot_meta.get("prompt_compiler", {}), dict) else {}
    version_payloads = _build_storyboard_prompt_version_payloads(
        session,
        args.book_id,
        shot,
        prompt_compiler_meta.get("latest_version"),
        prompt_compiler_meta.get("locked_version"),
    )
    recommendation = _recommend_storyboard_restore_version(version_payloads, prompt_compiler_meta.get("latest_version"))

    target_version = args.restore_version
    if target_version is None:
        if not recommendation:
            raise SystemExit("No recommended restore version is available. Pass --restore-version explicitly.")
        target_version = int(recommendation.get("version") or 0)

    target = (
        session.query(StoryboardPromptVersion)
        .filter(
            StoryboardPromptVersion.book_id == args.book_id,
            StoryboardPromptVersion.episode == args.episode,
            StoryboardPromptVersion.shot_id == shot_id,
            StoryboardPromptVersion.version == target_version,
        )
        .first()
    )
    if not target:
        raise SystemExit(f"Prompt version not found: version={target_version}")

    write_snapshot(
        snapshot_dir,
        f"book-{args.book_id}-ep-{args.episode}-shot-{shot_id}-before-restore",
        {
            "shot": {
                "book_id": args.book_id,
                "episode": args.episode,
                "shot_id": shot_id,
                "visual_prompt_static": shot.visual_prompt_static,
                "visual_prompt_motion": shot.visual_prompt_motion,
                "visual_prompt_final": shot.visual_prompt_final,
                "meta_info": shot_meta,
            },
            "target_version": {
                "id": target.id,
                "version": target.version,
                "compile_reason": target.compile_reason,
                "meta_info": json_load(target.meta_info),
            },
        },
    )

    reason = str(args.reason or "").strip() or "fixture-restore"
    result = _create_storyboard_prompt_rollback(session, shot, target, SimpleNamespace(reason=reason))
    result["action"] = "restore"
    result["recommended_restore_version"] = recommendation
    return result


def main() -> None:
    args = parse_args()
    snapshot_dir = ensure_snapshot_dir(args.snapshot_dir)
    init_db()

    with Session() as session:
        if args.mode == "status":
            result = cmd_status(session, args)
        elif args.mode == "degrade":
            result = cmd_degrade(session, args, snapshot_dir)
        else:
            result = cmd_restore(session, args, snapshot_dir)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
