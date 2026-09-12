"""Merge read-only scene reference plans into one reviewable batch list.

This command never calls an image/LLM provider and never writes the database.
It is intentionally generic: any number of plans produced by
``plan-storyboard-scene-reference-assets.py`` can be reviewed together before
an operator chooses which plan (if any) to apply or enqueue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]


def _resolve(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT_DIR / path


def load_plan(path_text: str) -> dict[str, Any]:
    path = _resolve(path_text)
    if not path.exists():
        raise RuntimeError(f"Scene reference plan not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("mode") != "readonly-scene-reference-plan":
        raise RuntimeError(f"Not a readonly scene reference plan: {path}")
    payload["_source_path"] = str(path)
    return payload


def _batch_token(items: list[dict[str, Any]]) -> str:
    canonical = [
        {
            "book_id": item.get("book_id"),
            "location_id": item.get("location_id"),
            "scene_name": item.get("scene_name"),
            "api_request": item.get("api_request"),
        }
        for item in items
    ]
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:20]


def merge_plans(plans: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    source_plans: list[dict[str, Any]] = []
    for plan in plans:
        book_id = int(plan.get("book_id"))
        source_plans.append({
            "book_id": book_id,
            "path": plan.get("_source_path", ""),
            "confirmation_token": str(plan.get("confirmationToken") or ""),
        })
        for raw in plan.get("items") or []:
            if not isinstance(raw, dict) or raw.get("status") != "planned":
                continue
            generation = raw.get("reference_generation") if isinstance(raw.get("reference_generation"), dict) else {}
            items.append({
                "book_id": book_id,
                "scene_name": raw.get("scene_name", ""),
                "location_id": raw.get("location_id"),
                "status": "awaiting_user_confirmation",
                "shot_ids": list(raw.get("shot_ids") or []),
                "issues": list(raw.get("issues") or []),
                "source_fingerprint": str(raw.get("source_fingerprint") or "").strip(),
                "current_asset": raw.get("current_asset") or {},
                "reference_stats": raw.get("reference_stats") or {},
                "formal_description": (raw.get("planned_asset_update") or {}).get("formal_description", ""),
                "reference_prompt": generation.get("prompt", ""),
                "negative_prompt": generation.get("negative_prompt", ""),
                "api_request": generation.get("api_request") or {},
                "source_plan": plan.get("_source_path", ""),
            })
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "readonly-scene-reference-batch-review",
        "writes_performed": False,
        "external_calls_performed": False,
        "requires_user_confirmation": bool(items),
        "batchConfirmationToken": _batch_token(items),
        "source_plans": source_plans,
        "summary": {
            "source_plan_count": len(plans),
            "planned_items": len(items),
            "affected_shots": sum(len(item["shot_ids"]) for item in items),
            "books": sorted({item["book_id"] for item in items}),
        },
        "items": items,
    }


def render_markdown(batch: dict[str, Any]) -> str:
    summary = batch.get("summary") or {}
    lines = [
        "# 场景参考图批量重生待确认清单",
        "",
        f"- 生成时间：{batch.get('generatedAt')}",
        f"- 模式：{batch.get('mode')}（只读，未调用模型，未写库）",
        f"- 批量确认令牌：`{batch.get('batchConfirmationToken')}`",
        f"- 来源计划：{summary.get('source_plan_count', 0)}",
        f"- 待确认场景：{summary.get('planned_items', 0)}",
        f"- 影响镜头：{summary.get('affected_shots', 0)}",
        "",
        "## 汇总",
        "",
        "| Book | 场景 | 资产 ID | 影响镜头 | 当前问题 | 状态 |",
        "| ---: | --- | ---: | --- | --- | --- |",
    ]
    for item in batch.get("items") or []:
        issues = "；".join(item.get("issues") or []) or "无"
        lines.append(
            f"| {item.get('book_id')} | {item.get('scene_name')} | {item.get('location_id')} | "
            f"{', '.join(item.get('shot_ids') or [])} | {issues} | {item.get('status')} |"
        )
    lines.extend(["", "## 逐项预览", ""])
    for item in batch.get("items") or []:
        lines.extend([
            f"### Book {item.get('book_id')} · {item.get('scene_name')} · 资产 {item.get('location_id')}",
            "",
            f"- 影响镜头：{', '.join(item.get('shot_ids') or []) or '无'}",
            f"- 当前问题：{'；'.join(item.get('issues') or []) or '无'}",
            "",
            "正式场景描述候选：",
            "",
            f"> {item.get('formal_description', '')}",
            "",
            "参考图提示词：",
            "",
            f"> {item.get('reference_prompt', '')}",
            "",
            "负向提示词：",
            "",
            f"> {item.get('negative_prompt', '')}",
            "",
            "API 请求草案（仅预览）：",
            "",
            "```json",
            json.dumps(item.get("api_request") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge readonly scene reference plans for human review.")
    parser.add_argument("--plan", action="append", required=True, help="Path to a readonly scene reference plan (repeatable).")
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary-md", default="")
    args = parser.parse_args()
    batch = merge_plans([load_plan(path) for path in args.plan])
    out_path = _resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))
    if args.summary_md:
        md_path = _resolve(args.summary_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(batch), encoding="utf-8")
        print(str(md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
