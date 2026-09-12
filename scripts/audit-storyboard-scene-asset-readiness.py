"""Audit real storyboard scene asset readiness before prompt batch apply.

This command is read-only for real projects. It checks whether storyboard
`scene_name` values can bind to real `VisualLocation` rows in the same book.
Clone-based repair can create temporary scene assets, so this audit is the
real-project guardrail that prevents a false-positive preflight from becoming
an unsafe apply.
"""

from __future__ import annotations

import json
import os
import sys
import hashlib
import io
import base64
import urllib.request
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.server import _normalize_scene_asset_id
from models import Book, Session, StoryboardShot, VisualLocation, VisualReferenceAsset, init_db


SAMPLE_REGISTRY_PATH = ROOT_DIR / "production-sample-registry.json"
REPORT_PREFIX = "storyboard-scene-asset-readiness"
MIN_LANDSCAPE_ASPECT_RATIO = 1.45


def log(message: str) -> None:
    print(f"[storyboard-scene-assets] {message}")


def parse_book_ids() -> list[int]:
    configured = os.environ.get("SCENE_ASSET_AUDIT_BOOK_IDS", "").strip()
    if configured:
        raw = configured
    else:
        try:
            registry = json.loads(SAMPLE_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Unable to read active production sample registry: {exc}") from exc
        values = registry.get("active_book_ids", []) if isinstance(registry, dict) else []
        raw = ",".join(str(value) for value in values if str(value).isdigit() and int(value) > 0)
    book_ids: list[int] = []
    for token in raw.split(","):
        value = token.strip()
        if value:
            book_ids.append(int(value))
    if not book_ids:
        raise RuntimeError("No active production sample IDs configured; set SCENE_ASSET_AUDIT_BOOK_IDS explicitly or populate production-sample-registry.json.")
    return book_ids


def compact_scene_name(value: Any) -> str:
    return str(value or "").strip()


def shot_label(shot: StoryboardShot) -> str:
    return f"{int(shot.episode or 1)}-{int(shot.shot_id)}"


def should_validate_image_dimensions() -> bool:
    return os.environ.get("SCENE_ASSET_AUDIT_VALIDATE_IMAGE_DIMENSIONS") == "1"


def inspect_reference_dimensions(row: VisualReferenceAsset) -> dict[str, Any]:
    source = str(row.local_path or "").strip() or str(row.image_url or "").strip()
    payload: dict[str, Any] = {
        "reference_id": getattr(row, "id", None),
        "source": source,
        "width": 0,
        "height": 0,
        "aspect_ratio": 0,
        "landscape_ok": False,
        "error": "",
    }
    if not source:
        payload["error"] = "missing image source"
        return payload

    try:
        from PIL import Image

        if source.startswith("data:image/") and ";base64," in source:
            data = base64.b64decode(source.split(";base64,", 1)[1])
            image = Image.open(io.BytesIO(data))
        elif source.startswith("http://") or source.startswith("https://"):
            request = urllib.request.Request(source, headers={"User-Agent": "screenplay-agent-readiness-audit/1.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read(8 * 1024 * 1024)
            image = Image.open(io.BytesIO(data))
        else:
            path = Path(source)
            if not path.is_absolute():
                path = ROOT_DIR / path
            image = Image.open(path)
        width, height = image.size
        aspect_ratio = round(width / height, 4) if height else 0
        payload.update({
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "landscape_ok": aspect_ratio >= MIN_LANDSCAPE_ASPECT_RATIO,
        })
    except Exception as exc:
        payload["error"] = str(exc)
    return payload


def audit_book(book_id: int) -> dict[str, Any]:
    with Session() as session:
        book = session.get(Book, book_id)
        shots = (
            session.query(StoryboardShot)
            .filter(StoryboardShot.book_id == book_id)
            .order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc())
            .all()
        )
        locations = (
            session.query(VisualLocation)
            .filter(VisualLocation.book_id == book_id)
            .order_by(VisualLocation.id.asc())
            .all()
        )
        reference_assets = (
            session.query(VisualReferenceAsset)
            .filter(VisualReferenceAsset.book_id == book_id)
            .order_by(VisualReferenceAsset.id.asc())
            .all()
        )

    scene_rows: dict[str, dict[str, Any]] = {}
    for shot in shots:
        name = compact_scene_name(shot.scene_name)
        if not name:
            name = "(empty scene_name)"
        item = scene_rows.setdefault(
            name,
            {
                "scene_name": name,
                "shot_count": 0,
                "shots": [],
                "matched_location_id": "",
                "matched_location_name": "",
                "status": "missing",
            },
        )
        item["shot_count"] += 1
        item["shots"].append(shot_label(shot))

    location_by_id = {str(row.id): row for row in locations}
    references_by_scene_id: dict[str, list[VisualReferenceAsset]] = {}
    for row in reference_assets:
        if str(row.asset_type or "").strip() != "scene":
            continue
        references_by_scene_id.setdefault(str(row.asset_id or "").strip(), []).append(row)

    for item in scene_rows.values():
        scene_name = item["scene_name"]
        if scene_name == "(empty scene_name)":
            item["status"] = "missing_scene_name"
            item["production_status"] = "blocked"
            item["production_issues"] = ["empty scene_name"]
            continue
        matched_id = _normalize_scene_asset_id(book_id, scene_name)
        matched = location_by_id.get(str(matched_id)) if matched_id else None
        if matched:
            item["matched_location_id"] = str(matched.id)
            item["matched_location_name"] = matched.name
            item["status"] = "ready"
            references = references_by_scene_id.get(str(matched.id), [])
            locked_count = sum(1 for row in references if str(row.status or "").strip() == "locked")
            selected_count = sum(1 for row in references if str(row.status or "").strip() == "selected")
            candidate_count = sum(1 for row in references if str(row.status or "").strip() == "candidate")
            active_references = [
                row for row in references
                if str(row.status or "").strip() in {"selected", "locked"}
            ]
            candidate_references = [
                row for row in references
                if str(row.status or "").strip() == "candidate"
            ]
            image_count = sum(
                1
                for row in active_references
                if str(row.image_url or "").strip() or str(row.local_path or "").strip()
            )
            dimension_payloads = [
                inspect_reference_dimensions(row)
                for row in active_references
                if should_validate_image_dimensions()
            ]
            candidate_dimension_payloads = [
                inspect_reference_dimensions(row)
                for row in candidate_references
                if should_validate_image_dimensions()
            ]
            landscape_reference_count = sum(1 for item in dimension_payloads if item.get("landscape_ok"))
            landscape_candidate_count = sum(1 for item in candidate_dimension_payloads if item.get("landscape_ok"))
            asset_status = str(getattr(matched, "asset_status", "") or "draft").strip() or "draft"
            description = str(getattr(matched, "description", "") or "").strip()
            notes = str(getattr(matched, "notes", "") or "").strip()
            production_issues: list[str] = []
            if asset_status in {"", "draft", "pending"}:
                production_issues.append(f"场景资产状态仍为 {asset_status or '空'}")
            if "最小场景资产" in description or "requires-human-asset-refinement" in notes:
                production_issues.append("场景资产仍使用分镜派生的 draft 描述")
            if locked_count + selected_count <= 0 or image_count <= 0:
                production_issues.append("场景资产没有 selected/locked 参考图")
            if should_validate_image_dimensions():
                if not dimension_payloads:
                    production_issues.append("场景资产参考图尺寸未验证")
                elif landscape_reference_count <= 0:
                    production_issues.append("场景资产没有符合横构图比例的 selected/locked 参考图")
            item["matched_asset_status"] = asset_status
            item["reference_total"] = len(references)
            item["reference_image_count"] = image_count
            item["reference_dimension_validation_enabled"] = should_validate_image_dimensions()
            item["active_reference_dimensions"] = dimension_payloads
            item["candidate_reference_dimensions"] = candidate_dimension_payloads
            item["landscape_reference_count"] = landscape_reference_count
            item["landscape_candidate_count"] = landscape_candidate_count
            item["locked_reference_count"] = locked_count
            item["selected_reference_count"] = selected_count
            item["candidate_reference_count"] = candidate_count
            item["production_status"] = "ready" if not production_issues else "needs_refinement"
            item["production_issues"] = production_issues
        else:
            item["status"] = "missing_visual_location"
            item["production_status"] = "blocked"
            item["production_issues"] = ["缺失 VisualLocation 场景资产"]

    scenes = sorted(
        scene_rows.values(),
        key=lambda item: (item["status"] == "ready", -int(item["shot_count"]), item["scene_name"]),
    )
    missing_scenes = [item for item in scenes if item["status"] != "ready"]
    production_blockers = [item for item in scenes if item.get("production_status") != "ready"]
    return {
        "book_id": book_id,
        "book_title": book.title if book else "",
        "storyboard_shots": len(shots),
        "visual_locations": len(locations),
        "visual_reference_assets": len(reference_assets),
        "unique_scene_names": len(scenes),
        "ready_scene_names": len(scenes) - len(missing_scenes),
        "missing_scene_names": len(missing_scenes),
        "affected_shots": sum(int(item["shot_count"]) for item in missing_scenes),
        "production_blocking_scene_names": len(production_blockers),
        "production_affected_shots": sum(int(item["shot_count"]) for item in production_blockers),
        "status": "ready" if not missing_scenes else "blocked",
        "production_status": "ready" if not production_blockers else "blocked",
        "scenes": scenes,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "books": len(results),
        "blocked_books": sum(1 for item in results if item["status"] != "ready"),
        "storyboard_shots": sum(int(item["storyboard_shots"]) for item in results),
        "visual_locations": sum(int(item["visual_locations"]) for item in results),
        "visual_reference_assets": sum(int(item.get("visual_reference_assets") or 0) for item in results),
        "unique_scene_names": sum(int(item["unique_scene_names"]) for item in results),
        "missing_scene_names": sum(int(item["missing_scene_names"]) for item in results),
        "affected_shots": sum(int(item["affected_shots"]) for item in results),
        "production_blocking_scene_names": sum(int(item.get("production_blocking_scene_names") or 0) for item in results),
        "production_affected_shots": sum(int(item.get("production_affected_shots") or 0) for item in results),
        "ready_for_binding_repair_apply": all(item["status"] == "ready" for item in results),
        "ready_for_prompt_batch_apply": all(item.get("production_status") == "ready" for item in results),
    }


def confirmation_token(results: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    payload = {
        "summary": summary,
        "missing": [
            {
                "book_id": item["book_id"],
                "scene_name": scene["scene_name"],
                "shot_count": scene["shot_count"],
                "shots": scene["shots"],
            }
            for item in results
            for scene in item["scenes"]
            if scene["status"] != "ready"
        ],
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def escape_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def write_reports(results: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[Path, Path]:
    from datetime import datetime

    artifacts_dir = ROOT_DIR / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    json_path = artifacts_dir / f"{REPORT_PREFIX}-{stamp}.json"
    md_path = artifacts_dir / f"{REPORT_PREFIX}-{stamp}.md"
    token = confirmation_token(results, summary)

    report = {
        "generatedAt": datetime.utcnow().isoformat(),
        "mode": "read-only-scene-asset-readiness",
        "confirmationToken": token,
        "summary": summary,
        "results": results,
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 分镜真实场景资产 readiness 审计",
        "",
        f"- 生成时间：{report['generatedAt']}",
        "- 模式：只读 / 未修改真实项目",
        f"- 确认令牌：`{token}`",
        f"- 项目数：{summary['books']}",
        f"- 阻塞项目数：{summary['blocked_books']}",
        f"- 分镜镜头数：{summary['storyboard_shots']}",
        f"- 真实场景资产数：{summary['visual_locations']}",
        f"- 场景/角色/道具参考资产数：{summary['visual_reference_assets']}",
        f"- 唯一场景名数：{summary['unique_scene_names']}",
        f"- 缺失场景名数：{summary['missing_scene_names']}",
        f"- 受影响镜头数：{summary['affected_shots']}",
        f"- 生产阻塞场景名数：{summary['production_blocking_scene_names']}",
        f"- 生产阻塞镜头数：{summary['production_affected_shots']}",
        f"- 可进入缺失绑定修复 apply：{'是' if summary['ready_for_binding_repair_apply'] else '否'}",
        f"- 可进入提示词批量 apply：{'是' if summary['ready_for_prompt_batch_apply'] else '否'}",
        "",
        "## 项目汇总",
        "",
        "| 项目 | 分镜镜头 | 真实场景资产 | 参考资产 | 唯一场景名 | 缺失场景名 | 生产阻塞场景 | 受影响镜头 | 绑定状态 | 生产状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_cell(f"#{item['book_id']} {item.get('book_title', '')}"),
                    str(item["storyboard_shots"]),
                    str(item["visual_locations"]),
                    str(item.get("visual_reference_assets") or 0),
                    str(item["unique_scene_names"]),
                    str(item["missing_scene_names"]),
                    str(item.get("production_blocking_scene_names") or 0),
                    str(item.get("production_affected_shots") or 0),
                    escape_cell(item["status"]),
                    escape_cell(item.get("production_status", "")),
                ]
            )
            + " |"
        )
    blocked = [item for item in results if item["status"] != "ready"]
    if blocked:
        lines.extend(["", "## 缺失清单", ""])
        for item in blocked:
            lines.extend(
                [
                    f"### #{item['book_id']} {item.get('book_title', '')}",
                    "",
                    "| 场景名 | 受影响镜头数 | 镜头 | 状态 |",
                    "| --- | ---: | --- | --- |",
                ]
            )
            for scene in item["scenes"]:
                if scene["status"] == "ready":
                    continue
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            escape_cell(scene["scene_name"]),
                            str(scene["shot_count"]),
                            escape_cell(", ".join(scene["shots"][:12])),
                            escape_cell(scene["status"]),
                        ]
                    )
                    + " |"
                )
            lines.append("")
    production_blocked = [item for item in results if item.get("production_status") != "ready"]
    if production_blocked:
        lines.extend(["", "## 生产可用性阻塞清单", ""])
        for item in production_blocked:
            lines.extend(
                [
                    f"### #{item['book_id']} {item.get('book_title', '')}",
                    "",
                    "| 场景名 | 资产ID | 资产状态 | 参考图 | 横构图图 | locked | selected | 受影响镜头 | 问题 |",
                    "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
                ]
            )
            for scene in item["scenes"]:
                if scene.get("production_status") == "ready":
                    continue
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            escape_cell(scene["scene_name"]),
                            escape_cell(scene.get("matched_location_id", "")),
                            escape_cell(scene.get("matched_asset_status", "")),
                            str(scene.get("reference_image_count") or 0),
                            str(scene.get("landscape_reference_count") or 0),
                            str(scene.get("locked_reference_count") or 0),
                            str(scene.get("selected_reference_count") or 0),
                            str(scene["shot_count"]),
                            escape_cell("；".join(scene.get("production_issues") or [])),
                        ]
                    )
                    + " |"
                )
            lines.append("")
    lines.extend(
        [
            "## 使用建议",
            "",
            "1. 对 `missing_visual_location` 的场景，先在资产中心补真实 `VisualLocation` 场景资产。",
            "2. 对 `production_status != ready` 的场景，补正式场景描述并生成/锁定 `VisualReferenceAsset` 参考图。",
            "3. 补齐后重新运行本命令，确认 `ready_for_prompt_batch_apply=true`。",
            "4. 再运行 `npm run plan:storyboard-batch-repair`，确认没有 `real_apply_blocker`。",
            "5. 最后才进入受确认令牌保护的 `npm run apply:storyboard-batch-repair`。",
            "",
            "如果确认要按本报告创建缺失的最小 draft 场景资产，可使用受保护命令：",
            "",
            "```bash",
            "APPLY_STORYBOARD_SCENE_ASSETS_REAL=1 \\",
            "APPLY_STORYBOARD_SCENE_ASSETS_REPORT=<本报告 JSON> \\",
            "APPLY_STORYBOARD_SCENE_ASSETS_CONFIRM=<确认令牌> \\",
            "npm run apply:scene-assets",
            "```",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def audit_scene_asset_readiness() -> None:
    init_db()
    book_ids = parse_book_ids()
    results = [audit_book(book_id) for book_id in book_ids]
    summary = summarize(results)
    json_path, md_path = write_reports(results, summary)
    for item in results:
        log(
            f"#{item['book_id']} {item.get('book_title', '')}: "
            f"shots={item['storyboard_shots']}, "
            f"locations={item['visual_locations']}, "
            f"missingScenes={item['missing_scene_names']}, "
            f"affectedShots={item['affected_shots']}, "
            f"bindingStatus={item['status']}, "
            f"productionBlockingScenes={item.get('production_blocking_scene_names')}, "
            f"productionStatus={item.get('production_status')}"
        )
    log(
        "Scene asset readiness summary: "
        f"books={summary['books']}, "
        f"blockedBooks={summary['blocked_books']}, "
        f"missingScenes={summary['missing_scene_names']}, "
        f"affectedShots={summary['affected_shots']}, "
        f"productionBlockingScenes={summary.get('production_blocking_scene_names')}, "
        f"productionAffectedShots={summary.get('production_affected_shots')}"
    )
    log(f"JSON report written: {json_path}")
    log(f"Markdown report written: {md_path}")
    if os.environ.get("SCENE_ASSET_AUDIT_STRICT") == "1" and not summary["ready_for_prompt_batch_apply"]:
        raise RuntimeError("Scene asset readiness audit found blocker(s).")


if __name__ == "__main__":
    audit_scene_asset_readiness()
