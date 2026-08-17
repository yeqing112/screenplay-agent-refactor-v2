"""Prop Tracker - 道具/证据追踪器

追踪关键道具和证据在场景间的流转，确保连续性。
在生成阶段就验证道具状态，而不是等QA发现问题再修补。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PropType(Enum):
    """道具类型"""
    NORMAL = "普通道具"
    KEY_EVIDENCE = "关键证据道具"
    CONTINUITY = "连续性道具"


class PropState(Enum):
    """道具状态"""
    INTACT = "完好"
    DAMAGED = "损坏"
    HIDDEN = "隐藏"
    FOUND = "发现"
    TRANSFERRED = "转移"
    CONSUMED = "消耗"


@dataclass
class PropTransfer:
    """道具转移记录"""
    from_scene: str
    to_scene: str
    from_holder: str
    to_holder: str
    method: str  # 转移方式：交给、偷走、发现、携带等
    timestamp: str = ""  # 故事内时间


@dataclass
class PropRecord:
    """道具记录"""
    name: str
    prop_type: PropType
    material: str = ""  # 材质
    appearance: str = ""  # 外观描述
    owner: str = ""  # 所有者
    current_holder: str = ""  # 当前持有者
    current_location: str = ""  # 当前位置
    current_state: PropState = PropState.INTACT
    first_appearance_scene: str = ""  # 首次出现场景
    transfers: list[PropTransfer] = field(default_factory=list)
    scene_history: list[dict[str, Any]] = field(default_factory=list)


class PropTracker:
    """道具追踪器
    
    功能：
    1. 记录道具在每个场景中的状态
    2. 验证道具转移的连续性
    3. 检测道具位置冲突
    4. 生成道具状态时间线
    """
    
    def __init__(self):
        self.props: dict[str, PropRecord] = {}
        self.scene_props: dict[str, list[str]] = {}  # scene -> [prop_names]
    
    def register_prop(self, prop: PropRecord):
        """注册道具"""
        self.props[prop.name] = prop
    
    def add_scene_prop(self, scene_name: str, prop_name: str, **kwargs):
        """记录道具在场景中的出现"""
        if scene_name not in self.scene_props:
            self.scene_props[scene_name] = []
        if prop_name not in self.scene_props[scene_name]:
            self.scene_props[scene_name].append(prop_name)
        
        if prop_name not in self.props:
            self.props[prop_name] = PropRecord(
                name=prop_name,
                prop_type=kwargs.get("prop_type", PropType.NORMAL),
            )
        
        prop = self.props[prop_name]
        prop.scene_history.append({
            "scene": scene_name,
            **kwargs,
        })
    
    def record_transfer(
        self,
        prop_name: str,
        from_scene: str,
        to_scene: str,
        from_holder: str,
        to_holder: str,
        method: str,
    ):
        """记录道具转移"""
        if prop_name not in self.props:
            return
        
        prop = self.props[prop_name]
        transfer = PropTransfer(
            from_scene=from_scene,
            to_scene=to_scene,
            from_holder=from_holder,
            to_holder=to_holder,
            method=method,
        )
        prop.transfers.append(transfer)
        prop.current_holder = to_holder
    
    def validate_continuity(self) -> list[dict[str, Any]]:
        """验证道具连续性
        
        返回所有连续性问题
        """
        issues = []
        
        # 检查每个道具的转移链
        for prop_name, prop in self.props.items():
            if prop.prop_type == PropType.NORMAL:
                continue  # 普通道具不检查连续性
            
            # 检查转移链完整性
            for i, transfer in enumerate(prop.transfers):
                # 检查转移前后的持有者一致性
                if i > 0:
                    prev_transfer = prop.transfers[i - 1]
                    if prev_transfer.to_holder != transfer.from_holder:
                        issues.append({
                            "type": "HOLDER_MISMATCH",
                            "prop": prop_name,
                            "scene": transfer.from_scene,
                            "message": f"道具 {prop_name} 从 {prev_transfer.to_holder} 转移到 {transfer.from_holder}，但前一次转移结束时持有者是 {prev_transfer.to_holder}",
                            "fix": f"在场景 {transfer.from_scene} 添加道具转移说明，明确 {prop_name} 如何从 {prev_transfer.to_holder} 转移到 {transfer.from_holder}",
                        })
                
                # 检查转移方式合理性
                if not self._is_transfer_method_valid(prop, transfer):
                    issues.append({
                        "type": "INVALID_TRANSFER_METHOD",
                        "prop": prop_name,
                        "scene": transfer.to_scene,
                        "message": f"道具 {prop_name} 的转移方式 '{transfer.method}' 不合理",
                        "fix": f"修改转移方式或添加转移过程说明",
                    })
        
        # 检查关键道具位置冲突
        issues.extend(self._check_location_conflicts())
        
        return issues
    
    def _is_transfer_method_valid(self, prop: PropRecord, transfer: PropTransfer) -> bool:
        """检查转移方式是否合理"""
        # 关键证据道具需要明确的转移说明
        if prop.prop_type == PropType.KEY_EVIDENCE:
            valid_methods = ["交给", "递给", "偷走", "发现", "拾取", "携带", "藏匿", "搜出"]
            return transfer.method in valid_methods
        return True
    
    def _check_location_conflicts(self) -> list[dict[str, Any]]:
        """检查道具位置冲突"""
        issues = []
        
        # 按场景检查道具位置
        scene_prop_locations: dict[str, dict[str, str]] = {}
        
        for scene_name, prop_names in self.scene_props.items():
            scene_prop_locations[scene_name] = {}
            for prop_name in prop_names:
                if prop_name in self.props:
                    prop = self.props[prop_name]
                    scene_prop_locations[scene_name][prop_name] = prop.current_location
        
        # 检查相邻场景的位置连续性
        scene_list = sorted(self.scene_props.keys())
        for i in range(1, len(scene_list)):
            prev_scene = scene_list[i - 1]
            curr_scene = scene_list[i]
            
            prev_props = scene_prop_locations.get(prev_scene, {})
            curr_props = scene_prop_locations.get(curr_scene, {})
            
            # 手动添加道具
            common_props = set(prev_props.keys()) & set(curr_props.keys())
            for prop_name in common_props:
                prev_loc = prev_props[prop_name]
                curr_loc = curr_props[prop_name]
                
                if prev_loc != curr_loc:
                    # 位置变化，检查是否有转移说明
                    if not self._has_transfer_between_scenes(prop_name, prev_scene, curr_scene):
                        issues.append({
                            "type": "LOCATION_CHANGE_NO_TRANSFER",
                            "prop": prop_name,
                            "scene": curr_scene,
                            "message": f"道具 {prop_name} 从 {prev_loc}（{prev_scene}）移动到 {curr_loc}（{curr_scene}），但没有转移说明",
                            "fix": f"在场景 {curr_scene} 添加道具转移镜头或说明",
                        })
        
        return issues
    
    def _has_transfer_between_scenes(self, prop_name: str, from_scene: str, to_scene: str) -> bool:
        """检查道具是否在两个场景之间有转移记录"""
        if prop_name not in self.props:
            return False
        
        prop = self.props[prop_name]
        for transfer in prop.transfers:
            if transfer.from_scene == from_scene and transfer.to_scene == to_scene:
                return True
        return False
    
    def get_prop_timeline(self, prop_name: str) -> list[dict[str, Any]]:
        """获取道具时间线"""
        if prop_name not in self.props:
            return []
        
        prop = self.props[prop_name]
        timeline = []
        
        for record in prop.scene_history:
            timeline.append({
                "scene": record.get("scene", ""),
                "holder": record.get("holder", ""),
                "location": record.get("location", ""),
                "state": record.get("state", ""),
                "description": record.get("description", ""),
            })
        
        return timeline
    
    def generate_prop_state_summary(self) -> dict[str, Any]:
        """生成道具状态摘要"""
        summary = {
            "total_props": len(self.props),
            "by_type": {},
            "by_state": {},
            "props_with_issues": [],
        }
        
        for prop_name, prop in self.props.items():
            # 按类型统计
            type_name = prop.prop_type.value
            if type_name not in summary["by_type"]:
                summary["by_type"][type_name] = 0
            summary["by_type"][type_name] += 1
            
            # 按状态统计
            state_name = prop.current_state.value
            if state_name not in summary["by_state"]:
                summary["by_state"][state_name] = 0
            summary["by_state"][state_name] += 1
        
        return summary


def build_prop_tracker_from_facts(
    story_fact_sheet: dict[str, Any],
    scene_execution_cards: list[dict[str, Any]],
) -> PropTracker:
    """从事实表构建道具追踪器"""
    tracker = PropTracker()
    
    # 注册道具
    for prop_data in story_fact_sheet.get("props", []):
        prop_type_str = prop_data.get("type", "普通道具")
        prop_type_map = {
            "普通道具": PropType.NORMAL,
            "关键证据道具": PropType.KEY_EVIDENCE,
            "连续性道具": PropType.CONTINUITY,
        }
        prop_type = prop_type_map.get(prop_type_str, PropType.NORMAL)
        
        prop = PropRecord(
            name=prop_data.get("name", ""),
            prop_type=prop_type,
            material=prop_data.get("material", ""),
            appearance=prop_data.get("appearance", ""),
            owner=prop_data.get("owner", ""),
            current_holder=prop_data.get("current_holder", ""),
            current_location=prop_data.get("location", ""),
            first_appearance_scene=prop_data.get("first_appearance", ""),
        )
        tracker.register_prop(prop)
    
    # 记录每个场景的道具
    for scene in scene_execution_cards:
        scene_name = scene.get("name", "")
        for prop_name in scene.get("props", []):
            tracker.add_scene_prop(
                scene_name=scene_name,
                prop_name=prop_name,
                holder=scene.get("prop_holders", {}).get(prop_name, ""),
                location=scene.get("prop_locations", {}).get(prop_name, ""),
            )
    
    return tracker
