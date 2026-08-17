"""Stable base portrait generation for character assets."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import config
from core.llm import call_llm_json
from core.prompts import load_prompt
from models import CharacterProfile

logger = logging.getLogger(__name__)


STRING_FIELDS = [
    "face_shape",
    "facial_features",
    "body_type",
    "skin_tone",
    "distinguishing_marks",
    "signature_outfit",
    "accessories",
    "temperament",
    "vibe",
    "color_palette",
    "speech_style",
    "body_language",
    "hairstyle",
    "visual_prompt_en",
    "visual_prompt_zh",
    "core_prompt_en",
    "core_prompt_zh",
    "outfit_prompt_en",
    "outfit_prompt_zh",
    "scene_prompt_en",
    "scene_prompt_zh",
    "personality",
]

MALE_HINTS = ["男", "男性", "和尚", "僧", "师兄", "弟子", "少年", "青年男子", "公子", "少爷", "父亲", "老人"]
FEMALE_HINTS = ["女", "女性", "姐姐", "姑娘", "少女", "夫人", "太太", "娘娘", "母亲", "女弟子", "小姐"]
CHILD_HINTS = ["孩童", "孩子", "幼童", "小孩", "童子"]
ELDER_HINTS = ["老人", "老者", "六十", "七十", "年迈", "白发", "花白", "苍老", "垂暮"]
TEEN_HINTS = ["少年", "少女", "十几岁", "稚气"]
YOUNG_HINTS = ["青年", "年轻", "二十", "二十多岁", "三十岁上下", "弟子"]
MIDDLE_HINTS = ["中年", "四十", "五十"]
REGION_HINTS = ["中国", "中式", "华人", "汉人", "古代中国", "明代", "唐代", "宋代"]

HAIR_KEYWORDS = ["光头", "剃度", "短发", "束发", "盘发", "半扎", "长发", "发髻", "白发", "花白"]
OUTFIT_KEYWORDS = ["僧袍", "布衣", "长衫", "短打", "便服", "披风", "盔甲", "连衣裙", "弟子衣装", "袍", "布鞋"]
ACCESSORY_KEYWORDS = ["念珠", "包袱", "吊坠", "腕表", "木棍", "草帽", "玉佩", "发簪", "荷包", "佛珠"]
SKIN_KEYWORDS = ["面色偏白", "苍白", "暗黄", "黝黑", "日晒", "血色不足", "疲态", "汗渍", "风吹日晒"]
BODY_KEYWORDS = ["中等体型", "偏瘦", "纤瘦", "高挑", "瘦削", "健壮", "懒散", "拘谨", "站姿松散"]
FEATURE_KEYWORDS = ["眼下", "眼神", "嘴唇", "皱纹", "眉", "鼻", "脸色", "疲态", "浑浊", "血丝"]
MARK_KEYWORDS = ["疤", "痣", "伤", "血迹", "汗渍", "泥点", "泪痕", "皱纹"]


def force_string_types(payload: dict) -> None:
    for key in STRING_FIELDS:
        value = payload.get(key, "")
        if isinstance(value, list):
            payload[key] = "，".join(str(item).strip() for item in value if str(item).strip())
        elif value is None:
            payload[key] = ""
        elif not isinstance(value, str):
            payload[key] = str(value)


def _clean_text(value: str) -> str:
    text = str(value or "").strip()
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    return text.strip("，,。.;； ")


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    return [item.strip() for item in re.split(r"[。！？；;\n]", cleaned) if item.strip()]


def _split_clauses(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[，,。；;]", _clean_text(value)) if item.strip()]


def _dedupe_phrases(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for raw in values:
        value = _clean_text(raw)
        if not value:
            continue
        if any(value == existing or value in existing for existing in deduped):
            continue
        deduped = [existing for existing in deduped if existing not in value]
        deduped.append(value)
    return deduped


def _dedupe_clause_text(value: str) -> str:
    return "，".join(_dedupe_phrases(_split_clauses(value)))


def _contains_any(text: str, needles: list[str]) -> bool:
    cleaned = _clean_text(text)
    return any(needle in cleaned for needle in needles)


def _format_makeup_scope_label(scope: str) -> str:
    normalized = _clean_text(scope).lower()
    if normalized == "base_identity":
        return "基础定妆"
    if normalized == "episode_default":
        return "分集默认"
    if normalized == "shot_variant":
        return "分镜精调"
    return _clean_text(scope)


def _format_makeup_stage_label(stage_name: str, scope: str, episode: int | None = None) -> str:
    cleaned = _clean_text(stage_name)
    normalized = cleaned.lower()
    normalized_scope = _clean_text(scope).lower()

    if normalized == "base_identity" or normalized_scope == "base_identity":
        return "基础身份阶段"

    episode_match = re.match(r"^episode_(\d+)_default$", normalized)
    if episode_match:
        return f"第{episode_match.group(1)}集默认造型"

    shot_match = re.match(r"^shot_(\d+)_(.+)$", cleaned, flags=re.IGNORECASE)
    if shot_match:
        return f"镜头 {shot_match.group(1)} · {shot_match.group(2).replace('_', ' ')}"

    if normalized_scope == "episode_default" and episode:
        return f"第{int(episode)}集默认造型"

    return cleaned


def _normalize_identity_label(identity: str) -> str:
    text = _clean_text(identity)
    if not text:
        return "普通角色（推测）"
    if any(keyword in text for keyword in ["和尚", "僧", "僧侣", "守门僧人"]):
        return "和尚（寺庙僧侣）"
    if any(keyword in text for keyword in ["弟子", "新入弟子", "新来的弟子", "归寺少年"]):
        return "寺中新入门的弟子（推测）"
    return text


def _sentence_candidates(fragments: list[str]) -> list[str]:
    candidates: list[str] = []
    for fragment in fragments:
        candidates.extend(_split_sentences(fragment))
    return candidates


def _extract_keyword_phrases(fragments: list[str], keywords: list[str], limit: int = 3) -> list[str]:
    found: list[str] = []
    for sentence in _sentence_candidates(fragments):
        for keyword in keywords:
            if keyword not in sentence:
                continue
            candidate = sentence
            if len(candidate) > 34:
                pieces = [part.strip() for part in re.split(r"[，,]", candidate) if part.strip()]
                candidate = next((part for part in pieces if keyword in part), candidate)
            candidate = _clean_text(candidate)
            if candidate and candidate not in found:
                found.append(candidate)
                if len(found) >= limit:
                    return _dedupe_phrases(found)
    return _dedupe_phrases(found)


def _normalize_face_clauses(clauses: list[str]) -> list[str]:
    normalized: list[str] = []
    seen_pale_face = False
    for clause in clauses:
        if any(keyword in clause for keyword in ["动作", "肩背", "站姿", "姿态", "倚着", "门框"]):
            continue
        if "肤色自然" in clause:
            continue
        if "面色偏白" in clause or "脸色发白" in clause:
            if seen_pale_face:
                continue
            seen_pale_face = True
            normalized.append("面色偏白，雨夜奔波后的疲态轻压在眼下")
            continue
        normalized.append(clause)
    return _dedupe_phrases(normalized)


def infer_gender(name: str, fragments: list[str], char_info: dict) -> str:
    text = " ".join(
        [
            _clean_text(name),
            _clean_text(char_info.get("identity", "") or ""),
            _clean_text(char_info.get("personality", "") or ""),
            " ".join(_clean_text(item) for item in fragments[:12]),
        ]
    )
    male_hits = sum(1 for item in MALE_HINTS if item in text)
    female_hits = sum(1 for item in FEMALE_HINTS if item in text)
    if male_hits > female_hits:
        return "男性"
    if female_hits > male_hits:
        return "女性"
    if "阿宁" in name or "和尚" in text or "僧" in text or "弟子" in text:
        return "男性"
    return "人物"


def infer_age(name: str, fragments: list[str], char_info: dict) -> str:
    text = " ".join(
        [
            _clean_text(name),
            _clean_text(char_info.get("identity", "") or ""),
            _clean_text(char_info.get("personality", "") or ""),
            " ".join(_clean_text(item) for item in fragments[:12]),
        ]
    )
    if any(item in text for item in CHILD_HINTS):
        return "儿童(<14)"
    if any(item in text for item in TEEN_HINTS):
        return "少年(14-18)"
    if any(item in text for item in ELDER_HINTS):
        return "老年(55+)"
    if any(item in text for item in MIDDLE_HINTS):
        return "中年(35-55)"
    if any(item in text for item in YOUNG_HINTS):
        return "青年(18-35)"
    return "青年(18-35)"


def infer_role(name: str, char_info: dict) -> str:
    chapter_count = len(char_info.get("chapters", []) or [])
    if chapter_count > 10:
        return "protagonist"
    if chapter_count > 5:
        return "supporting"
    return "minor"


def _infer_region(char_info: dict, fragments: list[str]) -> str:
    for value in [char_info.get("region", ""), char_info.get("nationality", ""), char_info.get("identity", "")]:
        cleaned = _clean_text(value)
        if cleaned and any(hint in cleaned for hint in REGION_HINTS):
            return "中国"
    joined = " ".join(_clean_text(item) for item in fragments[:8])
    if any(hint in joined for hint in REGION_HINTS):
        return "中国"
    return "中国"


def _infer_identity(char_info: dict, fragments: list[str]) -> str:
    identity = _normalize_identity_label(char_info.get("identity", "") or "")
    if identity:
        return identity
    text = " ".join(_clean_text(item) for item in fragments[:10])
    if "和尚" in text or "僧" in text:
        return "和尚（寺庙僧侣）"
    if "弟子" in text:
        return "寺中新入门的弟子（推测）"
    return "普通角色（推测）"


def _infer_hairstyle(identity: str, fragments: list[str], gender: str) -> str:
    if "和尚" in identity or "僧" in identity:
        return "剃着光头，头皮干净，略带青色头皮质感"
    if "弟子" in identity:
        return "黑色短发或束发，稍显凌乱但克制"
    matches = _extract_keyword_phrases(fragments, HAIR_KEYWORDS, limit=2)
    text = "，".join(matches)
    if text:
        if "短发" in text and "束发" not in text:
            return "黑色短发或束发，稍显凌乱但克制"
        return text
    if gender == "女性":
        return "中长发，保持基础发型一致"
    return "黑色短发或束发，保持人物识别度"


def _infer_outfit(identity: str, fragments: list[str]) -> str:
    matches = _extract_keyword_phrases(fragments, OUTFIT_KEYWORDS, limit=3)
    text = "，".join(matches)
    if "和尚" in identity or "僧" in identity:
        return "灰旧僧袍，布料磨旧发暗，穿着松散，带着久穿后的皱褶"
    if "弟子" in identity:
        if "雨" in text or _contains_any(" ".join(fragments), ["雨夜", "湿衣", "受潮", "雨水"]):
            return "朴素弟子衣装因雨夜受潮贴身，整体简洁克制"
        return "朴素弟子衣装，便于行动，整体简洁克制"
    return text or f"符合【{identity}】身份的基础服装，材质朴素，细节克制"


def _infer_accessories(identity: str, fragments: list[str]) -> str:
    matches = _extract_keyword_phrases(fragments, ACCESSORY_KEYWORDS, limit=3)
    text = "，".join(matches)
    if "念珠" in text:
        return "一串磨旧念珠"
    if "和尚" in identity or "僧" in identity:
        return "一串磨旧念珠"
    if "包袱" in text:
        return "旧包袱"
    return text or "无明显配饰"


def _infer_skin_tone(fragments: list[str]) -> str:
    matches = _extract_keyword_phrases(fragments, SKIN_KEYWORDS, limit=2)
    if matches:
        text = "，".join(matches)
        if "面色偏白" in text or "脸色发白" in text:
            return "面色偏白，雨夜奔波后的疲态轻压在眼下"
        return text
    return "肤色自然，带有真实生活痕迹"


def _infer_body_type(identity: str, age_range: str, fragments: list[str]) -> str:
    text = "，".join(_extract_keyword_phrases(fragments, BODY_KEYWORDS, limit=3))
    if "和尚" in identity or "僧" in identity:
        return "中等体型，姿态略松散，带着久居寺中的朴素与懈怠感"
    if "弟子" in identity:
        return "中等偏瘦体型，动作克制，带着新入门弟子的拘谨感"
    if text:
        return text
    if "老年" in age_range:
        return "偏瘦体型，带有老年角色的真实松弛感"
    return "中等体型，站姿标准，轮廓清楚"


def _infer_features(identity: str, fragments: list[str]) -> str:
    clauses = _normalize_face_clauses(_extract_keyword_phrases(fragments, FEATURE_KEYWORDS, limit=4))
    text = _dedupe_clause_text("，".join(clauses))
    if "和尚" in identity or "僧" in identity:
        return "剃着光头，神情懒散，眼神带一点轻慢，像个混日子的僧人"
    if "弟子" in identity:
        base = [
            "面色偏白，雨夜奔波后的疲态轻压在眼下",
            "情绪克制，目光里仍压着不服气",
        ]
        if text:
            base.extend(_split_clauses(text))
        return _dedupe_clause_text("，".join(base))
    return text or "五官稳定，角色识别度明确，适合影视化建模"


def _infer_marks(fragments: list[str]) -> str:
    matches = _extract_keyword_phrases(fragments, MARK_KEYWORDS, limit=2)
    return _dedupe_clause_text("，".join(matches)) or "无明显特殊标记"


def _infer_temperament(char_info: dict, fragments: list[str]) -> str:
    personality = _clean_text(char_info.get("personality", "") or "")
    if personality:
        return personality
    if _contains_any(" ".join(fragments), ["不服气", "克制"]):
        return "克制、隐忍、不服输"
    if _contains_any(" ".join(fragments), ["懒散", "轻慢"]):
        return "懒散、轻慢、推诿"
    return "克制、自然、真实"


def _infer_face_shape(identity: str, age_range: str, fragments: list[str]) -> str:
    if "老年" in age_range:
        return "脸部轮廓偏瘦，岁月痕迹明显"
    if "和尚" in identity:
        return "脸部轮廓朴实，骨相清楚"
    return "脸部轮廓稳定，镜头识别度高"


def _infer_speech_style(identity: str, char_info: dict) -> str:
    personality = _clean_text(char_info.get("personality", "") or "")
    if "和尚" in identity:
        return "说话散漫，带一点敷衍和推脱"
    if "弟子" in identity:
        return "说话克制谨慎，压着情绪"
    if personality:
        return f"语言风格贴合其性格：{personality}"
    return "语言风格自然克制"


def _infer_body_language(identity: str, fragments: list[str]) -> str:
    if "和尚" in identity:
        return "站姿松散，动作慢半拍，带一点敷衍感"
    if "弟子" in identity:
        return "动作克制，肩背微紧，带着新人的拘谨"
    matches = _extract_keyword_phrases(fragments, ["站姿", "动作", "低头", "抬眼", "倚着", "慢吞吞"], limit=2)
    return "，".join(matches) or "动作自然，符合剧情状态"


def _style_temperament(identity: str, temperament: str, features: str) -> str:
    del features
    text = _dedupe_clause_text(temperament)
    if "和尚" in identity:
        if any(keyword in text for keyword in ["懒散", "轻慢", "欺", "推诿", "混日子"]):
            return "懒散、轻慢、爱欺负新人、略显粗鄙"
        return "懒散、轻慢、略显粗鄙"
    if "弟子" in identity:
        if any(keyword in text for keyword in ["不服", "隐忍", "倔强", "坚韧", "顺从"]):
            return "克制、隐忍、坚韧、内心有不屈和傲气"
        return "克制、隐忍、谨慎"
    return text


def canonicalize_character_prompt_inputs(*, identity: str, temperament: str, appearance: str = "") -> dict:
    canonical_identity = _normalize_identity_label(identity)
    canonical_temperament = _style_temperament(canonical_identity, temperament, appearance)
    return {
        "identity": canonical_identity,
        "temperament": canonical_temperament,
        "appearance": _clean_text(appearance),
    }


def canonicalize_variant_prompt_inputs(
    *,
    identity: str,
    makeup_expression: str = "",
    scene_effects: str = "",
    hairstyle: str = "",
    outfit: str = "",
    accessories: str = "",
) -> dict:
    canonical_identity = _normalize_identity_label(identity)
    makeup_text = _clean_text(makeup_expression)
    scene_text = _clean_text(scene_effects)
    hair_text = _dedupe_clause_text(hairstyle)
    outfit_text = _dedupe_clause_text(outfit)
    accessories_text = _dedupe_clause_text(accessories)

    if "和尚" in canonical_identity:
        if not makeup_text or any(keyword in makeup_text for keyword in ["混日子", "轻慢", "光头"]):
            makeup_text = "剃着光头，神情懒散，眼神带一点轻慢，像个混日子的僧人"
        if not scene_text:
            scene_text = "无额外场景污染，保持标准影棚状态"
    elif "弟子" in canonical_identity:
        if not makeup_text or any(keyword in makeup_text for keyword in ["疲态", "不服气", "脸色发白", "面色偏白"]):
            makeup_text = "面色偏白，雨夜奔波后的疲态轻压在眼下，情绪克制，目光里仍压着不服气"
        if not scene_text:
            scene_text = "无额外场景污染，保持标准影棚状态"
    else:
        if not makeup_text:
            makeup_text = "表情自然克制，整体呈现真实影视妆感"
        if not scene_text:
            scene_text = "无额外场景污染，保持标准影棚状态"

    return {
        "identity": canonical_identity,
        "makeup_expression": makeup_text,
        "scene_effects": scene_text,
        "hairstyle": hair_text or _clean_text(hairstyle),
        "outfit": outfit_text or _clean_text(outfit),
        "accessories": accessories_text or _clean_text(accessories),
    }


def _style_features(identity: str, features: str, skin_tone: str, body_language: str) -> str:
    del skin_tone, body_language
    clauses = _normalize_face_clauses(_split_clauses(features))
    return _dedupe_clause_text("，".join(clauses))


def _style_outfit(identity: str, outfit: str, accessories: str) -> str:
    del accessories
    text = _dedupe_clause_text(outfit)
    if "和尚" in identity and "僧袍" not in text:
        return "灰旧僧袍，布料磨旧发暗，穿着松散，带着久穿后的皱褶"
    if "弟子" in identity and "弟子衣装" not in text:
        return "朴素弟子衣装，便于行动，整体简洁克制"
    return text


def _style_accessories(identity: str, accessories: str) -> str:
    text = _dedupe_clause_text(accessories)
    if "和尚" in identity and not text:
        return "一串磨旧念珠"
    return text or "无明显配饰"


def _style_body_type(identity: str, body_type: str) -> str:
    text = _dedupe_clause_text(body_type)
    if "和尚" in identity:
        return "中等体型，姿态略松散，带着久居寺中的朴素与懈怠感"
    if "弟子" in identity:
        return "中等偏瘦体型，动作克制，带着新入门弟子的拘谨感"
    return text or "中等体型，站姿标准"


def _prompt_value(value: str, fallback: str) -> str:
    cleaned = _clean_text(value)
    return cleaned or fallback


def _format_bracketed_segments(value: str, fallback: str = "", split_clauses: bool = True) -> str:
    clauses = _dedupe_phrases(_split_clauses(value) if split_clauses else [_clean_text(value)])
    if not clauses and fallback:
        clauses = _dedupe_phrases(_split_clauses(fallback) if split_clauses else [_clean_text(fallback)])
    if not clauses:
        return "【无明确描述】"
    return "、".join(f"【{clause}】" for clause in clauses)


def compile_character_sheet_prompts(
    *,
    scope: str,
    age: str,
    region: str,
    gender: str,
    identity: str,
    temperament: str,
    appearance: str,
    hairstyle: str,
    body_type: str = "",
    outfit: str,
    accessories: str,
    skin_tone: str,
    marks: str,
    episode: int | None = None,
    stage_name: str = "",
    variant_name: str = "",
    shot_label: str = "-",
    scene_effects: str = "",
    makeup_expression: str = "",
) -> dict:
    normalized_scope = str(scope or "base_identity").strip().lower()
    age_text = _prompt_value(age, "青年(18-35)")
    region_text = _prompt_value(region, "中国")
    gender_text = _prompt_value(gender, "人物")
    identity_text = _prompt_value(identity, "普通角色（推测）")
    temperament_text = _prompt_value(temperament, "自然、克制、真实")
    appearance_text = _prompt_value(appearance, "五官稳定，角色识别度明确")
    hairstyle_text = _prompt_value(hairstyle, "保持基础发型一致")
    body_type_text = _prompt_value(body_type, "中等体型，站姿标准")
    outfit_text = _prompt_value(outfit, "符合身份的基础服装")
    accessories_text = _prompt_value(accessories, "无明显配饰")
    skin_tone_text = _prompt_value(skin_tone, "肤色自然")
    marks_text = _prompt_value(marks, "无明显特殊标记")
    stage_name_text = _prompt_value(
        _format_makeup_stage_label(stage_name, normalized_scope, int(episode) if episode else None),
        _format_makeup_scope_label(normalized_scope),
    )
    variant_name_text = _prompt_value(variant_name, stage_name_text)
    scene_effects_text = _prompt_value(scene_effects, "无额外场景污染，保持标准影棚状态")
    makeup_expression_text = _prompt_value(makeup_expression, "表情自然克制，整体呈现真实影视妆感")
    episode_text = f"第{int(episode)}集" if episode else "当前集"
    temperament_segments = _format_bracketed_segments(temperament_text, "自然、克制、真实")
    appearance_segments = _format_bracketed_segments(appearance_text, "五官稳定，角色识别度明确", split_clauses=False)
    hairstyle_segments = _format_bracketed_segments(hairstyle_text, "保持基础发型一致")
    body_type_segments = _format_bracketed_segments(body_type_text, "中等体型，站姿标准")
    outfit_segments = _format_bracketed_segments(outfit_text, "符合身份的基础服装", split_clauses=False)
    accessories_segments = _format_bracketed_segments(accessories_text, "无明显配饰")
    skin_tone_segments = _format_bracketed_segments(skin_tone_text, "肤色自然")
    marks_segments = _format_bracketed_segments(marks_text, "无明显特殊标记")
    makeup_expression_segments = _format_bracketed_segments(makeup_expression_text, "表情自然克制", split_clauses=False)
    scene_effects_segments = _format_bracketed_segments(scene_effects_text, "无额外场景污染，保持标准影棚状态", split_clauses=False)

    scene_prompt_zh = "角色设定板，六宫格排版，纯白或浅灰背景，统一柔和影棚布光，超写实，电影级质感，高细节，8k，专业影视定妆照风格。"
    outfit_prompt_zh = f"服装：{outfit_segments}。配饰：{accessories_segments}。肤色与质感：{skin_tone_segments}。辨识特征：{marks_segments}。"

    if normalized_scope == "base_identity":
        core_prompt_zh = (
            "人物定妆设定板，展示同一个角色的六个视角。 "
            "上排为脸部特写：正面、侧面、45度； 下排为全身展示：正面、侧面、背面。 "
            "六个视角必须是同一个人，保持面部一致性、发型一致性、服装一致性、体型一致性。 "
            f"人物为：【{age_text}】岁的【{region_text}】【{gender_text}】，身份是【{identity_text}】，气质{temperament_segments}。 "
            f"外貌特征：{appearance_segments}。 发型：{hairstyle_segments}。 体型：{body_type_segments}。 "
            "表情自然克制，站姿标准，适合影视角色建模。"
        )
    elif normalized_scope == "episode_default":
        core_prompt_zh = (
            "人物集默认定妆设定板，展示同一个角色在当前剧集状态下的六个视角。 "
            "上排为脸部特写：正面、侧面、45度； 下排为全身展示：正面、侧面、背面。 "
            "六个视角必须是同一个人，严格继承基础定妆的面部一致性、发型一致性、体型一致性和气质一致性。 "
            f"人物为：【{age_text}】岁的【{region_text}】【{gender_text}】，身份是【{identity_text}】，气质{temperament_segments}。 "
            f"基础外貌保持：{appearance_segments}。 当前剧集状态：{episode_text} / {stage_name_text} / {variant_name_text}。 "
            f"当前服装：{outfit_segments}。 当前发型：{hairstyle_segments}。 当前妆容与表情：{makeup_expression_segments}。 "
            f"当前配饰：{accessories_segments}。 场景影响：{scene_effects_segments}。 "
            "表情自然克制，站姿标准，适合影视角色建模。"
        )
    else:
        shot_part = f" / 镜号 {shot_label}" if normalized_scope == "shot_variant" else ""
        core_prompt_zh = (
            "人物分镜精调定妆设定板，展示同一个角色在当前分镜状态下的六个视角。 "
            "上排为脸部特写：正面、侧面、45度； 下排为全身展示：正面、侧面、背面。 "
            "六个视角必须是同一个人，严格继承基础定妆的面部一致性、发型一致性、体型一致性和气质一致性。 "
            f"人物为：【{age_text}】岁的【{region_text}】【{gender_text}】，身份是【{identity_text}】，气质{temperament_segments}。 "
            f"基础外貌保持：{appearance_segments}。 当前分镜状态：{episode_text} / {stage_name_text}{shot_part} / {variant_name_text}。 "
            f"当前服装：{outfit_segments}。 当前发型：{hairstyle_segments}。 当前妆容与表情：{makeup_expression_segments}。 "
            f"当前配饰：{accessories_segments}。 场景影响：{scene_effects_segments}。 "
            "表情自然克制，站姿标准，适合影视角色建模。"
        )

    if normalized_scope == "episode_default":
        core_prompt_zh = core_prompt_zh.replace("人物集默认定妆设定板", "人物分集默认定妆设定板")
        core_prompt_zh = re.sub(
            r"当前剧集状态：([^/。]+)\s*/\s*[^/。]+\s*/\s*([^。]+)。",
            lambda match: f"当前剧集状态：{match.group(1).strip()} / 分集默认 / {match.group(2).strip()}。",
            core_prompt_zh,
        )

    visual_prompt_zh = f"{core_prompt_zh} {outfit_prompt_zh} {scene_prompt_zh}"
    return {
        "core_prompt_zh": core_prompt_zh,
        "outfit_prompt_zh": outfit_prompt_zh,
        "scene_prompt_zh": scene_prompt_zh,
        "visual_prompt_zh": visual_prompt_zh,
    }


def _merge_with_fallback(llm_result: dict, fallback: dict) -> dict:
    merged = dict(fallback)
    merged.update({key: value for key, value in llm_result.items() if value not in (None, "")})
    force_string_types(merged)
    for key in ["region", "gender", "age", "identity"]:
        merged[key] = fallback[key]
    for key in ["core_prompt_zh", "outfit_prompt_zh", "scene_prompt_zh", "visual_prompt_zh"]:
        merged[key] = fallback[key]
    if not _clean_text(merged.get("core_prompt_en", "")):
        merged["core_prompt_en"] = fallback["core_prompt_en"]
    if not _clean_text(merged.get("outfit_prompt_en", "")):
        merged["outfit_prompt_en"] = fallback["outfit_prompt_en"]
    if not _clean_text(merged.get("scene_prompt_en", "")):
        merged["scene_prompt_en"] = fallback["scene_prompt_en"]
    if not _clean_text(merged.get("visual_prompt_en", "")):
        merged["visual_prompt_en"] = fallback["visual_prompt_en"]
    return merged


def _should_attempt_llm(fragments: list[str], fragments_text: str) -> bool:
    api_key = str(getattr(config, "OPENAI_API_KEY", "") or "").strip()
    if api_key in {"", "sk-placeholder", "***"}:
        return False
    if len(fragments) < 3:
        return False
    if len(fragments_text) < 180:
        return False
    return True


def _build_fallback_profile(name: str, fragments: list[str], char_info: dict, *, gender: str, age_range: str, role: str, identity: str) -> dict:
    region = _infer_region(char_info, fragments)
    face_shape = _infer_face_shape(identity, age_range, fragments)
    skin_tone = _infer_skin_tone(fragments)
    body_language = _infer_body_language(identity, fragments)
    features = _style_features(identity, _infer_features(identity, fragments), skin_tone, body_language)
    body_type = _style_body_type(identity, _infer_body_type(identity, age_range, fragments))
    marks = _infer_marks(fragments)
    hairstyle = _infer_hairstyle(identity, fragments, gender)
    outfit = _style_outfit(identity, _infer_outfit(identity, fragments), _infer_accessories(identity, fragments))
    accessories = _style_accessories(identity, _infer_accessories(identity, fragments))
    temperament = _style_temperament(identity, _infer_temperament(char_info, fragments), features)
    speech_style = _infer_speech_style(identity, char_info)
    personality = _clean_text(char_info.get("personality", "") or temperament)
    relationships = char_info.get("relationships", {}) or {}
    relation_text = "，".join(
        f"{_clean_text(k)}:{_clean_text(v)}"
        for k, v in relationships.items()
        if _clean_text(k) and _clean_text(v)
    ) or "关系信息有限"
    vibe = f"{name}的整体气质围绕【{identity}】展开，视觉上强调真实、可拍摄、可延展。"
    color_palette = "灰、褐、暗青"
    prompt_bundle = compile_character_sheet_prompts(
        scope="base_identity",
        age=age_range,
        region=region,
        gender=gender,
        identity=identity,
        temperament=temperament,
        appearance=features,
        hairstyle=hairstyle,
        body_type=body_type,
        outfit=outfit,
        accessories=accessories,
        skin_tone=skin_tone,
        marks=marks,
    )
    visual_prompt_en = (
        f"Character turnaround sheet for {name}, six-panel layout, same person across all views, "
        f"face close-up front, side, 45-degree, full body front, side, back, "
        f"{gender}, {age_range}, from {region}, identity {identity}, temperament {temperament}, "
        f"appearance {features}, hairstyle {hairstyle}, body type {body_type}, outfit {outfit}, accessories {accessories}, "
        "soft studio lighting, white or light gray background, cinematic realism, 8k."
    )
    return {
        "name": name,
        "face_shape": face_shape,
        "facial_features": features,
        "body_type": body_type,
        "skin_tone": skin_tone,
        "distinguishing_marks": marks,
        "signature_outfit": outfit,
        "accessories": accessories,
        "hairstyle": hairstyle,
        "temperament": temperament,
        "vibe": vibe,
        "color_palette": color_palette,
        "personality": personality,
        "speech_style": speech_style,
        "body_language": body_language,
        "relationships": relation_text,
        "visual_prompt_en": visual_prompt_en,
        "visual_prompt_zh": prompt_bundle["visual_prompt_zh"],
        "core_prompt_en": visual_prompt_en,
        "core_prompt_zh": prompt_bundle["core_prompt_zh"],
        "outfit_prompt_en": f"Outfit: {outfit}. Accessories: {accessories}.",
        "outfit_prompt_zh": prompt_bundle["outfit_prompt_zh"],
        "scene_prompt_en": "Six-panel character sheet, white or light gray studio background, soft lighting, cinematic realism, 8k.",
        "scene_prompt_zh": prompt_bundle["scene_prompt_zh"],
        "region": region,
        "gender": gender,
        "age": age_range,
        "identity": identity,
        "role": role,
    }


def generate_base_profile(book_id: int, session, name: str, fragments: list[str], char_info: dict) -> dict:
    fragments = fragments or []
    fragments_text = "\n".join(str(item) for item in fragments[:50] if str(item).strip())
    identity = _infer_identity(char_info, fragments)
    gender = infer_gender(name, fragments, char_info)
    age_range = infer_age(name, fragments, char_info)
    role = infer_role(name, char_info)
    fallback = _build_fallback_profile(
        name=name,
        fragments=fragments,
        char_info=char_info,
        gender=gender,
        age_range=age_range,
        role=role,
        identity=identity,
    )
    result = dict(fallback)
    if _should_attempt_llm(fragments, fragments_text):
        try:
            relationships_str = (
                json.dumps(char_info.get("relationships", {}), ensure_ascii=False)
                if char_info.get("relationships")
                else "{}"
            )
            prompt = load_prompt(
                "portrait/base_profile",
                character_name=name,
                fragments=fragments_text,
                gender=gender,
                age_range=age_range,
                role=role,
                identity=identity,
                personality=char_info.get("personality", "未知"),
                relationships=relationships_str,
            )
            llm_result = call_llm_json(prompt, estimated_tokens=len(fragments_text) + config.PORTRAIT_EXCERPT_CHARS)
            if isinstance(llm_result, dict):
                result = _merge_with_fallback(llm_result, fallback)
        except Exception as exc:
            logger.warning("Base portrait fallback used for %s: %s", name, exc)
    else:
        logger.info("Base portrait using deterministic fallback for %s", name)

    chapter_numbers = [int(item) for item in (char_info.get("chapters", []) or []) if str(item).isdigit()]
    first_chapter = char_info.get("first_chapter", chapter_numbers[0] if chapter_numbers else 1)
    last_chapter = max(chapter_numbers) if chapter_numbers else first_chapter
    chapter_range = f"第{first_chapter}章-第{last_chapter}章"
    importance = "high" if len(chapter_numbers) > 10 else "medium" if len(chapter_numbers) > 3 else "low"

    existing = session.query(CharacterProfile).filter(CharacterProfile.book_id == book_id, CharacterProfile.name == name).first()
    profile_payload = {
        "aliases": json.dumps(char_info.get("aliases", []), ensure_ascii=False),
        "gender": gender,
        "age_range": age_range,
        "role": role,
        "identity": identity,
        "nationality": fallback["region"],
        "face_shape": result.get("face_shape", ""),
        "facial_features": result.get("facial_features", ""),
        "body_type": result.get("body_type", ""),
        "skin_tone": result.get("skin_tone", ""),
        "distinguishing_marks": result.get("distinguishing_marks", ""),
        "signature_outfit": result.get("signature_outfit", ""),
        "accessories": result.get("accessories", ""),
        "hairstyle": result.get("hairstyle", ""),
        "temperament": result.get("temperament", ""),
        "vibe": result.get("vibe", ""),
        "color_palette": result.get("color_palette", ""),
        "personality": result.get("personality", ""),
        "speech_style": result.get("speech_style", ""),
        "body_language": result.get("body_language", ""),
        "relationships": json.dumps(char_info.get("relationships", {}), ensure_ascii=False),
        "visual_prompt_en": result.get("visual_prompt_en", ""),
        "visual_prompt_zh": result.get("visual_prompt_zh", ""),
        "core_prompt_en": result.get("core_prompt_en", ""),
        "core_prompt_zh": result.get("core_prompt_zh", ""),
        "outfit_prompt_en": result.get("outfit_prompt_en", ""),
        "outfit_prompt_zh": result.get("outfit_prompt_zh", ""),
        "scene_prompt_en": result.get("scene_prompt_en", ""),
        "scene_prompt_zh": result.get("scene_prompt_zh", ""),
        "chapter_range": chapter_range,
        "importance": importance,
        "updated_at": datetime.utcnow(),
    }
    if existing:
        for key, value in profile_payload.items():
            setattr(existing, key, value)
    else:
        session.add(CharacterProfile(book_id=book_id, name=name, **profile_payload))
    session.commit()
    return result
