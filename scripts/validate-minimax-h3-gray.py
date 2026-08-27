"""Safe gray validation for MiniMax H3 machine-prompt video submission.

Default behavior is dry-run only:

- reads one real storyboard shot
- loads its MiniMax H3 machine-prompt export through the backend read-only API
- checks video model/provider readiness
- resolves the adopted first frame when available
- writes a JSON/Markdown preflight report

It does not register a task, call MiniMax, or write storyboard assets unless all
real-run gates are explicitly enabled:

- CLI flag: --allow-real
- MINIMAX_H3_GRAY_REAL=1
- MINIMAX_H3_GRAY_CONFIRM=CONFIRM_MINIMAX_H3_SUBMIT
- MINIMAX_H3_GRAY_WHITELIST contains the exact book_id:episode:shot_id target

Real mode intentionally goes through the same backend task endpoints used by
the formal workspace so task persistence and video asset writeback are tested
as a production-like path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.generation_adapters import ModelProfileError, resolve_generation_profile
from api.server import app
from core import safe_json_loads
from models import Book, Session, StoryboardShot, init_db


REPORT_PREFIX = "minimax-h3-gray"
CONFIRMATION_TOKEN = "CONFIRM_MINIMAX_H3_SUBMIT"


def log(message: str) -> None:
    print(f"[minimax-h3-gray] {message}")


def timestamp_slug() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def default_artifact_path(suffix: str) -> Path:
    return ROOT_DIR / "artifacts" / f"{REPORT_PREFIX}-{timestamp_slug()}.{suffix}"


def target_key(book_id: int, episode: int, shot_id: str | int) -> str:
    return f"{int(book_id)}:{int(episode)}:{int(shot_id)}"


def parse_whitelist(raw: str) -> set[str]:
    entries: set[str] = set()
    for token in str(raw or "").split(","):
        parts = [part.strip() for part in token.strip().split(":")]
        if not any(parts):
            continue
        if len(parts) != 3 or not all(parts):
            raise RuntimeError("MINIMAX_H3_GRAY_WHITELIST must use comma-separated book_id:episode:shot_id entries.")
        entries.add(target_key(int(parts[0]), int(parts[1]), int(parts[2])))
    return entries


def load_storyboard_target(book_id: int, episode: int, shot_id: int) -> tuple[Book, StoryboardShot]:
    with Session() as session:
        book = session.query(Book).filter(Book.id == book_id).first()
        shot = (
            session.query(StoryboardShot)
            .filter(
                StoryboardShot.book_id == book_id,
                StoryboardShot.episode == episode,
                StoryboardShot.shot_id == shot_id,
            )
            .first()
        )
        if not book or not shot:
            raise RuntimeError(f"Storyboard target not found: {target_key(book_id, episode, shot_id)}")
        # Detach scalar fields used by report after Session closes.
        session.expunge(book)
        session.expunge(shot)
        return book, shot


def find_first_frame(shot: StoryboardShot, requested_asset_id: str = "") -> dict[str, Any] | None:
    asset_links = safe_json_loads(shot.asset_links, {}) if shot.asset_links else {}
    if not isinstance(asset_links, dict):
        asset_links = {}
    images = asset_links.get("images")
    if not isinstance(images, list):
        images = []
    requested = str(requested_asset_id or "").strip()
    if requested:
        for item in images:
            if isinstance(item, dict) and str(item.get("id") or "").strip() == requested:
                return item
        return None
    for item in reversed(images):
        if isinstance(item, dict) and bool(item.get("adopted")):
            return item
    return None


def load_machine_prompt_export(client: TestClient, book_id: int, episode: int, shot_id: int) -> dict[str, Any]:
    response = client.get(f"/api/books/{book_id}/storyboard/{episode}/{shot_id}/machine-prompt-export?target_model=minimax-h3")
    if response.status_code != 200:
        raise RuntimeError(f"Machine prompt export preview failed: HTTP {response.status_code} {response.text}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Machine prompt export preview did not return a JSON object.")
    return payload


def h3_fields(export_payload: dict[str, Any]) -> dict[str, Any]:
    model_exports = export_payload.get("model_exports") if isinstance(export_payload.get("model_exports"), dict) else {}
    h3 = model_exports.get("minimax-h3") if isinstance(model_exports.get("minimax-h3"), dict) else {}
    fields = h3.get("fields") if isinstance(h3.get("fields"), dict) else {}
    return fields


def effective_video_profile(model_profile_id: str = "") -> tuple[dict[str, Any] | None, str]:
    try:
        profile = resolve_generation_profile("video", model_profile_id or None)
    except (ModelProfileError, ValueError) as exc:
        return None, str(exc)
    return profile, ""


def public_profile_summary(profile: dict[str, Any] | None, error: str = "") -> dict[str, Any]:
    if not profile:
        return {
            "ok": False,
            "error": error,
            "id": "",
            "name": "",
            "provider": "",
            "model_name": "",
            "base_url": "",
            "api_key_configured": False,
        }
    api_key = str(profile.get("api_key") or "").strip()
    return {
        "ok": True,
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or ""),
        "provider": str(profile.get("provider") or ""),
        "model_name": str(profile.get("model_name") or ""),
        "base_url": str(profile.get("base_url") or ""),
        "api_key_configured": bool(api_key and api_key != "sk-placeholder"),
        "enabled": bool(profile.get("enabled", True)),
    }


def build_preflight_report(args: argparse.Namespace, client: TestClient) -> dict[str, Any]:
    book, shot = load_storyboard_target(args.book_id, args.episode, args.shot_id)
    export_payload = load_machine_prompt_export(client, args.book_id, args.episode, args.shot_id)
    fields = h3_fields(export_payload)
    prompt = str(fields.get("integrated_multimodal_description") or "").strip()
    first_frame = find_first_frame(shot, args.first_frame_asset_id) if args.use_first_frame else None
    first_frame_url = ""
    if isinstance(first_frame, dict):
        first_frame_url = str(first_frame.get("uri") or first_frame.get("previewUrl") or "").strip()

    profile, profile_error = effective_video_profile(args.model_profile_id)
    profile_summary = public_profile_summary(profile, profile_error)

    blockers: list[str] = []
    warnings: list[str] = []
    if not prompt:
        blockers.append("missing_h3_integrated_multimodal_description")
    if len(prompt) > 7000:
        blockers.append("h3_prompt_exceeds_7000_chars")
    if not profile:
        blockers.append("missing_video_model_profile")
    elif profile_summary["provider"] != "minimax-h3-async":
        blockers.append("video_profile_is_not_minimax_h3_async")
    elif not profile_summary["api_key_configured"]:
        blockers.append("minimax_h3_api_key_missing")
    if profile and not str(profile.get("base_url") or "").strip():
        blockers.append("minimax_h3_base_url_missing")
    if args.use_first_frame and not first_frame:
        warnings.append("no_adopted_first_frame_found_will_use_text_to_video")
    elif args.use_first_frame and not first_frame_url:
        blockers.append("selected_first_frame_has_no_url")

    whitelist = parse_whitelist(os.environ.get("MINIMAX_H3_GRAY_WHITELIST", ""))
    current_target = target_key(args.book_id, args.episode, args.shot_id)
    safety = {
        "allow_real_cli": bool(args.allow_real),
        "real_env_enabled": os.environ.get("MINIMAX_H3_GRAY_REAL") == "1",
        "confirmation_matches": os.environ.get("MINIMAX_H3_GRAY_CONFIRM", "").strip() == CONFIRMATION_TOKEN,
        "target": current_target,
        "whitelist": sorted(whitelist),
        "target_whitelisted": current_target in whitelist,
        "required_confirmation_token": CONFIRMATION_TOKEN,
    }
    safety["will_submit"] = bool(
        safety["allow_real_cli"]
        and safety["real_env_enabled"]
        and safety["confirmation_matches"]
        and safety["target_whitelisted"]
        and not blockers
    )

    return {
        "mode": "real-submit" if safety["will_submit"] else "dry-run-preflight",
        "created_at": datetime.utcnow().isoformat(),
        "target": {
            "book_id": args.book_id,
            "book_title": str(book.title or ""),
            "episode": args.episode,
            "shot_id": args.shot_id,
            "scene_name": str(shot.scene_name or ""),
        },
        "submission": {
            "target_model": "minimax-h3",
            "prompt_length": len(prompt),
            "prompt_preview": prompt[:800],
            "duration_seconds": args.duration_seconds,
            "aspect_ratio": args.aspect_ratio,
            "use_first_frame": bool(args.use_first_frame),
            "first_frame_asset_id": str(first_frame.get("id") or "") if isinstance(first_frame, dict) else "",
            "first_frame_url": first_frame_url,
            "task_mode": "image_to_video" if first_frame_url else "text_to_video",
            "api_submission": True,
            "actual_provider_submission": bool(safety["will_submit"]),
        },
        "profile": profile_summary,
        "source_layers": export_payload.get("source_layers") if isinstance(export_payload.get("source_layers"), dict) else {},
        "readiness": {
            "ready_for_real_submit": not blockers,
            "blockers": blockers,
            "warnings": warnings,
        },
        "safety_gate": safety,
        "real_run_command": [
            '$env:MINIMAX_H3_GRAY_REAL="1"',
            f'$env:MINIMAX_H3_GRAY_CONFIRM="{CONFIRMATION_TOKEN}"',
            f'$env:MINIMAX_H3_GRAY_WHITELIST="{current_target}"',
            f"python scripts/validate-minimax-h3-gray.py --book-id {args.book_id} --episode {args.episode} --shot-id {args.shot_id} --allow-real",
        ],
    }


def submit_real(client: TestClient, args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    target = report["target"]
    log("Registering machine prompt API submission task...")
    export_payload = load_machine_prompt_export(client, args.book_id, args.episode, args.shot_id)
    register = client.post(
        f"/api/books/{args.book_id}/storyboard/{args.episode}/{args.shot_id}/machine-prompt-api-submissions",
        json={
            "targetModel": "minimax-h3",
            "exportChannel": "api",
            "operatorName": "minimax-h3-gray-script",
            "submissionMode": "task_intent_only",
            "hasManualExportDraft": False,
            "exportPayload": export_payload,
            "notes": "MiniMax H3 gray validation: registered before confirmed provider submit.",
        },
    )
    if register.status_code != 200:
        raise RuntimeError(f"Register API submission failed: HTTP {register.status_code} {register.text}")
    registered = register.json()
    task_id = str(registered.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("Register API submission did not return task_id.")

    log(f"Registered task {task_id}; submitting to MiniMax H3...")
    body: dict[str, Any] = {
        "confirmationToken": CONFIRMATION_TOKEN,
        "durationSeconds": args.duration_seconds,
        "aspectRatio": args.aspect_ratio,
        "useFirstFrame": bool(args.use_first_frame),
        "notes": "MiniMax H3 gray validation: confirmed real provider submission.",
    }
    if args.model_profile_id:
        body["modelProfileId"] = args.model_profile_id
    if args.first_frame_asset_id:
        body["firstFrameAssetId"] = args.first_frame_asset_id
    submit = client.post(f"/api/prototyping/tasks/{task_id}/submit-machine-prompt-provider", json=body)
    if submit.status_code != 200:
        raise RuntimeError(f"Confirmed provider submit failed for {task_id}: HTTP {submit.status_code} {submit.text}")
    submitted = submit.json()
    final_task = client.get(f"/api/prototyping/tasks/{task_id}")
    final_payload = final_task.json() if final_task.status_code == 200 else {"error": final_task.text}
    return {
        "task_id": task_id,
        "registered_response": registered,
        "submitted_response": submitted,
        "final_task": final_payload,
        "target": target,
    }


def render_markdown(report: dict[str, Any]) -> str:
    target = report.get("target") or {}
    submission = report.get("submission") or {}
    readiness = report.get("readiness") or {}
    profile = report.get("profile") or {}
    safety = report.get("safety_gate") or {}
    lines = [
        f"# MiniMax H3 灰度预检｜Book {target.get('book_id')} E{target.get('episode')} S{target.get('shot_id')}",
        "",
        f"- 模式：{report.get('mode')}",
        f"- 项目：{target.get('book_title')}",
        f"- 场景：{target.get('scene_name')}",
        f"- Prompt 长度：{submission.get('prompt_length')}",
        f"- 任务模式：{submission.get('task_mode')}",
        f"- 首帧：{submission.get('first_frame_asset_id') or '无，文生视频'}",
        f"- 模型配置：{profile.get('id') or '-'} / {profile.get('provider') or '-'} / {profile.get('model_name') or '-'}",
        f"- API Key：{'已配置' if profile.get('api_key_configured') else '未配置'}",
        f"- 可真实提交：{readiness.get('ready_for_real_submit')}",
        f"- 本次会真实提交：{safety.get('will_submit')}",
        "",
        "## Blockers",
        "",
    ]
    blockers = readiness.get("blockers") or []
    if blockers:
        lines.extend([f"- {item}" for item in blockers])
    else:
        lines.append("- 无")
    warnings = readiness.get("warnings") or []
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend([f"- {item}" for item in warnings])
    else:
        lines.append("- 无")
    lines.extend(["", "## 真实运行门禁", ""])
    for key in ("allow_real_cli", "real_env_enabled", "confirmation_matches", "target_whitelisted"):
        lines.append(f"- {key}: {safety.get(key)}")
    lines.extend(["", "## 真实运行命令", "", "```powershell"])
    lines.extend(str(item) for item in report.get("real_run_command") or [])
    lines.extend(["```", "", "## H3 Prompt 预览", "", "```text", str(submission.get("prompt_preview") or ""), "```"])
    if report.get("real_submission_result"):
        result = report["real_submission_result"]
        final_task = result.get("final_task") if isinstance(result.get("final_task"), dict) else {}
        lines.extend(
            [
                "",
                "## 真实提交结果",
                "",
                f"- task_id: {result.get('task_id')}",
                f"- status: {final_task.get('status')}",
                f"- external_task_id: {final_task.get('external_task_id')}",
                f"- external_status: {final_task.get('external_status')}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_report(report: dict[str, Any], out: str = "", summary_md: str = "") -> tuple[Path, Path]:
    out_path = Path(out) if out else default_artifact_path("json")
    if not out_path.is_absolute():
        out_path = ROOT_DIR / out_path
    md_path = Path(summary_md) if summary_md else out_path.with_suffix(".md")
    if not md_path.is_absolute():
        md_path = ROOT_DIR / md_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return out_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or confirmed real MiniMax H3 machine-prompt gray validation.")
    parser.add_argument("--book-id", type=int, default=75)
    parser.add_argument("--episode", type=int, default=1)
    parser.add_argument("--shot-id", type=int, default=1)
    parser.add_argument("--model-profile-id", default="")
    parser.add_argument("--duration-seconds", type=int, default=5)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--first-frame-asset-id", default="")
    parser.add_argument("--no-first-frame", dest="use_first_frame", action="store_false")
    parser.set_defaults(use_first_frame=True)
    parser.add_argument("--allow-real", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--summary-md", default="")
    parser.add_argument("positionals", nargs="*", help="Optional positional fallback: book_id episode shot_id")
    args = parser.parse_args()
    if args.positionals:
        if len(args.positionals) != 3:
            raise RuntimeError("Positional fallback must be exactly: book_id episode shot_id.")
        args.book_id = int(args.positionals[0])
        args.episode = int(args.positionals[1])
        args.shot_id = int(args.positionals[2])

    started = time.monotonic()
    init_db()
    client = TestClient(app)
    report = build_preflight_report(args, client)
    if report["mode"] == "real-submit":
        report["real_submission_result"] = submit_real(client, args, report)
    else:
        log("Dry-run preflight only; no provider call and no storyboard asset write.")
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    out_path, md_path = write_report(report, args.out, args.summary_md)
    log(f"Report written: {out_path}")
    log(f"Summary written: {md_path}")
    if report["mode"] != "real-submit":
        log("To run a real gray sample, review the report and use the printed gated command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
