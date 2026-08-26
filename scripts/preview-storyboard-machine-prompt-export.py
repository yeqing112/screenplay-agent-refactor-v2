"""Preview director-shot to machine-prompt exports for real storyboard shots.

Read-only pipeline:

StoryboardShot -> structured shot auto binding -> Prompt IR -> Rule Compiler
-> Director Shot Text -> Machine Prompt -> Model/WebUI export preview.

No DB writes, no LLM calls, no API submissions.
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
from core.machine_prompt import (
    build_director_shot_text,
    compile_machine_prompt,
    export_generic_zh_video_webui,
    export_machine_prompt,
    export_minimax_h3_webui,
)
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


def preview_shot_export(book_id: int, shot: StoryboardShot, target_model: str) -> dict[str, Any]:
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
    director_text = build_director_shot_text(shot_ir)
    machine_prompt = compile_machine_prompt(
        shot_ir,
        reference_images=compile_context.get("reference_images", []),
        reference_summary=compile_context.get("reference_summary", ""),
        director_shot_text=director_text,
    )
    target_export = export_machine_prompt(machine_prompt, target_model)

    return {
        "book_id": book_id,
        "episode": int(shot.episode),
        "shot_id": int(shot.shot_id),
        "scene_name": str(shot.scene_name or "").strip(),
        "source_layers": {
            "director_shot_text_is_user_editable": True,
            "machine_prompt_is_compiled": True,
            "model_export_is_submission_ready_but_not_submitted": True,
        },
        "director_shot_text": director_text,
        "structured_shot": structured,
        "shot_ir": serialize_shot_ir(shot_ir),
        "machine_prompt": machine_prompt,
        "model_exports": {
            target_model: target_export,
            "minimax-h3": export_minimax_h3_webui(machine_prompt),
            "generic-zh-video": export_generic_zh_video_webui(machine_prompt),
        },
        "bound_asset_count": len(compile_context.get("bound_assets", [])),
        "reference_image_count": len(compile_context.get("reference_images", [])),
        "warnings": compile_context.get("warnings", []),
    }


def _trim(text: object, limit: int = 420) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit - 1]}…"


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    shots = result.get("shots") or []
    reference_counts = [int(shot.get("reference_image_count") or 0) for shot in shots]
    h3_lengths = []
    for shot in shots:
        h3 = ((shot.get("model_exports") or {}).get("minimax-h3") or {}).get("fields") or {}
        h3_lengths.append(len(str(h3.get("integrated_multimodal_description") or "")))
    return {
        "shot_count": len(shots),
        "api_submission": False,
        "reference_image_total": sum(reference_counts),
        "zero_reference_shots": [
            f"{shot.get('episode')}-{shot.get('shot_id')}"
            for shot in shots
            if int(shot.get("reference_image_count") or 0) == 0
        ],
        "h3_integrated_description_min_length": min(h3_lengths) if h3_lengths else 0,
        "export_modes": ["minimax-h3 webui_copy", "generic-zh-video webui_copy"],
    }


def render_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary") or _summarize(result)
    lines = [
        f"# Book {result.get('book_id')} 机器提示词导出只读预览",
        "",
        f"- 模式：{result.get('mode')}",
        f"- 目标模型：{result.get('target_model')}",
        f"- 分镜数：{summary.get('shot_count')}",
        f"- API 提交：{summary.get('api_submission')}（本预览只导出，不提交）",
        f"- 参考图总数：{summary.get('reference_image_total')}",
        f"- H3 integrated 描述最短长度：{summary.get('h3_integrated_description_min_length')}",
        f"- 导出模式：{', '.join(summary.get('export_modes') or [])}",
        "",
        "## 分镜逐条预览",
        "",
    ]
    for shot in result.get("shots") or []:
        h3 = (((shot.get("model_exports") or {}).get("minimax-h3") or {}).get("fields") or {})
        generic = ((shot.get("model_exports") or {}).get("generic-zh-video") or {}).get("prompt")
        machine = shot.get("machine_prompt") or {}
        shot_label = f"E{shot.get('episode')}-S{shot.get('shot_id')}"
        lines.extend(
            [
                f"### {shot_label}｜{shot.get('scene_name')}",
                "",
                f"- 绑定资产数：{shot.get('bound_asset_count')}；参考图数：{shot.get('reference_image_count')}",
                f"- 导演分镜可编辑：{(shot.get('source_layers') or {}).get('director_shot_text_is_user_editable')}",
                f"- 机器提示词提交 API：{machine.get('api_submission')}",
                "",
                "导演分镜语言：",
                "",
                "```text",
                _trim(shot.get("director_shot_text"), 900),
                "```",
                "",
                "MiniMax H3 / WebUI 导出：",
                "",
                "```text",
                "integrated_multimodal_description:",
                _trim(h3.get("integrated_multimodal_description"), 1200),
                "",
                "overall_soundscape:",
                _trim(h3.get("overall_soundscape"), 500),
                "",
                "non_diegetic_music:",
                _trim(h3.get("non_diegetic_music"), 500),
                "```",
                "",
                "通用中文视频 WebUI 导出：",
                "",
                "```text",
                _trim(generic, 1200),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview machine prompt exports without writing DB.")
    parser.add_argument("--book-id", type=int, default=75)
    parser.add_argument("--episode", type=int, default=None)
    parser.add_argument("--target-model", default="minimax-h3")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default="")
    parser.add_argument("--summary-md", default="")
    args = parser.parse_args()

    with Session() as session:
        query = session.query(StoryboardShot).filter(StoryboardShot.book_id == args.book_id)
        if args.episode is not None:
            query = query.filter(StoryboardShot.episode == args.episode)
        query = query.order_by(StoryboardShot.episode.asc(), StoryboardShot.shot_id.asc())
        if args.limit and args.limit > 0:
            query = query.limit(args.limit)
        shots = query.all()
        result = {
            "mode": "readonly_machine_prompt_export_preview",
            "book_id": args.book_id,
            "target_model": args.target_model,
            "shots": [preview_shot_export(args.book_id, shot, args.target_model) for shot in shots],
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
