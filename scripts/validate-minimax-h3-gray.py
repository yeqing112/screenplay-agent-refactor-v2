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
from datetime import UTC, datetime
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
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def default_artifact_path(suffix: str) -> Path:
    return ROOT_DIR / "artifacts" / f"{REPORT_PREFIX}-{timestamp_slug()}.{suffix}"


def target_key(book_id: int, episode: int, shot_id: str | int) -> str:
    return f"{int(book_id)}:{int(episode)}:{int(shot_id)}"


def parse_csv_ints(raw: str) -> list[int]:
    values: list[int] = []
    for token in str(raw or "").split(","):
        token = token.strip()
        if token:
            values.append(int(token))
    return values


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


def _asset_url(asset: dict[str, Any] | None) -> str:
    if not isinstance(asset, dict):
        return ""
    return str(asset.get("uri") or asset.get("previewUrl") or "").strip()


def _has_legacy_director_markers(prompt: str) -> bool:
    normalized = str(prompt or "")
    return any(marker in normalized for marker in ("[画面", "画面开场", "画面切", "请生成", "用于首帧"))


def _has_gray_sample_safety_risk(prompt: str) -> bool:
    normalized = str(prompt or "")
    return any(
        marker in normalized
        for marker in (
            "高速砸进",
            "面部朝下",
            "停止运动",
            "泥坑",
            "下坠",
            "坠落",
            "跌落",
            "受伤",
            "惊恐",
            "血",
            "未成年",
            "儿童",
        )
    )


def select_gray_candidate(book_ids: list[int], client: TestClient | None = None) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    order = {book_id: index for index, book_id in enumerate(book_ids)}
    with Session() as session:
        books = {int(book.id): str(book.title or "") for book in session.query(Book).filter(Book.id.in_(book_ids)).all()}
        rows = (
            session.query(StoryboardShot)
            .filter(StoryboardShot.book_id.in_(book_ids))
            .order_by(StoryboardShot.book_id.asc(), StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc())
            .all()
        )
        for shot in rows:
            first_frame = find_first_frame(shot)
            first_frame_url = _asset_url(first_frame)
            if not first_frame_url:
                continue
            asset_links = safe_json_loads(shot.asset_links, {}) if shot.asset_links else {}
            videos = asset_links.get("videos") if isinstance(asset_links, dict) else []
            if not isinstance(videos, list):
                videos = []
            has_existing_video = any(isinstance(item, dict) for item in videos)
            is_external_http = first_frame_url.startswith("http://") or first_frame_url.startswith("https://")
            is_local_placeholder = first_frame_url.startswith("/api/prototyping/assets/")
            is_data_uri = first_frame_url.startswith("data:")
            prompt = ""
            prompt_has_legacy_markers = False
            prompt_has_safety_risk = False
            prompt_length = 0
            if client is not None:
                try:
                    export_payload = load_machine_prompt_export(client, int(shot.book_id), int(shot.episode or 1), int(shot.shot_id))
                    prompt = str(h3_fields(export_payload).get("integrated_multimodal_description") or "").strip()
                    prompt_length = len(prompt)
                    prompt_has_legacy_markers = _has_legacy_director_markers(prompt)
                    prompt_has_safety_risk = _has_gray_sample_safety_risk(prompt)
                except Exception:
                    prompt_has_legacy_markers = True
            score = 0
            if is_external_http:
                score += 100
            if not has_existing_video:
                score += 40
            if not is_local_placeholder and not is_data_uri:
                score += 20
            if prompt and not prompt_has_legacy_markers:
                score += 30
            if prompt_has_legacy_markers:
                score -= 80
            if prompt_has_safety_risk:
                score -= 100
            score -= order.get(int(shot.book_id), 999)
            candidates.append(
                {
                    "book_id": int(shot.book_id),
                    "book_title": books.get(int(shot.book_id), ""),
                    "episode": int(shot.episode or 1),
                    "shot_id": int(shot.shot_id),
                    "scene_name": str(shot.scene_name or ""),
                    "first_frame_asset_id": str(first_frame.get("id") or "") if isinstance(first_frame, dict) else "",
                    "first_frame_url": first_frame_url,
                    "has_existing_video": has_existing_video,
                    "is_external_http": is_external_http,
                    "prompt_length": prompt_length,
                    "prompt_has_legacy_director_markers": prompt_has_legacy_markers,
                    "prompt_has_gray_sample_safety_risk": prompt_has_safety_risk,
                    "score": score,
                }
            )
    if not candidates:
        raise RuntimeError(f"No adopted first-frame candidates found in books: {book_ids}")
    candidates.sort(key=lambda item: (-int(item["score"]), item["book_id"], item["episode"], item["shot_id"]))
    selected = candidates[0]
    selected["candidate_count"] = len(candidates)
    selected["alternatives"] = candidates[1:6]
    return selected


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
    if _has_gray_sample_safety_risk(prompt):
        warnings.append("h3_prompt_contains_gray_sample_safety_risk_markers")
    if _has_legacy_director_markers(prompt):
        warnings.append("h3_prompt_contains_legacy_director_markers")
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
        "created_at": datetime.now(UTC).isoformat(),
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
        "candidate_selection": getattr(args, "selected_candidate", None),
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
    candidate_selection = report.get("candidate_selection") if isinstance(report.get("candidate_selection"), dict) else None
    if candidate_selection:
        lines.extend(
            [
                "",
                "## 自动候选选择",
                "",
                f"- 候选总数：{candidate_selection.get('candidate_count')}",
                f"- 选中首帧：{candidate_selection.get('first_frame_asset_id')}",
                f"- 外部 URL：{candidate_selection.get('is_external_http')}",
                f"- 已有视频：{candidate_selection.get('has_existing_video')}",
                f"- Prompt 遗留导演标记：{candidate_selection.get('prompt_has_legacy_director_markers')}",
                f"- Prompt 灰度安全风险：{candidate_selection.get('prompt_has_gray_sample_safety_risk')}",
            ]
        )
        alternatives = candidate_selection.get("alternatives") if isinstance(candidate_selection.get("alternatives"), list) else []
        if alternatives:
            lines.append("- 备选：")
            for item in alternatives:
                lines.append(
                    f"  - {target_key(item.get('book_id'), item.get('episode'), item.get('shot_id'))}"
                    f"｜{item.get('scene_name')}｜external={item.get('is_external_http')}"
                    f"｜hasVideo={item.get('has_existing_video')}"
                    f"｜legacyMarkers={item.get('prompt_has_legacy_director_markers')}"
                    f"｜safetyRisk={item.get('prompt_has_gray_sample_safety_risk')}"
                )
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
    parser.add_argument("--auto-candidate", action="store_true", help="Select a real shot with an adopted first-frame image.")
    parser.add_argument("--candidate-book-ids", default="75,5,3,1,14")
    parser.add_argument("positionals", nargs="*", help="Optional positional fallback: book_id episode shot_id")
    args = parser.parse_args()
    if args.positionals:
        if len(args.positionals) == 1 and args.positionals[0].strip().lower() in {"auto", "auto-candidate"}:
            args.auto_candidate = True
        elif len(args.positionals) != 3:
            raise RuntimeError("Positional fallback must be exactly: book_id episode shot_id.")
        else:
            args.book_id = int(args.positionals[0])
            args.episode = int(args.positionals[1])
            args.shot_id = int(args.positionals[2])

    started = time.monotonic()
    init_db()
    client = TestClient(app)
    if args.auto_candidate:
        selected = select_gray_candidate(parse_csv_ints(args.candidate_book_ids), client=client)
        args.book_id = int(selected["book_id"])
        args.episode = int(selected["episode"])
        args.shot_id = int(selected["shot_id"])
        args.first_frame_asset_id = str(selected.get("first_frame_asset_id") or "")
        args.selected_candidate = selected
        log(
            "Selected candidate "
            f"{target_key(args.book_id, args.episode, args.shot_id)} "
            f"from {selected.get('candidate_count')} first-frame candidate(s)."
        )
    else:
        args.selected_candidate = None
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
