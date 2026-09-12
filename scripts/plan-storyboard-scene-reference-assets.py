"""Plan production scene reference assets for real storyboard books.

This command is intentionally read-only. It turns existing storyboard shots
and VisualLocation draft rows into a reviewable scene-reference plan:

- formal scene description candidates
- reference image generation prompts
- API request drafts for /api/prototyping/generate-reference-image

It does not enqueue generation tasks and does not write DB rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.server import (
    _build_scene_asset_prompt_contract,
    _flatten_scene_layer_text,
    _build_scene_reference_negative_prompt,
    SCENE_REFERENCE_MODE_REQUIREMENT,
    SCENE_REFERENCE_STYLE_REQUIREMENT,
    SCENE_REFERENCE_VIEW_SCHEMA,
    _normalize_scene_asset_id,
)
from api.model_registry import get_default_profile
from core.scene_reference_plan import scene_location_fingerprint, scene_location_snapshot
from models import Session, StoryboardShot, VisualLocation, VisualReferenceAsset, init_db


DEFAULT_NEGATIVE_PROMPT = "低质量，模糊，畸变，字幕，水印，logo，过曝，欠曝，透视错误，空间错乱，现代广告大字干扰"
BANNED_SCENE_REFERENCE_FRAGMENTS = (
    "2行2列",
    "四格",
    "四等分",
    "每个格子",
    "多视角",
    "大全景视角",
    "人物",
    "面部",
    "瞳孔",
    "手部",
    "手指",
    "照片",
    "海报",
    "标题",
    "台词",
    "对白",
    "画面切到",
    "镜头切到",
)


def _clean(text: Any) -> str:
    return " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())


def _sentence(text: Any) -> str:
    value = _clean(text)
    if not value:
        return ""
    return value if value.endswith(("。", "！", "？", ".", "!", "?")) else f"{value}。"


def _join_unique(values: list[str], limit: int = 6) -> str:
    seen: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text not in seen:
            seen.append(text)
    return "；".join(seen[:limit])


def _split_scene_fragments(text: str) -> list[str]:
    normalized = _clean(text).replace("。", "；").replace("，", "；")
    return [part.strip(" ；。") for part in normalized.split("；") if part.strip(" ；。")]


def _safe_scene_text(text: str, *, limit: int = 8) -> str:
    parts = []
    for part in _split_scene_fragments(text):
        if any(fragment in part for fragment in BANNED_SCENE_REFERENCE_FRAGMENTS):
            continue
        parts.append(part)
    return "；".join(parts[: max(0, int(limit))])


def _negative_prompt(location: VisualLocation) -> str:
    return _build_scene_reference_negative_prompt(_clean(location.negative_prompt) or DEFAULT_NEGATIVE_PROMPT)


def _is_placeholder_scene_description(location: VisualLocation) -> bool:
    """Return whether the stored description is an import/readiness placeholder.

    Placeholder text is operational metadata, not a visual fact.  It must not
    leak into the production prompt when a plan is compiled.  The check is
    marker-based and applies to any scene/book; it does not depend on a scene
    name or a particular story.
    """
    description = _clean(getattr(location, "description", ""))
    notes = _clean(getattr(location, "notes", ""))
    return (
        "最小场景资产" in description
        or "requires-human-asset-refinement" in notes
        or "scene-reference-plan-applied" in notes
    )


def _shot_label(shot: StoryboardShot) -> str:
    return f"{int(shot.episode or 1)}-{int(shot.shot_id)}"


def _story_samples(shots: list[StoryboardShot]) -> list[str]:
    samples: list[str] = []
    for shot in shots:
        action = _clean(shot.action_process or shot.start_state or shot.end_state)
        if action:
            samples.append(f"{_shot_label(shot)}：{action}")
    return samples[:5]


def _infer_scene_design(scene_name: str, shots: list[StoryboardShot], location: VisualLocation) -> dict[str, str]:
    # Build every scene from its own structured asset fields and storyboard
    # evidence.  No scene name is special-cased: new books follow the same
    # path as existing books.
    contract = _build_scene_asset_prompt_contract(location)
    semantic_layers = contract.get("structured_variant_fields", {}).get("semantic_layers", {})
    canonical = semantic_layers.get("canonical", {}) if isinstance(semantic_layers, dict) else {}
    state = semantic_layers.get("state", {}) if isinstance(semantic_layers, dict) else {}
    look = semantic_layers.get("look", {}) if isinstance(semantic_layers, dict) else {}
    # A storyboard shot is evidence for shot planning, not authority for the
    # reusable scene asset.  Do not infer scene lighting from a shot's
    # lighting field: doing so would silently promote a temporary shot look
    # (for example "雨夜" or a dramatic key light) into the canonical scene
    # reference prompt.  Only explicit scene State/legacy scene fields may
    # contribute here; the formal API contract remains the single renderer.
    lighting = _safe_scene_text(_flatten_scene_layer_text(state.get("lighting", "")), limit=3) or _safe_scene_text(getattr(location, "lighting_mood", ""), limit=3)
    color_palette = _safe_scene_text(_flatten_scene_layer_text(look.get("palette", "")), limit=2) or _safe_scene_text(getattr(location, "color_palette", ""), limit=2)
    style = _safe_scene_text(_flatten_scene_layer_text(look.get("style", "")), limit=2) or _safe_scene_text(getattr(location, "style", ""), limit=2)
    scene_mood = _safe_scene_text(getattr(location, "scene_mood_zh", ""), limit=2)
    time_period = _clean(getattr(location, "time_period", ""))
    key_props_raw = getattr(location, "key_props", "")
    try:
        key_props = json.loads(key_props_raw) if isinstance(key_props_raw, str) else key_props_raw
    except (TypeError, ValueError):
        key_props = []
    if not isinstance(key_props, list):
        key_props = []
    key_props_text = "、".join(_clean(item) for item in key_props if _clean(item))
    camera_angles = _join_unique([str(shot.camera_angle or "") for shot in shots if str(shot.camera_angle or "").strip()], limit=4)
    camera_movements = _join_unique([str(shot.camera_movement or "") for shot in shots if str(shot.camera_movement or "").strip()], limit=4)
    actions = _join_unique([str(shot.action_process or "") for shot in shots], limit=4)
    base = _safe_scene_text(_flatten_scene_layer_text(canonical)) or f"{scene_name}，依据资产字段和真实分镜证据整理的场景空间。"
    formal_parts = [f"{scene_name}。{_sentence(base)}"]
    if key_props_text:
        formal_parts.append(_sentence(f"固定陈设：{key_props_text}"))
    if lighting:
        formal_parts.append(_sentence(f"光线氛围：{lighting}"))
    if color_palette:
        formal_parts.append(_sentence(f"色彩基调：{color_palette}"))
    if time_period:
        formal_parts.append(_sentence(f"时代与环境质感：{time_period}"))
    formal_description = " ".join(formal_parts).strip()
    reference_prompt = contract.get("rendered_prompt_preview") or f"{scene_name} 场景参考图，{SCENE_REFERENCE_MODE_REQUIREMENT}"

    return {
        "formal_description": formal_description,
        "lighting_mood": lighting,
        "camera_summary": "；".join(part for part in [camera_angles, camera_movements] if part),
        "action_summary": actions,
        "reference_layout": "2x2_four_view",
        "reference_view_schema": [dict(item) for item in SCENE_REFERENCE_VIEW_SCHEMA],
        "reference_prompt": reference_prompt,
        "negative_prompt": contract.get("reference_negative_prompt") or _negative_prompt(location),
    }


def _reference_stats(references: list[VisualReferenceAsset]) -> dict[str, int]:
    statuses = Counter(str(row.status or "").strip() or "candidate" for row in references)
    return {
        "total": len(references),
        "image_count": sum(1 for row in references if _clean(row.image_url) or _clean(row.local_path)),
        "candidate": statuses.get("candidate", 0),
        "selected": statuses.get("selected", 0),
        "locked": statuses.get("locked", 0),
        "rejected": statuses.get("rejected", 0),
    }


def _production_issues(scene_name: str, location: VisualLocation, references: list[VisualReferenceAsset]) -> list[str]:
    stats = _reference_stats(references)
    asset_status = _clean(location.asset_status) or "draft"
    description = _clean(location.description)
    visual_prompt = _clean(location.visual_prompt_zh or location.core_prompt_zh)
    notes = _clean(location.notes)
    issues: list[str] = []
    if asset_status in {"draft", "pending"}:
        issues.append(f"场景资产状态仍为 {asset_status}")
    if "最小场景资产" in description or "requires-human-asset-refinement" in notes:
        issues.append("场景资产仍使用分镜派生的 draft 描述")
    if scene_name and scene_name not in f"{description} {visual_prompt}":
        issues.append("场景资产描述未包含精确分镜场景名")
    if stats["selected"] + stats["locked"] <= 0 or stats["image_count"] <= 0:
        issues.append("场景资产没有 selected/locked 参考图")
    return issues


def _confirmation_token(items: list[dict[str, Any]]) -> str:
    payload = [
        {
            "scene_name": item.get("scene_name"),
            "location_id": item.get("location_id"),
            "api_request": (item.get("reference_generation") or {}).get("api_request"),
        }
        for item in items
        if item.get("status") == "planned"
    ]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def plan_book(book_id: int, model_profile_id: str | None = None) -> dict[str, Any]:
    # Resolve the image provider from the same model registry used by the
    # production workspace.  Keeping a historical provider id as the default
    # would make a read-only plan silently diverge from the active image model.
    if not model_profile_id:
        profile = get_default_profile("image")
        model_profile_id = str(profile.get("id") or "") if profile else ""
    if not model_profile_id:
        raise RuntimeError("当前没有可用的默认图片模型，无法生成场景参考图计划。")
    with Session() as session:
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
        references = (
            session.query(VisualReferenceAsset)
            .filter(VisualReferenceAsset.book_id == book_id)
            .order_by(VisualReferenceAsset.id.asc())
            .all()
        )

    references_by_scene_id: dict[str, list[VisualReferenceAsset]] = {}
    for row in references:
        if str(row.asset_type or "").strip() == "scene":
            references_by_scene_id.setdefault(str(row.asset_id or "").strip(), []).append(row)

    shots_by_scene: dict[str, list[StoryboardShot]] = {}
    for shot in shots:
        shots_by_scene.setdefault(_clean(shot.scene_name), []).append(shot)

    locations_by_id = {str(row.id): row for row in locations}
    items: list[dict[str, Any]] = []
    for scene_name, scene_shots in sorted(shots_by_scene.items(), key=lambda item: item[0]):
        location_id = _normalize_scene_asset_id(book_id, scene_name)
        location = locations_by_id.get(str(location_id)) if location_id else None
        if location is None:
            items.append({
                "scene_name": scene_name,
                "status": "missing_visual_location",
                "shot_count": len(scene_shots),
                "shot_ids": [_shot_label(shot) for shot in scene_shots],
                "issues": ["缺失 VisualLocation 场景资产"],
            })
            continue

        scene_refs = references_by_scene_id.get(str(location.id), [])
        issues = _production_issues(scene_name, location, scene_refs)
        design = _infer_scene_design(scene_name, scene_shots, location)
        episode = int(scene_shots[0].episode or 1)
        request_payload = {
            "bookId": book_id,
            "episode": episode,
            "shotId": f"scene-{location.id}",
            "sourceNodeId": f"visual-location-{location.id}",
            "sourceAssetId": str(location.id),
            "assetScope": "location",
            "assetSubject": scene_name,
            "targetKind": "reference-image",
            "modelProfileId": model_profile_id,
            "prompt": design["reference_prompt"],
            "negativePrompt": design["negative_prompt"],
            "aspectRatio": "16:9",
            "count": 1,
            "referenceAssetIds": [],
            "referenceImages": [],
        }
        visual_asset_patch = {
            "asset_status": "ref_ready",
            "negative_prompt": design["negative_prompt"],
            "jimeng_ref_name": f"@{scene_name}",
            "shot_ids": [_shot_label(shot) for shot in scene_shots],
        }
        items.append({
            "scene_name": scene_name,
            "location_id": int(location.id),
            "status": "planned" if issues else "already_ready",
            "issues": issues,
            "shot_count": len(scene_shots),
            "shot_ids": [_shot_label(shot) for shot in scene_shots],
            "story_samples": _story_samples(scene_shots),
            "current_asset": {
                "asset_status": _clean(location.asset_status) or "draft",
                "description": _clean(location.description),
                "visual_prompt_zh": _clean(location.visual_prompt_zh),
                "notes": _clean(location.notes),
            },
            "source_snapshot": scene_location_snapshot(location),
            "source_fingerprint": scene_location_fingerprint(location),
            "reference_stats": _reference_stats(scene_refs),
            "planned_asset_update": {
                "formal_description": design["formal_description"],
                "lighting_mood": design["lighting_mood"],
                "camera_summary": design["camera_summary"],
                "action_summary": design["action_summary"],
                "reference_layout": design["reference_layout"],
                "reference_view_schema": design["reference_view_schema"],
                "visual_asset_patch": visual_asset_patch,
            },
            "reference_generation": {
                "prompt": design["reference_prompt"],
                "negative_prompt": design["negative_prompt"],
                "api_request": request_payload,
            },
        })

    planned = [item for item in items if item.get("status") == "planned"]
    plan = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "readonly-scene-reference-plan",
        "book_id": book_id,
        "summary": {
            "storyboard_shots": len(shots),
            "visual_locations": len(locations),
            "visual_reference_assets": len(references),
            "scene_names": len(items),
            "planned_scene_references": len(planned),
            "affected_shots": sum(int(item.get("shot_count") or 0) for item in planned),
        },
        "items": items,
    }
    plan["confirmationToken"] = _confirmation_token(items)
    return plan


def _escape_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def render_markdown(plan: dict[str, Any]) -> str:
    summary = plan.get("summary") or {}
    lines = [
        f"# Book {plan.get('book_id')} 场景参考图生产计划",
        "",
        f"- 生成时间：{plan.get('generatedAt')}",
        f"- 模式：{plan.get('mode')} / 只读，未生成图片，未写库",
        f"- 确认令牌：`{plan.get('confirmationToken')}`",
        f"- 分镜镜头数：{summary.get('storyboard_shots')}",
        f"- 场景资产数：{summary.get('visual_locations')}",
        f"- 参考资产数：{summary.get('visual_reference_assets')}",
        f"- 需规划场景参考图：{summary.get('planned_scene_references')}",
        f"- 影响镜头：{summary.get('affected_shots')}",
        "",
        "## 场景汇总",
        "",
        "| 场景 | 资产ID | 状态 | 镜头数 | 参考图 | 问题 |",
        "| --- | ---: | --- | ---: | ---: | --- |",
    ]
    for item in plan.get("items", []):
        stats = item.get("reference_stats") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(item.get("scene_name")),
                    _escape_cell(item.get("location_id", "")),
                    _escape_cell(item.get("status")),
                    str(item.get("shot_count") or 0),
                    str(stats.get("image_count") or 0),
                    _escape_cell("；".join(item.get("issues") or [])),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 逐场景计划", ""])
    for item in plan.get("items", []):
        planned = item.get("planned_asset_update") or {}
        generation = item.get("reference_generation") or {}
        lines.extend(
            [
                f"### {item.get('scene_name')}｜资产 {item.get('location_id', '')}",
                "",
                f"- 状态：{item.get('status')}",
                f"- 影响镜头：{', '.join(item.get('shot_ids') or [])}",
                f"- 问题：{'；'.join(item.get('issues') or []) or '无'}",
                "",
                "正式场景描述候选：",
                "",
                f"> {planned.get('formal_description', '')}",
                "",
                "参考图生成提示词：",
                "",
                f"> {generation.get('prompt', '')}",
                "",
                "负向提示词：",
                "",
                f"> {generation.get('negative_prompt', '')}",
                "",
                "代表性分镜动作：",
                "",
            ]
        )
        samples = item.get("story_samples") or []
        if samples:
            for sample in samples:
                lines.append(f"- {sample}")
        else:
            lines.append("- 无")
        lines.extend(["", "API 请求草案：", "", "```json", json.dumps(generation.get("api_request") or {}, ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan scene reference assets without writes.")
    parser.add_argument("--book-id", type=int, default=75)
    parser.add_argument("--out", default="")
    parser.add_argument("--summary-md", default="")
    parser.add_argument("--model-profile-id", default=None)
    args = parser.parse_args()

    init_db()
    plan = plan_book(args.book_id, args.model_profile_id)
    payload = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(str(out_path))
    else:
        print(payload)
    if args.summary_md:
        md_path = Path(args.summary_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(plan), encoding="utf-8")
        print(str(md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
