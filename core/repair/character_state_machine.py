"""Character State Machine - 角色状态机

追踪角色状态转换，确保状态变化有触发器且符合人设。
在生成阶段就验证状态一致性，而不是等QA发现问题再修补。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CharacterLayer(Enum):
    """角色层级"""
    PUBLIC = "public"      # 公开层：外部可见的表现
    HIDDEN = "hidden"      # 隐藏层：真实意图/能力
    TRANSITION = "transition"  # 状态转换


class TransitionType(Enum):
    """状态转换类型"""
    TRIGGERED = "triggered"      # 有触发器的转换
    GRADUAL = "gradual"          # 渐进式转换
    REVEAL = "reveal"            # 隐藏层揭示
    MASK = "mask"                # 人设掩饰


@dataclass
class StateTransition:
    """状态转换"""
    from_state: str
    to_state: str
    layer: CharacterLayer
    transition_type: TransitionType
    trigger: str  # 触发器描述
    scene: str  # 发生场景
    visibility: str = "visible"  # visible/hidden/subtle


@dataclass
class CharacterState:
    """角色状态"""
    name: str
    public_persona: str          # 公开人设定义
    hidden_layer: str            # 隐藏层定义
    speech_style: str            # 说话风格
    current_public_state: str    # 当前公开状态
    current_hidden_state: str    # 当前隐藏状态
    state_history: list[dict[str, Any]] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)


class CharacterStateMachine:
    """角色状态机
    
    功能：
    1. 追踪角色在每个场景中的状态
    2. 验证状态转换的触发器
    3. 检测人设层级混淆
    4. 生成状态转换时间线
    """
    
    def __init__(self):
        self.characters: dict[str, CharacterState] = {}
        self.scene_characters: dict[str, list[str]] = {}  # scene -> [char_names]
    
    def register_character(self, char: CharacterState):
        """注册角色"""
        self.characters[char.name] = char
    
    def add_scene_character(
        self,
        scene_name: str,
        char_name: str,
        public_state: str = "",
        hidden_state: str = "",
    ):
        """记录角色在场景中的状态"""
        if scene_name not in self.scene_characters:
            self.scene_characters[scene_name] = []
        if char_name not in self.scene_characters[scene_name]:
            self.scene_characters[scene_name].append(char_name)
        
        if char_name not in self.characters:
            self.characters[char_name] = CharacterState(
                name=char_name,
                public_persona="",
                hidden_layer="",
                speech_style="",
                current_public_state="",
                current_hidden_state="",
            )
        
        char = self.characters[char_name]
        char.state_history.append({
            "scene": scene_name,
            "public_state": public_state,
            "hidden_state": hidden_state,
        })
        
        if public_state:
            char.current_public_state = public_state
        if hidden_state:
            char.current_hidden_state = hidden_state
    
    def record_transition(
        self,
        char_name: str,
        from_state: str,
        to_state: str,
        layer: CharacterLayer,
        transition_type: TransitionType,
        trigger: str,
        scene: str,
    ):
        """记录状态转换"""
        if char_name not in self.characters:
            return
        
        char = self.characters[char_name]
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            layer=layer,
            transition_type=transition_type,
            trigger=trigger,
            scene=scene,
        )
        char.transitions.append(transition)
    
    def validate_transitions(self) -> list[dict[str, Any]]:
        """验证状态转换
        
        返回所有转换问题
        """
        issues = []
        
        for char_name, char in self.characters.items():
            # 检查转换触发器
            for transition in char.transitions:
                if not transition.trigger and transition.transition_type == TransitionType.TRIGGERED:
                    issues.append({
                        "type": "NO_TRIGGER",
                        "character": char_name,
                        "scene": transition.scene,
                        "message": f"角色 {char_name} 从 {transition.from_state} 转换到 {transition.to_state} 缺少触发器",
                        "fix": f"在场景 {transition.scene} 为 {char_name} 添加状态转换触发器",
                    })
            
            # 检查人设层级混淆
            issues.extend(self._check_layer_confusion(char))
            
            # 检查说话风格漂移
            issues.extend(self._check_speech_style_drift(char))
        
        return issues
    
    def _check_layer_confusion(self, char: CharacterState) -> list[dict[str, Any]]:
        """检查人设层级混淆"""
        issues = []
        
        # 如果有隐藏层揭示，检查是否有铺垫
        reveal_transitions = [t for t in char.transitions if t.transition_type == TransitionType.REVEAL]
        
        for reveal in reveal_transitions:
            # 检查揭示前是否有铺垫
            if not self._has_reveal_seeding(char, reveal.scene):
                issues.append({
                    "type": "NO_REVEAL_SEEDING",
                    "character": char.name,
                    "scene": reveal.scene,
                    "message": f"角色 {char.name} 在场景 {reveal.scene} 揭示隐藏层，但之前没有铺垫",
                    "fix": f"在 {reveal.scene} 之前的场景为 {char.name} 添加隐藏层铺垫（微小动作、眼神变化等）",
                })
        
        return issues
    
    def _has_reveal_seeding(self, char: CharacterState, reveal_scene: str) -> bool:
        """检查揭示前是否有铺垫"""
        # 简化实现：检查是否有铺垫相关的转换
        for transition in char.transitions:
            if transition.scene == reveal_scene:
                continue
            if transition.transition_type in [TransitionType.TRIGGERED, TransitionType.GRADUAL]:
                return True
        return False
    
    def _check_speech_style_drift(self, char: CharacterState) -> list[dict[str, Any]]:
        """检查说话风格漂移
        
        规则：
        - 说话风格必须与人设定义的风格匹配
        - 例如：人设定义为"缓慢深沉"，但场景中说话语速很快
        """
        issues = []
        
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
            if style in char.speech_style:
                for drift_keyword in drift_keywords:
                    # 检查状态历史中是否有风格漂移
                    for history in char.state_history:
                        if drift_keyword in str(history.get("public_state", "")):
                            issues.append({
                                "type": "STYLE_DRIFT",
                                "character": char.name,
                                "scene": history.get("scene", ""),
                                "message": f"角色 {char.name} 在场景 {history.get('scene', '')} 的说话风格与人设不匹配",
                                "fix": f"调整 {char.name} 的台词，使其符合人设定义的说话风格",
                            })
        
        return issues
    
    def get_character_timeline(self, char_name: str) -> list[dict[str, Any]]:
        """获取角色时间线"""
        if char_name not in self.characters:
            return []
        
        char = self.characters[char_name]
        timeline = []
        
        for record in char.state_history:
            timeline.append({
                "scene": record.get("scene", ""),
                "public_state": record.get("public_state", ""),
                "hidden_state": record.get("hidden_state", ""),
            })
        
        return timeline
    
    def generate_state_summary(self) -> dict[str, Any]:
        """生成状态摘要"""
        summary = {
            "total_characters": len(self.characters),
            "characters_with_transitions": 0,
            "total_transitions": 0,
            "transition_types": {},
        }
        
        for char_name, char in self.characters.items():
            if char.transitions:
                summary["characters_with_transitions"] += 1
                summary["total_transitions"] += len(char.transitions)
                
                for transition in char.transitions:
                    type_name = transition.transition_type.value
                    if type_name not in summary["transition_types"]:
                        summary["transition_types"][type_name] = 0
                    summary["transition_types"][type_name] += 1
        
        return summary


def build_state_machine_from_facts(
    story_fact_sheet: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
) -> CharacterStateMachine:
    """从事实表构建状态机"""
    machine = CharacterStateMachine()
    
    # 注册角色
    for char_data in story_fact_sheet.get("characters", []):
        char = CharacterState(
            name=char_data.get("name", ""),
            public_persona=char_data.get("public_persona", ""),
            hidden_layer=char_data.get("hidden_layer", ""),
            speech_style=char_data.get("speech_style", ""),
            current_public_state=char_data.get("visible_state", ""),
            current_hidden_state=char_data.get("hidden_state", ""),
        )
        machine.register_character(char)
    
    # 记录每个场景的角色
    for scene in scene_execution_cards:
        scene_name = scene.get("name", "")
        for char_name in scene.get("characters", []):
            machine.add_scene_character(
                scene_name=scene_name,
                char_name=char_name,
                public_state=scene.get("character_states", {}).get(char_name, ""),
            )
    
    return machine
