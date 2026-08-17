"""Stage Split Generator - 人物阶段化画像生成。"""
import json

import config
from models import CharacterProfile, CharacterStage
from core.llm import call_llm_json
from core import safe_json_loads
import logging

logger = logging.getLogger(__name__)
from core.prompts import load_prompt
from agents.portrait_base import force_string_types


def generate_stages(book_id: int, session, name: str, fragments: list,
                    char_info: dict):
    """为角色生成阶段化切分并存入 DB。"""
    # 章节出场信息摘要
    chapters = char_info.get("chapters", [])
    chapter_info_lines = [f"第{ch_seq}章" for ch_seq in chapters[:100]]
    chapter_info = "、".join(chapter_info_lines)
    if len(chapters) > 100:
        chapter_info += f"...等共{len(chapters)}章"

    fragments_summary = "\n".join(fragments[:30])

    # 获取基础画像
    base_profile = ""
    profile = session.query(CharacterProfile).filter(
        CharacterProfile.book_id == book_id,
        CharacterProfile.name == name,
    ).first()
    if profile:
        base_profile = (
            f"性别: {profile.gender}, 身份: {profile.identity}, "
            f"气质: {profile.temperament}, 穿着: {profile.signature_outfit}"
        )

    total_ch = char_info.get("chapters", [0])[-1] if char_info.get("chapters") else 100
    prompt = load_prompt(
        "portrait/stage_split",
        character_name=name,
        total_chapters=total_ch,
        base_profile=base_profile or "暂无",
        chapter_info=chapter_info,
        all_fragments=fragments_summary,
    )

    try:
        result = call_llm_json(prompt, estimated_tokens=5000)
    except Exception as e:
        logger.warning("阶段切分失败: %s", e)
        return

    if isinstance(result, dict):
        result = result.get("stages", [result])

    # 为每个 stage 推断分层字段
    for stage in result:
        force_string_types(stage)
        if not stage.get("core_prompt_en"):
            stage["core_prompt_en"] = stage.get("visual_prompt_en", "")
            stage["core_prompt_zh"] = stage.get("visual_prompt_zh", "")
            stage["outfit_prompt_en"] = ""
            stage["outfit_prompt_zh"] = ""
            stage["scene_prompt_en"] = ""
            stage["scene_prompt_zh"] = ""

    # 删除旧阶段，写入新阶段
    session.query(CharacterStage).filter(
        CharacterStage.book_id == book_id,
        CharacterStage.character_name == name,
    ).delete()

    for stage in result:
        session.add(CharacterStage(
            book_id=book_id,
            character_name=name,
            stage_name=stage.get("stage_name", ""),
            chapter_start=stage.get("chapter_start", 0),
            chapter_end=stage.get("chapter_end", 0),
            timeline=stage.get("timeline", ""),
            identity=stage.get("identity", ""),
            age_description=stage.get("age_description", ""),
            face_shape=stage.get("face_shape", ""),
            facial_features=stage.get("facial_features", ""),
            body_type=stage.get("body_type", ""),
            skin_tone=stage.get("skin_tone", ""),
            distinguishing_marks=stage.get("distinguishing_marks", ""),
            signature_outfit=stage.get("signature_outfit", ""),
            accessories=stage.get("accessories", ""),
            temperament=stage.get("temperament", ""),
            vibe=stage.get("vibe", ""),
            color_palette=stage.get("color_palette", ""),
            personality=stage.get("personality", ""),
            speech_style=stage.get("speech_style", ""),
            body_language=stage.get("body_language", ""),
            visual_prompt_en=stage.get("visual_prompt_en", ""),
            visual_prompt_zh=stage.get("visual_prompt_zh", ""),
            core_prompt_en=stage.get("core_prompt_en", ""),
            core_prompt_zh=stage.get("core_prompt_zh", ""),
            outfit_prompt_en=stage.get("outfit_prompt_en", ""),
            outfit_prompt_zh=stage.get("outfit_prompt_zh", ""),
            scene_prompt_en=stage.get("scene_prompt_en", ""),
            scene_prompt_zh=stage.get("scene_prompt_zh", ""),
        ))
    session.commit()
