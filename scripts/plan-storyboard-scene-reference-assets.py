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
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.server import _normalize_scene_asset_id
from models import Session, StoryboardShot, VisualLocation, VisualReferenceAsset, init_db


DEFAULT_NEGATIVE_PROMPT = "低质量，模糊，畸变，字幕，水印，logo，过曝，欠曝，透视错误，空间错乱，现代广告大字干扰"
SCENE_REFERENCE_NEGATIVE_TERMS = "人物，人脸，人形，角色，分格，拼图，多宫格，四宫格，多视角排版，文字说明"
SCENE_REFERENCE_MODE_REQUIREMENT = (
    "单张 16:9 横构图，无人物、无人脸、不出现角色。"
    "画面必须是一张完整场景参考图，不分格、不拼图、不做多视角排版。"
)
SCENE_DESIGN_PRESETS: dict[str, dict[str, str]] = {
    "便利店收银台": {
        "description": (
            "深夜便利店收银区，狭窄收银台位于画面中心，台面有扫码器、香烟展示架、小票机和一杯冰美式；"
            "两侧货架向后延伸，玻璃门外是黑暗街道，门上悬着小风铃。冷白荧光灯从头顶压下，商品标签反光刺眼。"
        ),
        "lighting": "冷白荧光灯顶光，低饱和、硬阴影、深夜悬疑短剧质感。",
    },
    "监控室": {
        "description": (
            "便利店后方狭小监控室，墙面布满监控屏，桌面有老旧主机、键盘、鼠标、杂乱线缆、塑料包装和饮料杯；"
            "角落堆放纸箱和清洁工具，空间封闭压抑。"
        ),
        "lighting": "主要光源来自蓝绿色监控屏幕和主机指示灯，昏暗、轻微屏幕噪点、悬疑电影感。",
    },
    "原始丛林上空": {
        "description": (
            "原始丛林上空与树冠层，远处是连绵墨绿色森林海，近处巨大树冠互相挤压，中间露出一块泥泞林间空地；"
            "树冠缝隙中有雾气、断枝、藤蔓和斑驳光束，空间纵深从高空一路落到林地。"
        ),
        "lighting": "正午阳光穿透浓密树冠，形成强烈明暗反差和潮湿雾气中的光柱。",
    },
    "原始丛林深处": {
        "description": (
            "原始森林深处，古树参天，粗大树根盘绕泥地，藤蔓从高处垂落，蕨类植物和灌木遮住林间小路；"
            "地面潮湿、覆盖枯叶苔藓，零散灰白兽骨半埋在泥中。"
        ),
        "lighting": "树冠遮蔽下的斑驳顶光，墨绿与棕褐主色，阴影深重、潮湿原始。",
    },
    "部落营地": {
        "description": (
            "原始部落营地位于茂密森林中，几棵巨大冷杉树之间搭建树屋平台，藤蔓编织屋顶，兽皮帘垂挂；"
            "地面有圆形石砌火塘、石墩、木栅栏、窝棚和图腾柱。"
        ),
        "lighting": "林间正午散射光与火塘残余暖色共同塑造原始、粗粝、仪式感强的氛围。",
    },
    "公立医院病房": {
        "description": (
            "普通公立医院病房，白色瓷砖墙面、淡蓝色窗帘、冷白日光灯管，两张病床和金属输液架整齐排列；"
            "浅色防滑砖地面、床头柜、监护仪与消毒水气味共同形成冰冷整洁的空间。"
        ),
        "lighting": "冷白顶光为主，少量淡蓝窗帘反光，干净但缺乏温度。",
    },
    "地下赌场VIP包厢": {
        "description": (
            "地下赌场 VIP 包厢，深色木质护墙板、绿色赌桌、高背皮质沙发、酒柜吧台和暗红地毯构成封闭空间；"
            "空气中有烟雾，桌面筹码和酒杯形成危险、奢靡的地下氛围。"
        ),
        "lighting": "暗红霓虹与绿色赌桌射灯混合，烟雾形成光束，压抑危险。",
    },
    "宋氏大厦顶层办公室": {
        "description": (
            "高层写字楼顶层办公室，整面落地玻璃幕墙外是城市天际线，室内有极简办公桌、黑色沙发区、深灰大理石地面；"
            "无主灯间接照明和开阔尺度形成冷峻权力感。"
        ),
        "lighting": "落地窗冷调自然光结合隐形线性灯，桌面和地面有克制反光。",
    },
    "现代简约别墅客厅": {
        "description": (
            "现代极简别墅客厅，大面积落地玻璃门、白色墙面、冷灰大理石地面、白色沙发、黑色茶几和悬挑楼梯；"
            "空间开阔、昂贵、冷清，家具线条克制。"
        ),
        "lighting": "自然光从玻璃门倾泻而入，间接照明补充层次，整体明亮清冷。",
    },
    "高端私人会所走廊": {
        "description": (
            "高端私人会所走廊，深色木饰面墙、暗红地毯、一排厚重木门、装饰画和水晶壁灯沿走廊延伸；"
            "空间狭长、私密、奢华，尽头门缝可透出一线冷光。"
        ),
        "lighting": "暖黄壁灯与远端冷白门缝形成冷暖对比，暧昧且带窒息感。",
    },
    "陈二蛋与大凤的卧室": {
        "description": (
            "湘西吊脚楼二层卧室，木梁与竹席天花板裸露，两张硬板床分列两侧，稻草薄被凌乱，中间小木柜放着油灯；"
            "破损窗纸和木窗棂在地板上投下几何阴影。"
        ),
        "lighting": "惨白月光从南窗射入，室内冷蓝紫阴影浓重，乡土恐怖氛围。",
    },
    "陈二蛋家厨房": {
        "description": (
            "吊脚楼厨房内部，熏黑木梁、竹椽和斑驳木板墙围出低矮空间，砖石灶台嵌着大铁锅，灶膛余烬泛红；"
            "夯土地面潮湿，墙边摆着瓦罐、陶碗、木水桶，半开的木窗外是暮色山影。"
        ),
        "lighting": "黄昏暮光与灶膛余烬混合，暖暗高反差，烟气让光线有颗粒感。",
    },
    "麻栗山村口空地": {
        "description": (
            "湘西苗寨村口空地，远处是喀斯特山峰和梯田，周围木质吊脚楼环绕，黄泥地干裂，中央有石碾和散落青石板；"
            "村口空间开阔，带贫瘠、炎热、乡土现实感。"
        ),
        "lighting": "正午毒辣阳光直射，地面硬阴影清晰，空气有热浪蒸腾感。",
    },
}
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
    "胡涂",
    "颜夕",
    "颜乐",
    "王强",
    "宋庭筠",
    "陈二蛋",
    "二蛋娘",
    "大凤",
    "姬由",
    "神农大帝",
    "姬瑶",
)


def _clean(text: Any) -> str:
    return " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())


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


def _safe_scene_text(text: str) -> str:
    parts = []
    for part in _split_scene_fragments(text):
        if any(fragment in part for fragment in BANNED_SCENE_REFERENCE_FRAGMENTS):
            continue
        parts.append(part)
    return "；".join(parts[:8])


def _safe_lighting_summary(shots: list[StoryboardShot], limit: int = 3) -> str:
    parts: list[str] = []
    for shot in shots:
        for part in _split_scene_fragments(str(shot.lighting or "")):
            if any(fragment in part for fragment in BANNED_SCENE_REFERENCE_FRAGMENTS):
                continue
            if part and part not in parts:
                parts.append(part)
            if len(parts) >= limit:
                return "；".join(parts)
    return "；".join(parts)


def _negative_prompt(location: VisualLocation) -> str:
    base = _clean(location.negative_prompt) or DEFAULT_NEGATIVE_PROMPT
    extras = [term.strip() for term in SCENE_REFERENCE_NEGATIVE_TERMS.split("，") if term.strip()]
    for term in extras:
        if term not in base:
            base += f"，{term}"
    return base


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
    preset = SCENE_DESIGN_PRESETS.get(scene_name)
    lighting = preset["lighting"] if preset else _safe_lighting_summary(shots)
    camera_angles = _join_unique([str(shot.camera_angle or "") for shot in shots if str(shot.camera_angle or "").strip()], limit=4)
    camera_movements = _join_unique([str(shot.camera_movement or "") for shot in shots if str(shot.camera_movement or "").strip()], limit=4)
    actions = _join_unique([str(shot.action_process or "") for shot in shots], limit=4)
    existing_prompt = _safe_scene_text(_clean(location.visual_prompt_zh or location.core_prompt_zh or location.description))

    if preset:
        base = preset["description"]
        if scene_name and scene_name not in base:
            base = f"{scene_name}。{base}"
        formal_description = f"{base}{' ' + lighting if lighting else ''}".strip()
    else:
        base = existing_prompt or f"{scene_name}，依据真实分镜归纳出的场景资产。"
        formal_description = (
            f"{scene_name}。{base} "
            f"{'光线氛围：' + lighting if lighting else ''}"
        ).strip()
    reference_prompt = (
        f"{scene_name} 场景参考图，{SCENE_REFERENCE_MODE_REQUIREMENT}"
        f"{base} "
        f"{'光线氛围为' + lighting.rstrip('。') + '。' if lighting else ''}"
        "写实电影感，空间层次清晰，道具位置明确，材质细节稳定，适合作为后续分镜首帧一致性的生产级场景资产参考。"
    )

    return {
        "formal_description": formal_description,
        "lighting_mood": lighting,
        "camera_summary": "；".join(part for part in [camera_angles, camera_movements] if part),
        "action_summary": actions,
        "reference_prompt": reference_prompt,
        "negative_prompt": _negative_prompt(location),
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


def plan_book(book_id: int, model_profile_id: str = "preset-poyo-image-gpt-image-2") -> dict[str, Any]:
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
            "reference_stats": _reference_stats(scene_refs),
            "planned_asset_update": {
                "formal_description": design["formal_description"],
                "lighting_mood": design["lighting_mood"],
                "camera_summary": design["camera_summary"],
                "action_summary": design["action_summary"],
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
        "generatedAt": datetime.utcnow().isoformat(),
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
    parser.add_argument("--model-profile-id", default="preset-poyo-image-gpt-image-2")
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
