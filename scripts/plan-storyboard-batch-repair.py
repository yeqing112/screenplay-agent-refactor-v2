"""Create a real-project storyboard batch repair preflight plan.

This command is intentionally dry-run for real projects. It uses temporary clone
repair to estimate before/after quality, then writes an impact plan that can be
reviewed before any future real-project apply command exists.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("VALIDATE_STORYBOARD_REPAIR_TEMP_BOOK_ID", "999906")

BATCH_HELPER_PATH = ROOT_DIR / "scripts" / "validate-storyboard-batch-repair-clone.py"
spec = importlib.util.spec_from_file_location("storyboard_batch_repair_helper", BATCH_HELPER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load batch helper script: {BATCH_HELPER_PATH}")
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

from models import Session, StoryboardPromptVersion, StoryboardShot, init_db


DEFAULT_REPORT_PREFIX = "storyboard-batch-repair-preflight"


def log(message: str) -> None:
    print(f"[storyboard-batch-preflight] {message}")


def latest_prompt_version_snapshot(book_id: int, episode: int, shot_id: int) -> dict[str, Any]:
    with Session() as session:
        latest = (
            session.query(StoryboardPromptVersion)
            .filter(
                StoryboardPromptVersion.book_id == book_id,
                StoryboardPromptVersion.episode == episode,
                StoryboardPromptVersion.shot_id == shot_id,
            )
            .order_by(StoryboardPromptVersion.version.desc())
            .first()
        )
        if not latest:
            return {
                "status": "missing_prompt_version",
                "message": "真实项目当前没有 prompt version；落库前必须先创建 baseline version 才能安全回滚。",
                "version_id": None,
                "version": None,
                "compile_reason": None,
            }
        return {
            "status": "ready",
            "message": "可作为真实落库后的推荐回滚锚点。",
            "version_id": latest.id,
            "version": latest.version,
            "compile_reason": latest.compile_reason,
        }


def real_apply_readiness(sample: dict[str, Any]) -> dict[str, Any]:
    book_id = int(sample["book_id"])
    episode = int(sample["episode"])
    shot_id = int(sample["shot_id"])
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    with Session() as session:
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
            blockers.append({
                "code": "storyboard_shot_not_found",
                "message": "真实项目镜头不存在，不能进入 apply。",
            })
            return {"ready": False, "blockers": blockers, "warnings": warnings}

        meta_info = batch.helper.safe_json_loads(shot.meta_info, {})
        seed = {
            "shot_id": shot.shot_id,
            "scene_name": shot.scene_name,
            "makeup_prompts": batch.helper._load_episode_makeup_prompt_stub(book_id, episode),
            "action_process": shot.action_process,
            "dialogue": shot.dialogue,
            "start_state": shot.start_state,
            "end_state": shot.end_state,
            "duration": shot.duration,
            "camera_angle": shot.camera_angle,
            "camera_movement": shot.camera_movement,
            "transition": shot.transition,
        }
        structured = batch.helper._auto_bind_structured_shot_assets(
            book_id,
            episode,
            batch.helper._derive_structured_shot_payload(meta_info, seed),
            seed,
        )
        scene_asset_id = str(structured.get("scene_asset_id") or "").strip()
        source_issues = sample.get("source_audit", {}).get("issues", [])
        if "missing_structured_scene_asset" in source_issues and not scene_asset_id:
            blockers.append({
                "code": "real_project_missing_bindable_scene_asset",
                "message": (
                    "克隆预检可通过是因为临时项目会补一个临时场景资产；"
                    "真实项目当前没有可由场景名自动绑定的场景资产，apply 后仍会缺 scene_asset_id。"
                ),
                "scene_name": str(shot.scene_name or ""),
            })
        elif not scene_asset_id:
            warnings.append({
                "code": "real_project_scene_binding_unresolved",
                "message": "真实项目当前未解析到 scene_asset_id；若本镜头不要求修复场景资产，可继续人工评审。",
                "scene_name": str(shot.scene_name or ""),
            })
        return {
            "ready": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
            "predicted_scene_asset_id": scene_asset_id,
        }


def confirmation_token(samples: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    payload = {
        "samples": [
            {
                "book_id": item["book_id"],
                "episode": item["episode"],
                "shot_id": item["shot_id"],
                "source_issues": item["source_audit"]["issues"],
                "after_issues": item["after_audit"]["issues"],
            }
            for item in samples
        ],
        "summary": summary,
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def plan_status(results: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    missing_anchors = [
        item
        for item in results
        if item.get("rollback_anchor", {}).get("status") != "ready"
    ]
    real_apply_blockers = [
        blocker
        for item in results
        for blocker in item.get("real_apply_readiness", {}).get("blockers", [])
    ]
    return {
        "dry_run_only": True,
        "real_project_mutated": False,
        "ready_for_human_review": summary["after_errors"] == 0,
        "ready_for_apply_command": summary["after_errors"] == 0 and not real_apply_blockers,
        "requires_baseline_version_before_apply": len(missing_anchors) > 0,
        "missing_rollback_anchor_count": len(missing_anchors),
        "real_apply_blocker_count": len(real_apply_blockers),
    }


def escape_cell(value: Any) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    return text


def write_reports(results: list[dict[str, Any]], summary: dict[str, Any], status: dict[str, Any], token: str) -> tuple[Path, Path]:
    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    stamp = batch.helper.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    json_path = artifacts_dir / f"{DEFAULT_REPORT_PREFIX}-{stamp}.json"
    md_path = artifacts_dir / f"{DEFAULT_REPORT_PREFIX}-{stamp}.md"

    report = {
        "generatedAt": batch.helper.datetime.utcnow().isoformat(),
        "mode": "dry-run-preflight",
        "tempBookId": batch.helper.TEMP_BOOK_ID,
        "confirmationToken": token,
        "status": status,
        "summary": summary,
        "results": results,
        "nextStep": (
            "Review this plan. Do not apply to real projects until an explicit apply command "
            "requires this confirmation token and creates rollback anchors for every selected shot."
        ),
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 分镜批量修复预检计划",
        "",
        f"- 生成时间：{report['generatedAt']}",
        f"- 模式：dry-run / 未修改真实项目",
        f"- 临时项目：`book {batch.helper.TEMP_BOOK_ID}`",
        f"- 确认令牌：`{token}`",
        f"- 样本数：{summary['samples']}",
        f"- error：{summary['before_errors']} -> {summary['after_errors']}",
        f"- warning：{summary['before_warnings']} -> {summary['after_warnings']}",
        f"- 可进入人工评审：{'是' if status['ready_for_human_review'] else '否'}",
        f"- 可直接进入未来 apply 命令：{'是' if status['ready_for_apply_command'] else '否'}",
        f"- 缺少回滚锚点：{status['missing_rollback_anchor_count']}",
        f"- 真实 apply 阻塞项：{status['real_apply_blocker_count']}",
        "",
        "## 样本影响清单",
        "",
        "| 项目 | 镜头 | 修复前 error | 修复后 error | 修复前 warning | 修复后 warning | 回滚锚点 | 真实 apply 状态 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in results:
        anchor = item.get("rollback_anchor", {})
        anchor_label = (
            f"v{anchor.get('version')} / id {anchor.get('version_id')}"
            if anchor.get("status") == "ready"
            else anchor.get("status")
        )
        readiness = item.get("real_apply_readiness", {})
        blocker_codes = [
            str(blocker.get("code") or "")
            for blocker in readiness.get("blockers", [])
            if str(blocker.get("code") or "").strip()
        ]
        readiness_label = "ready" if readiness.get("ready") else ", ".join(blocker_codes) or "blocked"
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_cell(f"#{item['book_id']} {item.get('book_title', '')}"),
                    escape_cell(f"{item['episode']}-{item['shot_id']}"),
                    str(len(item["source_audit"]["issues"])),
                    str(len(item["after_audit"]["issues"])),
                    str(len(item["source_audit"]["warnings"])),
                    str(len(item["after_audit"]["warnings"])),
                    escape_cell(anchor_label),
                    escape_cell(readiness_label),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 落库前门禁",
            "",
            "1. 必须由用户明确确认本预检报告。",
            "2. apply 命令必须要求确认令牌，不能仅凭默认参数写真实项目。",
            "3. 每个真实镜头必须有可回滚锚点；没有 prompt version 的镜头，应先创建 baseline version。",
            "4. 真实项目必须存在可绑定的场景资产；克隆预检中的临时场景资产不能作为真实 apply 依据。",
            "5. apply 后必须立即产出二次审计和推荐 rollback 清单。",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def create_preflight_plan() -> None:
    init_db()
    client = TestClient(batch.helper.app)
    book_ids = batch.parse_book_ids()
    limit = batch.target_shot_count()
    samples = batch.select_failing_samples(book_ids, limit)
    log(
        "Selected samples: "
        + ", ".join(f"#{item['book_id']}:{item['episode']}:{item['shot_id']}" for item in samples)
    )
    results = []
    for sample in samples:
        repaired = batch.repair_clone_sample(client, sample)
        repaired["rollback_anchor"] = latest_prompt_version_snapshot(
            sample["book_id"],
            sample["episode"],
            sample["shot_id"],
        )
        repaired["real_apply_readiness"] = real_apply_readiness(sample)
        repaired["proposed_apply"] = {
            "method": "POST",
            "path": f"/api/books/{sample['book_id']}/storyboard/{sample['episode']}/{sample['shot_id']}/compile-prompts",
            "body": {
                "compileReason": "batch-quality-repair-confirmed",
                "force": True,
            },
        }
        results.append(repaired)

    summary = batch.summarize(results)
    token = confirmation_token(results, summary)
    status = plan_status(results, summary)
    json_path, md_path = write_reports(results, summary, status, token)
    log(
        "Preflight summary: "
        f"samples={summary['samples']}, "
        f"errors {summary['before_errors']} -> {summary['after_errors']}, "
        f"warnings {summary['before_warnings']} -> {summary['after_warnings']}, "
        f"missing rollback anchors={status['missing_rollback_anchor_count']}, "
        f"real apply blockers={status['real_apply_blocker_count']}"
    )
    log(f"JSON report written: {json_path}")
    log(f"Markdown report written: {md_path}")
    if summary["after_errors"] > 0:
        raise RuntimeError(f"Preflight clone repair left {summary['after_errors']} error(s).")
    if status["real_apply_blocker_count"] > 0 and os.environ.get("PLAN_STORYBOARD_BATCH_REPAIR_STRICT_READY") == "1":
        raise RuntimeError(f"Preflight found {status['real_apply_blocker_count']} real apply blocker(s).")


if __name__ == "__main__":
    create_preflight_plan()
