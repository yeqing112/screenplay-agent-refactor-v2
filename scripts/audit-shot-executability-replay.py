"""Read-only replay audit for storyboard shot executability.

This deliberately does not call an LLM, create Prompt Versions, or modify a
StoryboardShot. It lets production review historical shots before choosing a
controlled recompilation batch.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core import safe_json_loads
from core.shot_executability import validate_shot_executability
from models import Session, StoryboardShot, init_db

DEFAULT_BOOK_IDS = [75, 14, 5, 3, 1]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _beats(meta: dict[str, Any]) -> list[dict[str, Any]]:
    structured = _as_dict(meta.get("structured_shot"))
    compiler = _as_dict(meta.get("prompt_compiler"))
    context = _as_dict(compiler.get("prompt_compile_context"))
    for value in (context.get("action_beats"), structured.get("action_beats")):
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _existing_result(meta: dict[str, Any]) -> dict[str, Any]:
    structured = _as_dict(meta.get("structured_shot"))
    compiler = _as_dict(meta.get("prompt_compiler"))
    context = _as_dict(compiler.get("prompt_compile_context"))
    for value in (context.get("executability"), structured.get("executability")):
        if isinstance(value, dict):
            return value
    return {}


def _row_payload(row: StoryboardShot) -> dict[str, Any]:
    meta = safe_json_loads(row.meta_info, {}) if row.meta_info else {}
    meta = _as_dict(meta)
    result = validate_shot_executability(
        duration=row.duration,
        action_process=str(row.action_process or ""),
        action_beats=_beats(meta),
        camera_movement=str(row.camera_movement or "static"),
        start_state=str(row.start_state or ""),
        end_state=str(row.end_state or ""),
        motion_prompt=str(row.visual_prompt_motion or ""),
    )
    existing = _existing_result(meta)
    return {
        "book_id": row.book_id,
        "episode": row.episode,
        "shot_id": row.shot_id,
        "scene_name": row.scene_name,
        "duration": row.duration,
        "camera_movement": row.camera_movement,
        "action_process": str(row.action_process or ""),
        "action_beats": _beats(meta),
        "replay": result,
        "stored_status": str(existing.get("status") or "") or None,
        "needs_recompile": not bool(existing),
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 分镜可拍性节拍回放报告",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "本报告是只读确定性回放：不调用 LLM、不创建 Prompt Version、不修改任何镜头。",
        "",
        "## 汇总",
        "",
        f"- 抽样镜头：{summary['sampled_shots']}",
        f"- pass：{summary['status_counts'].get('pass', 0)}",
        f"- warning：{summary['status_counts'].get('warning', 0)}",
        f"- blocked：{summary['status_counts'].get('blocked', 0)}",
        f"- 缺少已持久化结果、需受控重编译：{summary['needs_recompile']}",
        "",
        "## 优先治理清单",
        "",
        "| 镜头 | 时长 | 回放结果 | 动作数 | 主要问题 | 建议 |",
        "| --- | ---: | --- | ---: | --- | --- |",
    ]
    for item in report["shots"]:
        replay = item["replay"]
        findings = "；".join(str(row.get("message") or row.get("code") or "") for row in replay.get("findings", [])) or "-"
        suggestion_parts: list[str] = []
        for row in replay.get("suggestions", []):
            if row.get("type") == "extend_duration":
                suggestion_parts.append(f"延长至 {row.get('recommended_duration')}s")
            elif row.get("type") == "trim_non_core_actions":
                suggestion_parts.append("删减非核心动作")
            elif row.get("type") == "split_shot":
                suggestion_parts.append("拆为两个连续镜头")
            else:
                suggestion_parts.append(str(row.get("type") or ""))
        suggestions = "；".join(part for part in suggestion_parts if part)
        if not suggestions:
            suggestions = "重新编译以写入结果" if item["needs_recompile"] else "-"
        lines.append(
            f"| book {item['book_id']} / ep {item['episode']} / shot {item['shot_id']} | {item['duration']}s | {replay['status']} | {replay['action_count']} | {findings} | {suggestions} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--book-id", type=int, action="append", dest="book_ids")
    parser.add_argument("--out", type=Path, default=ROOT_DIR / "artifacts" / "shot-executability-replay.json")
    args = parser.parse_args()
    if not args.book_ids:
        args.book_ids = DEFAULT_BOOK_IDS
    init_db()
    with Session() as session:
        query = session.query(StoryboardShot)
        if args.book_ids:
            query = query.filter(StoryboardShot.book_id.in_(args.book_ids))
        rows = query.order_by(StoryboardShot.book_id.desc(), StoryboardShot.episode, StoryboardShot.shot_id).limit(max(1, args.limit)).all()
    shots = [_row_payload(row) for row in rows]
    status_counts = Counter(str(item["replay"].get("status") or "unknown") for item in shots)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only-deterministic-replay",
        "summary": {
            "sampled_shots": len(shots),
            "status_counts": dict(status_counts),
            "needs_recompile": sum(1 for item in shots if item["needs_recompile"]),
        },
        "shots": shots,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.out.with_suffix(".md")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"report": str(args.out), "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
