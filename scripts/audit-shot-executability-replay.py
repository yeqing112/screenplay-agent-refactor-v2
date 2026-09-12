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
from core.shot_planner import build_action_timing_plan, build_shot_intent_plan
from models import Session, StoryboardShot, init_db

SAMPLE_REGISTRY_PATH = ROOT_DIR / "production-sample-registry.json"


def _default_book_ids() -> list[int]:
    """Read active production samples without hard-coding book identifiers."""
    try:
        registry = json.loads(SAMPLE_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [int(value) for value in registry.get("active_book_ids", []) if str(value).isdigit()]


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
    structured = _as_dict(meta.get("structured_shot"))
    compiler = _as_dict(meta.get("prompt_compiler"))
    context = _as_dict(compiler.get("prompt_compile_context"))
    action_beats = _beats(meta)
    result = validate_shot_executability(
        duration=row.duration,
        action_process=str(row.action_process or ""),
        action_beats=action_beats,
        camera_movement=str(row.camera_movement or "static"),
        start_state=str(row.start_state or ""),
        end_state=str(row.end_state or ""),
        motion_prompt=str(row.visual_prompt_motion or ""),
    )
    existing = _existing_result(meta)
    emotion_arc = structured.get("emotion_arc") if isinstance(structured.get("emotion_arc"), dict) else context.get("emotion_arc", {})
    intent_plan = build_shot_intent_plan(
        shot_purpose=getattr(row, "shot_purpose", "") or structured.get("shot_purpose") or context.get("shot_purpose") or "",
        core_action=structured.get("core_action") or context.get("core_action") or "",
        action_process=str(row.action_process or ""),
        action_beats=action_beats,
        emotion_arc=emotion_arc if isinstance(emotion_arc, dict) else {},
        start_state=str(row.start_state or structured.get("start_state") or context.get("start_state") or ""),
        end_state=str(row.end_state or structured.get("end_state") or context.get("end_state") or ""),
    )
    timing_plan = build_action_timing_plan(
        duration=row.duration,
        action_beats=action_beats,
        fallback_action=str(row.action_process or ""),
    )
    return {
        "book_id": row.book_id,
        "episode": row.episode,
        "shot_id": row.shot_id,
        "scene_name": row.scene_name,
        "duration": row.duration,
        "camera_movement": row.camera_movement,
        "action_process": str(row.action_process or ""),
        "action_beats": action_beats,
        "replay": result,
        "shot_intent_plan": intent_plan,
        "action_timing_plan": timing_plan,
        "stored_status": str(existing.get("status") or "") or None,
        "needs_recompile": not bool(existing),
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    required_intent = summary.get("required_intent_statuses") or []
    required_timing = summary.get("required_timing_statuses") or []
    missing_intent = summary.get("coverage_missing", {}).get("intent") or []
    missing_timing = summary.get("coverage_missing", {}).get("timing") or []
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
        f"- 要求最少镜头：{summary.get('required_minimum', 0) or '未设置'}",
        f"- 样本数量门禁：{'通过' if summary.get('meets_minimum', True) else '未通过'}",
        f"- 必需意图状态：{', '.join(required_intent) if required_intent else '未设置'}",
        f"- 必需节拍状态：{', '.join(required_timing) if required_timing else '未设置'}",
        f"- 状态覆盖门禁：{'通过' if summary.get('meets_required_coverage', True) else '未通过'}",
        f"- 缺少意图状态：{', '.join(missing_intent) if missing_intent else '无'}",
        f"- 缺少节拍状态：{', '.join(missing_timing) if missing_timing else '无'}",
        "- 发布阻塞：" + ("；".join(summary.get("release_blockers") or []) if summary.get("release_blockers") else "无"),
        "- 下一步：" + ("；".join(summary.get("next_actions") or []) if summary.get("next_actions") else "无"),
        f"- pass：{summary['status_counts'].get('pass', 0)}",
        f"- warning：{summary['status_counts'].get('warning', 0)}",
        f"- blocked：{summary['status_counts'].get('blocked', 0)}",
        f"- 意图规划 ready：{summary['intent_status_counts'].get('ready', 0)} / needs_information：{summary['intent_status_counts'].get('needs_information', 0)}",
        f"- 节拍规划 ready：{summary['timing_status_counts'].get('ready', 0)} / conflict：{summary['timing_status_counts'].get('conflict', 0)} / needs_information：{summary['timing_status_counts'].get('needs_information', 0)}",
        f"- 缺少已持久化结果、需受控重编译：{summary['needs_recompile']}",
        "",
        "## 优先治理清单",
        "",
        "| 镜头 | 时长 | 回放结果 | 意图 | 节拍 | 动作数 | 主要问题 | 建议 |",
        "| --- | ---: | --- | --- | --- | ---: | --- | --- |",
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
            f"| book {item['book_id']} / ep {item['episode']} / shot {item['shot_id']} | {item['duration']}s | {replay['status']} | {item['shot_intent_plan']['status']} | {item['action_timing_plan']['status']} | {replay['action_count']} | {findings} | {suggestions} |"
        )
    return "\n".join(lines) + "\n"


def _missing_required_statuses(
    counts: Counter[str] | dict[str, int], required: list[str]
) -> list[str]:
    """Return required statuses absent from a replay report.

    Status coverage is deliberately expressed as a generic contract instead of
    a book/shot/keyword rule.  This keeps the production gate honest when a
    sample set only contains happy-path shots.
    """
    return [status for status in required if int(counts.get(status, 0) or 0) <= 0]


def _build_gate_actions(
    *,
    sampled_shots: int,
    required_minimum: int,
    missing_intent: list[str],
    missing_timing: list[str],
) -> tuple[list[str], list[str]]:
    """Build generic, actionable release-gate output from observed evidence."""
    blockers: list[str] = []
    actions: list[str] = []
    if sampled_shots < required_minimum:
        blockers.append(f"真实 active 镜头不足（{sampled_shots}/{required_minimum}）")
        actions.append(f"补充真实 active 镜头，直到达到至少 {required_minimum} 个")
    if missing_intent:
        blockers.append(f"缺少意图状态：{', '.join(missing_intent)}")
        actions.append(f"在正式镜头工作台补齐意图证据：{', '.join(missing_intent)}")
    if missing_timing:
        blockers.append(f"缺少节拍状态：{', '.join(missing_timing)}")
        actions.append(f"在正式镜头工作台补齐节拍证据：{', '.join(missing_timing)}")
    if not blockers:
        actions.append("继续执行真实浏览器回归和受控媒体灰度")
    return blockers, actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--require-minimum",
        type=int,
        default=0,
        help="Require at least this many active real shots; report is still written before a non-zero exit.",
    )
    parser.add_argument(
        "--require-intent-status",
        action="append",
        default=[],
        help="Require at least one shot for each intent status (repeatable).",
    )
    parser.add_argument(
        "--require-timing-status",
        action="append",
        default=[],
        help="Require at least one shot for each action-timing status (repeatable).",
    )
    parser.add_argument("--book-id", type=int, action="append", dest="book_ids")
    parser.add_argument("--out", type=Path, default=ROOT_DIR / "artifacts" / "shot-executability-replay.json")
    args = parser.parse_args()
    if not args.book_ids:
        args.book_ids = _default_book_ids()
    init_db()
    with Session() as session:
        query = session.query(StoryboardShot)
        if args.book_ids:
            query = query.filter(StoryboardShot.book_id.in_(args.book_ids))
        rows = query.order_by(StoryboardShot.book_id.desc(), StoryboardShot.episode, StoryboardShot.shot_id).limit(max(1, args.limit)).all()
    shots = [_row_payload(row) for row in rows]
    status_counts = Counter(str(item["replay"].get("status") or "unknown") for item in shots)
    intent_status_counts = Counter(str(item["shot_intent_plan"].get("status") or "unknown") for item in shots)
    timing_status_counts = Counter(str(item["action_timing_plan"].get("status") or "unknown") for item in shots)
    missing_intent = _missing_required_statuses(intent_status_counts, args.require_intent_status)
    missing_timing = _missing_required_statuses(timing_status_counts, args.require_timing_status)
    meets_required_coverage = not missing_intent and not missing_timing
    release_blockers, next_actions = _build_gate_actions(
        sampled_shots=len(shots),
        required_minimum=max(0, args.require_minimum),
        missing_intent=missing_intent,
        missing_timing=missing_timing,
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only-deterministic-replay",
        "summary": {
            "sampled_shots": len(shots),
            "required_minimum": max(0, args.require_minimum),
            "meets_minimum": len(shots) >= max(0, args.require_minimum),
            "required_intent_statuses": list(dict.fromkeys(args.require_intent_status)),
            "required_timing_statuses": list(dict.fromkeys(args.require_timing_status)),
            "meets_required_coverage": meets_required_coverage,
            "coverage_missing": {"intent": missing_intent, "timing": missing_timing},
            "status_counts": dict(status_counts),
            "intent_status_counts": dict(intent_status_counts),
            "timing_status_counts": dict(timing_status_counts),
            "needs_recompile": sum(1 for item in shots if item["needs_recompile"]),
            "release_blockers": release_blockers,
            "next_actions": next_actions,
        },
        "shots": shots,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.out.with_suffix(".md")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"report": str(args.out), "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["summary"]["meets_minimum"] and meets_required_coverage else 2


if __name__ == "__main__":
    raise SystemExit(main())
