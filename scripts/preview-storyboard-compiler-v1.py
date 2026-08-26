"""Preview Prompt Compiler V1 pipeline for real storyboard shots without DB writes.

This script intentionally performs a read-only pass:

StoryboardShot -> structured_shot auto binding -> Prompt IR -> Rule Compiler
-> Model Adapter baseline.

It does not call an LLM and does not persist any prompt/version changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.server import (
    _auto_bind_structured_shot_assets,
    _build_prompt_compile_context_v2,
    _build_storyboard_reference_summary,
    _build_storyboard_reference_summary_from_bound_assets,
    _derive_structured_shot_payload,
    _load_asset_links,
    safe_json_loads,
)
from core.model_adapter import adapt_ir_to_model
from core.prompt_ir import build_shot_ir_from_context, serialize_shot_ir
from core.rule_compiler import compile_rules
from models import Session, StoryboardShot


def _shot_seed(shot: StoryboardShot) -> dict[str, Any]:
    return {
        "shot_id": str(shot.shot_id),
        "scene_name": str(shot.scene_name or "").strip(),
        "duration": int(shot.duration or 3),
        "camera_angle": str(shot.camera_angle or "MS").strip(),
        "camera_movement": str(shot.camera_movement or "static").strip(),
        "transition": str(shot.transition or "cut").strip(),
        "start_state": str(shot.start_state or "").strip(),
        "action_process": str(shot.action_process or "").strip(),
        "end_state": str(shot.end_state or "").strip(),
        "dialogue": str(shot.dialogue or "").strip(),
        "style_key": "default",
    }


def preview_shot(book_id: int, shot: StoryboardShot, target_model: str) -> dict[str, Any]:
    meta_info = safe_json_loads(shot.meta_info) if shot.meta_info else {}
    if not isinstance(meta_info, dict):
        meta_info = {}

    seed = _shot_seed(shot)
    structured = _auto_bind_structured_shot_assets(
        book_id,
        int(shot.episode),
        _derive_structured_shot_payload(meta_info, seed),
        seed,
    )
    asset_link_summary = _build_storyboard_reference_summary(
        _load_asset_links(shot.asset_links),
        str(shot.scene_name or "").strip(),
    )
    compile_context = _build_prompt_compile_context_v2(
        book_id,
        shot,
        structured,
        {},
        asset_link_summary,
    )
    compile_context["target_model"] = target_model
    compile_context["reference_summary"] = _build_storyboard_reference_summary_from_bound_assets(
        compile_context.get("bound_assets", []),
        str(compile_context.get("scene_name") or shot.scene_name or "").strip(),
    )

    shot_ir = build_shot_ir_from_context(compile_context)
    shot_ir = compile_rules(shot_ir, compile_context.get("production_skill", {}))
    shot_ir_payload = serialize_shot_ir(shot_ir)
    adapter_output = adapt_ir_to_model(shot_ir, target_model)

    return {
        "book_id": book_id,
        "episode": int(shot.episode),
        "shot_id": int(shot.shot_id),
        "scene_name": str(shot.scene_name or "").strip(),
        "current_prompts": {
            "static": str(shot.visual_prompt_static or "").strip(),
            "motion": str(shot.visual_prompt_motion or "").strip(),
            "final": str(shot.visual_prompt_final or "").strip(),
        },
        "current_prompt_lengths": {
            "static": len(str(shot.visual_prompt_static or "").strip()),
            "motion": len(str(shot.visual_prompt_motion or "").strip()),
            "final": len(str(shot.visual_prompt_final or "").strip()),
        },
        "structured_shot": structured,
        "shot_ir": shot_ir_payload,
        "model_adapter": adapter_output,
        "bound_asset_count": len(compile_context.get("bound_assets", [])),
        "reference_image_count": len(compile_context.get("reference_images", [])),
        "warnings": compile_context.get("warnings", []),
    }


def _count_replacement_chars(value: Any) -> int:
    if isinstance(value, str):
        return value.count("\ufffd")
    if isinstance(value, list):
        return sum(_count_replacement_chars(item) for item in value)
    if isinstance(value, dict):
        return sum(_count_replacement_chars(item) for item in value.values())
    return 0


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    shots = result.get("shots", [])
    static_lengths = [
        int((shot.get("current_prompt_lengths") or {}).get("static") or 0)
        for shot in shots
    ]
    motion_lengths = [
        int((shot.get("current_prompt_lengths") or {}).get("motion") or 0)
        for shot in shots
    ]
    adapter_static_lengths = [
        len(str((shot.get("model_adapter") or {}).get("static_prompt") or "").strip())
        for shot in shots
    ]
    adapter_motion_lengths = [
        len(str((shot.get("model_adapter") or {}).get("motion_prompt") or "").strip())
        for shot in shots
    ]
    warning_total = sum(len(shot.get("warnings") or []) for shot in shots)
    zero_reference_shots = [
        f"{shot.get('episode')}-{shot.get('shot_id')}"
        for shot in shots
        if int(shot.get("reference_image_count") or 0) == 0
    ]
    warning_texts: dict[str, int] = {}
    for shot in shots:
        for warning in shot.get("warnings") or []:
            warning_texts[str(warning)] = warning_texts.get(str(warning), 0) + 1
    return {
        "current_static_min": min(static_lengths) if static_lengths else 0,
        "current_motion_min": min(motion_lengths) if motion_lengths else 0,
        "current_static_lt_80": sum(1 for length in static_lengths if length < 80),
        "current_motion_lt_80": sum(1 for length in motion_lengths if length < 80),
        "adapter_static_min": min(adapter_static_lengths) if adapter_static_lengths else 0,
        "adapter_motion_min": min(adapter_motion_lengths) if adapter_motion_lengths else 0,
        "warning_total": warning_total,
        "warning_texts": warning_texts,
        "zero_reference_shots": zero_reference_shots,
        "replacement_char_total": _count_replacement_chars(result),
    }


def _trim(text: str, limit: int = 260) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}…"


def render_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary") or _summarize(result)
    lines = [
        f"# Book {result.get('book_id')} Prompt Compiler V1 只读预览",
        "",
        f"- 模式：{result.get('mode')}",
        f"- 目标模型：{result.get('target_model')}",
        f"- 分镜数：{result.get('shot_count')}",
        f"- 当前静态提示词低于 80 字：{summary.get('current_static_lt_80')}",
        f"- 当前动态提示词低于 80 字：{summary.get('current_motion_lt_80')}",
        f"- Adapter 静态提示词最短长度：{summary.get('adapter_static_min')}",
        f"- Adapter 动态提示词最短长度：{summary.get('adapter_motion_min')}",
        f"- 预览文本替换符 `U+FFFD` 数量：{summary.get('replacement_char_total')}",
        f"- 编译警告总数：{summary.get('warning_total')}",
        "",
        "## 警告聚合",
        "",
    ]
    warning_texts = summary.get("warning_texts") or {}
    if warning_texts:
        for warning, count in sorted(warning_texts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {warning} × {count}")
    else:
        lines.append("- 无")
    lines.extend(["", "## 分镜逐条预览", ""])
    for shot in result.get("shots", []):
        current_prompts = shot.get("current_prompts") or {}
        adapter = shot.get("model_adapter") or {}
        lengths = shot.get("current_prompt_lengths") or {}
        warnings = shot.get("warnings") or []
        shot_label = f"E{shot.get('episode')}-S{shot.get('shot_id')}"
        lines.extend(
            [
                f"### {shot_label}｜{shot.get('scene_name')}",
                "",
                f"- 绑定资产数：{shot.get('bound_asset_count')}；参考图数：{shot.get('reference_image_count')}",
                f"- 当前提示词长度：静态 {lengths.get('static')} / 动态 {lengths.get('motion')} / final {lengths.get('final')}",
                f"- 警告：{'；'.join(warnings) if warnings else '无'}",
                "",
                "当前静态提示词：",
                "",
                f"> {_trim(current_prompts.get('static'))}",
                "",
                "当前动态提示词：",
                "",
                f"> {_trim(current_prompts.get('motion'))}",
                "",
                "Adapter 静态基线：",
                "",
                f"> {_trim(adapter.get('static_prompt'))}",
                "",
                "Adapter 动态基线：",
                "",
                f"> {_trim(adapter.get('motion_prompt'))}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview Prompt Compiler V1 pipeline without writing DB.")
    parser.add_argument("--book-id", type=int, default=75)
    parser.add_argument("--episode", type=int, default=None)
    parser.add_argument("--target-model", default="jimeng")
    parser.add_argument("--out", default="")
    parser.add_argument("--summary-md", default="")
    args = parser.parse_args()

    with Session() as session:
        query = session.query(StoryboardShot).filter(StoryboardShot.book_id == args.book_id)
        if args.episode is not None:
            query = query.filter(StoryboardShot.episode == args.episode)
        shots = query.order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc()).all()
        result = {
            "mode": "readonly_preview",
            "book_id": args.book_id,
            "target_model": args.target_model,
            "shot_count": len(shots),
            "shots": [preview_shot(args.book_id, shot, args.target_model) for shot in shots],
        }
        result["summary"] = _summarize(result)

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(str(out_path))
    else:
        print(payload)
    if args.summary_md:
        summary_path = Path(args.summary_md)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(render_markdown(result), encoding="utf-8")
        print(str(summary_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
