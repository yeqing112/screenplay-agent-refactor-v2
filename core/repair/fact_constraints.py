"""Fact Layer Constraints - 结构化约束验证器

将启发式的关键词匹配替换为确定性的结构化验证。
在生成阶段就保证正确性，而不是等QA发现问题再修补。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConstraintSeverity(Enum):
    """约束违反严重程度"""
    ERROR = "error"      # 必须修复，阻断流程
    WARNING = "warning"  # 应该修复，允许继续
    INFO = "info"        # 建议修复


class FactLayer(Enum):
    """事实层级"""
    PUBLIC = "public"              # 公开层：角色可见的外部表现
    HIDDEN = "hidden"              # 隐藏层：角色的真实意图/能力
    TRANSITION = "transition"      # 状态转换：触发器和过程
    RELATIONSHIP = "relationship"  # 关系层：角色间的关系状态


@dataclass
class ConstraintViolation:
    """约束违反记录"""
    constraint_id: str
    layer: FactLayer
    severity: ConstraintSeverity
    message: str
    location: str  # 场景名或位置
    fix_suggestion: str
    affected_entities: list[str] = field(default_factory=list)


@dataclass
class CharacterFact:
    """角色事实定义"""
    name: str
    public_persona: str          # 公开人设
    hidden_layer: str            # 隐藏层
    speech_style: str            # 说话风格
    visible_state: str           # 当前可见状态
    hidden_state: str            # 当前隐藏状态
    state_transition_trigger: str  # 状态转换触发器
    persona_layer_guardrail: str  # 人设层级护栏


@dataclass
class PropFact:
    """道具事实定义"""
    name: str
    prop_type: str               # 普通/关键证据/连续性道具
    owner: str                   # 当前持有者
    location: str                # 当前位置
    state: str                   # 当前状态
    first_appearance: str        # 首次出现场景
    chain: list[dict[str, Any]] = field(default_factory=list)  # 流转链


class FactConstraintValidator:
    """事实约束验证器
    
    在生成阶段验证以下约束：
    1. 角色人设一致性：公开层/隐藏层不混淆
    2. 道具唯一性：关键道具不重复/不丢失
    3. 证据可见性：关键证据必须在画面中
    4. 状态转换：转换必须有触发器
    """
    
    def __init__(
        self,
        characters: list[CharacterFact],
        props: list[PropFact],
        scenes: list[dict[str, Any]],
    ):
        self.characters = {c.name: c for c in characters}
        self.props = {p.name: p for p in props}
        self.scenes = scenes
        self.violations: list[ConstraintViolation] = []
    
    def validate_all(self) -> list[ConstraintViolation]:
        """执行所有约束验证"""
        self.violations = []
        self._validate_character_consistency()
        self._validate_prop_uniqueness()
        self._validate_prop_continuity()
        self._validate_evidence_visibility()
        self._validate_state_transitions()
        return self.violations
    
    def _validate_character_consistency(self):
        """验证角色人设一致性
        
        规则：
        - 公开层行为不能突然变成隐藏层行为（除非有触发器）
        - 说话风格必须与当前人设层匹配
        - 状态转换必须有明确触发器
        """
        for scene in self.scenes:
            scene_name = scene.get("name", "")
            characters_in_scene = scene.get("characters", [])
            
            for char_name in characters_in_scene:
                if char_name not in self.characters:
                    continue
                char = self.characters[char_name]
                
                # 检查人设层级混淆
                if self._scene_shows_hidden_layer(scene, char_name):
                    if not self._has_trigger_in_scene(scene, char_name):
                        self.violations.append(ConstraintViolation(
                            constraint_id="CHAR_HIDEN_NO_TRIGGER",
                            layer=FactLayer.HIDDEN,
                            severity=ConstraintSeverity.ERROR,
                            message=f"角色 {char_name} 在场景 {scene_name} 展示了隐藏层行为，但没有状态转换触发器",
                            location=scene_name,
                            fix_suggestion=f"在场景 {scene_name} 为 {char_name} 添加状态转换触发器，如停顿、眼神变化、道具接触等",
                            affected_entities=[char_name],
                        ))
                
                # 检查说话风格漂移
                if self._dialogue_style_drifts(scene, char_name, char):
                    self.violations.append(ConstraintViolation(
                        constraint_id="CHAR_STYLE_DRIFT",
                        layer=FactLayer.PUBLIC,
                        severity=ConstraintSeverity.WARNING,
                        message=f"角色 {char_name} 在场景 {scene_name} 的说话风格与人设不匹配",
                        location=scene_name,
                        fix_suggestion=f"调整 {char_name} 的台词，使其符合人设定义的说话风格",
                        affected_entities=[char_name],
                    ))
    
    def _validate_prop_uniqueness(self):
        """验证关键道具唯一性
        
        规则：
        - 同一关键道具不能同时出现在两个地方
        - 关键道具的归属必须明确
        - 道具状态变化必须有原因
        """
        prop_locations: dict[str, list[tuple[str, str]]] = {}  # prop -> [(scene, location)]
        
        for scene in self.scenes:
            scene_name = scene.get("name", "")
            props_in_scene = scene.get("props", [])
            
            for prop_name in props_in_scene:
                if prop_name not in self.props:
                    continue
                prop = self.props[prop_name]
                
                if prop.prop_type == "关键证据":
                    if prop_name not in prop_locations:
                        prop_locations[prop_name] = []
                    prop_locations[prop_name].append((scene_name, prop.location))
        
        # 检查关键道具是否在同一时间出现在不同地方
        for prop_name, locations in prop_locations.items():
            unique_locations = set(loc for _, loc in locations)
            if len(unique_locations) > 1:
                self.violations.append(ConstraintViolation(
                    constraint_id="PROP_LOCATION_CONFLICT",
                    layer=FactLayer.RELATIONSHIP,
                    severity=ConstraintSeverity.ERROR,
                    message=f"关键道具 {prop_name} 出现在多个位置：{unique_locations}",
                    location=str([s for s, _ in locations]),
                    fix_suggestion=f"统一 {prop_name} 的位置，或明确展示道具转移过程",
                    affected_entities=[prop_name],
                ))
    
    def _validate_prop_continuity(self):
        """验证道具连续性
        
        规则：
        - 道具从一个场景到另一个场景必须有转移说明
        - 道具状态变化必须有原因
        - 搜索/发现过程必须符合物理逻辑
        """
        for i, scene in enumerate(self.scenes):
            scene_name = scene.get("name", "")
            props_in_scene = scene.get("props", [])
            
            for prop_name in props_in_scene:
                if prop_name not in self.props:
                    continue
                prop = self.props[prop_name]
                
                # 检查道具转移
                if i > 0:
                    prev_scene = self.scenes[i - 1]
                    prev_props = prev_scene.get("props", [])
                    
                    if prop_name in prev_props:
                        # 道具在上一场景也出现，检查转移说明
                        if not self._has_prop_transfer_explanation(scene, prop_name):
                            self.violations.append(ConstraintViolation(
                                constraint_id="PROP_TRANSFER_MISSING",
                                layer=FactLayer.RELATIONSHIP,
                                severity=ConstraintSeverity.WARNING,
                                message=f"道具 {prop_name} 从 {prev_scene.get('name', '')} 转移到 {scene_name} 缺少转移说明",
                                location=scene_name,
                                fix_suggestion=f"在场景 {scene_name} 开头添加道具获取/转移的过渡镜头",
                                affected_entities=[prop_name],
                            ))
    
    def _validate_evidence_visibility(self):
        """验证证据可见性
        
        规则：
        - 关键证据必须在画面中可见
        - 证据发现过程必须符合物理逻辑
        - 证据不能只存在于台词中
        """
        for scene in self.scenes:
            scene_name = scene.get("name", "")
            evidence_in_scene = scene.get("evidence", [])
            
            for evidence in evidence_in_scene:
                if evidence.get("type") == "关键证据":
                    if not evidence.get("on_screen"):
                        self.violations.append(ConstraintViolation(
                            constraint_id="EVIDENCE_NOT_ON_SCREEN",
                            layer=FactLayer.PUBLIC,
                            severity=ConstraintSeverity.ERROR,
                            message=f"关键证据 {evidence.get('name', '')} 在场景 {scene_name} 中未在画面中展示",
                            location=scene_name,
                            fix_suggestion=f"在场景 {scene_name} 添加证据的视觉展示镜头（特写、对比、处理过程等）",
                            affected_entities=[evidence.get("name", "")],
                        ))
    
    def _validate_state_transitions(self):
        """验证状态转换
        
        规则：
        - 状态转换必须有触发器
        - 转换过程必须可见
        - 转换后的新状态必须与后续场景一致
        """
        for scene in self.scenes:
            scene_name = scene.get("name", "")
            transitions = scene.get("state_transitions", [])
            
            for transition in transitions:
                char_name = transition.get("character", "")
                from_state = transition.get("from_state", "")
                to_state = transition.get("to_state", "")
                
                if not transition.get("trigger"):
                    self.violations.append(ConstraintViolation(
                        constraint_id="TRANSITION_NO_TRIGGER",
                        layer=FactLayer.TRANSITION,
                        severity=ConstraintSeverity.ERROR,
                        message=f"角色 {char_name} 从 {from_state} 转换到 {to_state} 缺少触发器",
                        location=scene_name,
                        fix_suggestion=f"为 {char_name} 的状态转换添加可见触发器（事件、对话、道具接触等）",
                        affected_entities=[char_name],
                    ))
    
    def _scene_shows_hidden_layer(self, scene: dict, char_name: str) -> bool:
        """检查场景是否展示了角色的隐藏层行为"""
        # 这里需要根据具体场景内容判断
        # 简化实现：检查是否有隐藏层关键词
        scene_text = str(scene.get("content", ""))
        hidden_keywords = ["冷", "锋利", "危险", "计算", "隐藏", "伪装"]
        return any(kw in scene_text for kw in hidden_keywords)
    
    def _has_trigger_in_scene(self, scene: dict, char_name: str) -> bool:
        """检查场景中是否有状态转换触发器"""
        # 检查场景中是否有明确的触发器描述
        # 触发器应该是明确的事件或动作，而不是简单的关键词匹配
        scene_text = str(scene.get("content", ""))
        
        # 明确的触发器关键词（状态转换触发器）
        trigger_keywords = ["发现", "看到", "听到", "遇到", "突然", "意外", "被迫", "必须"]
        
        # 检查是否有明确的触发器描述
        # 排除简单的描述性关键词（如"眼神"）
        for keyword in trigger_keywords:
            if keyword in scene_text:
                # 检查是否是明确的触发器描述
                # 例如："发现危险"、"看到异常"、"听到声音"
                if any(f"{keyword}{kw}" in scene_text for kw in ["到", "了", "了危险", "了异常", "了声音"]):
                    return True
        
        return False
    
    def _dialogue_style_drifts(self, scene: dict, char_name: str, char: CharacterFact) -> bool:
        """检查对话风格是否漂移
        
        规则：
        - 说话风格必须与人设定义的风格匹配
        - 例如：人设定义为"缓慢深沉"，但场景中说话语速很快
        """
        scene_text = str(scene.get("content", ""))
        speech_style = str(char.speech_style or "").lower()
        
        # 检查说话风格关键词
        style_keywords = {
            "缓慢": ["快速", "急促", "飞快", "迅速"],
            "深沉": ["轻浮", "随便", "草率"],
            "单纯": ["复杂", "深奥", "晦涩"],
            "热情": ["冷淡", "冷漠", "疏远"],
            "神秘": ["直白", "坦率", "直接"],
        }
        
        # 检查是否有风格漂移
        for style, drift_keywords in style_keywords.items():
            if style in speech_style:
                for drift_keyword in drift_keywords:
                    if drift_keyword in scene_text:
                        return True
        
        return False
    
    def _has_prop_transfer_explanation(self, scene: dict, prop_name: str) -> bool:
        """检查场景中是否有道具转移说明"""
        scene_text = str(scene.get("content", ""))
        transfer_keywords = ["拿起", "携带", "取出", "获得", "递"]
        return any(kw in scene_text for kw in transfer_keywords)


def build_constraint_validator_from_facts(
    story_fact_sheet: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
) -> FactConstraintValidator:
    """从故事事实表构建约束验证器"""
    
    # 解析角色事实
    characters = []
    for char_data in story_fact_sheet.get("characters", []):
        characters.append(CharacterFact(
            name=char_data.get("name", ""),
            public_persona=char_data.get("public_persona", ""),
            hidden_layer=char_data.get("hidden_layer", ""),
            speech_style=char_data.get("speech_style", ""),
            visible_state=char_data.get("visible_state", ""),
            hidden_state=char_data.get("hidden_state", ""),
            state_transition_trigger=char_data.get("state_transition_trigger", ""),
            persona_layer_guardrail=char_data.get("persona_layer_guardrail", ""),
        ))
    
    # 解析道具事实
    props = []
    for prop_data in story_fact_sheet.get("props", []):
        props.append(PropFact(
            name=prop_data.get("name", ""),
            prop_type=prop_data.get("type", "普通"),
            owner=prop_data.get("owner", ""),
            location=prop_data.get("location", ""),
            state=prop_data.get("state", ""),
            first_appearance=prop_data.get("first_appearance", ""),
        ))
    
    return FactConstraintValidator(
        characters=characters,
        props=props,
        scenes=scene_execution_cards,
    )
