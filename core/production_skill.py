"""Production Skill registry, project state, and runtime helpers."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from typing import Any

from models import get_kv, set_kv
from core.repair import build_structural_validation_block, format_structural_validation_for_prompt
from core import safe_json_loads


# ── Structured Scene State Model ─────────────────────────────────────────────

@dataclass
class CharacterState:
    """角色在场景结束时的结构化状态。"""
    name: str
    gender: str = ""
    position: str = ""
    emotional_state: str = ""
    props_held: list[str] = field(default_factory=list)
    behavior_guardrails: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CharacterState":
        return cls(
            name=str(d.get("name") or "").strip(),
            gender=str(d.get("gender") or "").strip(),
            position=str(d.get("position") or "").strip(),
            emotional_state=str(d.get("emotional_state") or "").strip(),
            props_held=[str(p) for p in (d.get("props_held") or []) if p],
            behavior_guardrails=[str(g) for g in (d.get("behavior_guardrails") or []) if g],
        )


@dataclass
class PropState:
    """道具在场景结束时的结构化状态。"""
    name: str
    owner: str = ""
    location: str = ""
    physical_state: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PropState":
        return cls(
            name=str(d.get("name") or "").strip(),
            owner=str(d.get("owner") or "").strip(),
            location=str(d.get("location") or "").strip(),
            physical_state=str(d.get("physical_state") or "").strip(),
        )


@dataclass
class SceneState:
    """场景结束时的完整结构化状态，用于传递给下一场景。"""
    characters: list[CharacterState] = field(default_factory=list)
    props: list[PropState] = field(default_factory=list)
    environmental_state: str = ""
    time_anchor: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": [c.to_dict() for c in self.characters],
            "props": [p.to_dict() for p in self.props],
            "environmental_state": self.environmental_state,
            "time_anchor": self.time_anchor,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SceneState":
        if not d:
            return cls()
        chars = []
        for c in (d.get("characters") or []):
            if isinstance(c, dict) and c.get("name"):
                chars.append(CharacterState.from_dict(c))
        props = []
        for p in (d.get("props") or []):
            if isinstance(p, dict) and p.get("name"):
                props.append(PropState.from_dict(p))
        return cls(
            characters=chars,
            props=props,
            environmental_state=str(d.get("environmental_state") or "").strip(),
            time_anchor=str(d.get("time_anchor") or "").strip(),
        )

    def format_for_prompt(self) -> str:
        """格式化为 prompt 可读的文本。"""
        lines: list[str] = []
        if self.time_anchor:
            lines.append(f"### 时间锚点\n当前时间：{self.time_anchor}")
        if self.characters:
            lines.append("### 角色状态")
            for c in self.characters:
                held = "、".join(c.props_held) if c.props_held else "无"
                gender_info = f"，性别={c.gender}" if c.gender else ""
                lines.append(f"- {c.name}：位置={c.position}，情绪={c.emotional_state}{gender_info}，持有道具=[{held}]")
                if c.behavior_guardrails:
                    lines.append(f"  行为约束：{'；'.join(c.behavior_guardrails)}")
        if self.props:
            lines.append("### 道具状态")
            for p in self.props:
                owner_info = f"持有人={p.owner}" if p.owner else f"位置={p.location}"
                lines.append(f"- {p.name}：{owner_info}，物理状态={p.physical_state}")
        if self.environmental_state:
            lines.append(f"### 环境状态\n{self.environmental_state}")
        return "\n".join(lines)

    def extract_prop_names(self) -> list[str]:
        """提取所有道具名称，用于一致性校验。"""
        return [p.name for p in self.props if p.name]


DEFAULT_SKILL_ID = "rebirth_suspense"


_COMMON_HARD_CONSTRAINTS = [
    "开场 5 秒必须出现情绪事件或信息事件，不能平铺交代。",
    "每场戏都必须发生局势变化，不能只有解释和铺垫。",
    "每集至少推进一个旧问题，并制造一个新问题。",
    "关键剧情节点必须天然可分镜化，不能依赖大段说明。",
    "关键人物、场景、道具必须可资产化并可复用。",
]

_COMMON_SOFT_PREFERENCES = [
    "优先使用低理解成本的画面与对白。",
    "优先写可以被镜头直接捕捉的行为，而不是抽象判断。",
    "镜头描述优先服务情绪推进和信息揭示，不做空泛文艺化抒情。",
]

_COMMON_FORBIDDEN_PATTERNS = [
    "纯说明式对白",
    "无画面支撑的长段解释",
    "没有镜头目的的分镜复述",
    "角色状态与已绑定资产明显漂移",
    "关键证据只存在于台词里而不进入画面",
]


_BUILTIN_SKILLS: dict[str, dict[str, Any]] = {
    "rebirth_suspense": {
        "skill_meta": {
            "id": "rebirth_suspense",
            "name": "重生悬疑 Production Skill",
            "version": "1.0.0",
            "platforms": ["douyin", "kuaishou"],
            "tracks": ["重生悬疑"],
            "stages": ["script", "directing", "asset", "qa"],
            "summary": "强调旧疑点推进、新疑点生成、证据驱动和可视化悬念。",
        },
        "script_rules": {
            "positioning": "重生不是噱头，核心是带着部分秘密重开局。",
            "episode_structure": [
                "开场立即给出情绪压力或异常信息。",
                "中段通过人物选择推动疑点升级。",
                "结尾同时给出情绪钩子和信息钩子。",
            ],
            "character_rules": [
                "主角知道部分真相，但不能全知全能。",
                "关系线必须成为悬疑推进器的一部分。",
            ],
            "evidence_rules": [
                "关键疑点尽量落到证据、动作、现场痕迹、关键道具。",
                "禁止只靠解释交代悬疑转折。",
            ],
        },
        "directing_rules": {
            "lens_intent": [
                "每个镜头必须标明主要目的：建立、揭示、压迫、误导、反转、收束之一。",
                "静态提示词负责首帧画面事实，运动提示词负责时间轴和情绪推进。",
            ],
            "camera_preferences": [
                "悬疑信息揭示优先使用特写、遮挡、视线引导和空间层次。",
                "冲突场优先强调前后景关系和人物站位变化。",
            ],
            "continuity_rules": [
                "镜头必须继承同一角色的版本资产，允许状态变化但不允许身份漂移。",
                "关键证据道具进入画面时必须保持材质、损耗、形制一致。",
            ],
        },
        "asset_rules": {
            "character_policy": [
                "人物资产分为基础定妆、集级默认、分镜精调三个层级。",
                "同一角色允许跨集多造型、多状态版本。",
            ],
            "location_policy": [
                "场景资产分为基础场景与时间、损耗、情绪版本。",
                "关键场景必须能沉淀为复用空间资产。",
            ],
            "prop_policy": [
                "道具区分普通道具、关键证据道具、连续性道具。",
                "高重要度道具必须能被剧本和分镜共同引用。",
            ],
            "reference_policy": [
                "所有核心资产优先绑定结构化 reference_token 与参考图。",
                "提示词中允许自然提及引用 token，但后端必须保存结构化绑定。",
            ],
        },
        "hard_constraints": _COMMON_HARD_CONSTRAINTS,
        "soft_preferences": _COMMON_SOFT_PREFERENCES,
        "forbidden_patterns": _COMMON_FORBIDDEN_PATTERNS,
        "qa_checks": [
            "开场是否有情绪事件或信息事件",
            "每场戏是否发生局势变化",
            "每集是否推进旧疑点并制造新疑点",
            "分镜是否体现镜头目的与信息揭示",
            "关键资产是否有结构化沉淀与引用",
        ],
        "output_contracts": {
            "script": ["剧集设定", "集级大纲", "场次级剧本", "情绪点标注", "疑点/反转点标注"],
            "directing": ["镜头级分镜结构", "静态提示词", "运动提示词", "镜头意图标签", "资产引用列表"],
            "asset": ["资产主卡", "版本卡", "参考图绑定", "提示词模板", "上下游引用关系"],
            "qa": ["通过/警告/失败", "失败原因", "自动修复建议", "回注修复指令"],
        },
    },
    "romance_abuse": {
        "skill_meta": {
            "id": "romance_abuse",
            "name": "情感虐恋 Production Skill",
            "version": "1.0.0",
            "platforms": ["douyin", "kuaishou"],
            "tracks": ["情感虐恋"],
            "stages": ["script", "directing", "asset", "qa"],
            "summary": "强调关系压强、误会反转、情绪对撞和人物状态版本。",
        },
        "script_rules": {
            "positioning": "核心不是虐本身，而是关系失衡与情绪兑现。",
            "episode_structure": [
                "开场必须直接落入关系压力点。",
                "每集至少制造一次误判、错位或情绪背刺。",
                "尾钩优先留在人际关系或身份真相上。",
            ],
            "character_rules": [
                "人物选择比人物表态更重要。",
                "冲突必须落在具体互动，而不是空泛吵架。",
            ],
            "evidence_rules": [
                "情绪证据要可见，例如礼物、伤痕、旧照、短信、空间痕迹。",
            ],
        },
        "directing_rules": {
            "lens_intent": [
                "镜头优先放大关系距离、身体动作克制与情绪反差。",
            ],
            "camera_preferences": [
                "对峙场景优先使用中近景和交叉视线组织。",
            ],
            "continuity_rules": [
                "人物妆发与服装状态必须服务情绪阶段，不可随意跳变。",
            ],
        },
        "asset_rules": {
            "character_policy": ["人物必须支持情绪阶段版和关系阶段版资产。"],
            "location_policy": ["关系关键场必须支持重复复用并体现阶段变化。"],
            "prop_policy": ["礼物、信件、手机消息等必须作为高重要度道具。"],
            "reference_policy": ["关系核心人物优先绑定稳定参考图与版本资产。"],
        },
        "hard_constraints": _COMMON_HARD_CONSTRAINTS,
        "soft_preferences": _COMMON_SOFT_PREFERENCES,
        "forbidden_patterns": _COMMON_FORBIDDEN_PATTERNS,
        "qa_checks": [
            "是否建立明确关系压强",
            "是否存在具体情绪对撞",
            "关键情绪道具是否进入画面",
        ],
        "output_contracts": {
            "script": ["关系设定", "集级冲突点", "场次级剧本", "情绪爆点标注"],
            "directing": ["镜头级分镜结构", "静态提示词", "运动提示词", "关系镜头标签", "资产引用列表"],
            "asset": ["人物主卡", "关系阶段卡", "情绪道具卡", "参考图绑定"],
            "qa": ["通过/警告/失败", "失败原因", "自动修复建议"],
        },
    },
    "rise_revenge": {
        "skill_meta": {
            "id": "rise_revenge",
            "name": "逆袭爽剧 Production Skill",
            "version": "1.0.0",
            "platforms": ["douyin", "kuaishou"],
            "tracks": ["逆袭爽剧"],
            "stages": ["script", "directing", "asset", "qa"],
            "summary": "强调压制-反击-翻盘节奏、爽点兑现和强动作可拍性。",
        },
        "script_rules": {
            "positioning": "核心是连续压制后快速兑现反击。",
            "episode_structure": [
                "尽早建立压制局面。",
                "中段埋下反击手段或资源。",
                "结尾最好有阶段性翻盘或更大压制升级。",
            ],
            "character_rules": [
                "主角每集至少做出一次主动选择。",
            ],
            "evidence_rules": [
                "反击结果尽量视觉化，不只写成结论。",
            ],
        },
        "directing_rules": {
            "lens_intent": ["镜头应服务压迫感、反击感、爽点兑现。"],
            "camera_preferences": ["动作与反击场面优先强调空间调度和节奏转换。"],
            "continuity_rules": ["人物与关键战果道具需跨镜保持一致。"],
        },
        "asset_rules": {
            "character_policy": ["人物需支持落魄版、反击版、翻盘版等多状态资产。"],
            "location_policy": ["高频对抗空间应可复用。"],
            "prop_policy": ["反击证据、合同、筹码、金钱类道具必须结构化。"],
            "reference_policy": ["关键逆袭节点优先配置参考图锚点。"],
        },
        "hard_constraints": _COMMON_HARD_CONSTRAINTS,
        "soft_preferences": _COMMON_SOFT_PREFERENCES,
        "forbidden_patterns": _COMMON_FORBIDDEN_PATTERNS,
        "qa_checks": [
            "是否建立压制与反击链",
            "爽点是否兑现到画面",
            "关键资产是否支持连续兑现",
        ],
        "output_contracts": {
            "script": ["角色定位", "压制点", "反击点", "爽点标注"],
            "directing": ["镜头级分镜结构", "静态提示词", "运动提示词", "爽点镜头标签", "资产引用列表"],
            "asset": ["人物状态版", "关键空间", "关键筹码道具", "参考图绑定"],
            "qa": ["通过/警告/失败", "失败原因", "自动修复建议"],
        },
    },
}


def list_builtin_production_skills() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in _BUILTIN_SKILLS.values()]


def get_builtin_production_skill(skill_id: str | None) -> dict[str, Any]:
    normalized = str(skill_id or "").strip() or DEFAULT_SKILL_ID
    payload = _BUILTIN_SKILLS.get(normalized) or _BUILTIN_SKILLS[DEFAULT_SKILL_ID]
    return deepcopy(payload)


def production_skill_state_key(book_id: int) -> str:
    return f"product_workspace:production_skill:{book_id}"


def default_project_production_skill_state() -> dict[str, Any]:
    return {
        "skill_id": DEFAULT_SKILL_ID,
        "platform": "douyin",
        "track": "重生悬疑",
        "emotion_goal": "高压悬念",
        "rhythm_strength": "strong_hooks",
        "visual_style": "cinematic_realism",
        "priorities": ["storyboard", "assets", "mystery"],
        "enforcement": "strict",
        "custom_note": "",
        "locked_at": None,
    }


def normalize_project_production_skill_state(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    base = default_project_production_skill_state()
    priorities = source.get("priorities", base["priorities"])
    if not isinstance(priorities, list):
        priorities = base["priorities"]
    normalized_priorities = [
        str(item).strip()
        for item in priorities
        if str(item).strip()
    ] or list(base["priorities"])
    skill_id = str(source.get("skill_id") or source.get("skillId") or base["skill_id"]).strip() or base["skill_id"]
    builtin = get_builtin_production_skill(skill_id)
    tracks = builtin["skill_meta"].get("tracks", []) if isinstance(builtin.get("skill_meta"), dict) else []
    normalized = {
        "skill_id": builtin["skill_meta"]["id"],
        "platform": str(source.get("platform") or base["platform"]).strip() or base["platform"],
        "track": str(source.get("track") or (tracks[0] if tracks else base["track"])).strip() or base["track"],
        "emotion_goal": str(source.get("emotion_goal") or source.get("emotionGoal") or base["emotion_goal"]).strip() or base["emotion_goal"],
        "rhythm_strength": str(source.get("rhythm_strength") or source.get("rhythmStrength") or base["rhythm_strength"]).strip() or base["rhythm_strength"],
        "visual_style": str(source.get("visual_style") or source.get("visualStyle") or base["visual_style"]).strip() or base["visual_style"],
        "priorities": normalized_priorities,
        "enforcement": str(source.get("enforcement") or base["enforcement"]).strip() or base["enforcement"],
        "custom_note": str(source.get("custom_note") or source.get("customNote") or "").strip(),
        "locked_at": str(source.get("locked_at") or source.get("lockedAt") or "").strip() or None,
    }
    return normalized


def read_project_production_skill_state(book_id: int) -> dict[str, Any]:
    raw = get_kv(production_skill_state_key(book_id), "")
    if not raw:
        return normalize_project_production_skill_state()
    parsed = safe_json_loads(raw, {})
    return normalize_project_production_skill_state(parsed)


def write_project_production_skill_state(book_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_project_production_skill_state(payload)
    set_kv(production_skill_state_key(book_id), json.dumps(normalized, ensure_ascii=False))
    return normalized


def build_project_production_skill_runtime(book_id: int) -> dict[str, Any]:
    state = read_project_production_skill_state(book_id)
    builtin = get_builtin_production_skill(state["skill_id"])
    runtime = deepcopy(builtin)
    runtime["project_config"] = deepcopy(state)
    runtime["runtime_summary"] = {
        "skill_name": builtin["skill_meta"]["name"],
        "track": state["track"],
        "platform": state["platform"],
        "emotion_goal": state["emotion_goal"],
        "rhythm_strength": state["rhythm_strength"],
        "visual_style": state["visual_style"],
        "priorities": list(state["priorities"]),
        "enforcement": state["enforcement"],
        "locked": bool(state.get("locked_at")),
        "custom_note": state["custom_note"],
    }
    return runtime


def build_production_skill_prompt_block(book_id: int, stage: str) -> str:
    runtime = build_project_production_skill_runtime(book_id)
    summary = runtime.get("runtime_summary", {})
    stage_rules = runtime.get(f"{stage}_rules", {}) if isinstance(runtime.get(f"{stage}_rules", {}), dict) else {}
    hard_constraints = runtime.get("hard_constraints", []) if isinstance(runtime.get("hard_constraints", []), list) else []
    soft_preferences = runtime.get("soft_preferences", []) if isinstance(runtime.get("soft_preferences", []), list) else []
    forbidden_patterns = runtime.get("forbidden_patterns", []) if isinstance(runtime.get("forbidden_patterns", []), list) else []
    output_contracts = runtime.get("output_contracts", {}) if isinstance(runtime.get("output_contracts", {}), dict) else {}
    lines = [
        "## Production Skill",
        f"Skill: {summary.get('skill_name', '')}",
        f"赛道: {summary.get('track', '')}",
        f"平台: {summary.get('platform', '')}",
        f"情绪目标: {summary.get('emotion_goal', '')}",
        f"节奏强度: {summary.get('rhythm_strength', '')}",
        f"视觉风格: {summary.get('visual_style', '')}",
        f"执行强度: {summary.get('enforcement', '')}",
        f"优先目标: {', '.join(summary.get('priorities', []) or [])}",
    ]
    custom_note = str(summary.get("custom_note") or "").strip()
    if custom_note:
        lines.append(f"项目补充约束: {custom_note}")
    if stage_rules:
        lines.append(f"### {stage} 规则")
        for key, value in stage_rules.items():
            if isinstance(value, list):
                lines.append(f"- {key}: {'；'.join(str(item) for item in value if str(item).strip())}")
            elif isinstance(value, str) and value.strip():
                lines.append(f"- {key}: {value.strip()}")
    if hard_constraints:
        lines.append("### 硬约束")
        lines.extend(f"- {item}" for item in hard_constraints if str(item).strip())
    if soft_preferences:
        lines.append("### 软偏好")
        lines.extend(f"- {item}" for item in soft_preferences if str(item).strip())
    if forbidden_patterns:
        lines.append("### 禁止项")
        lines.extend(f"- {item}" for item in forbidden_patterns if str(item).strip())
    stage_contract = output_contracts.get(stage, [])
    if isinstance(stage_contract, list) and stage_contract:
        lines.append("### 输出契约")
        lines.extend(f"- {item}" for item in stage_contract if str(item).strip())
    return "\n".join(lines).strip()


SCRIPT_QA_RULE_FAMILY_MAP: dict[str, str] = {
    "motivation": "character_state_transition",
    "relationship_conflict": "character_consistency",
    "characterization": "character_consistency",
    "emotion_arc": "character_state_transition",
    "dialogue_style": "character_consistency",
    "foreshadowing": "clue_payoff_integrity",
    "continuity": "prop_evidence_continuity",
    "hook": "episode_hook_strength",
    "pace": "scene_effectiveness",
    "format": "output_completeness",
    "visual": "clue_payoff_integrity",
    "visualization": "clue_payoff_integrity",
    "other": "generic_skill_gap",
}

SCRIPT_QA_RULE_FAMILY_REPAIR_GOALS: dict[str, str] = {
    "character_consistency": "先统一人物基础设定、可见状态与隐藏状态，避免人设和对白气质漂移。",
    "character_state_transition": "补足状态切换的触发器、递进动作与情绪拐点，让人物变化可被看见和理解。",
    "clue_payoff_integrity": "补足线索进入、误导、回收与支付节点，确保信息推进不是断裂的。",
    "prop_evidence_continuity": "补足关键道具首次曝光、归属关系、传递链与证据作用。",
    "episode_hook_strength": "增强开场钩子、中段升级与结尾拉力，保证集级留存驱动力。",
    "scene_effectiveness": "清理无效场次，确保每场戏都有明确目的、冲突和局势变化。",
    "output_completeness": "先补齐缺失段落、结构截断和格式缺口，再做风格强化。",
    "generic_skill_gap": "回到通用 Production Skill 约束重新校准，按结构合同补齐缺口。",
}

SCRIPT_QA_STRUCTURE_LAYER_MAP: dict[str, str] = {
    "character_consistency": "fact_layer",
    "character_state_transition": "fact_layer",
    "prop_evidence_continuity": "fact_layer",
    "clue_payoff_integrity": "scene_execution_layer",
    "scene_effectiveness": "scene_execution_layer",
    "episode_hook_strength": "compiler_layer",
    "output_completeness": "compiler_layer",
    "generic_skill_gap": "compiler_layer",
}

SCRIPT_QA_REPAIR_STAGE_MAP: dict[str, str] = {
    "character_consistency": "fact_generation",
    "character_state_transition": "fact_generation",
    "prop_evidence_continuity": "fact_generation",
    "clue_payoff_integrity": "scene_execution",
    "scene_effectiveness": "scene_execution",
    "episode_hook_strength": "screenplay_compile",
    "output_completeness": "screenplay_compile",
    "generic_skill_gap": "structure_qa",
}

SCRIPT_REPAIR_STAGE_ACTIONS: dict[str, list[str]] = {
    "fact_generation": [
        "先锁定人物公开层、隐藏层、行为触发器与说话节奏，再改对白和动作。",
        "先锁定高价值道具的唯一性、数量、归属和跨场流转，再写发现与栽赃过程。",
        "先锁定帮助者动机、知识来源、时间锚点和空间前提，再进入揭示场。",
    ],
    "scene_execution": [
        "按场景补齐开场状态、镜头内可见证据、局势变化和场景出口钩子。",
        "把关键推理改成镜头可见的比较、触摸、对照、翻找或目击动作。",
        "把身体约束、门闩结构、搜身范围、转场路径和交接动作拍实，不允许只靠说明跳过。",
    ],
    "screenplay_compile": [
        "在不改坏事实层的前提下统一场景顺序、信息增量和结尾拉力。",
        "压缩解释台词，把解释改成道具处理、短句冲突和画面证明。",
    ],
    "structure_qa": [
        "逐条回收上一轮 QA 失败项，避免修复一个问题时重新制造旧问题。",
        "检查场景边界、格式完整性和钩子增量，保证结果是可直接进入下一环节的剧本。",
    ],
}


def classify_script_qa_rule_family(issue: dict[str, Any] | None) -> str:
    payload = issue if isinstance(issue, dict) else {}
    issue_type = str(payload.get("type") or "").strip().lower()
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    combined = f"{title}\n{description}".lower()

    if issue_type == "logic_gap" and any(
        token in combined for token in ["视角", "记忆", "闪回", "来源", "provenance", "pov", "identity source"]
    ):
        return "character_state_transition"
    if any(token in combined for token in ["人设", "画像", "性格", "气质", "说话", "台词风格", "speech style", "persona", "character image", "drift"]):
        return "character_consistency"
    if any(token in combined for token in ["对白格式", "台词格式", "角色：台词", "subtitle", "format drift", "dialogue format"]):
        return "output_completeness"
    if any(token in combined for token in ["只存在于台词", "未入画", "缺乏画面支撑", "画面证据", "on-screen", "off-screen", "visual evidence", "flashback", "视角", "记忆来源", "来源不明"]):
        return "clue_payoff_integrity"
    if any(token in combined for token in ["可见性", "显影", "肉眼可见", "试剂", "暗房", "浮现", "visibility", "latent", "reagent", "develop"]):
        return "clue_payoff_integrity"
    if any(token in combined for token in ["时间线", "时序", "页数", "编号", "第二页", "第三页", "水位", "timeline", "page", "numbering", "water level"]):
        return "prop_evidence_continuity"
    if any(token in combined for token in ["信息量过载", "太多反转", "节奏", "过载", "overload", "too many reveals", "pace"]):
        return "scene_effectiveness"
    if issue_type == "logic":
        if any(token in combined for token in ["可见性", "显影", "肉眼可见", "试剂", "暗房", "浮现", "visibility", "latent", "reagent", "develop"]):
            return "clue_payoff_integrity"
        if any(token in combined for token in ["时间线", "时序", "页数", "编号", "第二页", "第三页", "水位", "timeline", "page", "numbering", "water level", "绳子", "道具去向"]):
            return "prop_evidence_continuity"
        if any(token in combined for token in ["画面", "比对", "验证", "show", "visual", "on-screen"]):
            return "clue_payoff_integrity"
        return "generic_skill_gap"
    if issue_type == "logic_gap":
        if any(token in combined for token in ["直接出现", "缺乏交代", "如何脱身", "过渡镜头", "suddenly appears", "scene transition", "handoff missing"]):
            return "character_state_transition"
        if any(token in combined for token in ["视角", "记忆", "闪回", "来源", "provenance", "pov", "identity source"]):
            return "character_state_transition"
        if any(token in combined for token in ["身份", "令牌", "道具", "证据", "经书", "线索", "后山", "identity", "token", "prop", "evidence", "clue", "book"]):
            return "prop_evidence_continuity"
        if any(token in combined for token in ["\u52a8\u673a", "\u8f6c\u53d8", "\u4f2a\u88c5", "\u9690\u5fcd", "\u53cd\u51fb", "\u53cd\u5e94", "motivation", "transition", "disguise", "reaction", "trigger", "\u6263\u538b", "\u7ed1\u4eba", "\u52a8\u673a\u504f\u5f31"]):
            return "character_state_transition"
        if any(token in combined for token in ["伏笔", "回收", "铺垫", "支付", "钩子", "foreshadow", "payoff", "hook"]):
            return "clue_payoff_integrity"
        return "generic_skill_gap"
    return SCRIPT_QA_RULE_FAMILY_MAP.get(issue_type, "generic_skill_gap")


def build_script_rule_family_repair_goal(rule_family: str) -> str:
    family = str(rule_family or "").strip() or "generic_skill_gap"
    return SCRIPT_QA_RULE_FAMILY_REPAIR_GOALS.get(
        family,
        SCRIPT_QA_RULE_FAMILY_REPAIR_GOALS["generic_skill_gap"],
    )


def classify_script_qa_structure_layer(issue: dict[str, Any] | None) -> str:
    family = classify_script_qa_rule_family(issue)
    return SCRIPT_QA_STRUCTURE_LAYER_MAP.get(family, "compiler_layer")


def classify_script_qa_repair_stage(issue: dict[str, Any] | None) -> str:
    family = classify_script_qa_rule_family(issue)
    return SCRIPT_QA_REPAIR_STAGE_MAP.get(family, "structure_qa")


def build_script_issue_rewrite_directive(issue: dict[str, Any] | None) -> str:
    payload = issue if isinstance(issue, dict) else {}
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    issue_type = str(payload.get("type") or "").strip().lower()
    combined = f"{title}\n{description}".lower()

    if any(token in combined for token in ["推诿", "混日子", "被迫管事", "临时被迫", "主动踹门", "主动搜身", "主动扣押", "forced to enforce", "lazy enforcer", "reluctant enforcement"]):
        return (
            "If a lazy, evasive, or perfunctory character must enforce rules anyway, show that enforcement in-character: reluctant efficiency, complaint, excuse-making, borrowed authority, sloppy handling, or passing responsibility while still getting the result."
        )
    if any(token in combined for token in ["画像", "人设", "气质", "懒惰", "懒散", "character image", "persona", "drift"]):
        return (
            "Keep the bound persona visible before the reveal: in the character's first beats, add small public-mask behaviors, let lazy or perfunctory roles keep slack phrasing and delayed action tempo, and reveal hidden competence first through noticing, deflection, or strategic delay before any overtly sharp behavior lands."
        )
    if any(token in combined for token in ["对白格式", "台词格式", "角色：台词", "subtitle", "dialogue format"]):
        return (
            "Normalize spoken lines into a stable `角色：台词` pattern and move tone, blocking, and movement into adjacent action lines."
        )
    if any(token in combined for token in ["时间线", "时序", "出现时间", "昨夜", "黄昏", "下午", "今早", "before entering", "timeline", "dusk", "last night"]):
        return (
            "Unify all relative-time anchors for this clue chain. Prefer changing the smallest conflicting line instead of inventing a new chronology branch."
        )
    if any(token in combined for token in ["开锁", "门闩", "铁皮门扣", "锁结构", "hook opens", "latch", "hardware geometry", "lock-breaking"]):
        return (
            "Match the escape beat to the shown latch geometry: establish the reachable path first, then show exactly how the hook, wire, or loop engages the hardware."
        )
    if any(token in combined for token in ["库房", "柴房", "扣押地点", "转去", "storehouse", "shed", "custody location"]):
        return (
            "Keep the announced custody destination consistent, or add the reroute beat on screen before the next scene begins."
        )
    if any(token in combined for token in ["撞进来", "被抓住", "反绑", "画面事实矛盾", "custody wording", "arrived wording", "visual fact conflict"]):
        return (
            "Match accusation wording to the visible custody state on screen; if the suspect is already restrained, use caught, found, hauled in, or discovered language instead of verbs that imply free self-entry."
        )
    if any(token in combined for token in ["脱身", "离开", "场景转换", "过渡", "解绑", "escape", "untie", "transition missing"]):
        return (
            "Bridge the state change on screen: if the character moves from restraint, custody, or hiding into a free next scene, show the release or escape beat first."
        )
    if any(token in combined for token in ["反绑", "绑住", "手伸进", "动作矛盾", "restrained", "impossible motion", "身体动作"]):
        return (
            "Respect the body constraint already on screen: show the release, workaround, or reposition first, then let the action happen."
        )
    if any(token in combined for token in ["页数", "编号", "第二页", "第三页", "page", "numbering", "count"]):
        return (
            "Preserve the exact page number, count, or label already established earlier in the episode; if a correction is needed, stage it explicitly on screen."
        )
    if any(token in combined for token in ["亲眼见", "亲耳听", "亲眼所见", "eyewitness", "you saw", "certainty"]):
        return (
            "Dialogue cannot overclaim beyond the shown evidence; if the character inferred it, phrase it as inference instead of eyewitness fact."
        )
    if any(token in combined for token in ["可见性", "显影", "肉眼可见", "试剂", "暗房", "浮现", "visibility", "latent", "reagent", "develop"]):
        return (
            "Choose one evidence-visibility model and keep it consistent: either the mark is visibly present now, or it needs a staged reveal method, but not both without explanation."
        )
    if any(token in combined for token in ["缺乏画面支撑", "未入画", "颜色判断", "比对", "验证", "画面", "visual", "on-screen"]):
        return (
            "Convert the claim into an on-screen comparison beat with handling, placement, or close-up, so the audience can verify the evidence inside the frame."
        )
    if any(token in combined for token in ["未揭穿", "未检查", "没深究", "行为动机缺失", "noticed but ignored", "didn't inspect", "ignored anomaly"]):
        return (
            "If a character notices an abnormal clue but does not expose it, stage the skip as an intentional choice: interruption, test, bluff, private agenda, or deliberate surveillance value signaled in the same beat."
        )
    if any(token in combined for token in ["画外音", "锉刀", "响声", "声音", "纯音效", "sound cue", "audio"]):
        return (
            "Pair the plot-relevant sound with a visible source, silhouette, tool edge, or body movement so the clue is not carried by audio alone."
        )
    if any(token in combined for token in ["语义冲突", "查清了", "明早再放", "说法冲突", "closure wording", "released later"]):
        return (
            "Rewrite the status line so its wording matches the current action phase: use search, hold, wait, or recheck language while the suspicion is still unresolved, and avoid solved or cleared wording too early."
        )
    if any(token in combined for token in ["语义含混", "不清", "转移视线", "ambiguous line", "muddy dialogue"]):
        return (
            "Rewrite the line to carry one readable function only: explanation, deflection, threat, or bait. Keep any misdirection intentional and immediately understandable to the viewer."
        )
    if any(token in combined for token in ["水位", "湿布", "砖缝", "先搜", "后发现", "searched", "water level", "missed before"]):
        return (
            "Stage one explicit discovery gate for the later find: angle, water level, obstruction, darkness, or another concrete reason the earlier search could miss it."
        )
    if any(token in combined for token in ["草纤维", "纤维位置", "同一根", "位置跳跃", "fiber appears", "same fiber", "teleport between places"]):
        return (
            "Keep the evidence family on one readable chain: if a fiber, thread, dust trace, or residue appears in multiple places, show whether it is the same trace being carried or a separate related trace with its own source."
        )
    if any(token in combined for token in ["道具去向", "道具连续性", "绳子", "来源", "谁拿", "prop", "handoff", "source chain"]):
        return (
            "Close the prop chain on screen: show who retrieved it, where it came from, and how it travels from the earlier scene into the current one."
        )
    if any(token in combined for token in ["重复取", "重新取", "放回又拿起", "重复拿", "same character", "re-taking", "puts it back", "handles it again"]):
        return (
            "If the same character places a high-value prop back into view and then handles it again soon after, show the intervening reason on screen: changed objective, bait setup, verification step, surveillance purpose, or forced retrieval."
        )
    if any(token in combined for token in ["搜身", "未搜出", "藏匿", "暗袋", "search", "stash", "not found"]):
        return (
            "Define the search scope and the hiding place precisely, so the audience understands why some evidence is found and other evidence survives the search."
        )
    if any(token in combined for token in ["押去", "关一夜", "拖去", "转场过快", "held overnight", "escorted to", "custody bridge", "skip to night"]):
        return (
            "Bridge the custody transfer on screen: if someone is marched off, locked up, or held overnight, add the escort, shove, relock, lantern walk, or time-cut handoff beat before the holding scene begins."
        )
    if any(token in combined for token in ["再次检查", "第二次", "又去摸", "重复搜查", "checks again", "inspects again", "second inspection", "again later", "robe seam again", "same seam again"]):
        return (
            "If a character inspects the same hidden area again later, add the new trigger that justifies the repeat check: a fresh clue, a raised stake, a resumed interruption, or a changed objective."
        )
    if any(token in combined for token in ["重复使用", "去向不清", "消失", "从墙角捡起", "被丢弃后", "又出现在怀里", "state reuse", "reappears", "same prop"]):
        return (
            "Reuse the prop from its latest known state and location, and show the recovery if it was discarded or removed; do not fetch it again from an earlier place once it has already been pocketed, wrapped, or moved."
        )
    if any(token in combined for token in ["人影", "黑影", "重复", "递进", "shadow", "motif", "hook strength"]):
        return (
            "If the same suspense motif returns, make the second beat reveal more than the first: new identity value, stronger threat, or a concrete object clue."
        )
    if any(token in combined for token in ["鞋影", "门外人", "身份指向模糊", "暗示过多", "watcher", "shadow identity"]):
        return (
            "Calibrate the watcher hint to the intended certainty: either keep it source-level and ambiguous, or add a second anchor such as shoe shape, sleeve edge, gait, tool, or repeated stance so the audience leans in the intended direction."
        )
    if any(token in combined for token in ["指向", "另有其人", "推断", "指向性", "ambiguous", "distinguish"]):
        return (
            "Add the distinguishing feature that keeps the inference sharp: cut angle, age of damage, location marker, or another concrete difference separating the obvious suspect from the hidden one."
        )
    if any(token in combined for token in ["草纤维", "同材质", "唯一性", "fiber", "same material", "unique signature"]):
        return (
            "A shared material is not enough for a decisive match. Add one unique signature on screen: placement pattern, cut angle, wrap style, residue, age of damage, or source-limited usage."
        )
    if any(token in combined for token in ["余韵", "残留", "时空混淆", "flashback echo", "rain sound", "memory echo"]):
        return (
            "If a sensory echo survives after a flashback, mark it clearly as subjective carryover inside the character's head rather than as current environmental reality."
        )
    if any(token in combined for token in ["闪回插入时机", "打断紧张节奏", "闪回过长", "flashback interrupts tension", "flashback too long", "pressure drag"]):
        return (
            "Shorten the flashback into compressed inserts or move it to the first safe beat, so the active danger keeps pressing while the backstory lands."
        )
    if any(token in combined for token in ["\u660e\u5929\u638f\u4e95", "\u51b3\u7b56\u52a8\u673a", "\u4e3a\u4ec0\u4e48\u4e0d\u62a5\u5b98", "goal", "why not report", "\u6263\u538b", "\u7ed1\u4eba", "\u52a8\u673a\u504f\u5f31"]):
        return (
            "Before the character commits to the next risky action, state the concrete objective on screen so the audience knows what they are trying to recover, verify, or expose."
        )
    if any(token in combined for token in ["开锁", "门闩", "铁皮门扣", "锁结构", "hook opens", "latch", "hardware geometry", "lock-breaking"]):
        return (
            "Match the escape beat to the shown latch geometry: establish the reachable path first, then show exactly how the hook, wire, or loop engages the hardware."
        )
    if any(token in combined for token in ["探出门缝", "钩住绳圈", "路径不清", "tool path", "through the crack", "hook path", "spatially unclear"]):
        return (
            "Stage the hidden tool path in camera-readable steps: entry point, contact target, pull direction, and resulting hardware movement. Do not rely on an off-screen hook path the audience cannot reconstruct."
        )
    if any(token in combined for token in ["解释性", "说明式对白", "讲解", "explanatory dialogue", "too explanatory"]):
        return (
            "Shrink the explanation into action plus one short line; let the object handling and close-up carry most of the reasoning."
        )
    if any(token in combined for token in ["刻痕来源", "蜡下有字", "hidden mark source", "inscription provenance", "铜字"]):
        return (
            "Stage the provenance of the hidden inscription earlier: show when the mark was carved, written, or sealed under the cover before the later reveal pays it off."
        )
    if any(token in combined for token in ["心理描写", "不宜直接拍摄", "记进心里", "abstract psychology", "internal state"]):
        return (
            "Replace abstract inner narration with a visible micro-action: a pause, touch, eye shift, breath catch, or prop beat that lets the camera carry the thought."
        )
    if any(token in combined for token in ["不声张", "没报警", "silent", "stay quiet", "动机不明"]):
        return (
            "Give the silence a visible motive beat: fear, infiltration, lack of proof, self-protection, or another strategic reason stated on screen."
        )
    if any(token in combined for token in ["用途", "未形成明确指向", "信息量不足", "说话", "tool purpose", "foreshadowing weak"]):
        return (
            "Turn vague foreshadowing into a bounded unresolved question: show what class of future effect the tool or clue will have, but hold back the exact mechanism so curiosity stays specific instead of foggy."
        )
    if issue_type in {"visualization", "visual"}:
        return "Move the key clue out of explanation and into a visible shot-comparison beat."
    if issue_type in {"characterization", "relationship_conflict", "dialogue_style"}:
        return "Reconcile spoken lines, body language, and visible behavior with the bound character persona before adding new plot mechanics."
    if issue_type in {"continuity", "logic", "logic_gap"}:
        return "Repair the contradiction with the smallest consistent adjustment and keep every affected prop fact stable across scenes."
    return "Apply the fix directly inside the screenplay body with visible action, stable continuity, and no new unsupported facts."


def _normalize_name_list(values: Any) -> list[str]:
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    elif isinstance(values, str):
        # 处理逗号分隔的字符串
        return [name.strip() for name in values.split(",") if name.strip()]
    return []


def _build_character_speech_style_anchor(track_goal: str, name: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if not name:
        return ""
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return "keep a public-facing mask in dialogue, then reveal the colder hidden layer only after a visible trigger"
    if "romance" in normalized_track or "\u8650\u604b" in track_goal:
        return "dialogue should carry emotional restraint, relationship pressure, and subtext instead of flat explanation"
    if "revenge" in normalized_track or "\u723d\u5267" in track_goal or "\u9006\u88ad" in track_goal:
        return "dialogue should move from suppression to decisive counterattack without losing motivation clarity"
    return "dialogue should stay consistent with the character's visible state and social mask"


def _build_signature_speech_requirement(track_goal: str, name: str) -> str:
    if not name:
        return ""
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return "if character canon defines a habitual phrase, draggy cadence, excuse pattern, or ritual opener, seed that signature in early lines so the social mask is audible before deeper intent surfaces"
    return "if canon gives the character a recognizable phrase, cadence, or dodge pattern, keep it audible in early lines instead of flattening every speaker into neutral exposition"


def _build_character_behavior_guardrails(track_goal: str, character_personality: str = "") -> list[str]:
    normalized_track = str(track_goal or "").lower()
    normalized_personality = str(character_personality or "").lower()
    rules = [
        "do not jump straight from setup to hidden truth without a visible trigger",
        "keep wording, body language, and action rhythm aligned with the current visible state",
        "if the script relies on a bound portrait or character asset canon, either preserve that persona in behavior or explicitly rewrite the canon before the screenplay contradicts it",
    ]
    
    # 根据角色性格添加特定的行为约束
    if "内向" in normalized_personality or "introverted" in normalized_personality:
        rules.extend([
            "character should speak less and observe more, preferring silence or minimal responses",
            "avoid sudden aggressive or confrontational behavior unless triggered by a specific event",
            "physical movements should be restrained and deliberate, not expansive or attention-seeking",
            "dialogue should be concise, with frequent pauses and incomplete sentences",
            "maintain physical distance from other characters unless there is a compelling reason to approach",
        ])
    
    if "神秘" in normalized_personality or "mysterious" in normalized_personality:
        rules.extend([
            "avoid revealing personal information or motivations directly",
            "use ambiguous or evasive responses when asked direct questions",
            "maintain an air of unpredictability through inconsistent behavior patterns",
            "let other characters interpret the meaning behind actions rather than explaining them",
            "reveal information gradually through actions and reactions, not exposition",
        ])
    
    if "疲惫" in normalized_personality or "tired" in normalized_personality or "weary" in normalized_personality:
        rules.extend([
            "physical movements should be slow, heavy, and lacking energy",
            "dialogue should be short, possibly trailing off or incomplete",
            "avoid sudden bursts of energy or assertive behavior unless absolutely necessary",
            "show exhaustion through posture (slumped shoulders, leaning on things), facial expressions (drooping eyelids, sighing), and speech patterns (slow, monotone)",
            "reactions to events should be delayed or muted compared to other characters",
            "emotional responses should be suppressed or expressed through physical fatigue rather than verbal outbursts",
        ])
    
    if "怪异" in normalized_personality or "strange" in normalized_personality or "eccentric" in normalized_personality:
        rules.extend([
            "behavior should be unpredictable and sometimes illogical",
            "reactions may be disproportionate to the situation",
            "may speak to themselves or respond to things others don't notice",
            "physical movements may be jerky, sudden, or follow unusual patterns",
            "maintain an unsettling quality that makes other characters uncomfortable",
        ])
    
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        rules.extend(
            [
                "if the character is pretending to be lazy or harmless, preserve that mask in most early lines",
                "if the bound public layer is lazy, perfunctory, timid, or dismissive, keep that quality in line rhythm and action tempo instead of switching into sharp procedural efficiency too early",
                "if a lazy or perfunctory character still has to enforce rules, search someone, or hold custody, stage that action through reluctance, delegation, complaint, procedural cover, or sloppy-but-effective handling instead of clean zeal",
                "when the hidden layer surfaces, mark it with a pause, gaze shift, prop contact, or pressure beat",
                "if the character suddenly sounds colder, sharper, or more dangerous, show the trigger that makes the shift playable in the same beat",
                "when a character hides competence under laziness or softness, let that competence surface through what they quietly notice, delay, or skip rather than through openly forceful command lines right away",
                "if the role carries a public mask and a hidden layer, stage both consistently instead of letting the hidden competence erase the mask too early",
            ]
        )
    return rules


def _build_flashback_provenance_guardrail(track_goal: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return (
            "Every flashback must declare whose memory, reconstruction, inherited image, or discovered record it is. "
            "Do not show a POV the current character cannot access unless the screenplay explicitly explains why they can access it."
        )
    return (
        "Every flashback must have a clear owner and source. Do not use unattached omniscient flashbacks as proof."
    )


def _build_identity_cover_guardrail(track_goal: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return (
            "If a character is using a borrowed identity, forged document, alias, or cover story, show on screen what cover was used, "
            "why it worked, and when the audience should understand the difference between cover and truth."
        )
    return "If the script relies on disguise or false identity, make the cover mechanism legible on screen."


def _build_offscreen_incident_anchor_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if the conflict depends on an off-screen theft, missing item, injury, or alarm event, add one visible aftermath anchor in frame: an empty slot, broken string, disturbed shrine, missing seal, inventory gap, or another concrete sign the event really happened."
    )


def _build_dialogue_evidence_order_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, when dialogue names a key clue, theft, cut mark, or missing item for the first time, pair that line with the visual anchor in the same beat or show the anchor earlier. "
        "Do not let the audience hear about decisive evidence long before they see any trace of it."
    )


def _build_asset_canon_reconciliation_guardrail(track_goal: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return (
            "If a bound portrait, character sheet, or asset canon defines a public persona, keep screenplay behavior inside that mask "
            "unless the scene explicitly establishes a revised canon, a disguised performance, or a revealed hidden layer."
        )
    return (
        "Do not contradict a bound portrait or character asset canon unless the script explicitly establishes why the visible behavior has changed."
    )


def _build_persona_layer_guardrail(track_goal: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return (
            "Model character canon in two layers when needed: a public mask that survives ordinary interaction, and a hidden competence or motive layer that only surfaces after a visible trigger. Do not flatten both layers into one undifferentiated behavior track."
        )
    return (
        "If a role carries both social mask and private intent, keep the visible layer readable before the deeper layer takes over."
    )


def _build_hidden_layer_seed_requirement(track_goal: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return (
            "Before a character reveals hidden competence, cold calculation, or escape readiness, plant at least one small on-screen seed in an earlier beat: a reflexive touch toward a stash, a too-fast eye change, a protected sleeve fold, a deliberate delay, or another readable hint that the outer mask is not the whole truth."
        )
    return (
        "If a later scene depends on hidden competence, seed that ability earlier with one visible setup beat."
    )


def _build_hidden_layer_reveal_trigger_requirement(track_goal: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return (
            "When the hidden layer finally surfaces, tie it to a visible trigger in the same beat: pressure spike, prop contact, clue recognition, custody change, or another concrete event the audience can point to."
        )
    return (
        "When a hidden layer surfaces, connect it to a visible trigger instead of letting the shift arrive abstractly."
    )


def _build_dialogue_format_guardrail() -> str:
    return (
        "Dialogue lines should use one stable extraction-friendly pattern such as `角色：台词`; keep action, tone, and blocking outside the spoken line so downstream subtitle and asset tooling can parse them reliably."
    )


def _build_scene_driver_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    if scene_index == 1:
        return (
            f"In {name}, define who actively drives the scene opening pressure. "
            "The first mover should cause the first visible disturbance, not just observe or explain it."
        )
    return (
        f"In {name}, define which character or force drives the turn of the scene. "
        "The scene should not drift as mutual explanation; one side must push, test, hide, trap, search, stall, or provoke."
    )


def _build_scene_visual_anchor_goal(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, give the scene one dominant visual anchor that can be filmed and remembered: "
        "a disturbed prop, suspicious surface, blocking pattern, physical mismatch, body trace, or unstable action target."
    )


def _build_scene_new_evidence_goal(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    if scene_index == 1:
        return (
            f"In {name}, introduce at least one fresh clue, pressure sign, or suspicious abnormality into the frame. "
            "The episode cannot open on pure atmosphere or character explanation."
        )
    return (
        f"In {name}, add at least one new piece of usable information to the episode evidence chain: "
        "a clue, contradiction, motive trace, prop state change, access fact, or witness reaction."
    )


def _build_scene_reused_clue_goal(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    if scene_index == 1:
        return (
            f"In {name}, if no prior clue exists yet, establish the first clue in a way that later scenes can revisit with added detail."
        )
    return (
        f"In {name}, if the beat touches an earlier clue again, reuse it with new meaning, new angle, new holder, or new physical detail. "
        "Do not simply restate the earlier discovery."
    )


def _build_scene_exit_delta_goal(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, end on a concrete exit delta that changes the next scene's playable situation: "
        "new suspicion direction, new custody state, new concealment problem, new timing pressure, or new evidence destination."
    )


def _build_scene_transition_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"Bridge entry into {name}: show how characters arrive, how any newly visible prop/evidence is obtained, "
        "and what pressure carries over from the previous scene."
    )


def _build_custody_destination_consistency_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, once characters say they are locking someone in a specific place such as a storehouse, cell, shed, or back room, the next scene must either use that same destination or show the reroute on screen. "
        "Do not let custody location switch by implication alone."
    )


def _build_relative_time_anchor_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, the time_anchor must advance realistically based on scene content. "
        "Each scene should advance time by at least 3-5 minutes for dialogue-heavy scenes, "
        "or 10-15 minutes for scenes with significant action or location changes. "
        "Never keep the same time_anchor across consecutive scenes unless they are a direct continuation "
        "within seconds. The time_anchor in the state output should reflect the END of the scene, "
        "not the beginning. For example, if a scene starts at 23:47 and has 5+ minutes of dialogue, "
        "the ending time_anchor should be 23:52 or later."
    )


def _build_time_progression_hint(scene_name: str, scene_index: int) -> str:
    """为每个场景提供时间推进提示。"""
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    if scene_index == 1:
        return (
            f"Scene '{name}' is the opening scene. Set a specific starting time (e.g., 23:47). "
            "This scene should establish the time baseline for all subsequent scenes."
        )
    else:
        return (
            f"Scene '{name}' follows the previous scene. The time must advance by at least 3-10 minutes "
            "depending on scene content. Include the elapsed time in your state output's time_anchor field. "
            "For example: '23:55' or '00:05' (if crossing midnight)."
        )


def _build_action_feasibility_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, respect the body's current constraints. If a character is tied, injured, pinned, carrying something, or half-hidden, "
        "their next action must remain physically possible unless the screenplay first shows the release, shift, or workaround. "
        "If the restraint anchor or custody setup changes inside the same scene, show the unhook, reposition, or rebind beat explicitly before the new state appears."
    )


def _build_investigation_trace_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, every major inference must be tied to a visible source: a prop surface, a prior action, "
        "a flashback beat, a discovered trace, or an on-screen comparison."
    )


def _build_motivation_visibility_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character takes a risky, hidden, or high-cost action, place the motive on screen before the act "
        "or immediately after through a visible look, prop target, remembered trigger, or concise line anchored to the action. "
        "If another character escalates from suspicion into confiscation, restraint, beating, or surveillance, stage the concrete trigger for that escalation in frame."
    )


def _build_search_trigger_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character suddenly turns toward a wall root, grass pile, bed board, hidden compartment, or another search target, "
        "show the trigger first: a glance, dent, loose brick, displaced straw, remembered phrase, sound, stain, or another readable cue."
    )


def _build_suggestive_glance_resolution_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character gives a meaningful glance toward a prop, corner, doorway, or hiding place, either pay that glance off with a later reveal or convert it into a concrete action so it does not hang as empty emphasis."
    )


def _build_attitude_anchor_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character withholds information, deliberately avoids a search area, or leaves a clue untouched, add a small visible attitude anchor in the same beat: a pause, finger stop, tightened jaw, narrowed eyes, breath catch, or another readable stance signal."
    )


def _build_visual_evidence_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a deduction depends on smell, texture, stain, cut edge, wax, rust, blood, or surface detail, "
        "add a close-up or handling beat so the evidence exists in the frame and not only in dialogue."
    )


def _build_occluded_evidence_layer_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, separate visible surface evidence from hidden underlayer inference. "
        "If a mark sits under wax, cloth, mud, paper, skin, or another cover, the frame may show only the surface trace, edge pressure, bulge, stain, or seal condition until the cover is actually opened."
    )


def _build_seed_clue_visibility_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a clue will matter in a later reveal, show its seed detail in the active scene image now: a scratch, pressure dent, wax nick, missing corner, thread color, or other specific micro-feature. Do not leave that clue only inside end-note annotations or later explanation."
    )


def _build_concealed_clue_focus_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a clue remains physically concealed for now, still give the audience a perceivable suspense focal point: a bulge under wax, a warped edge, a partial groove, trapped residue, or another visible abnormality that signals something worth remembering under the cover."
    )


def _build_prior_discovery_delta_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a clue surface, seam, dent, wax edge, knife mark, or odd trace was already shown earlier, later handling must add a new layer of information instead of replaying the same discovery as if it were brand new."
    )


def _build_comparison_visualization_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if the screenplay claims two cloth scraps, rope ends, cuts, marks, or surfaces belong together, stage the comparison in frame with overlap, edge match, side-by-side placement, or a direct handling beat instead of relying on dialogue alone."
    )


def _build_multi_signal_match_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if the script upgrades a clue match from similar reaction into same source, require at least two confirming dimensions in frame, such as edge fit plus residue, fiber pattern plus tear angle, tool mark plus placement, or color plus damage continuity."
    )


def _build_color_signal_clarity_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a clue color could be misread as blood, rust, mud, wax, or dye, anchor the intended reading in frame through texture, source, residue, smell, or a follow-up close-up."
    )


def _build_prop_asset_spec_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, any high-value prop that may recur in later scenes or downstream asset generation must be described with stable build facts: material, carved or painted text placement, damage pattern, sealing layer, side/orientation, and any old-vs-new mark relationship."
    )


def _build_audio_visual_pairing_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a sound cue matters to the plot, pair it with a visible source, silhouette, tool edge, body part, or moving shadow so the audience can anchor the sound in frame."
    )


def _build_delayed_discovery_gate_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if an object is discovered later in a place already searched earlier, show why it was missed before: "
        "darkness, angle, hidden compartment, water level, obstruction, or an earlier interruption."
    )


def _build_knowledge_provenance_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character uses a hidden method, ritual, code, or evidence-reveal technique, show where that knowledge came from: "
        "a prior lesson, remembered image, visible trace, earlier failed attempt, or another on-screen source."
    )


def _build_split_evidence_timeline_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a document, clue, or prop appears both as a delivered item and as a later reveal, show the split explicitly: "
        "copy, torn page, extracted fragment, duplicate bundle, or a prior removal beat. Do not let one object serve two contradictory timelines."
    )


def _build_ending_image_hook_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, the ending hook MUST be strong and memorable. "
        "If this is the last scene of the episode, the hook must include: "
        "1) A shocking revelation or twist that recontextualizes everything seen so far, "
        "2) A concrete visual image (prop, gesture, or environment change) that viewers will remember, "
        "3) An emotional punch that makes viewers desperate to see the next episode. "
        "The hook should land on a visible image memory, not only on dialogue or abstract explanation. "
        "Examples of strong hooks: a character's hidden identity is revealed, a seemingly dead person appears, "
        "a critical piece of evidence is found that changes everything, or a character makes an irreversible choice. "
        "NEVER end with a vague or ambiguous statement. Always end with a specific, concrete, shocking moment."
    )


def _build_orphan_clue_payoff_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, do not introduce a striking clue image unless it will be reused, paid off, or explicitly downgraded later. "
        "If a dent, matching scar, odd mark, or alignment shot exists only for atmosphere and never affects suspicion, cut it."
    )


def _build_in_character_enforcement_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a lazy, evasive, timid, or perfunctory character has to search, detain, escort, or enforce rules, stage that action through their own mask: complaint, procedural excuse, half-hearted handling, delegated force, or efficiency born from wanting the trouble gone."
    )


def _build_hook_escalation_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, each scene's hook must ESCALATE beyond the previous one. "
        "The final scene of the episode must have the strongest hook of all. "
        "Hooks must be SPECIFIC and CONCRETE, not vague. "
        "Examples of escalating hooks: "
        "Scene 1: mysterious stranger appears → Scene 2: stranger knows protagonist's name → "
        "Scene 3: stranger reveals they are from the protagonist's past → "
        "Final scene: stranger shows proof that protagonist is not who they think they are."
    )


def _build_hook_delta_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, the ending hook must add a fresh delta beyond what the audience already knew: a new suspect direction, new timed danger, new prop state, new access point, or new consequence. Mere restatement of an existing clue is not enough."
    )


def _build_hook_question_specificity_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, the ending hook should leave one bounded unresolved question the audience can phrase concretely from the final image: who came through, why this prop changed, what new trace appeared, or what consequence is about to land. Avoid ending on mood alone."
    )


def _build_witness_silence_motivation_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character witnesses danger, blood, or a major crime clue but stays silent, state the reason on screen: "
        "fear, infiltration goal, lack of proof, self-protection, or a strategic choice not to alarm the culprit."
    )


def _build_scene_revelation_density_guardrail(scene_index: int) -> str:
    return (
        f"Scene {scene_index} should not stack too many unrelated major reveals in one uninterrupted dialogue run; "
        "cluster revelations around one causal thread and separate additional turns with visual beats or defer them."
    )


def _build_omniscience_guardrail(track_goal: str) -> str:
    normalized_track = str(track_goal or "").lower()
    if "suspense" in normalized_track or "\u60ac\u7591" in track_goal:
        return (
            "Do not let the protagonist sound omniscient; if they know something unusual, show the source, the prior investigation beat, "
            "or the sensory trigger before the conclusion lands."
        )
    return (
        "Do not let key deductions appear from nowhere; reveal the observation or prior action that supports each major conclusion."
    )


def _build_prop_timeline_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"Track where each high-value prop is before, during, and after {name}; "
        "the same prop cannot exist in two contradictory locations or states without an explicit handoff, retrieval, or inference."
    )


def _build_prop_scene_open_state(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"At the start of {name}, make the current holder, visible location, or hidden stash state of every high-value prop already in play readable on screen."
    )


def _build_prop_scene_close_target(scene_name: str, scene_index: int, next_scene_name: str | None = None) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    next_name = str(next_scene_name or "").strip()
    if next_name:
        return (
            f"Before {name} ends, leave each high-value prop in a readable end state that can carry into {next_name}: who holds it, where it is placed, or how it is concealed."
        )
    return (
        f"Before {name} ends, leave each high-value prop in a readable end state: who holds it, where it is placed, or how it is concealed for the next beat."
    )


def _build_prop_required_transfer_beats(scene_name: str, scene_index: int, next_scene_name: str | None = None) -> list[str]:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    beats = [
        f"If a high-value prop changes hands, containers, or hiding place in {name}, show that transfer in the action before the scene exits.",
        f"If a prop is confiscated, pocketed, tied into a bundle, or left behind in {name}, the screenplay must identify that state as the new continuity baseline.",
    ]
    next_name = str(next_scene_name or "").strip()
    if next_name:
        beats.append(
            f"If {next_name} opens in a different location, leave a readable bridge for how the carried evidence from {name} arrives there."
        )
    return beats


def _build_prop_source_chain_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a prop found in storage, a room, or a chest is used to explain an earlier action, show the source chain clearly: "
        "who took it, from where, and how it connects back to the earlier scene."
    )


def _build_same_scene_prop_handoff_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if one character inspects, pockets, returns, or passes a high-value prop and another character handles it later in the same scene, show the handoff or return beat explicitly before the second handling appears."
    )


def _build_prop_state_reuse_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, once a prop has been pocketed, wrapped, dropped, hidden, or handed off, later reuse must come from that latest state and location, not from the earlier source position."
    )


def _build_prop_repeat_take_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if the same character visibly places a high-value prop back into view, storage, or a staged surface and then handles it again soon after, "
        "show one intervening reason on screen: changed objective, bait setup, verification step, surveillance purpose, or forced retrieval."
    )


def _build_discarded_prop_recovery_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a prop is thrown away, dropped into water, confiscated, or kicked aside, later reappearance must show the recovery beat, handback, or hidden retrieval on screen."
    )


def _build_evidence_consistency_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, once a clue or prop is identified, do not relabel its nature or provenance later unless the script clearly marks "
        "the earlier statement as a lie, bluff, or incomplete deduction with an on-screen cue or later reveal."
    )


def _build_prop_naming_consistency_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, once a high-value prop receives its working name, keep that label stable across action lines and dialogue. Do not alternate between labels such as wooden tag, token, 牌子, or 法牌 unless the script explicitly marks one as mistaken, colloquial, or provisional."
    )


def _build_micro_fact_consistency_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, preserve previously established page numbers, counts, labels, cut directions, finger identities, and other micro-facts. "
        "Do not shift a clue from page three to page two, or from one body part to another, unless the script clearly explains the correction."
    )


def _build_claim_evidence_ceiling_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, dialogue cannot claim stronger certainty than the shown evidence supports. If a character did not literally witness something, phrase it as inference, comparison, or suspicion instead of direct eyewitness certainty."
    )


def _build_unique_clue_signature_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, shared material alone is not enough for a decisive clue match. If fibers, knots, stains, cuts, or marks are used to identify a culprit, "
        "add one unique signature such as placement pattern, cut angle, wrap style, residue, age of damage, or source-limited usage."
    )


def _build_single_source_evidence_chain_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if the same evidence family appears across multiple locations, surfaces, or beats, "
        "stage one readable chain model: either the same trace is carried, dropped, retrieved, or compared step by step, "
        "or clearly label later traces as separate but related instances. Do not let identical evidence seem to teleport between places."
    )


def _build_evidence_observation_anchor_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a later deduction depends on a repeated trace, matching fiber, altered knot, or prop detail, give the deciding character one active observation beat: touch, pause, side-by-side look, remembered glance, or placement comparison. Do not rely on isolated close-ups alone."
    )


def _build_search_scope_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if one character searches another, define the search scope in action: outer robe, sleeves, waistband, chest fold, box, bedding, or body frisk. The audience should understand why some evidence is found and some remains hidden."
    )


def _build_route_trigger_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character moves straight toward a precise location, target, or hiding place, show the route trigger first: a light source, footstep, fresh trace, remembered landmark, sound cue with visible source, or another concrete reason that justifies the destination."
    )


def _build_repeat_inspection_trigger_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character checks the same seam bulge, hidden hard object, stash point, or suspicious layer more than once across the episode, "
        "the later inspection must be triggered by a new interruption ending, a fresh clue, a raised stake, or a changed objective visible on screen."
    )


def _build_anomaly_skip_reason_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character notices an abnormal detail during a search, frisk, or inspection but does not pursue it, stage the reason immediately in frame: interruption, bluff, concealed alliance, fear of exposure, competing priority, or a deliberate decision signaled by pause and withdrawal."
    )


def _build_custody_transfer_bridge_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character is announced to be escorted, locked up, transferred, or held overnight, "
        "bridge the custody transition with one readable transfer beat: drag, shove, relock, wake-up time cut, lantern walk, or guard handoff. "
        "Do not skip from daytime accusation to a later holding state without a visible custody bridge."
    )


def _build_prop_custody_chain_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a high-value prop becomes evidence, explicitly show who takes custody of it, who carries it next, and where it is stored, pocketed, or hidden before the next scene reuses it."
    )


def _build_future_knowledge_guardrail(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, a character's inner line, whispered deduction, or spoken conclusion cannot describe a later event they have not yet witnessed. Keep deductions limited to currently available evidence until the confirming image actually appears."
    )


def _build_core_prop_count_stability_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, do not multiply a core prop into duplicate copies, twins, decoys, or mirrored versions unless the screenplay seeded that duplication earlier with a visible source, a swap beat, or an explicit prior-stash setup."
    )


def _build_restrained_access_sequence_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a restrained character needs an item hidden at the chest, waist, boot, sleeve, or front body, stage the access sequence physically: loosen restraint first, rotate the body, use a reachable tool, or establish enough slack. Do not let behind-the-back restraints magically permit front-body retrieval."
    )


def _build_helper_motive_seed_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a secondary character repeatedly conceals evidence, leaves a tool, softens a search, or quietly helps the protagonist, plant at least one motive seed on screen: old debt, shared target, fear of a third party, self-protection, or another readable reason."
    )


def _build_inference_disambiguation_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if one clue could implicate both the obvious suspect and a hidden suspect, add a distinguishing feature such as cut angle, aging, placement, or damage pattern that keeps the inference sharp."
    )


def _build_accusation_evidence_threshold_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if one character detains, accuses, or searches another for a specific crime, put at least one visible accusation trigger on screen: a matching knot pattern, exclusive residue, marked prop, witness trace, missing inventory sign, or another concrete suspicion anchor."
    )


def _build_next_action_objective_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, before a character commits to the next risky action, state the concrete objective on screen: what they expect to recover, verify, expose, or prevent."
    )


def _build_action_status_precision_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, spoken status words such as checked, confirmed, solved, cleared, released, detained, or finished must match the actual action state on screen. "
        "Do not let dialogue announce closure while the scene is still escalating custody, suspicion, or investigation."
    )


def _build_escape_hardware_geometry_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, any escape, lock-pick, latch-lift, or door-release beat must match the shown hardware geometry. "
        "Before a hook, wire, loop, or finger can open the door, the frame must establish the reachable latch path and how the tool physically engages it."
    )


def _build_tool_path_staging_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a hidden tool is threaded through a gap, seam, slot, or latch opening, stage the tool path in camera-readable steps: "
        "entry point, contact target, direction of pull, and resulting hardware movement. Avoid describing off-screen hook paths the audience cannot spatially reconstruct."
    )


def _build_detainer_intent_anchor_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if characters detain, watch, or re-check someone beyond routine procedure, give the audience one concrete intent anchor in frame: a suspicious prop detail, exchanged glance, unfinished clue, muttered reason, or repeated monitoring target."
    )


def _build_flashback_pressure_continuity_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a flashback interrupts an active danger beat, keep the present-tense pressure alive across the cut with a sound carry, image echo, ticking action, or immediate return trigger so suspense does not reset."
    )


def _build_expository_dialogue_compression_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a clue can be explained by object handling and close-up, compress the dialogue to one short confirming line rather than a full spoken explanation."
    )


def _build_preloaded_tool_origin_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a hidden helper tool, wax cloth, copper wire, note, or stash appears from the protagonist's clothes or bedding, establish earlier when and why it was planted there. "
        "If several hidden helper items belong to the same concealed kit, pre-stage that kit together instead of introducing each piece as a separate surprise."
    )


def _build_hidden_inscription_provenance_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a later reveal depends on a covered inscription, carved stroke, hidden label, or sealed mark under wax, cloth, mud, or another layer, earlier material must show when it was written, cut, or covered. "
        "Do not let a meaningful hidden mark appear later without a provenance beat."
    )


def _build_environment_coherence_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, keep weather, light source, and visibility consistent. Rain, moonlight, lamp glow, darkness, and wet surfaces should describe one compatible environment state."
    )


def _build_prop_restaging_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, if a character reuses a prop to fake their earlier state, such as re-looping a rope or re-hanging a token, show the restaging action explicitly instead of skipping from hidden possession to visible setup."
    )


def _build_hook_image_dominance_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, the ending hook should still read without the final line. Add a visible prop gesture, silhouette shift, body action, or object change so the image carries the hook even before dialogue lands."
    )


def _build_subjective_state_externalization_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, do not leave key psychology as abstract narration alone. If the script says someone remembers, decides, clocks something, grows suspicious, or files a clue away, externalize that state through an action, pause, eye shift, touch, breath change, or prop interaction the camera can actually show."
    )


def _build_identity_hint_calibration_requirement(scene_name: str, scene_index: int) -> str:
    name = str(scene_name or "").strip() or f"scene-{scene_index}"
    return (
        f"In {name}, calibrate hidden-identity hints to the intended certainty level. "
        "If the script wants a watcher, intruder, or shadow figure to remain ambiguous, keep clues source-level and non-exclusive; if the script wants the audience to lean toward one identity, add at least one second anchor such as shoe shape, sleeve edge, gait, tool, or repeated stance pattern."
    )


def _infer_character_gender(name: str) -> str:
    """从角色名推断性别。"""
    if not name:
        return ""
    # 常见女性名字后缀
    female_suffixes = ["女", "娘", "姐", "妹", "嫂", "婶", "婆", "妈", "英", "兰", "莲", "梅", "凤", "鹃", "燕", "霞", "雪", "琳", "婷", "颖", "莉", "蓉", "薇", "倩", "媛", "慧", "敏", "静", "洁", "莹", "玲", "珍", "芳", "丽", "娟", "艳", "燕", "妮", "娜"]
    # 常见男性名字后缀
    male_suffixes = ["男", "哥", "弟", "叔", "伯", "爸", "爷", "强", "伟", "勇", "军", "明", "华", "建", "国", "志", "文", "斌", "浩", "宇", "轩", "泽", "豪", "鑫", "磊", "刚", "波", "涛", "鹏", "飞", "龙", "虎"]
    
    for suffix in female_suffixes:
        if name.endswith(suffix):
            return "女"
    for suffix in male_suffixes:
        if name.endswith(suffix):
            return "男"
    # 默认根据常见姓氏推断（无法确定时返回空）
    return ""


def _infer_character_visible_state(track_goal: str, name: str) -> str:
    if not name:
        return ""
    if "悬疑" in track_goal:
        return "表面状态未完全可信，需保留行为与真实意图之间的落差。"
    if "虐恋" in track_goal:
        return "对外情绪表达与真实情绪未必一致，关系压力优先。"
    if "爽剧" in track_goal or "逆袭" in track_goal:
        return "当前处于受压或蓄力状态，需要为后续反击保留空间。"
    return "当前集行为状态需与角色基础设定保持一致。"


def _infer_character_hidden_state(track_goal: str) -> str:
    if "悬疑" in track_goal:
        return "隐藏目的、隐藏认知或隐藏身份必须在后续场次逐步揭示。"
    if "虐恋" in track_goal:
        return "隐藏情绪、误解来源或关系伤口需要逐步揭示。"
    if "爽剧" in track_goal or "逆袭" in track_goal:
        return "隐藏资源、计划或底牌需要为反击节点服务。"
    return ""


def _infer_character_visible_state_from_outline(
    track_goal: str, name: str, core_conflict: str, characters: list[str]
) -> str:
    """从大纲信息推断角色可见状态。"""
    if not name:
        return ""

    # 基于核心冲突推断角色立场（优先级最高）
    conflict_lower = core_conflict.lower() if core_conflict else ""
    
    # 推诿/挑水相关冲突
    if any(keyword in conflict_lower for keyword in ["推诿", "挑水", "打水", "谁去", "谁也不愿", "都不愿"]):
        return f"{name}当前处于推诿状态，不愿意主动承担挑水任务。表面维持和平，内心各怀心思。"
    
    # 水缸相关冲突
    if "水缸" in conflict_lower:
        if any(keyword in conflict_lower for keyword in ["没水", "无水", "干涸", "见底"]):
            return f"{name}知道水缸没水，但选择假装不知或等待他人行动。"
        if any(keyword in conflict_lower for keyword in ["有水", "水满", "漏水"]):
            return f"{name}对水缸状态有不同看法，可能隐藏着对水缸异常的了解。"
    
    # 一般冲突类型推断
    if "悬疑" in track_goal:
        return "表面状态未完全可信，需保留行为与真实意图之间的落差。"
    if "虐恋" in track_goal:
        return "对外情绪表达与真实情绪未必一致，关系压力优先。"
    if "爽剧" in track_goal or "逆袭" in track_goal:
        return "当前处于受压或蓄力状态，需要为后续反击保留空间。"
    return "当前集行为状态需与角色基础设定保持一致。"


def _infer_character_hidden_state_from_outline(
    track_goal: str, name: str, ending_hook: str
) -> str:
    """从大纲信息推断角色隐藏状态。"""
    if not name:
        return ""

    # 基于结尾钩子推断隐藏动机（优先级最高）
    ending_lower = ending_hook.lower() if ending_hook else ""
    
    # 悬疑/秘密相关结尾
    if any(keyword in ending_lower for keyword in ["黑影", "咬牙切齿", "神秘", "消失", "隐藏", "秘密"]):
        return f"{name}可能隐藏着不为人知的秘密或计划，结尾的异常暗示有人在暗中行动。"
    
    # 危机/紧张相关结尾
    if any(keyword in ending_lower for keyword in ["危机", "危险", "紧张", "摇摇欲坠", "坠落", "断裂"]):
        return f"{name}可能预感到危险即将来临，但选择隐瞒或独自面对。"
    
    # 一般类型推断
    if "悬疑" in track_goal:
        return "隐藏目的、隐藏认知或隐藏身份必须在后续场次逐步揭示。"
    if "虐恋" in track_goal:
        return "隐藏情绪、误解来源或关系伤口需要逐步揭示。"
    if "爽剧" in track_goal or "逆袭" in track_goal:
        return "隐藏资源、计划或底牌需要为反击节点服务。"
    return ""


def _infer_character_transition_trigger(name: str, core_conflict: str) -> str:
    """推断角色状态转变触发器。"""
    if not name:
        return ""

    conflict_lower = core_conflict.lower() if core_conflict else ""
    
    # 推诿/挑水相关冲突
    if any(keyword in conflict_lower for keyword in ["推诿", "挑水", "打水", "谁去", "谁也不愿", "都不愿"]):
        return f"{name}需要一个不得不行动的理由，如：发现水缸彻底干涸、有人受伤、或被逼到绝境。"
    
    # 水缸相关冲突
    if "水缸" in conflict_lower:
        return f"{name}在发现水缸异常或有人试图隐藏真相时，状态会发生转变。"
    
    # 一般冲突类型
    if any(keyword in conflict_lower for keyword in ["秘密", "隐藏", "真相", "发现"]):
        return f"{name}在发现关键秘密或真相被揭露时，状态会发生转变。"
    
    return ""


def _extract_scene_fact_rows(scenes: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """提取场景事实行，基于场景名称生成更有意义的数据。"""
    clue_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    key_prop_rows: list[dict[str, Any]] = []
    
    for index, scene_name in enumerate(scenes, start=1):
        scene_label = str(scene_name).strip()
        if not scene_label:
            continue
        
        # 基于场景名称推断线索
        clue_subject = _infer_clue_from_scene_name(scene_label, index)
        clue_rows.append(
            {
                "clue_id": f"scene_{index}_clue",
                "scene_index": index,
                "scene_name": scene_label,
                "clue_subject": clue_subject,
                "entry_mode": "visual" if clue_subject else "scene_pending_inference",
                "audience_meaning": f"观众在{scene_label}场景中注意到{clue_subject}" if clue_subject else "",
                "payoff_scene_index": index + 1 if index < len(scenes) else None,
            }
        )
        
        # 基于场景名称推断证据
        trigger_object = _infer_trigger_object_from_scene(scene_label)
        evidence_rows.append(
            {
                "chain_id": f"scene_{index}_evidence",
                "scene_index": index,
                "scene_name": scene_label,
                "trigger_object": trigger_object,
                "owner": "",
                "causal_role": f"在{scene_label}场景中发现或使用",
                "next_dependency": f"scene_{index + 1}_evidence" if index < len(scenes) else "",
            }
        )
    
    return clue_rows, evidence_rows, key_prop_rows


def _infer_clue_from_scene_name(scene_name: str, scene_index: int) -> str:
    """基于场景名称推断可能的线索。"""
    scene_lower = scene_name.lower()
    
    # 水缸相关场景
    if "水缸" in scene_name or "井" in scene_name:
        return "水缸状态、水位变化、水缸底部痕迹"
    
    # 寺庙相关场景
    if "寺庙" in scene_name or "庙" in scene_name or "院" in scene_name:
        return "寺庙环境异常、地面痕迹、物品摆放位置"
    
    # 房间相关场景
    if "房" in scene_name or "室" in scene_name:
        return "房间内物品状态、门窗痕迹、隐藏物品"
    
    # 山路相关场景
    if "山" in scene_name or "路" in scene_name:
        return "路上痕迹、脚印、遗落物品"
    
    # 默认
    return f"场景{scene_index}中的关键线索"


def _infer_trigger_object_from_scene(scene_name: str) -> str:
    """基于场景名称推断触发物。"""
    if "水缸" in scene_name:
        return "水缸、水、水位线"
    if "井" in scene_name:
        return "井绳、水桶、井口"
    if "庙" in scene_name or "院" in scene_name:
        return "香炉、供桌、地面"
    if "房" in scene_name:
        return "门、窗、家具"
    return ""


def _extract_scene_names_from_script(script_content: str) -> list[str]:
    content = str(script_content or "")
    if not content.strip():
        return []
    names: list[str] = []
    patterns = [
        r"(?m)^##\s*\u573a\u666f(?:[\u4e00-\u9fff0-9]+)\s*\[([^\]]+)\]",
        r"(?m)^##\s*\u573a\u666f(?:[\u4e00-\u9fff0-9]+)[:：]\s*([^\n]+)",
        r"\*\*\u573a\u666f(?:[\u4e00-\u9fff0-9]+)[:?]\[([^\]]+)\]\*\*",
        r"\*\*\u573a\u666f(?:[\u4e00-\u9fff0-9]+)[:?]([^\n*]+)\*\*",
        r"(?m)^##\s*Scene\s*[0-9]+\s*\[([^\]]+)\]",
        r"(?m)^##\s*Scene\s*[0-9]+[:：]\s*([^\n]+)",
        r"\*\*Scene\s*[0-9]+[:?]\[([^\]]+)\]\*\*",
        r"\*\*Scene\s*[0-9]+[:?]([^\n*]+)\*\*",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, content):
            name = str(match or "").strip()
            normalized_name = name.strip("[]")
            if normalized_name and normalized_name not in names:
                names.append(normalized_name)
            elif name and name not in names and normalized_name not in names:
                names.append(name)
    return names


def _resolve_foundation_scene_names(outline: dict[str, Any], script_content: str | None = None) -> list[str]:
    outline_scenes = _normalize_name_list(outline.get("scenes"))
    script_scenes = _extract_scene_names_from_script(str(script_content or ""))
    if len(script_scenes) >= len(outline_scenes) and script_scenes:
        return script_scenes
    if outline_scenes:
        return outline_scenes
    return script_scenes


def _inject_qa_backpressure_into_foundation(
    foundation: dict[str, Any],
    qa_issues: list[dict[str, Any]],
) -> None:
    foundation["qa_backpressure"] = [
        {
            "title": str(issue.get("title") or issue.get("description") or "").strip(),
            "severity": str(issue.get("severity") or "").strip(),
            "rule_family": classify_script_qa_rule_family(issue),
            "fix_mode": str(issue.get("fix_mode") or "").strip(),
        }
        for issue in qa_issues
        if isinstance(issue, dict)
    ]
    for issue in qa_issues:
        if not isinstance(issue, dict):
            continue
        rule_family = classify_script_qa_rule_family(issue)
        title = str(issue.get("title") or issue.get("description") or "").strip()
        if rule_family == "character_consistency":
            for card in foundation.get("character_state_cards", []):
                conflicts = card.get("forbidden_behavior_conflicts")
                if isinstance(conflicts, list) and title and title not in conflicts:
                    conflicts.append(title)
                canon_guardrail = str(card.get("asset_canon_reconciliation_guardrail") or "").strip()
                persona_layer_guardrail = str(card.get("persona_layer_guardrail") or "").strip()
                hidden_seed_requirement = str(card.get("hidden_layer_seed_requirement") or "").strip()
                hidden_trigger_requirement = str(card.get("hidden_layer_reveal_trigger_requirement") or "").strip()
                lower_title = title.lower()
                if any(token in lower_title for token in ["鐢诲儚", "瀹氬", "璧勪骇", "浜鸿", "姘旇川", "persona", "portrait", "canon"]):
                    card["asset_canon_reconciliation_guardrail"] = (
                        canon_guardrail + " QA flagged canon drift here, so screenplay behavior must either stay inside the asset persona or explicitly revise the canon in-story."
                    ).strip()
                    card["persona_layer_guardrail"] = (
                        persona_layer_guardrail + " QA flagged visible-mask drift here, so preserve the public layer in ordinary beats and reveal the hidden layer only after a staged trigger."
                    ).strip()
                if any(token in lower_title for token in ["藏物", "藏锋", "夹层", "hidden competence", "suddenly capable", "persona drift", "反差过大"]):
                    card["hidden_layer_seed_requirement"] = (
                        hidden_seed_requirement + " QA flagged hidden competence arriving too abruptly, so an earlier beat must plant one small physical seed of preparedness or withheld sharpness."
                    ).strip()
                    card["hidden_layer_reveal_trigger_requirement"] = (
                        hidden_trigger_requirement + " QA flagged the reveal as too abrupt, so the screenplay must tie the colder or more capable turn to a concrete visible trigger."
                    ).strip()
        if rule_family == "character_state_transition":
            for card in foundation.get("character_state_cards", []):
                if not card.get("state_transition_trigger"):
                    card["state_transition_trigger"] = "需要在正式剧本中补出显性触发器。"
                flashback_guardrail = str(card.get("flashback_provenance_guardrail") or "").strip()
                if "视角" in title or "闪回" in title or "记忆" in title:
                    card["flashback_provenance_guardrail"] = (
                        flashback_guardrail + " Prioritize explicit provenance for any recalled image mentioned by QA."
                    ).strip()
        if rule_family in {
            "clue_payoff_integrity",
            "prop_evidence_continuity",
            "character_state_transition",
            "episode_hook_strength",
            "generic_skill_gap",
        }:
            foundation.setdefault("diagnostic_flags", [])
            if title and title not in foundation["diagnostic_flags"]:
                foundation["diagnostic_flags"].append(title)
            lower_title = title.lower()
            for card in foundation.get("scene_goal_cards", []):
                if not isinstance(card, dict):
                    continue
                if any(token in lower_title for token in ["时间线", "黄昏", "昨夜", "进门之前", "before entering", "timeline", "dusk", "last night"]):
                    card["relative_time_anchor_requirement"] = (
                        str(card.get("relative_time_anchor_requirement") or "").strip()
                        + " QA flagged a relative-time conflict, so dialogue markers and flashback timing must use the same anchor."
                    ).strip()
                if any(token in lower_title for token in ["库房", "柴房", "扣押地点", "转去", "storehouse", "shed", "custody location"]):
                    card["custody_destination_consistency_requirement"] = (
                        str(card.get("custody_destination_consistency_requirement") or "").strip()
                        + " QA flagged a custody-location switch, so the next pass must either keep the announced destination or show the reroute explicitly."
                    ).strip()
                if any(token in lower_title for token in ["反绑", "绑住", "手伸进", "动作矛盾", "restrained", "impossible motion", "身体动作", "铁环", "重新绑腕", "rebind"]):
                    card["action_feasibility_requirement"] = (
                        str(card.get("action_feasibility_requirement") or "").strip()
                        + " QA flagged a body-constraint contradiction, so the next action must respect the restrained or hidden posture already on screen."
                    ).strip()
                if any(token in lower_title for token in ["来源", "方法", "由来", "怎么知道", "knowledge", "source", "provenance"]):
                    card["knowledge_provenance_requirement"] = (
                        str(card.get("knowledge_provenance_requirement") or "").strip()
                        + " QA flagged source ambiguity, so hidden methods and deductions in this pass must point to an on-screen origin."
                    ).strip()
                if any(token in lower_title for token in ["画外音", "锉刀", "响声", "声音", "纯音效", "sound cue", "audio"]):
                    card["audio_visual_pairing_requirement"] = (
                        str(card.get("audio_visual_pairing_requirement") or "").strip()
                        + " QA flagged a sound-only clue, so the sound should be paired with a visible source or silhouette."
                    ).strip()
                if any(token in lower_title for token in ["蜡块", "底下的刻痕", "蜡下", "盖住", "不可见", "under wax", "under cloth", "hidden under", "occluded"]):
                    card["occluded_evidence_layer_requirement"] = (
                        str(card.get("occluded_evidence_layer_requirement") or "").strip()
                        + " QA flagged hidden evidence being described as already visible, so action lines must separate the visible surface trace from the still-covered inner mark."
                    ).strip()
                if any(token in lower_title for token in ["铜字", "刻痕来源", "蜡下有字", "inscription provenance", "hidden mark source", "sealed mark"]):
                    card["hidden_inscription_provenance_requirement"] = (
                        str(card.get("hidden_inscription_provenance_requirement") or "").strip()
                        + " QA flagged a hidden inscription reveal without origin setup, so earlier material must show when the mark was written, carved, or covered."
                    ).strip()
                if any(token in lower_title for token in ["同一条缝", "重复当作新线索", "前后矛盾", "already shown earlier", "repeat discovery", "new discovery again", "previously shown seam"]):
                    card["prior_discovery_delta_requirement"] = (
                        str(card.get("prior_discovery_delta_requirement") or "").strip()
                        + " QA flagged a clue being rediscovered without new value, so the later beat must either acknowledge prior awareness or add a genuinely new layer."
                    ).strip()
                if any(token in lower_title for token in ["蜡下", "刻痕", "悬念焦点", "看不清", "worth remembering", "concealed clue", "focal point"]):
                    card["concealed_clue_focus_requirement"] = (
                        str(card.get("concealed_clue_focus_requirement") or "").strip()
                        + " QA flagged a concealed clue that never became memorable, so the frame needs one visible abnormality that tells the audience there is something under the cover worth tracking."
                    ).strip()
                if any(token in lower_title for token in ["亲眼见", "亲耳听", "亲眼所见", "eyewitness", "you saw", "certainty"]):
                    card["claim_evidence_ceiling_requirement"] = (
                        str(card.get("claim_evidence_ceiling_requirement") or "").strip()
                        + " QA flagged an overclaimed line, so dialogue certainty must match what the audience actually saw."
                    ).strip()
                if any(token in lower_title for token in ["搜身", "未搜出", "藏匿", "暗袋", "search", "stash", "not found"]):
                    card["search_scope_requirement"] = (
                        str(card.get("search_scope_requirement") or "").strip()
                        + " QA flagged a search-logic gap, so the search scope and hiding place must be readable on screen."
                    ).strip()
                if any(token in lower_title for token in ["再次检查", "第二次", "又去摸", "重复搜查", "checks again", "inspects again", "second inspection"]):
                    card["repeat_inspection_trigger_requirement"] = (
                        str(card.get("repeat_inspection_trigger_requirement") or "").strip()
                        + " QA flagged a repeated inspection with no new cause, so the later check must be tied to a fresh trigger, resumed interruption, or changed objective."
                    ).strip()
                if any(token in lower_title for token in ["墙根", "草堆", "柴房", "为什么知道", "主动转向", "查找", "search target", "why search there"]):
                    card["search_trigger_requirement"] = (
                        str(card.get("search_trigger_requirement") or "").strip()
                        + " QA flagged an unmotivated targeted search, so the screenplay must show the visual or remembered cue that directs the character there."
                    ).strip()
                if any(token in lower_title for token in ["直奔", "供台", "推理断档", "走向山门", "route trigger", "why go there", "destination jump"]):
                    card["route_trigger_requirement"] = (
                        str(card.get("route_trigger_requirement") or "").strip()
                        + " QA flagged a destination jump that felt like coincidence, so the next pass must stage the clue, light, sound, trace, or remembered landmark that sends the character there."
                    ).strip()
                if any(token in lower_title for token in ["预知", "时间线倒置", "之后发生", "未来画面", "future knowledge", "timeline inversion"]):
                    card["future_knowledge_guardrail"] = (
                        str(card.get("future_knowledge_guardrail") or "").strip()
                        + " QA flagged a conclusion that described a later event too early, so the next pass must delay that line until the confirming image is actually seen."
                    ).strip()
                if any(token in lower_title for token in ["未发现", "夜晚", "砖缝", "翻井口", "later discovery", "searched", "missed before"]):
                    card["delayed_discovery_gate_requirement"] = (
                        str(card.get("delayed_discovery_gate_requirement") or "").strip()
                        + " QA flagged a delayed-discovery jump, so the earlier miss and later find must be separated by a clear gating reason."
                    ).strip()
                if any(token in lower_title for token in ["账页", "账本", "一张", "副本", "送出", "复制", "duplicate", "timeline", "document", "page", "fragment"]):
                    card["split_evidence_timeline_requirement"] = (
                        str(card.get("split_evidence_timeline_requirement") or "").strip()
                        + " QA flagged a split-document timeline risk, so duplicate pages, extracted fragments, or prior deliveries must be shown explicitly."
                    ).strip()
                if any(token in lower_title for token in ["结尾", "尾钩", "井底", "hook", "末尾", "收尾"]):
                    card["ending_image_hook_requirement"] = (
                        str(card.get("ending_image_hook_requirement") or "").strip()
                        + " QA flagged a weak visual hook, so the scene should end on a concrete image instead of an abstract line alone."
                    ).strip()
                if any(token in lower_title for token in ["未被利用", "孤证", "只出现一次", "未回收", "orphan clue", "unused clue", "not reused"]):
                    card["orphan_clue_payoff_requirement"] = (
                        str(card.get("orphan_clue_payoff_requirement") or "").strip()
                        + " QA flagged a striking clue image that never pays off, so the next pass must either reuse it in suspicion logic or remove it."
                    ).strip()
                if any(token in lower_title for token in ["重复", "人影", "黑影", "递进", "shadow", "motif", "repeat hook"]):
                    card["hook_escalation_requirement"] = (
                        str(card.get("hook_escalation_requirement") or "").strip()
                        + " QA flagged a repeated hook motif, so the later beat must add new information or threat instead of repeating the same tease."
                    ).strip()
                if any(token in lower_title for token in ["钩子偏弱", "没有新信息", "重复已知事实", "hook weak", "restatement", "no new delta"]):
                    card["hook_delta_requirement"] = (
                        str(card.get("hook_delta_requirement") or "").strip()
                        + " QA flagged a hook that only restated known facts, so the final beat must introduce a fresh suspect direction, timed danger, prop change, or consequence."
                    ).strip()
                if any(token in lower_title for token in ["指向", "另有其人", "ambiguous", "distinguish", "指向性"]):
                    card["inference_disambiguation_requirement"] = (
                        str(card.get("inference_disambiguation_requirement") or "").strip()
                        + " QA flagged an ambiguous inference, so the script must add a concrete distinguishing feature."
                    ).strip()
                if any(token in lower_title for token in ["草纤维", "同材质", "唯一性", "fiber", "same material", "unique signature"]):
                    card["unique_clue_signature_requirement"] = (
                        str(card.get("unique_clue_signature_requirement") or "").strip()
                        + " QA flagged a clue match that relied on shared material alone, so the script must add a unique signature such as placement pattern, cut angle, or source-limited usage."
                    ).strip()
                if any(token in lower_title for token in ["白草纤维", "提示功能被弱化", "推理过程", "observation", "too implicit", "hidden clue chain"]):
                    card["evidence_observation_anchor_requirement"] = (
                        str(card.get("evidence_observation_anchor_requirement") or "").strip()
                        + " QA flagged an evidence chain that stayed too implicit, so the deciding character must actively observe, compare, touch, or align the trace before making the deduction."
                    ).strip()
                if any(token in lower_title for token in ["看了一眼", "看了眼", "眼神", "墙根", "语意不明", "glance", "lingering look"]):
                    card["suggestive_glance_resolution_requirement"] = (
                        str(card.get("suggestive_glance_resolution_requirement") or "").strip()
                        + " QA flagged a suggestive glance without payoff, so the look must either become a concrete action or receive a later reveal."
                    ).strip()
                    card["attitude_anchor_requirement"] = (
                        str(card.get("attitude_anchor_requirement") or "").strip()
                        + " QA flagged withheld intent, so the same beat must include a readable pause, finger stop, jaw set, eye change, or comparable stance cue."
                    ).strip()
                if any(token in lower_title for token in ["铜丝", "蜡布", "来历", "来源未交代", "stash", "preloaded", "藏在内衬", "来源未在闪回中铺垫", "flashback setup"]):
                    card["preloaded_tool_origin_requirement"] = (
                        str(card.get("preloaded_tool_origin_requirement") or "").strip()
                        + " QA flagged an unexplained hidden tool or stash, so the screenplay must establish when and why it was planted."
                    ).strip()
                if any(token in lower_title for token in ["压痕", "细痕", "缺口", "划痕", "种子线索", "未进入画面", "micro clue", "seed clue", "tiny clue", "not in frame"]):
                    card["seed_clue_visibility_requirement"] = (
                        str(card.get("seed_clue_visibility_requirement") or "").strip()
                        + " QA flagged a payoff clue that never entered the frame, so the active scene image must already expose the seed detail before later deduction."
                    ).strip()
                if any(token in lower_title for token in ["同一挂布", "撕裂口", "严丝合缝", "仅靠台词", "进入画面", "same cloth", "edge match", "compare in frame"]):
                    card["comparison_visualization_requirement"] = (
                        str(card.get("comparison_visualization_requirement") or "").strip()
                        + " QA flagged a claimed evidence match that was not visualized, so the screenplay must stage the overlap or side-by-side comparison in frame."
                    ).strip()
                    card["multi_signal_match_requirement"] = (
                        str(card.get("multi_signal_match_requirement") or "").strip()
                        + " QA flagged a same-source inference jump, so the script must add a second confirming dimension beyond color or one shared reaction."
                    ).strip()
                if any(token in lower_title for token in ["暗红", "血水", "锈色", "颜色歧义", "rust", "blood", "color cue"]):
                    card["color_signal_clarity_requirement"] = (
                        str(card.get("color_signal_clarity_requirement") or "").strip()
                        + " QA flagged a misleading clue color, so the screenplay must anchor the intended material reading with a source or texture cue."
                    ).strip()
                if any(token in lower_title for token in ["刻字", "层叠", "布局", "资产化", "道具无法资产化", "法牌", "prop layout", "asset-ready"]):
                    card["prop_asset_spec_requirement"] = (
                        str(card.get("prop_asset_spec_requirement") or "").strip()
                        + " QA flagged an asset-unsafe prop description, so the screenplay must state stable layout facts for text placement, material, seal, and old-vs-new marks."
                    ).strip()
                if any(token in lower_title for token in ["雨丝", "月光", "天气矛盾", "weather", "moonlight", "rain"]):
                    card["environment_coherence_requirement"] = (
                        str(card.get("environment_coherence_requirement") or "").strip()
                        + " QA flagged an environment-state contradiction, so weather, light, and visibility must be made compatible."
                    ).strip()
                if any(token in lower_title for token in ["空绳套", "重新绕好", "装成仍在被绑", "restage", "re-loop"]):
                    card["prop_restaging_requirement"] = (
                        str(card.get("prop_restaging_requirement") or "").strip()
                        + " QA flagged a restaged prop state, so the re-looping or reset action must be shown explicitly."
                    ).strip()
                if any(token in lower_title for token in ["\u660e\u5929\u638f\u4e95", "\u51b3\u7b56\u52a8\u673a", "\u4e3a\u4ec0\u4e48\u4e0d\u62a5\u5b98", "goal", "why not report", "\u6263\u538b", "\u7ed1\u4eba", "confiscation", "detain", "\u52a8\u673a\u504f\u5f31"]):
                    card["next_action_objective_requirement"] = (
                        str(card.get("next_action_objective_requirement") or "").strip()
                        + " QA flagged a weak next-action motive, so the risky next step must state a concrete objective on screen."
                    ).strip()
                    card["motivation_visibility_requirement"] = (
                        str(card.get("motivation_visibility_requirement") or "").strip()
                        + " QA flagged a weak coercive escalation motive, so the script must show the concrete trigger for detention, confiscation, or restraint."
                    ).strip()
                if any(token in lower_title for token in ["查清了", "明早再放", "放他走", "已查完", "结案", "说法冲突", "status wording", "closure wording", "released later"]):
                    card["action_status_precision_requirement"] = (
                        str(card.get("action_status_precision_requirement") or "").strip()
                        + " QA flagged status wording that outran the scene state, so dialogue about checking, clearing, or releasing must match the actual custody and investigation phase."
                    ).strip()
                if any(token in lower_title for token in ["开锁", "门闩", "铁皮门扣", "锁结构", "hook opens", "latch", "hardware geometry", "lock-breaking"]):
                    card["escape_hardware_geometry_requirement"] = (
                        str(card.get("escape_hardware_geometry_requirement") or "").strip()
                        + " QA flagged an escape beat that did not match the shown hardware geometry, so the latch path and tool engagement must be established in-frame."
                    ).strip()
                if any(token in lower_title for token in ["解释性", "说明式对白", "讲解", "explanatory dialogue", "too explanatory"]):
                    card["expository_dialogue_compression_requirement"] = (
                        str(card.get("expository_dialogue_compression_requirement") or "").strip()
                        + " QA flagged explanatory dialogue, so object handling and close-up should carry more of the reasoning."
                    ).strip()
                if any(token in lower_title for token in ["记进心里", "怀疑", "心理描写", "不宜直接拍摄", "abstract psychology", "internal state"]):
                    card["subjective_state_externalization_requirement"] = (
                        str(card.get("subjective_state_externalization_requirement") or "").strip()
                        + " QA flagged unfilmable internal narration, so the next pass must externalize that psychology through visible micro-action."
                    ).strip()
                if any(token in lower_title for token in ["山门丢", "丢念珠", "缺少画面", "场外事件", "off-screen event", "missing item event"]):
                    card["offscreen_incident_anchor_requirement"] = (
                        str(card.get("offscreen_incident_anchor_requirement") or "").strip()
                        + " QA flagged a conflict-driving off-screen incident with no visible aftermath, so the scene needs one concrete anchor of the missing item or damage."
                    ).strip()
                    card["dialogue_evidence_order_requirement"] = (
                        str(card.get("dialogue_evidence_order_requirement") or "").strip()
                        + " QA flagged evidence appearing first in dialogue, so the next pass must place the visual anchor before or during the first spoken mention."
                    ).strip()
                if any(token in lower_title for token in ["结尾钩子", "依赖台词", "图像性偏弱", "hook relies on dialogue", "image weak"]):
                    card["hook_image_dominance_requirement"] = (
                        str(card.get("hook_image_dominance_requirement") or "").strip()
                        + " QA flagged a dialogue-heavy hook, so the final image must still carry the hook before the line lands."
                    ).strip()
                if any(token in lower_title for token in ["结尾钩子强度不足", "缺少新问题", "普通逃脱", "hook strength", "no new question", "ordinary escape"]):
                    card["hook_question_specificity_requirement"] = (
                        str(card.get("hook_question_specificity_requirement") or "").strip()
                        + " QA flagged a hook that ended on mood or escape alone, so the final image must leave one concrete unresolved question the audience can state."
                    ).strip()
                if any(token in lower_title for token in ["未声张", "不声张", "没报警", "silent", "why stayed", "动机不明"]):
                    card["witness_silence_motivation_requirement"] = (
                        str(card.get("witness_silence_motivation_requirement") or "").strip()
                        + " QA flagged unexplained silence after witnessing danger, so the script must surface a concrete reason for staying quiet."
                    ).strip()
                if any(token in lower_title for token in ["鞋影", "门外人", "黑影", "身份指向", "暗示过多", "watcher", "shadow identity", "too specific", "identity hint"]):
                    card["identity_hint_calibration_requirement"] = (
                        str(card.get("identity_hint_calibration_requirement") or "").strip()
                        + " QA flagged identity hints that were either overcommitted or too vague, so the next pass must calibrate the clue density to the intended certainty level."
                    ).strip()
                if any(token in lower_title for token in ["主动调查", "侦查倾向过强", "超出画像", "enforcement", "too investigative", "too proactive"]):
                    card["in_character_enforcement_requirement"] = (
                        str(card.get("in_character_enforcement_requirement") or "").strip()
                        + " QA flagged enforcement behavior that drifted out of persona, so the next pass must keep search, detention, or escort actions inside the character's lazy or evasive mask."
                    ).strip()
                if any(token in lower_title for token in ["未检查", "没深究", "没有追查", "行为不合常理", "异常细节", "noticed but ignored", "ignored anomaly", "didn't inspect"]):
                    card["anomaly_skip_reason_requirement"] = (
                        str(card.get("anomaly_skip_reason_requirement") or "").strip()
                        + " QA flagged an abnormal detail that was noticed but not pursued, so the beat must show an interruption, bluff, concealed alliance, or deliberate strategic withdrawal."
                    ).strip()
                if any(token in lower_title for token in ["锁定甲", "扣押", "扣住", "扣人", "动机证据链不足", "拘押", "盘问升级", "accusation", "detention", "evidence threshold", "watch intent"]):
                    card["accusation_evidence_threshold_requirement"] = (
                        str(card.get("accusation_evidence_threshold_requirement") or "").strip()
                        + " QA flagged a coercive escalation without enough proof, so the beat must place at least one visible accusation trigger on screen before detention or forced re-check."
                    ).strip()
                    card["detainer_intent_anchor_requirement"] = (
                        str(card.get("detainer_intent_anchor_requirement") or "").strip()
                        + " QA flagged weak detention intent, so the screenplay must show the concrete watch, isolate, stall, or seize objective that justifies holding the target in frame."
                    ).strip()
                if any(token in lower_title for token in ["闪回", "紧张延续", "门外影子", "压力中断", "danger interrupted", "pressure continuity", "flashback drag"]):
                    card["flashback_pressure_continuity_requirement"] = (
                        str(card.get("flashback_pressure_continuity_requirement") or "").strip()
                        + " QA flagged a flashback that drained active danger, so the cutaway must keep the present-tense pressure alive across the cut and snap back before tension dissipates."
                    ).strip()
                if any(token in lower_title for token in ["两枚法牌", "数量关系不清", "双法牌", "duplicate prop", "two tokens", "count stability"]):
                    card["core_prop_count_stability_requirement"] = (
                        str(card.get("core_prop_count_stability_requirement") or "").strip()
                        + " QA flagged a core prop multiplying without setup, so the next pass must keep one stable prop count unless duplication was seeded earlier on screen."
                    ).strip()
                if any(token in lower_title for token in ["反绑", "够不到前襟", "取前襟", "behind-the-back", "front-body retrieval", "restrained access"]):
                    card["restrained_access_sequence_requirement"] = (
                        str(card.get("restrained_access_sequence_requirement") or "").strip()
                        + " QA flagged impossible front-body access under restraint, so the next pass must show the loosen-first or reachable-tool sequence before retrieval."
                    ).strip()
                if any(token in lower_title for token in ["帮助甲", "包庇", "掩饰", "留下油灯", "helper motive", "why help"]):
                    card["helper_motive_seed_requirement"] = (
                        str(card.get("helper_motive_seed_requirement") or "").strip()
                        + " QA flagged repeated covert help without motive, so the screenplay must plant one readable reason for that help on screen."
                    ).strip()
            for card in foundation.get("prop_timeline_cards", []):
                if not isinstance(card, dict):
                    continue
                if any(token in lower_title for token in ["\u53bb\u5411\u4e0d\u6e05", "\u53c8\u51fa\u73b0\u5728", "\u88ab\u4e22\u5f03\u540e", "\u6000\u91cc", "reappears", "discarded", "confiscated", "kicked aside"]):
                    card["discarded_prop_recovery_requirement"] = (
                        str(card.get("discarded_prop_recovery_requirement") or "").strip()
                        + " QA flagged a discarded-prop recovery gap, so later reuse must show the retrieval beat on screen."
                    ).strip()
                if any(token in lower_title for token in ["\u4ece\u5899\u89d2\u6361\u8d77", "\u91cd\u590d\u4f7f\u7528", "\u540c\u4e00\u4e2a", "same prop", "reused again"]):
                    card["prop_state_reuse_requirement"] = (
                        str(card.get("prop_state_reuse_requirement") or "").strip()
                        + " QA flagged a prop-state reuse conflict, so the later beat must source the prop from its latest known state."
                    ).strip()
                if any(token in lower_title for token in ["重复取", "重新取", "放回又拿起", "重复拿", "same character", "re-taking", "puts it back", "handles it again"]):
                    card["prop_repeat_take_requirement"] = (
                        str(card.get("prop_repeat_take_requirement") or "").strip()
                        + " QA flagged the same character repeatedly taking the same prop, so the screenplay must show the changed objective, bait setup, or verification reason between those actions."
                    ).strip()
                if any(token in lower_title for token in ["木牌", "法牌", "术语混用", "同一道具", "same prop two names", "naming drift"]):
                    card["prop_naming_consistency_requirement"] = (
                        str(card.get("prop_naming_consistency_requirement") or "").strip()
                        + " QA flagged prop naming drift, so one stable working label must be used across action and dialogue."
                    ).strip()
                if any(token in lower_title for token in ["位置矛盾", "又出现在包袱里", "交接缺失", "谁拿着", "same scene", "handoff", "return beat", "location jump"]):
                    card["same_scene_prop_handoff_requirement"] = (
                        str(card.get("same_scene_prop_handoff_requirement") or "").strip()
                        + " QA flagged a same-scene prop location jump, so the screenplay must show the handoff, return, concealment, or repossession beat before another character handles it."
                    ).strip()
                if any(token in lower_title for token in ["物证去向", "法牌", "谁收好", "证物", "custody chain", "evidence custody", "prop custody"]):
                    card["prop_custody_chain_requirement"] = (
                        str(card.get("prop_custody_chain_requirement") or "").strip()
                        + " QA flagged an evidence-custody gap, so the screenplay must show who takes custody of the prop, who carries it next, and where it is stored before reuse."
                    ).strip()
                if any(token in lower_title for token in ["物证去向", "法牌", "谁收好", "证物", "custody chain", "evidence custody", "prop custody"]):
                    card["prop_custody_chain_requirement"] = (
                        str(card.get("prop_custody_chain_requirement") or "").strip()
                        + " QA flagged an evidence-custody gap, so the screenplay must show who takes possession of the prop, who carries it next, and where it is stored before reuse."
                    ).strip()
                if any(token in lower_title for token in ["对白格式", "台词格式", "角色：台词", "subtitle", "dialogue format"]):
                    for character_card in foundation.get("character_state_cards", []):
                        if not isinstance(character_card, dict):
                            continue
                        character_card["dialogue_format_guardrail"] = (
                            str(character_card.get("dialogue_format_guardrail") or "").strip()
                            + " QA flagged format drift, so spoken lines in this pass should be normalized into one parseable `角色：台词` pattern."
                        ).strip()
                if any(token in lower_title for token in ["阿弥陀佛", "口头禅", "拖沓", "台词节奏", "借口", "signature speech", "cadence"]):
                    for character_card in foundation.get("character_state_cards", []):
                        if not isinstance(character_card, dict):
                            continue
                        character_card["signature_speech_requirement"] = (
                            str(character_card.get("signature_speech_requirement") or "").strip()
                            + " QA flagged flattened voice texture, so early lines should restore the character's habitual opener, cadence, or excuse pattern."
                        ).strip()


def script_skill_foundation_contract() -> dict[str, Any]:
    return {
        "episode_goal_card": {
            "episode": None,
            "title": "",
            "platform_goal": "",
            "track_goal": "",
            "core_conflict": "",
            "opening_hook": "",
            "midpoint_escalation": "",
            "ending_hook": "",
        },
        "story_fact_sheet": {
            "episode_objective": "",
            "character_fact_sheet": [],
            "prop_fact_sheet": [],
            "evidence_fact_sheet": [],
            "helper_motive_sheet": [],
            "spatial_mechanics_sheet": [],
            "hook_delta_sheet": [],
        },
        "character_state_cards": [],
        "scene_goal_cards": [],
        "clue_table": [],
        "evidence_chain_table": [],
        "key_prop_table": [],
        "prop_timeline_cards": [],
        "evidence_consistency_rules": [],
        "hook_table": [],
        "investigation_trace_rules": [],
        "qa_backpressure": [],
    }


def build_script_skill_foundation(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
    script_content: str | None = None,
) -> dict[str, Any]:
    runtime = build_project_production_skill_runtime(book_id)
    outline = episode_outline if isinstance(episode_outline, dict) else {}
    summary = runtime.get("runtime_summary", {}) if isinstance(runtime.get("runtime_summary"), dict) else {}
    foundation = script_skill_foundation_contract()
    
    # 获取角色性格和性别信息
    character_personalities = {}
    character_genders = {}
    try:
        from models import Session, BookBible
        with Session() as s:
            bible = s.query(BookBible).filter(BookBible.book_id == book_id).first()
            if bible and bible.content:
                import re
                character_sections = re.split(r"###\s+", bible.content)
                for section in character_sections:
                    if section.strip():
                        lines = section.strip().split("\n")
                        if lines:
                            char_name = lines[0].strip()
                            for line in lines:
                                if "性格" in line or "personality" in line.lower():
                                    personality_match = re.search(r"[*]*性格[*]*[：:]\s*(.+)", line)
                                    if personality_match:
                                        character_personalities[char_name] = personality_match.group(1).strip()
                                if "性别" in line or "gender" in line.lower():
                                    gender_match = re.search(r"[*]*性别[*]*[：:]\s*(.+)", line)
                                    if gender_match:
                                        gender_val = gender_match.group(1).strip()
                                        if "女" in gender_val:
                                            character_genders[char_name] = "女性"
                                        elif "男" in gender_val:
                                            character_genders[char_name] = "男性"
                                        else:
                                            character_genders[char_name] = gender_val
    except Exception:
        pass
    except Exception:
        pass  # 如果获取失败，使用空字典
    
    foundation["episode_goal_card"] = {
        "episode": outline.get("episode"),
        "title": str(outline.get("title") or "").strip(),
        "platform_goal": str(summary.get("platform") or "").strip(),
        "track_goal": str(summary.get("track") or "").strip(),
        "core_conflict": str(outline.get("core_conflict") or outline.get("core_event") or "").strip(),
        "opening_hook": str(outline.get("opening_hook") or "").strip(),
        "midpoint_escalation": str(outline.get("climax") or "").strip(),
        "ending_hook": str(outline.get("ending_hook") or "").strip(),
    }

    track_goal = foundation["episode_goal_card"]["track_goal"]
    core_conflict = foundation["episode_goal_card"].get("core_conflict") or ""
    ending_hook = foundation["episode_goal_card"].get("ending_hook") or ""
    characters = _normalize_name_list(outline.get("characters"))
    foundation["character_state_cards"] = [
        {
            "name": str(name).strip(),
            "gender": character_genders.get(str(name).strip()) or _infer_character_gender(str(name).strip()),
            "base_state": "",
            "episode_visible_state": _infer_character_visible_state_from_outline(
                track_goal, str(name).strip(), core_conflict, characters
            ),
            "hidden_state": _infer_character_hidden_state_from_outline(
                track_goal, str(name).strip(), ending_hook
            ),
            "state_transition_trigger": _infer_character_transition_trigger(
                str(name).strip(), core_conflict
            ),
            "speech_style_anchor": _build_character_speech_style_anchor(track_goal, str(name).strip()),
            "signature_speech_requirement": _build_signature_speech_requirement(track_goal, str(name).strip()),
            "behavior_guardrails": _build_character_behavior_guardrails(track_goal, character_personalities.get(str(name).strip(), "")),
            "omniscience_guardrail": _build_omniscience_guardrail(track_goal),
            "flashback_provenance_guardrail": _build_flashback_provenance_guardrail(track_goal),
            "identity_cover_guardrail": _build_identity_cover_guardrail(track_goal),
            "asset_canon_reconciliation_guardrail": _build_asset_canon_reconciliation_guardrail(track_goal),
            "persona_layer_guardrail": _build_persona_layer_guardrail(track_goal),
            "hidden_layer_seed_requirement": _build_hidden_layer_seed_requirement(track_goal),
            "hidden_layer_reveal_trigger_requirement": _build_hidden_layer_reveal_trigger_requirement(track_goal),
            "dialogue_format_guardrail": _build_dialogue_format_guardrail(),
            "allowed_disguise_signals": ["眼神变化", "动作停顿", "答非所问", "延迟反应"] if "悬疑" in track_goal or "suspense" in track_goal.lower() else [],
            "forbidden_behavior_conflicts": [],
        }
        for name in characters
        if str(name).strip()
    ]

    scenes = _resolve_foundation_scene_names(outline, script_content=script_content)
    foundation["scene_goal_cards"] = [
        {
            "scene_index": index + 1,
            "scene_name": str(scene_name).strip(),
            "scene_purpose": "",
            "scene_conflict": "",
            "scene_information_delta": "",
            "scene_emotion_delta": "",
            "scene_exit_hook": "",
            "scene_driver_requirement": _build_scene_driver_requirement(str(scene_name).strip(), index + 1),
            "scene_visual_anchor_goal": _build_scene_visual_anchor_goal(str(scene_name).strip(), index + 1),
            "scene_new_evidence_goal": _build_scene_new_evidence_goal(str(scene_name).strip(), index + 1),
            "scene_reused_clue_goal": _build_scene_reused_clue_goal(str(scene_name).strip(), index + 1),
            "scene_exit_delta_goal": _build_scene_exit_delta_goal(str(scene_name).strip(), index + 1),
            "transition_requirement": _build_scene_transition_requirement(str(scene_name).strip(), index + 1),
            "custody_destination_consistency_requirement": _build_custody_destination_consistency_requirement(str(scene_name).strip(), index + 1),
            "relative_time_anchor_requirement": _build_relative_time_anchor_requirement(str(scene_name).strip(), index + 1),
            "action_feasibility_requirement": _build_action_feasibility_requirement(str(scene_name).strip(), index + 1),
            "investigation_trace_requirement": _build_investigation_trace_requirement(str(scene_name).strip(), index + 1),
            "motivation_visibility_requirement": _build_motivation_visibility_requirement(str(scene_name).strip(), index + 1),
            "search_trigger_requirement": _build_search_trigger_requirement(str(scene_name).strip(), index + 1),
            "suggestive_glance_resolution_requirement": _build_suggestive_glance_resolution_requirement(str(scene_name).strip(), index + 1),
            "attitude_anchor_requirement": _build_attitude_anchor_requirement(str(scene_name).strip(), index + 1),
            "dialogue_evidence_order_requirement": _build_dialogue_evidence_order_requirement(str(scene_name).strip(), index + 1),
            "visual_evidence_requirement": _build_visual_evidence_requirement(str(scene_name).strip(), index + 1),
            "occluded_evidence_layer_requirement": _build_occluded_evidence_layer_requirement(str(scene_name).strip(), index + 1),
            "hidden_inscription_provenance_requirement": _build_hidden_inscription_provenance_requirement(str(scene_name).strip(), index + 1),
            "seed_clue_visibility_requirement": _build_seed_clue_visibility_requirement(str(scene_name).strip(), index + 1),
            "concealed_clue_focus_requirement": _build_concealed_clue_focus_requirement(str(scene_name).strip(), index + 1),
            "prior_discovery_delta_requirement": _build_prior_discovery_delta_requirement(str(scene_name).strip(), index + 1),
            "comparison_visualization_requirement": _build_comparison_visualization_requirement(str(scene_name).strip(), index + 1),
            "multi_signal_match_requirement": _build_multi_signal_match_requirement(str(scene_name).strip(), index + 1),
            "color_signal_clarity_requirement": _build_color_signal_clarity_requirement(str(scene_name).strip(), index + 1),
            "prop_asset_spec_requirement": _build_prop_asset_spec_requirement(str(scene_name).strip(), index + 1),
            "audio_visual_pairing_requirement": _build_audio_visual_pairing_requirement(str(scene_name).strip(), index + 1),
            "delayed_discovery_gate_requirement": _build_delayed_discovery_gate_requirement(str(scene_name).strip(), index + 1),
            "knowledge_provenance_requirement": _build_knowledge_provenance_requirement(str(scene_name).strip(), index + 1),
            "split_evidence_timeline_requirement": _build_split_evidence_timeline_requirement(str(scene_name).strip(), index + 1),
            "ending_image_hook_requirement": _build_ending_image_hook_requirement(str(scene_name).strip(), index + 1),
            "orphan_clue_payoff_requirement": _build_orphan_clue_payoff_requirement(str(scene_name).strip(), index + 1),
            "in_character_enforcement_requirement": _build_in_character_enforcement_requirement(str(scene_name).strip(), index + 1),
            "hook_escalation_requirement": _build_hook_escalation_requirement(str(scene_name).strip(), index + 1),
            "hook_delta_requirement": _build_hook_delta_requirement(str(scene_name).strip(), index + 1),
            "witness_silence_motivation_requirement": _build_witness_silence_motivation_requirement(str(scene_name).strip(), index + 1),
            "claim_evidence_ceiling_requirement": _build_claim_evidence_ceiling_requirement(str(scene_name).strip(), index + 1),
            "unique_clue_signature_requirement": _build_unique_clue_signature_requirement(str(scene_name).strip(), index + 1),
            "single_source_evidence_chain_requirement": _build_single_source_evidence_chain_requirement(str(scene_name).strip(), index + 1),
            "evidence_observation_anchor_requirement": _build_evidence_observation_anchor_requirement(str(scene_name).strip(), index + 1),
            "search_scope_requirement": _build_search_scope_requirement(str(scene_name).strip(), index + 1),
            "route_trigger_requirement": _build_route_trigger_requirement(str(scene_name).strip(), index + 1),
            "repeat_inspection_trigger_requirement": _build_repeat_inspection_trigger_requirement(str(scene_name).strip(), index + 1),
            "anomaly_skip_reason_requirement": _build_anomaly_skip_reason_requirement(str(scene_name).strip(), index + 1),
            "custody_transfer_bridge_requirement": _build_custody_transfer_bridge_requirement(str(scene_name).strip(), index + 1),
            "prop_custody_chain_requirement": _build_prop_custody_chain_requirement(str(scene_name).strip(), index + 1),
            "future_knowledge_guardrail": _build_future_knowledge_guardrail(str(scene_name).strip(), index + 1),
            "core_prop_count_stability_requirement": _build_core_prop_count_stability_requirement(str(scene_name).strip(), index + 1),
            "restrained_access_sequence_requirement": _build_restrained_access_sequence_requirement(str(scene_name).strip(), index + 1),
            "helper_motive_seed_requirement": _build_helper_motive_seed_requirement(str(scene_name).strip(), index + 1),
            "inference_disambiguation_requirement": _build_inference_disambiguation_requirement(str(scene_name).strip(), index + 1),
            "accusation_evidence_threshold_requirement": _build_accusation_evidence_threshold_requirement(str(scene_name).strip(), index + 1),
            "detainer_intent_anchor_requirement": _build_detainer_intent_anchor_requirement(str(scene_name).strip(), index + 1),
            "next_action_objective_requirement": _build_next_action_objective_requirement(str(scene_name).strip(), index + 1),
            "action_status_precision_requirement": _build_action_status_precision_requirement(str(scene_name).strip(), index + 1),
            "escape_hardware_geometry_requirement": _build_escape_hardware_geometry_requirement(str(scene_name).strip(), index + 1),
            "tool_path_staging_requirement": _build_tool_path_staging_requirement(str(scene_name).strip(), index + 1),
            "flashback_pressure_continuity_requirement": _build_flashback_pressure_continuity_requirement(str(scene_name).strip(), index + 1),
            "expository_dialogue_compression_requirement": _build_expository_dialogue_compression_requirement(str(scene_name).strip(), index + 1),
            "subjective_state_externalization_requirement": _build_subjective_state_externalization_requirement(str(scene_name).strip(), index + 1),
            "preloaded_tool_origin_requirement": _build_preloaded_tool_origin_requirement(str(scene_name).strip(), index + 1),
            "offscreen_incident_anchor_requirement": _build_offscreen_incident_anchor_requirement(str(scene_name).strip(), index + 1),
            "environment_coherence_requirement": _build_environment_coherence_requirement(str(scene_name).strip(), index + 1),
            "prop_restaging_requirement": _build_prop_restaging_requirement(str(scene_name).strip(), index + 1),
            "hook_image_dominance_requirement": _build_hook_image_dominance_requirement(str(scene_name).strip(), index + 1),
            "hook_question_specificity_requirement": _build_hook_question_specificity_requirement(str(scene_name).strip(), index + 1),
            "identity_hint_calibration_requirement": _build_identity_hint_calibration_requirement(str(scene_name).strip(), index + 1),
            "revelation_density_guardrail": _build_scene_revelation_density_guardrail(index + 1),
            "time_progression_hint": _build_time_progression_hint(str(scene_name).strip(), index + 1),
        }
        for index, scene_name in enumerate(scenes)
        if str(scene_name).strip()
    ]
    clue_rows, evidence_rows, key_prop_rows = _extract_scene_fact_rows(scenes)
    foundation["clue_table"] = clue_rows
    foundation["evidence_chain_table"] = evidence_rows
    foundation["key_prop_table"] = key_prop_rows
    foundation["prop_timeline_cards"] = [
        {
            "scene_index": index + 1,
            "scene_name": str(scene_name).strip(),
            "scene_open_state": _build_prop_scene_open_state(str(scene_name).strip(), index + 1),
            "scene_close_target": _build_prop_scene_close_target(
                str(scene_name).strip(),
                index + 1,
                scenes[index + 1] if index + 1 < len(scenes) else None,
            ),
            "required_transfer_beats": _build_prop_required_transfer_beats(
                str(scene_name).strip(),
                index + 1,
                scenes[index + 1] if index + 1 < len(scenes) else None,
            ),
            "prop_tracking_requirement": _build_prop_timeline_requirement(str(scene_name).strip(), index + 1),
            "prop_source_chain_requirement": _build_prop_source_chain_requirement(str(scene_name).strip(), index + 1),
            "same_scene_prop_handoff_requirement": _build_same_scene_prop_handoff_requirement(str(scene_name).strip(), index + 1),
            "prop_state_reuse_requirement": _build_prop_state_reuse_requirement(str(scene_name).strip(), index + 1),
            "prop_repeat_take_requirement": _build_prop_repeat_take_requirement(str(scene_name).strip(), index + 1),
            "discarded_prop_recovery_requirement": _build_discarded_prop_recovery_requirement(str(scene_name).strip(), index + 1),
            "evidence_consistency_requirement": _build_evidence_consistency_requirement(str(scene_name).strip(), index + 1),
            "prop_naming_consistency_requirement": _build_prop_naming_consistency_requirement(str(scene_name).strip(), index + 1),
            "micro_fact_consistency_requirement": _build_micro_fact_consistency_requirement(str(scene_name).strip(), index + 1),
            "high_value_props": [],
        }
        for index, scene_name in enumerate(scenes)
        if str(scene_name).strip()
    ]
    foundation["evidence_consistency_rules"] = [
        {
            "rule": "A clue cannot be declared one thing in one beat and treated as a different thing later unless the earlier claim is explicitly framed as deception or uncertainty.",
            "applies_to": "all_high_value_props",
        },
        {
            "rule": "Once a high-value clue or prop is named, keep the same core identity label across scenes unless the script explicitly reframes it as a mistaken guess, bluff, or later correction.",
            "applies_to": "all_high_value_props",
        },
        {
            "rule": "If a character is bluffing or misleading others, mark it with a visible cue, delayed reveal, or later correction in action.",
            "applies_to": "all_major_reveals",
        },
        {
            "rule": "High-value props that recur across scenes must keep one stable working name and one stable physical layout description so they can be reused as assets downstream.",
            "applies_to": "all_high_value_props",
        },
        {
            "rule": "Dialogue lines should keep one stable parseable format such as `角色：台词`, with action and tone carried by adjacent action lines instead of mixed into the quote line.",
            "applies_to": "all_dialogue_blocks",
        },
    ]

    foundation["hook_table"] = [
        {
            "hook_type": "opening",
            "content": foundation["episode_goal_card"]["opening_hook"],
            "target_effect": "attention_grab",
        },
        {
            "hook_type": "midpoint",
            "content": foundation["episode_goal_card"]["midpoint_escalation"],
            "target_effect": "pressure_escalation",
        },
        {
            "hook_type": "ending",
            "content": foundation["episode_goal_card"]["ending_hook"],
            "target_effect": "next_episode_pull",
        },
    ]
    foundation["story_fact_sheet"] = _build_story_fact_sheet(foundation, scenes)
    foundation["investigation_trace_rules"] = [
        {
            "rule": "Every major deduction needs an on-screen source or prior action trail.",
            "applies_to": "all_scenes",
        },
        {
            "rule": "If a later reveal depends on a tiny physical seed such as a scratch, pressure dent, wax nick, thread color, or missing corner, show that seed detail in the active scene image instead of only in summary notes.",
            "applies_to": "all_micro_seed_clues",
        },
        {
            "rule": "If a clue match escalates into same-source certainty, show at least two confirming visual dimensions instead of relying on one shared color or one shared reaction.",
            "applies_to": "all_same_source_evidence_claims",
        },
        {
            "rule": "If the same evidence family appears across multiple locations or surfaces, show one readable carry, drop, retrieval, or comparison chain, or explicitly mark later traces as separate related instances.",
            "applies_to": "all_multi_location_evidence_families",
        },
        {
            "rule": "Every flashback or remembered image must identify whose memory or reconstruction it is, and why the current viewpoint can access it.",
            "applies_to": "all_flashback_beats",
        },
        {
            "rule": "Risky covert actions such as infiltration, concealment, delivery, forgery, or evidence retrieval must carry an explicit on-screen motive anchor.",
            "applies_to": "all_high_cost_actions",
        },
        {
            "rule": "If a character suddenly searches a precise hiding place, show the visible trigger that directed them there before the search lands.",
            "applies_to": "all_targeted_search_beats",
        },
        {
            "rule": "If a character notices an abnormal detail during a search or frisk but does not pursue it, stage the interruption, concealment motive, or deliberate withdrawal in the same beat.",
            "applies_to": "all_abnormal_detail_skip_beats",
        },
        {
            "rule": "If a character withholds information through a glance, pause, or avoided search area, attach a readable attitude anchor in the same beat so the audience can register stance without learning the full answer yet.",
            "applies_to": "all_suggestive_withholding_beats",
        },
        {
            "rule": "If a character uses a hidden method or decoding technique, show the source of that knowledge before or during the reveal.",
            "applies_to": "all_hidden_method_reveals",
        },
        {
            "rule": "If one clue or document appears in multiple timeline states, show the split, copy, tear, or retrieval chain explicitly.",
            "applies_to": "all_split_document_or_duplicate_evidence_beats",
        },
        {
            "rule": "If dialogue uses relative time markers, keep them aligned with the staged flashback and action chronology.",
            "applies_to": "all_relative_time_claims",
        },
        {
            "rule": "If a searched location yields a later surprise discovery, stage the gating reason for why the earlier search missed it.",
            "applies_to": "all_delayed_discoveries_in_previously_searched_spaces",
        },
        {
            "rule": "If a witness sees blood, a body trace, or a crime clue and stays silent, show the strategic or emotional reason on screen.",
            "applies_to": "all_witness_silence_beats",
        },
        {
            "rule": "If a flashback interrupts active danger, preserve the present-tense pressure with a sound carry, image echo, or immediate return trigger so suspense stays live across the cut.",
            "applies_to": "all_pressure_interrupting_flashbacks",
        },
        {
            "rule": "Keep body-action logic physically playable; restrained or injured characters cannot perform impossible motions without a shown release or workaround.",
            "applies_to": "all_body_constraint_beats",
        },
        {
            "rule": "If a plot-relevant sound cue appears, pair it with a visible source inside the frame whenever possible.",
            "applies_to": "all_plot_relevant_sound_cues",
        },
        {
            "rule": "If a suspense image or shadow motif repeats, the later beat must escalate with new information instead of replaying the same vague tease.",
            "applies_to": "all_repeated_hook_motifs",
        },
        {
            "rule": "If two clues are declared to match, overlap, or come from the same source, the match must be staged visually through edge, texture, layout, or damage comparison.",
            "applies_to": "all_visual_match_claims",
        },
        {
            "rule": "If a clue color can be misread as blood, rust, mud, wax, or dye, the screenplay must anchor the intended reading with a follow-up close-up or source cue.",
            "applies_to": "all_color_dependent_clues",
        },
        {
            "rule": "If a prop was discarded, dropped, or confiscated earlier, later reuse must show the recovery or hidden retrieval beat on screen.",
            "applies_to": "all_discarded_prop_recoveries",
        },
        {
            "rule": "Dialogue should not claim stronger certainty than the shown evidence supports; eyewitness certainty must be earned on screen.",
            "applies_to": "all_evidence_claims_in_dialogue",
        },
        {
            "rule": "If one character detains or accuses another for a concrete crime, place at least one visible accusation trigger in frame instead of relying on generalized suspicion alone.",
            "applies_to": "all_detention_or_accusation_beats",
        },
        {
            "rule": "Repair contradictions with the smallest consistent adjustment; avoid inventing new chronology facts unless the screenplay stages them explicitly.",
            "applies_to": "all_repair_level_changes",
        },
        {
            "rule": "Do not collapse multiple independent revelations into one uninterrupted speech when they can be staged across beats.",
            "applies_to": "all_scenes",
        },
    ]

    normalized_qa_issues = qa_issues if isinstance(qa_issues, list) else []
    _inject_qa_backpressure_into_foundation(foundation, normalized_qa_issues)
    return foundation


def build_script_skill_foundation_prompt_block(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
    script_content: str | None = None,
) -> str:
    foundation = build_script_skill_foundation(
        book_id=book_id,
        episode_outline=episode_outline,
        qa_issues=qa_issues,
        script_content=script_content,
    )
    return "## Script Skill Foundation\n" + json.dumps(foundation, ensure_ascii=False, indent=2)


def build_script_generation_brief(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
    script_content: str | None = None,
) -> dict[str, Any]:
    foundation = build_script_skill_foundation(
        book_id=book_id,
        episode_outline=episode_outline,
        qa_issues=qa_issues,
        script_content=script_content,
    )
    episode_goal = foundation.get("episode_goal_card", {})
    return {
        "episode_goal": {
            "episode": episode_goal.get("episode"),
            "title": str(episode_goal.get("title") or "").strip(),
            "core_conflict": str(episode_goal.get("core_conflict") or "").strip(),
            "opening_hook": str(episode_goal.get("opening_hook") or "").strip(),
            "midpoint_escalation": str(episode_goal.get("midpoint_escalation") or "").strip(),
            "ending_hook": str(episode_goal.get("ending_hook") or "").strip(),
        },
        "story_fact_sheet": foundation.get("story_fact_sheet", {}),
        "character_playbook": [
            {
                "name": str(item.get("name") or "").strip(),
                "visible_state": str(item.get("episode_visible_state") or "").strip(),
                "hidden_state": str(item.get("hidden_state") or "").strip(),
                "transition_trigger": str(item.get("state_transition_trigger") or "").strip(),
                "speech_anchor": str(item.get("speech_style_anchor") or "").strip(),
                "signature_speech_requirement": str(item.get("signature_speech_requirement") or "").strip(),
                "behavior_guardrails": list(item.get("behavior_guardrails") or []),
                "persona_layer_guardrail": str(item.get("persona_layer_guardrail") or "").strip(),
            }
            for item in foundation.get("character_state_cards", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
        "scene_compilation_cards": [
            {
                "scene_index": item.get("scene_index"),
                "scene_name": str(item.get("scene_name") or "").strip(),
                "scene_purpose": str(item.get("scene_purpose") or "").strip(),
                "scene_conflict": str(item.get("scene_conflict") or "").strip(),
                "scene_information_delta": str(item.get("scene_information_delta") or "").strip(),
                "scene_emotion_delta": str(item.get("scene_emotion_delta") or "").strip(),
                "scene_exit_hook": str(item.get("scene_exit_hook") or "").strip(),
                "structural_goals": {
                    "scene_driver": str(item.get("scene_driver_requirement") or "").strip(),
                    "visual_anchor": str(item.get("scene_visual_anchor_goal") or "").strip(),
                    "new_evidence": str(item.get("scene_new_evidence_goal") or "").strip(),
                    "reused_clue": str(item.get("scene_reused_clue_goal") or "").strip(),
                    "exit_delta": str(item.get("scene_exit_delta_goal") or "").strip(),
                },
                "requirements": {
                    "transition": str(item.get("transition_requirement") or "").strip(),
                    "custody_destination_consistency": str(item.get("custody_destination_consistency_requirement") or "").strip(),
                    "dialogue_evidence_order": str(item.get("dialogue_evidence_order_requirement") or "").strip(),
                    "hidden_inscription_provenance": str(item.get("hidden_inscription_provenance_requirement") or "").strip(),
                    "prior_discovery_delta": str(item.get("prior_discovery_delta_requirement") or "").strip(),
                    "in_character_enforcement": str(item.get("in_character_enforcement_requirement") or "").strip(),
                    "hook_delta": str(item.get("hook_delta_requirement") or "").strip(),
                    "unique_clue_signature": str(item.get("unique_clue_signature_requirement") or "").strip(),
                    "repeat_inspection_trigger": str(item.get("repeat_inspection_trigger_requirement") or "").strip(),
                    "escape_hardware_geometry": str(item.get("escape_hardware_geometry_requirement") or "").strip(),
                    "flashback_pressure_continuity": str(item.get("flashback_pressure_continuity_requirement") or "").strip(),
                    "subjective_state_externalization": str(item.get("subjective_state_externalization_requirement") or "").strip(),
                },
            }
            for item in foundation.get("scene_goal_cards", [])
            if isinstance(item, dict) and str(item.get("scene_name") or "").strip()
        ],
        "scene_execution_cards": _build_scene_execution_cards(foundation),
        "evidence_chain_brief": [
            {
                "scene_name": str(item.get("scene_name") or "").strip(),
                "key_clue": str(item.get("clue") or "").strip(),
                "evidence_role": str(item.get("story_function") or "").strip(),
            }
            for item in foundation.get("clue_table", [])
            if isinstance(item, dict)
        ],
        "prop_timeline_brief": [
            {
                "scene_name": str(item.get("scene_name") or "").strip(),
                "scene_open_state": str(item.get("scene_open_state") or "").strip(),
                "scene_close_target": str(item.get("scene_close_target") or "").strip(),
                "required_transfer_beats": list(item.get("required_transfer_beats") or []),
                "high_value_props": list(item.get("high_value_props") or []),
                "tracking_requirement": str(item.get("prop_tracking_requirement") or "").strip(),
                "source_chain_requirement": str(item.get("prop_source_chain_requirement") or "").strip(),
                "same_scene_handoff_requirement": str(item.get("same_scene_prop_handoff_requirement") or "").strip(),
                "state_reuse_requirement": str(item.get("prop_state_reuse_requirement") or "").strip(),
                "repeat_take_requirement": str(item.get("prop_repeat_take_requirement") or "").strip(),
                "discarded_recovery_requirement": str(item.get("discarded_prop_recovery_requirement") or "").strip(),
                "naming_consistency_requirement": str(item.get("prop_naming_consistency_requirement") or "").strip(),
            }
            for item in foundation.get("prop_timeline_cards", [])
            if isinstance(item, dict) and str(item.get("scene_name") or "").strip()
        ],
        "hook_delta_targets": [
            {
                "hook_type": str(item.get("hook_type") or "").strip(),
                "content": str(item.get("content") or "").strip(),
                "target_effect": str(item.get("target_effect") or "").strip(),
            }
            for item in foundation.get("hook_table", [])
            if isinstance(item, dict)
        ],
    }


def _build_story_fact_sheet(
    foundation: dict[str, Any],
    scenes: list[str],
) -> dict[str, Any]:
    episode_goal = foundation.get("episode_goal_card", {}) if isinstance(foundation.get("episode_goal_card"), dict) else {}
    character_cards = foundation.get("character_state_cards", []) if isinstance(foundation.get("character_state_cards"), list) else []
    prop_rows = foundation.get("key_prop_table", []) if isinstance(foundation.get("key_prop_table"), list) else []
    clue_rows = foundation.get("clue_table", []) if isinstance(foundation.get("clue_table"), list) else []
    hook_rows = foundation.get("hook_table", []) if isinstance(foundation.get("hook_table"), list) else []

    character_fact_sheet = [
        {
            "name": str(item.get("name") or "").strip(),
            "gender": str(item.get("gender") or "").strip(),
            "public_layer": str(item.get("episode_visible_state") or "").strip(),
            "hidden_layer": str(item.get("hidden_state") or "").strip(),
            "transition_trigger": str(item.get("state_transition_trigger") or "").strip(),
            "public_mask_rule": str(item.get("persona_layer_guardrail") or "").strip(),
        }
        for item in character_cards
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]

    prop_fact_sheet = [
        {
            "prop_name": str(item.get("prop") or "").strip() or f"scene-{index + 1}-core-prop",
            "first_scene": str(item.get("scene_name") or "").strip(),
            "story_function": str(item.get("story_function") or "").strip(),
            "ownership_rule": "must stay on one coherent custody chain until the next explicit transfer",
            "uniqueness_rule": "do not duplicate this core prop without an earlier visible source, swap beat, or stash setup",
        }
        for index, item in enumerate(prop_rows)
        if isinstance(item, dict)
    ]

    evidence_fact_sheet = [
        {
            "evidence_name": str(item.get("clue") or "").strip() or f"scene-{index + 1}-evidence",
            "entry_scene": str(item.get("scene_name") or "").strip(),
            "story_function": str(item.get("story_function") or "").strip(),
            "observation_rule": "must be seen, handled, or compared on screen before dialogue claims certainty",
        }
        for index, item in enumerate(clue_rows)
        if isinstance(item, dict)
    ]

    helper_motive_sheet = [
        {
            "scene_name": str(scene_name).strip(),
            "requirement": "if a secondary character conceals evidence, softens a search, or quietly helps, plant one readable motive on screen before or during that beat",
        }
        for scene_name in scenes
        if str(scene_name).strip()
    ]

    spatial_mechanics_sheet = [
        {
            "scene_name": str(scene_name).strip(),
            "mechanics_rule": "if a latch, lock, compartment, stash, or restraint is plot-relevant, declare the reachable path, contact target, pull direction, and resulting movement in camera-readable steps",
        }
        for scene_name in scenes
        if str(scene_name).strip()
    ]

    hook_delta_sheet = [
        {
            "hook_type": str(item.get("hook_type") or "").strip(),
            "content": str(item.get("content") or "").strip(),
            "delta_rule": "must add one fresh state change, evidence direction, danger escalation, or unresolved concrete question",
        }
        for item in hook_rows
        if isinstance(item, dict)
    ]

    return {
        "episode_objective": str(episode_goal.get("core_conflict") or "").strip(),
        "character_fact_sheet": character_fact_sheet,
        "prop_fact_sheet": prop_fact_sheet,
        "evidence_fact_sheet": evidence_fact_sheet,
        "helper_motive_sheet": helper_motive_sheet,
        "spatial_mechanics_sheet": spatial_mechanics_sheet,
        "hook_delta_sheet": hook_delta_sheet,
    }


def _build_scene_execution_cards(foundation: dict[str, Any]) -> list[dict[str, Any]]:
    scene_cards = foundation.get("scene_goal_cards", []) if isinstance(foundation.get("scene_goal_cards"), list) else []
    character_cards = foundation.get("character_state_cards", []) if isinstance(foundation.get("character_state_cards"), list) else []
    prop_cards = foundation.get("prop_timeline_cards", []) if isinstance(foundation.get("prop_timeline_cards"), list) else []

    # 构建角色基础状态列表（所有场景共享）
    base_character_states = [
        CharacterState(
            name=str(item.get("name") or "").strip(),
            gender=str(item.get("gender") or "").strip(),
            position="未指定",
            emotional_state=str(item.get("episode_visible_state") or "").strip(),
            props_held=[],
            behavior_guardrails=list(item.get("behavior_guardrails") or []),
        )
        for item in character_cards
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]

    result: list[dict[str, Any]] = []
    for index, item in enumerate(scene_cards):
        if not isinstance(item, dict):
            continue
        scene_name = str(item.get("scene_name") or "").strip()
        if not scene_name:
            continue
        prop_card = prop_cards[index] if index < len(prop_cards) and isinstance(prop_cards[index], dict) else {}

        # 构建结构化 opening_state
        opening_state = SceneState(
            characters=[CharacterState(
                name=c.name,
                gender=c.gender,
                position=c.position,
                emotional_state=c.emotional_state,
                props_held=list(c.props_held),
                behavior_guardrails=list(c.behavior_guardrails),
            ) for c in base_character_states],
            props=[
                PropState(
                    name=str(prop_card.get("scene_name") or scene_name or "").strip(),
                    owner="",
                    location=str(prop_card.get("scene_open_state") or "").strip(),
                    physical_state="",
                )
            ] if prop_card.get("scene_open_state") else [],
            environmental_state="",
        )

        # closing_state 初始为空（场景生成后由 LLM 提取填充）
        closing_state = SceneState()

        result.append(
            {
                "scene_index": item.get("scene_index"),
                "scene_name": scene_name,
                "opening_state": opening_state.to_dict(),
                "scene_objective": str(item.get("scene_purpose") or "").strip() or str(item.get("scene_driver_requirement") or "").strip(),
                "scene_conflict": str(item.get("scene_conflict") or "").strip() or str(item.get("scene_visual_anchor_goal") or "").strip(),
                "required_visual_proofs": [
                    str(item.get("scene_new_evidence_goal") or "").strip(),
                    str(item.get("dialogue_evidence_order_requirement") or "").strip(),
                    str(item.get("visual_evidence_requirement") or "").strip(),
                ],
                "public_mask_beats": [
                    "keep the visible persona readable in ordinary interaction before the hidden layer takes over"
                ],
                "hidden_layer_leaks": [
                    str(character.get("hidden_layer_seed_requirement") or "").strip()
                    for character in character_cards
                    if isinstance(character, dict) and str(character.get("hidden_layer_seed_requirement") or "").strip()
                ],
                "closing_state": closing_state.to_dict(),
                "handoff_to_next_scene": str(item.get("transition_requirement") or "").strip(),
            }
        )
    return result


def build_script_generation_brief_prompt_block(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
    script_content: str | None = None,
) -> str:
    payload = build_script_generation_brief(
        book_id=book_id,
        episode_outline=episode_outline,
        qa_issues=qa_issues,
        script_content=script_content,
    )
    return "## Script Generation Brief\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _build_execution_plan_structured_fields(
    foundation: dict[str, Any] | None,
) -> dict[str, Any]:
    """从 foundation 中提取结构化字段，供 execution plan 消费。"""
    if not foundation or not isinstance(foundation, dict):
        return {
            "has_story_fact_sheet": False,
            "has_scene_execution_cards": False,
            "story_fact_sheet_summary": {},
            "scene_execution_cards_summary": [],
        }

    fact_sheet = foundation.get("story_fact_sheet") or {}
    exec_cards = foundation.get("scene_execution_cards") or []

    # 摘要 fact sheet 关键指标
    fact_summary = {
        "episode_objective": str(fact_sheet.get("episode_objective") or "").strip(),
        "character_count": len(fact_sheet.get("character_fact_sheet") or []),
        "prop_count": len(fact_sheet.get("prop_fact_sheet") or []),
        "evidence_count": len(fact_sheet.get("evidence_fact_sheet") or []),
        "hook_count": len(fact_sheet.get("hook_delta_sheet") or []),
    }

    # 摘要 execution cards 关键指标
    cards_summary = []
    for card in (exec_cards if isinstance(exec_cards, list) else []):
        if not isinstance(card, dict):
            continue
        cards_summary.append({
            "scene_index": card.get("scene_index"),
            "scene_name": str(card.get("scene_name") or "").strip(),
            "objective": str(card.get("scene_objective") or "").strip()[:100],
            "conflict": str(card.get("scene_conflict") or "").strip()[:100],
            "required_proof_count": len(card.get("required_visual_proofs") or []),
        })

    return {
        "has_story_fact_sheet": bool(fact_sheet),
        "has_scene_execution_cards": bool(exec_cards),
        "story_fact_sheet_summary": fact_summary,
        "scene_execution_cards_summary": cards_summary,
    }


def build_script_skill_execution_plan(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
    foundation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = build_project_production_skill_runtime(book_id)
    summary = runtime.get("runtime_summary", {}) if isinstance(runtime.get("runtime_summary"), dict) else {}
    normalized_qa_issues = qa_issues if isinstance(qa_issues, list) else []
    issue_families = [classify_script_qa_rule_family(item) for item in normalized_qa_issues if isinstance(item, dict)]
    family_counts: dict[str, int] = {}
    for family in issue_families:
        family_counts[family] = family_counts.get(family, 0) + 1
    layer_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    for issue in normalized_qa_issues:
        if not isinstance(issue, dict):
            continue
        layer = classify_script_qa_structure_layer(issue)
        stage = classify_script_qa_repair_stage(issue)
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    prioritized_families = sorted(
        family_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    repair_priorities = [
        {
            "rule_family": family,
            "issue_count": count,
            "repair_goal": build_script_rule_family_repair_goal(family),
        }
        for family, count in prioritized_families
    ]

    episode_title = ""
    if isinstance(episode_outline, dict):
        episode_title = str(episode_outline.get("title") or "").strip()

    prioritized_layers = sorted(layer_counts.items(), key=lambda item: (-item[1], item[0]))
    prioritized_stages = sorted(stage_counts.items(), key=lambda item: (-item[1], item[0]))

    return {
        "episode_title": episode_title,
        "track": str(summary.get("track") or "").strip(),
        "platform": str(summary.get("platform") or "").strip(),
        "enforcement": str(summary.get("enforcement") or "").strip(),
        "compiler_stages": [
            {
                "stage": "fact_generation",
                "goal": "先生成 Story Fact Sheet，锁定角色公开面/隐藏面、物证链、帮助动机、空间机关与钩子增量。",
            },
            {
                "stage": "scene_execution",
                "goal": "按场景生成 Scene Execution Cards，锁定每场开场状态、必需视觉证明、结束状态与承接条件。",
            },
            {
                "stage": "screenplay_compile",
                "goal": "基于事实层与场景执行层编译最终剧本，不再直接自由写整集。",
            },
            {
                "stage": "structure_qa",
                "goal": "先校验事实层、场景执行层与编译结果是否一致，再进入结果层 QA。",
            },
            {
                "stage": "platform_track_alignment",
                "goal": "先对齐平台节奏与赛道机制，避免写成泛短剧文风。",
            },
            {
                "stage": "character_state_alignment",
                "goal": "统一基础人设、可见状态、隐藏状态与转折触发器。",
            },
            {
                "stage": "scene_purpose_compilation",
                "goal": "为每一个场次写清目的、冲突、信息增量与情绪增量。",
            },
            {
                "stage": "clue_evidence_compilation",
                "goal": "把线索、证据、关键道具编排成可追溯因果链。",
            },
            {
                "stage": "hook_compilation",
                "goal": "确保开场钩子、中段升级和结尾钩子指向下一冲突。",
            },
            {
                "stage": "qa_backpressure_resolution",
                "goal": "优先吸收上一轮 QA 失败点，避免重复生成旧问题。",
            },
        ],
        "structure_focus": {
            "layer_counts": layer_counts,
            "stage_counts": stage_counts,
            "dominant_layer": prioritized_layers[0][0] if prioritized_layers else "",
            "dominant_stage": prioritized_stages[0][0] if prioritized_stages else "",
        },
        "repair_priorities": repair_priorities,
        "stage_repair_priorities": [
            {"repair_stage": stage, "issue_count": count}
            for stage, count in prioritized_stages
        ],
        "validation_checks": runtime.get("qa_checks", []) if isinstance(runtime.get("qa_checks"), list) else [],
        "structured_fields": _build_execution_plan_structured_fields(foundation),
    }


def _scene_index_from_section_label(label: str) -> int | None:
    normalized = str(label or "").strip()
    if not normalized:
        return None
    digit_match = re.search(r"(?:场景|scene)\s*([0-9]+)", normalized, flags=re.IGNORECASE)
    if digit_match:
        try:
            value = int(digit_match.group(1))
        except ValueError:
            value = 0
        return value if value > 0 else None

    cn_match = re.search(r"场景\s*([一二三四五六七八九十]+)", normalized)
    if not cn_match:
        return None
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    numerals = cn_match.group(1)
    if numerals == "十":
        return 10
    if numerals.startswith("十") and len(numerals) == 2:
        return 10 + mapping.get(numerals[1], 0)
    if numerals.endswith("十") and len(numerals) == 2:
        return mapping.get(numerals[0], 0) * 10
    total = 0
    for char in numerals:
        total = total * 10 + mapping.get(char, 0)
    return total or None


def _resolve_issue_scene_targets(issue: dict[str, Any], scene_names: list[str]) -> list[str]:
    if not isinstance(issue, dict):
        return []
    location = issue.get("location") if isinstance(issue.get("location"), dict) else {}
    section = str(location.get("script_section") or "").strip()
    title = str(issue.get("title") or issue.get("issue_title") or "").strip()
    description = str(issue.get("description") or "").strip()
    haystack = " ".join(part for part in [section, title, description] if part).lower()
    targets: list[str] = []
    for scene_name in scene_names:
        candidate = str(scene_name or "").strip()
        if candidate and candidate.lower() in haystack and candidate not in targets:
            targets.append(candidate)
    if targets:
        return targets
    scene_index = _scene_index_from_section_label(section)
    if scene_index and 1 <= scene_index <= len(scene_names):
        return [scene_names[scene_index - 1]]
    return []


def _build_stage_repair_agenda(
    *,
    repair_briefs: list[dict[str, Any]],
    issue_rewrite_directives: list[dict[str, Any]],
    stage_repair_priorities: list[dict[str, Any]],
    scene_names: list[str],
) -> list[dict[str, Any]]:
    directives_by_stage: dict[str, list[dict[str, Any]]] = {}
    for directive in issue_rewrite_directives:
        if not isinstance(directive, dict):
            continue
        stage = str(directive.get("repair_stage") or "").strip()
        if not stage:
            continue
        directives_by_stage.setdefault(stage, []).append(directive)

    briefs_by_stage: dict[str, list[dict[str, Any]]] = {}
    for brief in repair_briefs:
        if not isinstance(brief, dict):
            continue
        for stage in brief.get("repair_stages") or []:
            stage_name = str(stage or "").strip()
            if stage_name:
                briefs_by_stage.setdefault(stage_name, []).append(brief)

    agenda: list[dict[str, Any]] = []
    for item in stage_repair_priorities or []:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("repair_stage") or "").strip()
        if not stage:
            continue
        directives = directives_by_stage.get(stage, [])
        briefs = briefs_by_stage.get(stage, [])
        scene_targets: list[str] = []
        for directive in directives:
            for scene_name in _resolve_issue_scene_targets(directive, scene_names):
                if scene_name not in scene_targets:
                    scene_targets.append(scene_name)
        agenda.append(
            {
                "repair_stage": stage,
                "issue_count": int(item.get("issue_count") or len(directives) or 0),
                "ordered_actions": list(SCRIPT_REPAIR_STAGE_ACTIONS.get(stage, [])),
                "rule_families": [
                    str(brief.get("rule_family") or "").strip()
                    for brief in briefs
                    if str(brief.get("rule_family") or "").strip()
                ],
                "issue_titles": [
                    str(directive.get("issue_title") or "").strip()
                    for directive in directives
                    if str(directive.get("issue_title") or "").strip()
                ],
                "scene_targets": scene_targets,
            }
        )
    return agenda


def _build_scene_repair_agenda(
    *,
    scene_execution_cards: list[dict[str, Any]],
    scene_transition_requirements: list[dict[str, Any]],
    issue_rewrite_directives: list[dict[str, Any]],
    stage_repair_agenda: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    transition_by_scene = {
        str(item.get("scene_name") or "").strip(): item
        for item in scene_transition_requirements
        if isinstance(item, dict) and str(item.get("scene_name") or "").strip()
    }
    scene_names = [
        str(item.get("scene_name") or "").strip()
        for item in scene_execution_cards
        if isinstance(item, dict) and str(item.get("scene_name") or "").strip()
    ]
    directives_by_scene: dict[str, list[dict[str, Any]]] = {}
    for directive in issue_rewrite_directives:
        if not isinstance(directive, dict):
            continue
        for scene_name in _resolve_issue_scene_targets(directive, scene_names):
            directives_by_scene.setdefault(scene_name, []).append(directive)

    agenda: list[dict[str, Any]] = []
    for card in scene_execution_cards or []:
        if not isinstance(card, dict):
            continue
        scene_name = str(card.get("scene_name") or "").strip()
        if not scene_name:
            continue
        directives = directives_by_scene.get(scene_name, [])
        transition = transition_by_scene.get(scene_name, {})
        stage_tasks: list[dict[str, Any]] = []
        for stage_item in stage_repair_agenda:
            if not isinstance(stage_item, dict):
                continue
            stage = str(stage_item.get("repair_stage") or "").strip()
            scene_stage_directives = [
                directive
                for directive in directives
                if str(directive.get("repair_stage") or "").strip() == stage
            ]
            if not scene_stage_directives:
                continue
            stage_tasks.append(
                {
                    "repair_stage": stage,
                    "issue_titles": [
                        str(directive.get("issue_title") or "").strip()
                        for directive in scene_stage_directives
                        if str(directive.get("issue_title") or "").strip()
                    ],
                    "must_land": [
                        str(directive.get("directive") or "").strip()
                        for directive in scene_stage_directives
                        if str(directive.get("directive") or "").strip()
                    ],
                }
            )
        agenda.append(
            {
                "scene_name": scene_name,
                "opening_state": str(card.get("opening_state") or "").strip(),
                "scene_objective": str(card.get("scene_objective") or "").strip(),
                "scene_conflict": str(card.get("scene_conflict") or "").strip(),
                "required_visual_proofs": list(card.get("required_visual_proofs") or []),
                "closing_state": str(card.get("closing_state") or "").strip(),
                "handoff_to_next_scene": str(card.get("handoff_to_next_scene") or "").strip(),
                "transition_requirement": str(transition.get("transition_requirement") or "").strip(),
                "visual_evidence_requirement": str(transition.get("visual_evidence_requirement") or "").strip(),
                "prop_custody_chain_requirement": str(transition.get("prop_custody_chain_requirement") or "").strip(),
                "action_feasibility_requirement": str(transition.get("action_feasibility_requirement") or "").strip(),
                "hook_delta_requirement": str(transition.get("hook_delta_requirement") or "").strip(),
                "stage_tasks": stage_tasks,
            }
        )
    return agenda


def build_script_skill_execution_plan_prompt_block(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
) -> str:
    payload = build_script_skill_execution_plan(
        book_id=book_id,
        episode_outline=episode_outline,
        qa_issues=qa_issues,
    )
    return "## Script Skill Execution Plan\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def build_script_skill_repair_packet(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
    script_content: str | None = None,
) -> dict[str, Any]:
    foundation = build_script_skill_foundation(
        book_id=book_id,
        episode_outline=episode_outline,
        qa_issues=qa_issues,
        script_content=script_content,
    )
    execution_plan = build_script_skill_execution_plan(
        book_id=book_id,
        episode_outline=episode_outline,
        qa_issues=qa_issues,
    )
    normalized_qa_issues = qa_issues if isinstance(qa_issues, list) else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for issue in normalized_qa_issues:
        if not isinstance(issue, dict):
            continue
        family = classify_script_qa_rule_family(issue)
        grouped.setdefault(family, []).append(issue)

    repair_briefs: list[dict[str, Any]] = []
    for priority in execution_plan.get("repair_priorities", []):
        family = str(priority.get("rule_family") or "").strip()
        items = grouped.get(family, [])
        stage_focus = {
            "character_consistency": ["fact_generation"],
            "character_state_transition": ["fact_generation", "scene_execution"],
            "clue_payoff_integrity": ["scene_execution", "screenplay_compile"],
            "prop_evidence_continuity": ["fact_generation", "scene_execution"],
            "episode_hook_strength": ["screenplay_compile"],
            "scene_effectiveness": ["scene_execution"],
            "output_completeness": ["screenplay_compile"],
            "generic_skill_gap": ["structure_qa", "scene_execution"],
        }.get(family, ["structure_qa"])
        repair_briefs.append(
            {
                "rule_family": family,
                "repair_goal": build_script_rule_family_repair_goal(family),
                "issue_count": len(items),
                "structure_layers": sorted(
                    {
                        classify_script_qa_structure_layer(item)
                        for item in items
                        if isinstance(item, dict)
                    }
                ),
                "repair_stages": sorted(
                    {
                        classify_script_qa_repair_stage(item)
                        for item in items
                        if isinstance(item, dict)
                    }
                ),
                "issue_titles": [
                    str(item.get("title") or item.get("description") or "").strip()
                    for item in items
                    if str(item.get("title") or item.get("description") or "").strip()
                ],
                "target_sections": [
                    str((item.get("location") or {}).get("script_section") or "").strip()
                    for item in items
                    if isinstance(item.get("location"), dict)
                    and str((item.get("location") or {}).get("script_section") or "").strip()
                ],
                "compiler_stage_focus": stage_focus,
                "legacy_stage_focus": {
                    "character_consistency": ["character_state_alignment"],
                    "character_state_transition": ["character_state_alignment", "scene_purpose_compilation"],
                    "clue_payoff_integrity": ["clue_evidence_compilation", "hook_compilation"],
                    "prop_evidence_continuity": ["clue_evidence_compilation"],
                    "episode_hook_strength": ["hook_compilation"],
                    "scene_effectiveness": ["scene_purpose_compilation"],
                    "output_completeness": ["qa_backpressure_resolution"],
                    "generic_skill_gap": ["scene_purpose_compilation", "clue_evidence_compilation"],
                }.get(family, ["scene_purpose_compilation"]),
            }
        )

    scene_execution_cards = _build_scene_execution_cards(foundation)
    
    # Add structural validation
    structural_validation_block = build_structural_validation_block(
        foundation=foundation,
        scene_execution_cards=scene_execution_cards,
    )
    structural_validation_prompt = format_structural_validation_for_prompt(structural_validation_block)
    
    issue_rewrite_directives = [
        {
            "issue_title": str(item.get("title") or item.get("description") or "").strip(),
            "rule_family": classify_script_qa_rule_family(item),
            "structure_layer": classify_script_qa_structure_layer(item),
            "repair_stage": classify_script_qa_repair_stage(item),
            "directive": build_script_issue_rewrite_directive(item),
            "location": item.get("location") if isinstance(item.get("location"), dict) else {},
        }
        for item in normalized_qa_issues
        if isinstance(item, dict) and str(item.get("title") or item.get("description") or "").strip()
    ]
    scene_names = [
        str(item.get("scene_name") or "").strip()
        for item in foundation.get("scene_goal_cards", [])
        if isinstance(item, dict) and str(item.get("scene_name") or "").strip()
    ]
    scene_transition_requirements = [
        {
            "scene_name": str(item.get("scene_name") or "").strip(),
            "transition_requirement": str(item.get("transition_requirement") or "").strip(),
            "custody_destination_consistency_requirement": str(item.get("custody_destination_consistency_requirement") or "").strip(),
            "relative_time_anchor_requirement": str(item.get("relative_time_anchor_requirement") or "").strip(),
            "action_feasibility_requirement": str(item.get("action_feasibility_requirement") or "").strip(),
            "investigation_trace_requirement": str(item.get("investigation_trace_requirement") or "").strip(),
            "motivation_visibility_requirement": str(item.get("motivation_visibility_requirement") or "").strip(),
            "search_trigger_requirement": str(item.get("search_trigger_requirement") or "").strip(),
            "suggestive_glance_resolution_requirement": str(item.get("suggestive_glance_resolution_requirement") or "").strip(),
            "attitude_anchor_requirement": str(item.get("attitude_anchor_requirement") or "").strip(),
            "dialogue_evidence_order_requirement": str(item.get("dialogue_evidence_order_requirement") or "").strip(),
            "visual_evidence_requirement": str(item.get("visual_evidence_requirement") or "").strip(),
            "occluded_evidence_layer_requirement": str(item.get("occluded_evidence_layer_requirement") or "").strip(),
            "hidden_inscription_provenance_requirement": str(item.get("hidden_inscription_provenance_requirement") or "").strip(),
            "seed_clue_visibility_requirement": str(item.get("seed_clue_visibility_requirement") or "").strip(),
            "concealed_clue_focus_requirement": str(item.get("concealed_clue_focus_requirement") or "").strip(),
            "prior_discovery_delta_requirement": str(item.get("prior_discovery_delta_requirement") or "").strip(),
            "comparison_visualization_requirement": str(item.get("comparison_visualization_requirement") or "").strip(),
            "multi_signal_match_requirement": str(item.get("multi_signal_match_requirement") or "").strip(),
            "color_signal_clarity_requirement": str(item.get("color_signal_clarity_requirement") or "").strip(),
            "prop_asset_spec_requirement": str(item.get("prop_asset_spec_requirement") or "").strip(),
            "audio_visual_pairing_requirement": str(item.get("audio_visual_pairing_requirement") or "").strip(),
            "delayed_discovery_gate_requirement": str(item.get("delayed_discovery_gate_requirement") or "").strip(),
            "knowledge_provenance_requirement": str(item.get("knowledge_provenance_requirement") or "").strip(),
            "split_evidence_timeline_requirement": str(item.get("split_evidence_timeline_requirement") or "").strip(),
            "ending_image_hook_requirement": str(item.get("ending_image_hook_requirement") or "").strip(),
            "orphan_clue_payoff_requirement": str(item.get("orphan_clue_payoff_requirement") or "").strip(),
            "in_character_enforcement_requirement": str(item.get("in_character_enforcement_requirement") or "").strip(),
            "hook_escalation_requirement": str(item.get("hook_escalation_requirement") or "").strip(),
            "hook_delta_requirement": str(item.get("hook_delta_requirement") or "").strip(),
            "witness_silence_motivation_requirement": str(item.get("witness_silence_motivation_requirement") or "").strip(),
            "claim_evidence_ceiling_requirement": str(item.get("claim_evidence_ceiling_requirement") or "").strip(),
            "unique_clue_signature_requirement": str(item.get("unique_clue_signature_requirement") or "").strip(),
            "single_source_evidence_chain_requirement": str(item.get("single_source_evidence_chain_requirement") or "").strip(),
            "evidence_observation_anchor_requirement": str(item.get("evidence_observation_anchor_requirement") or "").strip(),
            "search_scope_requirement": str(item.get("search_scope_requirement") or "").strip(),
            "route_trigger_requirement": str(item.get("route_trigger_requirement") or "").strip(),
            "repeat_inspection_trigger_requirement": str(item.get("repeat_inspection_trigger_requirement") or "").strip(),
            "anomaly_skip_reason_requirement": str(item.get("anomaly_skip_reason_requirement") or "").strip(),
            "custody_transfer_bridge_requirement": str(item.get("custody_transfer_bridge_requirement") or "").strip(),
            "prop_custody_chain_requirement": str(item.get("prop_custody_chain_requirement") or "").strip(),
            "inference_disambiguation_requirement": str(item.get("inference_disambiguation_requirement") or "").strip(),
            "accusation_evidence_threshold_requirement": str(item.get("accusation_evidence_threshold_requirement") or "").strip(),
            "detainer_intent_anchor_requirement": str(item.get("detainer_intent_anchor_requirement") or "").strip(),
            "next_action_objective_requirement": str(item.get("next_action_objective_requirement") or "").strip(),
            "action_status_precision_requirement": str(item.get("action_status_precision_requirement") or "").strip(),
            "escape_hardware_geometry_requirement": str(item.get("escape_hardware_geometry_requirement") or "").strip(),
            "tool_path_staging_requirement": str(item.get("tool_path_staging_requirement") or "").strip(),
            "flashback_pressure_continuity_requirement": str(item.get("flashback_pressure_continuity_requirement") or "").strip(),
            "expository_dialogue_compression_requirement": str(item.get("expository_dialogue_compression_requirement") or "").strip(),
            "subjective_state_externalization_requirement": str(item.get("subjective_state_externalization_requirement") or "").strip(),
            "preloaded_tool_origin_requirement": str(item.get("preloaded_tool_origin_requirement") or "").strip(),
            "offscreen_incident_anchor_requirement": str(item.get("offscreen_incident_anchor_requirement") or "").strip(),
            "environment_coherence_requirement": str(item.get("environment_coherence_requirement") or "").strip(),
            "prop_restaging_requirement": str(item.get("prop_restaging_requirement") or "").strip(),
            "hook_image_dominance_requirement": str(item.get("hook_image_dominance_requirement") or "").strip(),
            "hook_question_specificity_requirement": str(item.get("hook_question_specificity_requirement") or "").strip(),
            "identity_hint_calibration_requirement": str(item.get("identity_hint_calibration_requirement") or "").strip(),
            "revelation_density_guardrail": str(item.get("revelation_density_guardrail") or "").strip(),
        }
        for item in foundation.get("scene_goal_cards", [])
        if isinstance(item, dict) and str(item.get("scene_name") or "").strip()
    ]
    stage_repair_agenda = _build_stage_repair_agenda(
        repair_briefs=repair_briefs,
        issue_rewrite_directives=issue_rewrite_directives,
        stage_repair_priorities=execution_plan.get("stage_repair_priorities", []),
        scene_names=scene_names,
    )
    scene_repair_agenda = _build_scene_repair_agenda(
        scene_execution_cards=scene_execution_cards,
        scene_transition_requirements=scene_transition_requirements,
        issue_rewrite_directives=issue_rewrite_directives,
        stage_repair_agenda=stage_repair_agenda,
    )

    return {
        "episode_goal_card": foundation.get("episode_goal_card", {}),
        "story_fact_sheet": foundation.get("story_fact_sheet", {}),
        "structure_focus": execution_plan.get("structure_focus", {}),
        "repair_priorities": execution_plan.get("repair_priorities", []),
        "stage_repair_priorities": execution_plan.get("stage_repair_priorities", []),
        "repair_briefs": repair_briefs,
        "issue_rewrite_directives": issue_rewrite_directives,
        "stage_repair_agenda": stage_repair_agenda,
        "scene_repair_agenda": scene_repair_agenda,
        "structural_validation": structural_validation_block.get("structural_validation", {}),
        "structural_repair_directives": structural_validation_block.get("repair_directives", []),
        "structural_validation_prompt": structural_validation_prompt,
        "scene_count": len(foundation.get("scene_goal_cards", [])),
        "character_count": len(foundation.get("character_state_cards", [])),
        "scene_execution_cards": scene_execution_cards,
        "character_state_brief": [
            {
                "name": str(item.get("name") or "").strip(),
                "visible_state": str(item.get("episode_visible_state") or "").strip(),
                "hidden_state": str(item.get("hidden_state") or "").strip(),
                "transition_trigger": str(item.get("state_transition_trigger") or "").strip(),
                "persona_layer_guardrail": str(item.get("persona_layer_guardrail") or "").strip(),
                "hidden_layer_seed_requirement": str(item.get("hidden_layer_seed_requirement") or "").strip(),
                "hidden_layer_reveal_trigger_requirement": str(item.get("hidden_layer_reveal_trigger_requirement") or "").strip(),
            }
            for item in foundation.get("character_state_cards", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
        "scene_names": scene_names,
        "qa_backpressure_titles": [
            str(item.get("title") or "").strip()
            for item in foundation.get("qa_backpressure", [])
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ],
        "scene_transition_requirements": scene_transition_requirements,
        "dialogue_guardrails": [
            {
                "character": str(item.get("name") or "").strip(),
                "speech_style_anchor": str(item.get("speech_style_anchor") or "").strip(),
                "signature_speech_requirement": str(item.get("signature_speech_requirement") or "").strip(),
                "behavior_guardrails": list(item.get("behavior_guardrails") or []),
                "omniscience_guardrail": str(item.get("omniscience_guardrail") or "").strip(),
                "flashback_provenance_guardrail": str(item.get("flashback_provenance_guardrail") or "").strip(),
                "identity_cover_guardrail": str(item.get("identity_cover_guardrail") or "").strip(),
                "asset_canon_reconciliation_guardrail": str(item.get("asset_canon_reconciliation_guardrail") or "").strip(),
                "persona_layer_guardrail": str(item.get("persona_layer_guardrail") or "").strip(),
                "dialogue_format_guardrail": str(item.get("dialogue_format_guardrail") or "").strip(),
            }
            for item in foundation.get("character_state_cards", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
        "prop_timeline_guardrails": [
            {
                "scene_name": str(item.get("scene_name") or "").strip(),
                "prop_tracking_requirement": str(item.get("prop_tracking_requirement") or "").strip(),
                "prop_source_chain_requirement": str(item.get("prop_source_chain_requirement") or "").strip(),
                "same_scene_prop_handoff_requirement": str(item.get("same_scene_prop_handoff_requirement") or "").strip(),
                "prop_state_reuse_requirement": str(item.get("prop_state_reuse_requirement") or "").strip(),
                "prop_repeat_take_requirement": str(item.get("prop_repeat_take_requirement") or "").strip(),
                "discarded_prop_recovery_requirement": str(item.get("discarded_prop_recovery_requirement") or "").strip(),
                "evidence_consistency_requirement": str(item.get("evidence_consistency_requirement") or "").strip(),
                "prop_naming_consistency_requirement": str(item.get("prop_naming_consistency_requirement") or "").strip(),
                "micro_fact_consistency_requirement": str(item.get("micro_fact_consistency_requirement") or "").strip(),
            }
            for item in foundation.get("prop_timeline_cards", [])
            if isinstance(item, dict) and str(item.get("scene_name") or "").strip()
        ],
        "investigation_trace_rules": list(foundation.get("investigation_trace_rules") or []),
        "evidence_consistency_rules": list(foundation.get("evidence_consistency_rules") or []),
    }


def build_script_skill_repair_packet_prompt_block(
    book_id: int,
    episode_outline: dict[str, Any] | None = None,
    qa_issues: list[dict[str, Any]] | None = None,
    script_content: str | None = None,
) -> str:
    payload = build_script_skill_repair_packet(
        book_id=book_id,
        episode_outline=episode_outline,
        qa_issues=qa_issues,
        script_content=script_content,
    )
    return "## Script Skill Repair Packet\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def extract_script_qa_issues_from_result(result_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = result_payload if isinstance(result_payload, dict) else {}
    issues = payload.get("issues")
    if isinstance(issues, list):
        return [item for item in issues if isinstance(item, dict)]
    errors = payload.get("errors")
    if isinstance(errors, list):
        normalized: list[dict[str, Any]] = []
        for item in errors:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "type": item.get("type") or "other",
                    "severity": item.get("severity") or "medium",
                    "title": item.get("title") or item.get("description") or "",
                    "description": item.get("description") or "",
                    "fix_mode": item.get("fix_mode") or "",
                }
            )
        return normalized
    return []


def load_latest_script_qa_issues(book_id: int, episode: int) -> list[dict[str, Any]]:
    from models import QAResult, Session

    with Session() as session:
        row = (
            session.query(QAResult)
            .filter(QAResult.book_id == book_id, QAResult.episode == episode)
            .order_by(QAResult.created_at.desc(), QAResult.id.desc())
            .first()
        )
        if not row or not row.result:
            return []
        payload = safe_json_loads(row.result, {})
        return extract_script_qa_issues_from_result(payload)
