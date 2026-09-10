"""Built-in, declarative Smart Director skills.

Skills are data, not executable plugins: they can constrain planning and add a
review prompt block, but have no database, network, shell, or credential access.
Third-party skills must eventually enter this reviewed registry format.
"""
from __future__ import annotations

from typing import Any


SKILLS: dict[str, dict[str, Any]] = {
    "short_drama_production": {
        "version": "1.0.0", "label": "短剧生产", "description": "围绕剧本、分镜、资产、QA 和交付提出全链路候选计划。",
        "input_schema": {"type": "object", "properties": {"episode": {"type": "integer"}, "shot_id": {"type": "integer"}}},
        "allowed_operations": ["read_state", "diagnose", "qa_read", "draft_prompt", "draft_repair", "write_prompt_version", "image_generation", "video_generation"],
        "required_evidence": ["script", "shots", "assets", "qa", "prompt_versions"],
        "prompt_block": "以短剧生产负责人视角，先检查上游版本、资产锁定、镜头可执行性与 QA；按生产顺序给出可审核建议。",
    },
    "continuity": {
        "version": "1.0.0", "label": "连续性", "description": "诊断相邻镜头人物、场景、道具、动作、时间与首尾帧承接。",
        "input_schema": {"type": "object", "properties": {"episode": {"type": "integer"}, "shot_id": {"type": "integer"}}},
        "allowed_operations": ["read_state", "diagnose", "continuity_check", "qa_read", "draft_prompt", "draft_repair", "write_prompt_version", "image_generation", "video_generation"],
        "required_evidence": ["shots", "assets", "qa", "prompt_versions"],
        "prompt_block": "以连续性监督视角，明确相邻镜头哪些事实必须连续、哪些应切换；区分诊断、候选修订和需要人工确认的生成动作。",
    },
    "tvc": {
        "version": "1.0.0", "label": "TVC", "description": "根据 Brief、卖点、品牌禁忌、平台规格和节奏生成受控创意候选。",
        "input_schema": {"type": "object", "properties": {"brief": {"type": "string"}, "platform": {"type": "string"}, "duration_seconds": {"type": "number"}}},
        "allowed_operations": ["read_state", "diagnose", "draft_prompt", "draft_repair", "write_prompt_version", "image_generation", "video_generation"],
        "required_evidence": ["project", "shots", "assets", "prompt_versions"],
        "prompt_block": "以商业片导演视角核对 Brief、品牌禁忌、平台比例和时长；没有证据时明确列为待补信息，不得虚构品牌事实。",
    },
    "children_education": {
        "version": "1.0.0", "label": "儿童教育", "description": "围绕年龄段、知识目标、安全、语言难度和互动节奏提出候选。",
        "input_schema": {"type": "object", "properties": {"age_range": {"type": "string"}, "learning_goal": {"type": "string"}}},
        "allowed_operations": ["read_state", "diagnose", "qa_read", "draft_prompt", "draft_repair", "write_prompt_version", "image_generation", "video_generation"],
        "required_evidence": ["script", "shots", "assets", "qa"],
        "prompt_block": "以儿童教育内容导演视角，优先核对年龄适配、安全、表达难度和互动节奏；证据不足时只提出待补项。",
    },
}


def list_skills() -> list[dict[str, Any]]:
    return [{"id": skill_id, **spec} for skill_id, spec in SKILLS.items()]


def get_skill(skill_id: str | None) -> dict[str, Any] | None:
    key = str(skill_id or "").strip()
    if not key:
        return None
    spec = SKILLS.get(key)
    return {"id": key, **spec} if spec else None


def apply_skill(skill_id: str | None, operations: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    skill = get_skill(skill_id)
    if not skill:
        if skill_id:
            raise ValueError("未注册的 Skill 不可执行或注入提示词")
        return None, operations
    allowed = set(skill["allowed_operations"])
    safe_operations = [item for item in operations if isinstance(item, dict) and str(item.get("operation") or "") in allowed]
    return skill, safe_operations
