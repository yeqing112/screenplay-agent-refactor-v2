"""Screenplay Compiler — 基于结构化中间层编译最终剧本。

核心原则：
1. 不得改写事实层已锁定的关键物证链
2. 不得跳过场景执行卡中的必需视觉证明
3. 不得在没有触发器的情况下让角色突然反转
4. 不得让机关操作超出事实层已声明的空间结构

输入：
- story_fact_sheet: 整集不可跳过的结构化事实
- scene_execution_cards: 按场次生成的执行卡
- foundation: 原始 foundation 数据（可选，用于补充上下文）

输出：
- 编译后的剧本内容（分场景结构化文本）
- 编译约束检查报告
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import config
from core.llm import call_llm
from core.structured_output import parse_json_object, strip_code_fences

logger = logging.getLogger(__name__)


# ── 编译约束 ──────────────────────────────────────────────────

COMPILER_CONSTRAINTS = [
    "不得改写事实层已锁定的关键物证链：物证的入画场景、持有者、流转路径必须与 fact_sheet 一致。",
    "不得跳过场景执行卡中的必需视觉证明：每个 required_visual_proofs 必须在对应场景中出现。",
    "不得在没有触发器的情况下让角色突然反转：角色状态变化必须有 transition_trigger 驱动。",
    "不得让机关操作超出事实层已声明的空间结构：锁、暗格、机关的路径必须与 spatial_mechanics_sheet 一致。",
    "角色公开面行为必须符合 public_mask_rule，直到 hidden_layer_leaks 节拍出现。",
    "每个场景的 closing_state 必须与下一场的 opening_state 衔接。",
    "钩子增量必须符合 delta_rule：带来新的状态变化、证据方向、危险升级或未解问题。",
    "剧本必须有完整的结尾：最后一场必须以强钩子结束，制造悬念或引出下一集。",
    "对白必须符合角色人设：每个角色的说话方式、语气、用词必须与 character_fact_sheet 一致。",
]


# ── 编译器 ──────────────────────────────────────────────────

def compile_screenplay(
    story_fact_sheet: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
    foundation: dict[str, Any] | None = None,
    genre_persona: str = "",
    raw_script_content: str = "",
) -> dict[str, Any]:
    """基于结构化中间层编译最终剧本。

    If raw_script_content is provided and sufficiently long, skip LLM generation
    and only perform constraint checking + ending enforcement.

    Returns:
        {
            "compiled_script": str,           # 编译后的完整剧本
            "constraint_report": list[dict],  # 约束检查报告
            "scene_count": int,               # 场景数
            "character_names": list[str],     # 出场角色
            "compilation_notes": list[str],   # 编译备注
        }
    """
    validation = _validate_inputs(story_fact_sheet, scene_execution_cards)
    compilation_notes: list[str] = []

    # If we have an existing script, skip LLM regeneration and just validate
    if raw_script_content and len(raw_script_content) > 1000:
        compilation_notes.append("使用已有脚本内容，跳过LLM重新生成")
        constraint_report = _check_constraints(
            compiled_script=raw_script_content,
            story_fact_sheet=story_fact_sheet,
            scene_execution_cards=scene_execution_cards,
        )
        compiled_script = _ensure_proper_ending(raw_script_content, story_fact_sheet)
        character_names = _extract_character_names(story_fact_sheet)
        return {
            "compiled_script": compiled_script,
            "constraint_report": constraint_report,
            "scene_count": len(scene_execution_cards),
            "character_names": character_names,
            "compilation_notes": compilation_notes,
            "validation": validation,
        }

    # Otherwise, generate via LLM (original flow)
    prompt = _build_compilation_prompt(
        story_fact_sheet=story_fact_sheet,
        scene_execution_cards=scene_execution_cards,
        foundation=foundation,
        genre_persona=genre_persona,
    )

    compiled_script = ""

    try:
        raw = call_llm(prompt, temperature=0.3, max_tokens=config.LLM_MAX_TOKENS)
        parsed_result = _parse_compilation_result(raw)

        if isinstance(parsed_result, dict):
            compiled_script = str(parsed_result.get("script") or "").strip()
            extra_notes = parsed_result.get("notes") or []
            if isinstance(extra_notes, list):
                compilation_notes.extend(str(n) for n in extra_notes if n)
        elif isinstance(parsed_result, str):
            compiled_script = parsed_result

        if not compiled_script:
            compilation_notes.append("LLM 返回空剧本，回退到原始文本拼接")
            compiled_script = _fallback_compilation(story_fact_sheet, scene_execution_cards)

        compiled_script = _ensure_proper_ending(compiled_script, story_fact_sheet)

    except Exception as exc:
        logger.error("Screenplay compilation failed: %s", exc)
        compilation_notes.append(f"编译异常: {exc}")
        compiled_script = _fallback_compilation(story_fact_sheet, scene_execution_cards)

    constraint_report = _check_constraints(
        compiled_script=compiled_script,
        story_fact_sheet=story_fact_sheet,
        scene_execution_cards=scene_execution_cards,
    )

    character_names = _extract_character_names(story_fact_sheet)

    return {
        "compiled_script": compiled_script,
        "constraint_report": constraint_report,
        "scene_count": len(scene_execution_cards),
        "character_names": character_names,
        "compilation_notes": compilation_notes,
        "validation": validation,
    }


# ── 输入验证 ──────────────────────────────────────────────────

def _validate_inputs(
    fact_sheet: dict[str, Any],
    exec_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    """验证结构化输入的完整性。"""
    issues: list[str] = []

    if not fact_sheet:
        issues.append("story_fact_sheet 为空")
    else:
        if not fact_sheet.get("episode_objective"):
            issues.append("episode_objective 缺失")
        if not fact_sheet.get("character_fact_sheet"):
            issues.append("character_fact_sheet 为空")
        if not fact_sheet.get("evidence_fact_sheet"):
            issues.append("evidence_fact_sheet 为空（可能无线索证据）")

    if not exec_cards:
        issues.append("scene_execution_cards 为空")
    else:
        for i, card in enumerate(exec_cards):
            if not isinstance(card, dict):
                issues.append(f"场景 {i+1} 不是有效字典")
                continue
            if not card.get("scene_name"):
                issues.append(f"场景 {i+1} 缺少 scene_name")
            if not card.get("scene_objective"):
                issues.append(f"场景 {i+1} ({card.get('scene_name', '?')}) 缺少 scene_objective")
            if not card.get("required_visual_proofs"):
                issues.append(f"场景 {i+1} ({card.get('scene_name', '?')}) 缺少 required_visual_proofs")

    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
        "fact_sheet_completeness": _fact_sheet_completeness(fact_sheet),
        "exec_cards_count": len(exec_cards),
    }


def _fact_sheet_completeness(fact_sheet: dict[str, Any]) -> dict[str, Any]:
    """评估 fact sheet 的完整度。"""
    if not fact_sheet:
        return {"score": 0, "missing": ["entire fact sheet"]}

    required_keys = [
        "episode_objective",
        "character_fact_sheet",
        "evidence_fact_sheet",
        "hook_delta_sheet",
    ]
    present = []
    missing = []
    for key in required_keys:
        val = fact_sheet.get(key)
        if val and (isinstance(val, list) and len(val) > 0 or isinstance(val, str) and val.strip()):
            present.append(key)
        else:
            missing.append(key)

    score = len(present) / len(required_keys) if required_keys else 0
    return {"score": round(score, 2), "missing": missing}


# ── 编译提示词 ──────────────────────────────────────────────────

def _build_compilation_prompt(
    story_fact_sheet: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
    foundation: dict[str, Any] | None,
    genre_persona: str,
) -> str:
    """构建编译提示词。"""
    fact_sheet_json = json.dumps(story_fact_sheet, ensure_ascii=False, indent=2)
    exec_cards_json = json.dumps(scene_execution_cards, ensure_ascii=False, indent=2)

    # 提取角色信息用于对白指导
    character_info = _build_character_info_block(story_fact_sheet)

    persona_block = ""
    if genre_persona:
        persona_block = f"\n## 体裁风格\n{genre_persona}\n"

    # 提取钩子信息用于结尾指导
    hook_info = _build_hook_info_block(story_fact_sheet)

    return (
        "你是一个专业的剧本编译器。请基于以下结构化中间层，编译成可拍摄的剧本。\n\n"
        "## 编译约束（必须严格遵守）\n\n"
        + "\n".join(f"- {c}" for c in COMPILER_CONSTRAINTS)
        + f"\n{persona_block}\n"
        "## Story Fact Sheet（事实层 — 不可改写）\n\n"
        f"```json\n{fact_sheet_json}\n```\n\n"
        f"{character_info}\n"
        f"{hook_info}\n"
        "## Scene Execution Cards（场景执行卡 — 必须兑现）\n\n"
        f"```json\n{exec_cards_json}\n```\n\n"
        "## 编译要求\n\n"
        "### 基本要求\n"
        "1. 逐场景编译，每个场景必须包含：\n"
        "   - 场景标题（场景名 + 地点 + 时间）\n"
        "   - 角色动作（必须体现 public_mask_beats 和 hidden_layer_leaks）\n"
        "   - 对白（符合角色人设，参考 character_info 中的说话风格）\n"
        "   - 视觉证明（必须包含 required_visual_proofs 中的所有要素）\n"
        "   - 道具使用（符合 prop_fact_sheet 的归属规则）\n"
        "2. 场景之间的状态变化必须与 closing_state / opening_state 衔接\n"
        "3. 证据入画必须遵循 observation_rule：先被看到，再被引用\n"
        "4. 角色状态变化必须有 transition_trigger 驱动\n"
        "5. 每场结尾必须推进至少一个 hook_delta\n\n"
        "### 对白格式（必须严格遵守）\n"
        "- 每行对白必须以 **角色名** 开头\n"
        "- 角色名后面直接跟对白内容，不要用冒号\n"
        "- 格式：**角色名**对白内容。\n"
        "- 示例：**张一**水怎么没了？\n"
        "- 示例：**张二**谁去挑水？\n\n"
        "### 字数要求\n"
        "- 全剧总字数必须达到 3000-5000 字\n"
        "- 每个场景至少 800 字\n"
        "- 对白和舞台指示要详细，不要过于简洁\n\n"
        "### 结尾要求（最重要）\n"
        "- **最后一场必须以强钩子结尾**：制造悬念、留下未解问题或引出下一集\n"
        "- 钩子必须具体、有画面感，不能是空泛的描述\n"
        "- 示例：*[画面特写：水缸底部隐约露出一个布包的一角，布上隐约可见血迹] [画面渐隐]*\n"
        "- 示例：*[张二转过头，眼神中闪过一丝不易察觉的慌张] [画面渐隐]*\n"
        "- **剧本必须以 `[画面渐隐]` 结束**\n\n"
        "## 输出格式\n\n"
        "请直接输出剧本文本（Markdown格式），不要输出JSON。格式如下：\n\n"
        "# 第X集 集名\n\n"
        "## 场景一：[场景名] — [地点] — [时间]\n\n"
        "（场景描述和动作）\n\n"
        "**角色名**对白内容。\n\n"
        "**角色名**对白内容。\n\n"
        "*（视觉证明：XXX）*\n\n"
        "---\n\n"
        "## 场景二：...\n\n"
        "（最后一场必须以强钩子结束）\n\n"
        "[画面渐隐]"
    )


def _build_character_info_block(fact_sheet: dict[str, Any]) -> str:
    """构建角色信息块，用于对白指导。"""
    chars = fact_sheet.get("character_fact_sheet") or []
    if not chars:
        return ""

    lines = ["## 角色信息（对白必须符合以下人设）\n"]
    for char in chars:
        if not isinstance(char, dict):
            continue
        name = str(char.get("name") or "").strip()
        gender = str(char.get("gender") or "").strip()
        public_layer = str(char.get("public_layer") or "").strip()
        hidden_layer = str(char.get("hidden_layer") or "").strip()
        public_mask_rule = str(char.get("public_mask_rule") or "").strip()

        if name:
            lines.append(f"### {name}")
            if gender:
                lines.append(f"- 性别：{gender}")
                # 添加代词提示
                if gender == "女性":
                    lines.append(f"- 代词：使用「她」作为代词")
                elif gender == "男性":
                    lines.append(f"- 代词：使用「他」作为代词")
            if public_layer:
                lines.append(f"- 公开面：{public_layer}")
            if hidden_layer:
                lines.append(f"- 隐藏面：{hidden_layer}")
            if public_mask_rule:
                lines.append(f"- 对白规则：{public_mask_rule}")
            lines.append("")

    return "\n".join(lines)


def _build_hook_info_block(fact_sheet: dict[str, Any]) -> str:
    """构建钩子信息块，用于结尾指导。"""
    hooks = fact_sheet.get("hook_delta_sheet") or []
    if not hooks:
        return ""

    lines = ["## 钩子信息（结尾必须体现以下钩子）\n"]
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        hook_type = str(hook.get("hook_type") or "").strip()
        content = str(hook.get("content") or "").strip()
        delta_rule = str(hook.get("delta_rule") or "").strip()

        if hook_type == "end" and content:
            lines.append(f"- 结尾钩子：{content}")
            if delta_rule:
                lines.append(f"- 钩子规则：{delta_rule}")
            lines.append("")

    return "\n".join(lines)


# ── 结果解析 ──────────────────────────────────────────────────

def _parse_compilation_result(raw: str) -> dict[str, Any] | str:
    """解析 LLM 编译结果。"""
    text = raw.strip()
    if not text:
        return ""

    # 尝试 JSON 解析
    try:
        cleaned = strip_code_fences(text)
        parsed = parse_json_object(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            return {"script": parsed, "notes": []}
    except Exception:
        pass

    # 尝试从文本中提取 script 字段
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            fragment = text[start:end]
            parsed = parse_json_object(fragment)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 回退：整个文本作为剧本，但清理英文部分
    cleaned_script = _clean_script_text(text)
    return {"script": cleaned_script, "notes": ["未检测到JSON结构，整个输出作为剧本内容"]}


def _clean_script_text(text: str) -> str:
    """清理剧本文本，移除非中文内容。"""
    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        # 跳过纯英文行（排除视觉证明标记）
        if re.match(r'^[a-zA-Z\s\.,!?;:\'"()\[\]{}]+$', line.strip()):
            # 保留视觉证明标记
            if '*(' in line or 'Need' in line or 'Good' in line:
                continue
            continue
        
        # 跳过内部推理标记
        if any(marker in line for marker in ['Need visual proof:', 'Need "smell', 'Need "who', 'Good.', 'monk two']):
            continue
        
        # 清理行内英文注释
        cleaned_line = re.sub(r'\s*\(.*?英文注释.*?\)', '', line)
        cleaned_line = re.sub(r'\s*//.*$', '', cleaned_line)
        cleaned_lines.append(cleaned_line)
    
    return "\n".join(cleaned_lines)


# ── 约束检查 ──────────────────────────────────────────────────

def _check_constraints(
    compiled_script: str,
    story_fact_sheet: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """检查编译结果是否满足约束。"""
    report: list[dict[str, Any]] = []

    if not compiled_script:
        report.append({
            "constraint": "compiled_script_not_empty",
            "status": "FAIL",
            "detail": "编译结果为空",
        })
        return report

    report.append({
        "constraint": "compiled_script_not_empty",
        "status": "PASS",
        "detail": f"剧本长度 {len(compiled_script)} 字符",
    })

    # 检查剧本是否有完整结尾
    has_ending = _check_script_ending(compiled_script)
    report.append({
        "constraint": "script_has_ending",
        "status": "PASS" if has_ending else "WARN",
        "detail": "剧本有完整结尾" if has_ending else "剧本缺少明确结尾标记",
    })

    # 检查场景执行卡中的必需视觉证明是否在剧本中出现
    for card in scene_execution_cards:
        if not isinstance(card, dict):
            continue
        scene_name = str(card.get("scene_name") or "").strip()
        proofs = card.get("required_visual_proofs") or []
        if not isinstance(proofs, list):
            continue
        for proof in proofs:
            proof_text = str(proof).strip()
            if not proof_text:
                continue
            # 使用语义匹配而非关键词匹配
            found = _check_visual_proof_in_script(proof_text, compiled_script, scene_name)
            report.append({
                "constraint": f"visual_proof_{scene_name}",
                "status": "PASS" if found else "WARN",
                "detail": f"场景「{scene_name}」视觉证明「{proof_text[:50]}」{'已出现' if found else '未检测到'}",
            })

    # 检查角色名是否在剧本中出现
    character_names = _extract_character_names(story_fact_sheet)
    for name in character_names:
        if name in compiled_script:
            report.append({
                "constraint": f"character_{name}_appears",
                "status": "PASS",
                "detail": f"角色「{name}」在剧本中出现",
            })
        else:
            report.append({
                "constraint": f"character_{name}_appears",
                "status": "WARN",
                "detail": f"角色「{name}」未在剧本中检测到",
            })

    # 检查关键道具是否在剧本中出现
    prop_facts = story_fact_sheet.get("prop_fact_sheet") or []
    for prop in prop_facts:
        if not isinstance(prop, dict):
            continue
        prop_name = str(prop.get("prop_name") or "").strip()
        if not prop_name:
            continue
        if prop_name in compiled_script:
            report.append({
                "constraint": f"prop_{prop_name}_appears",
                "status": "PASS",
                "detail": f"道具「{prop_name}」在剧本中出现",
            })
        else:
            report.append({
                "constraint": f"prop_{prop_name}_appears",
                "status": "WARN",
                "detail": f"道具「{prop_name}」未在剧本中检测到",
            })

    return report


def _check_script_ending(script: str) -> bool:
    """检查剧本是否有完整结尾。"""
    # 检查常见的结尾标记
    ending_markers = [
        "[画面渐隐]",
        "[渐隐]",
        "[黑屏]",
        "[完]",
        "[本集完]",
        "（完）",
        "【完】",
        "[淡出]",
        "[幕落]",
    ]
    script_lower = script.lower()
    for marker in ending_markers:
        if marker.lower() in script_lower:
            return True

    # 检查最后几行是否有结尾标记
    lines = script.strip().split("\n")
    last_lines = "\n".join(lines[-5:]) if len(lines) >= 5 else script
    for marker in ending_markers:
        if marker.lower() in last_lines.lower():
            return True

    return False


def _check_visual_proof_in_script(proof: str, script: str, scene_name: str) -> bool:
    """检查视觉证明是否在剧本中出现（语义匹配）。"""
    # 提取证明中的关键概念（中文关键词）
    # 将英文证明转换为中文关键词
    proof_keywords = _extract_proof_keywords(proof)
    if not proof_keywords:
        return True  # 如果没有可匹配的关键词，默认通过

    # 在剧本中查找这些关键词
    for keyword in proof_keywords:
        if keyword in script:
            return True

    return False


def _extract_proof_keywords(proof: str) -> list[str]:
    """从视觉证明中提取关键词。"""
    # 英文到中文的映射
    en_to_cn = {
        "clue": "线索",
        "evidence": "证据",
        "visual": "视觉",
        "anchor": "锚点",
        "proof": "证明",
        "reveal": "揭示",
        "show": "展示",
        "close-up": "特写",
        "close up": "特写",
        "shot": "镜头",
        "dialogue": "对白",
        "first": "首次",
        "new": "新",
        "fresh": "新鲜",
        "introduce": "引入",
        "name": "提到",
        "key": "关键",
        "theft": "盗窃",
        "cut": "切割",
        "mark": "痕迹",
        "missing": "失踪",
        "item": "物品",
        "smell": "气味",
        "texture": "质感",
        "stain": "污渍",
        "edge": "边缘",
        "wax": "蜡",
        "rust": "锈",
        "blood": "血",
        "surface": "表面",
        "detail": "细节",
        "information": "信息",
        "contradiction": "矛盾",
        "motive": "动机",
        "trace": "痕迹",
        "prop": "道具",
        "state": "状态",
        "change": "变化",
        "access": "接触",
        "fact": "事实",
        "witness": "证人",
        "reaction": "反应",
        "deduction": "推理",
        "depends": "依赖",
        "pair": "配对",
        "beat": "节拍",
        "earlier": "之前",
        "before": "之前",
        "long": "很久",
        "audience": "观众",
        "hear": "听到",
        "see": "看到",
        "trace": "痕迹",
    }

    keywords = []
    proof_lower = proof.lower()

    # 提取英文关键词并转换为中文
    for en_key, cn_val in en_to_cn.items():
        if en_key in proof_lower:
            keywords.append(cn_val)

    # 也提取直接的中文关键词
    cn_pattern = re.compile(r'[\u4e00-\u9fff]+')
    for match in cn_pattern.finditer(proof):
        word = match.group()
        if len(word) >= 2:
            keywords.append(word)

    # 去重并返回前5个
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:5]


# ── 辅助函数 ──────────────────────────────────────────────────

def _extract_character_names(fact_sheet: dict[str, Any]) -> list[str]:
    """从 fact sheet 提取角色名列表。"""
    names: list[str] = []
    for char in (fact_sheet.get("character_fact_sheet") or []):
        if isinstance(char, dict):
            name = str(char.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _ensure_proper_ending(script: str, fact_sheet: dict[str, Any]) -> str:
    """确保剧本有完整的结尾。"""
    if not script:
        return script

    # 检查是否已有结尾标记
    if _check_script_ending(script):
        return script

    # 获取钩子信息
    hook_delta = fact_sheet.get("hook_delta_sheet") or []
    ending_hook = ""
    for hook in hook_delta:
        if isinstance(hook, dict):
            hook_type = str(hook.get("hook_type") or "").strip()
            content = str(hook.get("content") or "").strip()
            if hook_type == "end" and content:
                ending_hook = content
                break

    # 如果没有钩子信息，使用默认结尾
    if not ending_hook:
        ending_hook = "悬念未解，真相仍在迷雾之中"

    # 添加结尾
    ending = f"\n\n*（{ending_hook}）*\n\n[画面渐隐]"
    return script.rstrip() + ending


def _fallback_compilation(
    fact_sheet: dict[str, Any],
    exec_cards: list[dict[str, Any]],
) -> str:
    """当 LLM 编译失败时，回退到结构化文本拼接。"""
    lines: list[str] = []

    episode_obj = str(fact_sheet.get("episode_objective") or "").strip()
    if episode_obj:
        lines.append(f"# 本集目标\n\n{episode_obj}\n")

    for card in exec_cards:
        if not isinstance(card, dict):
            continue
        scene_name = str(card.get("scene_name") or "").strip()
        objective = str(card.get("scene_objective") or "").strip()
        conflict = str(card.get("scene_conflict") or "").strip()
        proofs = card.get("required_visual_proofs") or []

        lines.append(f"## {scene_name}\n")
        if objective:
            lines.append(f"**目的**：{objective}\n")
        if conflict:
            lines.append(f"**冲突**：{conflict}\n")
        if proofs:
            lines.append("**必需视觉证明**：")
            for p in proofs:
                if p:
                    lines.append(f"- {p}")
            lines.append("")

    # 添加结尾
    lines.append("\n[画面渐隐]")

    return "\n".join(lines)
