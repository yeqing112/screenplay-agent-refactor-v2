"""Structural QA Agent - 结构化QA Agent

结合结构化验证和LLM分析，提供更准确的QA结果。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import config
from agents.base import BaseAgent
from core import safe_json_loads
from core.llm import call_llm
from core.production_skill import (
    build_production_skill_prompt_block,
    build_script_skill_execution_plan,
    classify_script_qa_repair_stage,
    classify_script_qa_rule_family,
    classify_script_qa_structure_layer,
)
from core.prompts import load_prompt
from core.structured_output import parse_json_object, strip_code_fences, write_debug_output
from core.repair import (
    StructuralRepairEngine,
    StructuralRepairPacket,
    ConstraintSeverity,
)
from models import Book, BookBible, CharacterProfile, QAResult, Script

logger = logging.getLogger(__name__)


class StructuralQAAgent(BaseAgent):
    """结构化QA Agent
    
    结合结构化验证和LLM分析：
    1. 使用结构化验证器发现确定性问题
    2. 使用LLM分析创意性问题
    3. 合并结果，生成修复指令
    """

    name = "qa_structural"

    def __init__(self, book_id: int):
        super().__init__(book_id)
        self.structural_engine: StructuralRepairEngine | None = None

    def run(self, *, episode: int) -> dict[str, Any]:
        """执行结构化QA"""
        with self.session() as session:
            book = self.get_book(session)
            if not book:
                return {"error": "Book not found"}

            # 加载数据
            script = self._load_script(session, episode)
            if not script:
                return {"error": "Script not found"}

            bible_content = self._load_bible(session)
            portrait_info = self._build_portrait_info(session)

            # 1. 结构化验证
            structural_result = self._run_structural_validation(script)

            # 2. LLM分析
            llm_result = self._run_llm_analysis(
                episode=episode,
                script_content=script.get("content", ""),
                bible_chars=bible_content,
                portrait_info=portrait_info,
            )

            # 3. 合并结果
            merged_result = self._merge_results(structural_result, llm_result)

            # 4. 生成修复指令
            repair_directives = self._generate_repair_directives(merged_result)

            return {
                "structural_findings": structural_result,
                "llm_findings": llm_result,
                "merged_result": merged_result,
                "repair_directives": repair_directives,
            }

    def _run_structural_validation(self, script: dict[str, Any]) -> dict[str, Any]:
        """运行结构化验证"""
        # 构建故事事实表
        story_fact_sheet = self._build_story_fact_sheet(script)
        
        # 构建场景执行卡
        scene_execution_cards = self._build_scene_execution_cards(script)

        # 初始化结构化引擎
        self.structural_engine = StructuralRepairEngine(
            story_fact_sheet=story_fact_sheet,
            scene_execution_cards=scene_execution_cards,
        )

        # 执行验证
        packet = self.structural_engine.pre_generation_validation()

        return {
            "constraint_violations": [
                {
                    "constraint_id": v.constraint_id,
                    "layer": v.layer.value,
                    "severity": v.severity.value,
                    "message": v.message,
                    "location": v.location,
                    "fix_suggestion": v.fix_suggestion,
                    "affected_entities": v.affected_entities,
                }
                for v in packet.constraint_violations
            ],
            "prop_issues": packet.prop_issues,
            "character_issues": packet.character_issues,
            "validation_summary": packet.validation_summary,
        }

    def _run_llm_analysis(
        self,
        episode: int,
        script_content: str,
        bible_chars: str,
        portrait_info: str,
    ) -> dict[str, Any]:
        """运行LLM分析"""
        # 构建prompt
        prompt = self._build_prompt(
            episode=episode,
            bible_chars=bible_chars,
            portrait_info=portrait_info,
            script_content=script_content,
        )

        # 调用LLM
        system = "你是一个专业的剧本QA专家。请分析剧本中的问题。"
        raw = call_llm(
            prompt,
            system=system,
            estimated_tokens=config.ESTIMATED_TOKENS_DEFAULT,
            temperature=0.1,
        )

        # 解析结果
        try:
            return self._parse_qa_payload(raw)
        except Exception as exc:
            logger.warning("LLM QA parse failed: %s", exc)
            return {"issues": [], "errors": [], "suggestions": []}

    def _merge_results(
        self, structural_result: dict, llm_result: dict
    ) -> dict[str, Any]:
        """合并结构化验证和LLM分析结果"""
        # 合并问题列表
        structural_issues = []
        for violation in structural_result.get("constraint_violations", []):
            structural_issues.append({
                "type": "structural_constraint",
                "severity": violation.get("severity", "warning"),
                "title": violation.get("constraint_id", ""),
                "description": violation.get("message", ""),
                "location": {"script_section": violation.get("location", "")},
                "suggestion": violation.get("fix_suggestion", ""),
                "source": "structural_validator",
            })

        for issue in structural_result.get("prop_issues", []):
            structural_issues.append({
                "type": "prop_continuity",
                "severity": "warning",
                "title": issue.get("type", ""),
                "description": issue.get("message", ""),
                "location": {"script_section": issue.get("scene", "")},
                "suggestion": issue.get("fix", ""),
                "source": "prop_tracker",
            })

        for issue in structural_result.get("character_issues", []):
            structural_issues.append({
                "type": "character_state",
                "severity": "warning",
                "title": issue.get("type", ""),
                "description": issue.get("message", ""),
                "location": {"script_section": issue.get("scene", "")},
                "suggestion": issue.get("fix", ""),
                "source": "state_machine",
            })

        # LLM问题
        llm_issues = llm_result.get("issues", [])

        # 合并（避免重复）
        all_issues = structural_issues.copy()
        for llm_issue in llm_issues:
            if not self._is_duplicate_issue(llm_issue, all_issues):
                all_issues.append(llm_issue)

        # 计算总体分数
        overall_score = self._calculate_overall_score(all_issues)

        return {
            "issues": all_issues,
            "structural_issue_count": len(structural_issues),
            "llm_issue_count": len(llm_issues),
            "overall_score": overall_score,
            "validation_summary": structural_result.get("validation_summary", {}),
        }

    def _is_duplicate_issue(
        self, new_issue: dict, existing_issues: list[dict]
    ) -> bool:
        """检查是否是重复问题"""
        new_title = str(new_issue.get("title", "")).lower()
        new_location = str(
            (new_issue.get("location") or {}).get("script_section", "")
        ).lower()

        for existing in existing_issues:
            existing_title = str(existing.get("title", "")).lower()
            existing_location = str(
                (existing.get("location") or {}).get("script_section", "")
            ).lower()

            if new_title == existing_title and new_location == existing_location:
                return True
        return False

    def _calculate_overall_score(self, issues: list[dict]) -> int:
        """计算总体分数"""
        severity_scores = {
            "high": 2.0,
            "medium": 1.0,
            "low": 0.35,
            "error": 2.0,
            "warning": 1.0,
            "info": 0.35,
        }

        penalty = 0.0
        for issue in issues:
            severity = str(issue.get("severity", "")).lower()
            penalty += severity_scores.get(severity, 0.6)

        if penalty <= 0:
            return 9
        if penalty <= 1:
            return 8
        if penalty <= 2.5:
            return 7
        if penalty <= 4:
            return 6
        if penalty <= 6:
            return 5
        return 4

    def _generate_repair_directives(
        self, merged_result: dict
    ) -> list[dict[str, Any]]:
        """生成修复指令"""
        directives = []

        for issue in merged_result.get("issues", []):
            directive = {
                "issue_type": issue.get("type", ""),
                "severity": issue.get("severity", ""),
                "title": issue.get("title", ""),
                "location": (issue.get("location") or {}).get("script_section", ""),
                "instruction": issue.get("suggestion", ""),
                "source": issue.get("source", "llm"),
            }
            directives.append(directive)

        # 按优先级排序
        priority_order = {"error": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 3}
        directives.sort(key=lambda x: priority_order.get(x.get("severity", ""), 3))

        return directives

    def _build_story_fact_sheet(self, script: dict[str, Any]) -> dict[str, Any]:
        """从剧本构建故事事实表 — 使用LLM提取结构化事实"""
        content = str(script.get("content") or "").strip()
        if not content:
            return {"episode_objective": "", "character_fact_sheet": [], "prop_fact_sheet": [], "evidence_fact_sheet": [], "helper_motive_sheet": [], "spatial_mechanics_sheet": [], "hook_delta_sheet": []}

        truncated = content[:config.SCRIPT_EXCERPT_CHARS]
        extraction_prompt = (
            "你是一个剧本结构分析专家。请从以下剧本内容中提取结构化事实信息。\n\n"
            "请严格输出JSON，格式如下：\n"
            "```json\n"
            "{\n"
            '  "episode_objective": "本集核心目标（一句话）",\n'
            '  "character_fact_sheet": [\n'
            "    {\n"
            '      "name": "角色名",\n'
            '      "public_layer": "公开面：角色在其他角色面前展示的形象",\n'
            '      "hidden_layer": "隐藏层：角色暗中的真实意图或秘密",\n'
            '      "transition_trigger": "转折触发器：什么事件会导致角色状态变化",\n'
            '      "public_mask_rule": "面具规则：角色需要维持的外在表现"\n'
            "    }\n"
            "  ],\n"
            '  "prop_fact_sheet": [\n'
            "    {\n"
            '      "prop_name": "关键道具名",\n'
            '      "first_scene": "首次出现场景",\n'
            '      "story_function": "剧情功能",\n'
            '      "ownership_rule": "归属规则：道具在谁手中流转"\n'
            "    }\n"
            "  ],\n"
            '  "evidence_fact_sheet": [\n'
            "    {\n"
            '      "evidence_name": "证据/线索名",\n'
            '      "entry_scene": "入画场景",\n'
            '      "story_function": "剧情功能",\n'
            '      "observation_rule": "观察规则：必须在镜头前被看到或比较"\n'
            "    }\n"
            "  ],\n"
            '  "helper_motive_sheet": [\n'
            "    {\n"
            '      "scene_name": "场景名",\n'
            '      "requirement": "帮助行为动机要求"\n'
            "    }\n"
            "  ],\n"
            '  "spatial_mechanics_sheet": [\n'
            "    {\n"
            '      "scene_name": "场景名",\n'
            '      "mechanics_rule": "空间机关规则：锁、暗格、机关的操作路径"\n'
            "    }\n"
            "  ],\n"
            '  "hook_delta_sheet": [\n'
            "    {\n"
            '      "hook_type": "钩子类型(opening/mid/end)",\n'
            '      "content": "钩子内容",\n'
            '      "delta_rule": "增量规则：必须带来新的状态变化或信息"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n\n"
            "要求：\n"
            "1. 只从剧本文本中提取可验证的事实，不要虚构\n"
            "2. 角色的公开面和隐藏层必须能从剧本对白和动作中推断\n"
            "3. 道具必须是推动剧情的关键道具，不是背景摆设\n"
            "4. 证据必须有明确的入画场景和观察方式\n"
            "5. 钩子增量必须指向下一集或下一场的新冲突\n\n"
            f"剧本内容：\n{truncated}"
        )

        try:
            raw = call_llm(extraction_prompt, temperature=0.2, max_tokens=4096)
            parsed = parse_json_object(strip_code_fences(raw.strip()))
            if isinstance(parsed, dict):
                return {
                    "episode_objective": str(parsed.get("episode_objective") or "").strip(),
                    "character_fact_sheet": parsed.get("character_fact_sheet") or [],
                    "prop_fact_sheet": parsed.get("prop_fact_sheet") or [],
                    "evidence_fact_sheet": parsed.get("evidence_fact_sheet") or [],
                    "helper_motive_sheet": parsed.get("helper_motive_sheet") or [],
                    "spatial_mechanics_sheet": parsed.get("spatial_mechanics_sheet") or [],
                    "hook_delta_sheet": parsed.get("hook_delta_sheet") or [],
                }
        except Exception as exc:
            logger.warning("Failed to extract story fact sheet via LLM: %s", exc)

        return {"episode_objective": "", "character_fact_sheet": [], "prop_fact_sheet": [], "evidence_fact_sheet": [], "helper_motive_sheet": [], "spatial_mechanics_sheet": [], "hook_delta_sheet": []}

    def _build_scene_execution_cards(self, script: dict[str, Any]) -> list[dict[str, Any]]:
        """从剧本构建场景执行卡 — 使用LLM提取场景结构"""
        content = str(script.get("content") or "").strip()
        if not content:
            return []

        truncated = content[:config.SCRIPT_EXCERPT_CHARS]
        extraction_prompt = (
            "你是一个剧本结构分析专家。请从以下剧本内容中提取每个场景的执行卡信息。\n\n"
            "请严格输出JSON数组，格式如下：\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "scene_index": 1,\n'
            '    "scene_name": "场景名称",\n'
            '    "opening_state": {\n'
            '      "characters": [{"name": "角色名", "visible_state": "开场时的状态"}],\n'
            '      "props": "开场时道具状态描述"\n'
            "    },\n"
            '    "scene_objective": "本场戏存在的目的",\n'
            '    "scene_conflict": "本场戏的核心冲突",\n'
            '    "required_visual_proofs": ["必须在镜头前证明的事实1", "事实2"],\n'
            '    "public_mask_beats": ["角色维持公开面具的关键节拍"],\n'
            '    "hidden_layer_leaks": ["隐藏层泄露的细节"],\n'
            '    "closing_state": {\n'
            '      "characters": "角色结束时状态变化",\n'
            '      "props": "道具结束时状态"\n'
            "    },\n"
            '    "handoff_to_next_scene": "传递给下一场的承接条件"\n'
            "  }\n"
            "]\n"
            "```\n\n"
            "要求：\n"
            "1. 每个场景必须有明确的目的和冲突\n"
            "2. required_visual_proofs 列出本场必须在镜头前证明的事实\n"
            "3. public_mask_beats 是角色维持外在形象的关键动作\n"
            "4. hidden_layer_leaks 是角色不小心暴露真实意图的细节\n"
            "5. handoff_to_next_scene 描述本场结束时的状态，作为下一场的起点\n\n"
            f"剧本内容：\n{truncated}"
        )

        try:
            raw = call_llm(extraction_prompt, temperature=0.2, max_tokens=4096)
            parsed = parse_json_object(strip_code_fences(raw.strip()))
            if isinstance(parsed, list):
                result: list[dict[str, Any]] = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    result.append({
                        "scene_index": item.get("scene_index"),
                        "scene_name": str(item.get("scene_name") or "").strip(),
                        "opening_state": item.get("opening_state") or {"characters": [], "props": ""},
                        "scene_objective": str(item.get("scene_objective") or "").strip(),
                        "scene_conflict": str(item.get("scene_conflict") or "").strip(),
                        "required_visual_proofs": item.get("required_visual_proofs") or [],
                        "public_mask_beats": item.get("public_mask_beats") or [],
                        "hidden_layer_leaks": item.get("hidden_layer_leaks") or [],
                        "closing_state": item.get("closing_state") or {"characters": "", "props": ""},
                        "handoff_to_next_scene": str(item.get("handoff_to_next_scene") or "").strip(),
                    })
                return result
        except Exception as exc:
            logger.warning("Failed to extract scene execution cards via LLM: %s", exc)

        return []

    def _load_script(self, session, episode: int) -> dict | None:
        """加载剧本"""
        try:
            row = session.query(Script).filter(
                Script.book_id == self.book_id,
                Script.episode == episode,
            ).order_by(Script.id.desc()).first()
            if not row:
                return None
            return {
                "episode": row.episode,
                "content": row.content or "",
            }
        except Exception as exc:
            logger.warning("Failed to load script: %s", exc)
            return None

    def _load_bible(self, session) -> str:
        """加载圣经"""
        try:
            row = session.query(BookBible).filter(
                BookBible.book_id == self.book_id
            ).order_by(BookBible.id.desc()).first()
            return row.content if row else ""
        except Exception as exc:
            logger.warning("Failed to load bible: %s", exc)
            return ""

    def _build_portrait_info(self, session) -> str:
        """构建角色画像信息"""
        portrait_info = ""
        try:
            portraits = session.query(CharacterProfile).filter(
                CharacterProfile.book_id == self.book_id
            ).all()
            for portrait in portraits:
                portrait_info += f"\n### {portrait.name}\n"
                portrait_info += f"性别: {portrait.gender} | 年龄: {portrait.age_range}\n"
                portrait_info += f"说话风格: {portrait.speech_style}\n"
        except Exception as exc:
            logger.warning("Failed to load character profiles: %s", exc)
        return portrait_info or "(暂无画像数据)"

    def _build_prompt(
        self,
        *,
        episode: int,
        bible_chars: str,
        portrait_info: str,
        script_content: str,
    ) -> str:
        """构建LLM prompt"""
        prompt = load_prompt(
            "qa/qa",
            bible_chars=bible_chars[:config.CHAR_INFO_CHARS],
            portrait_info=portrait_info[:config.PORTRAIT_EXCERPT_CHARS],
            episode=episode,
            script=script_content[:5000],
        )
        skill_block = build_production_skill_prompt_block(self.book_id, "qa")
        return f"{skill_block}\n\n{prompt}"

    def _parse_qa_payload(self, raw: str) -> dict:
        """解析QA结果"""
        return parse_json_object(raw, label="qa payload", required_keys={"issues"})
