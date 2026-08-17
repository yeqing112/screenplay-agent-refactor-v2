"""Comprehensive Issue Test - 全面问题测试

测试当前结构化修复引擎的局限性，识别需要改进的地方。
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.repair import (
    StructuralRepairEngine,
    FactConstraintValidator,
    PropTracker,
    CharacterStateMachine,
    build_structural_validation_block,
    format_structural_validation_for_prompt,
    extract_facts_from_foundation,
)
from core.repair.fact_constraints import (
    CharacterFact,
    PropFact,
    ConstraintSeverity,
)


def create_test_data_with_hidden_layer_issues():
    """创建包含隐藏层问题的测试数据"""
    return {
        "title": "隐藏层测试",
        "characters": [
            {
                "name": "主角",
                "public_persona": "天真的学生",
                "hidden_layer": "隐藏的特工",
                "speech_style": "单纯直接",
                "visible_state": "天真好奇",
                "hidden_state": "高度警觉",
                "state_transition_trigger": "发现危险",
                "persona_layer_guardrail": "保持天真人设直到有明确触发器",
            },
        ],
        "props": [],
        "scenes": [
            {
                "name": "场景1",
                "characters": ["主角"],
                "props": [],
                "content": "主角天真地走在路上",
            },
            {
                "name": "场景2",
                "characters": ["主角"],
                "props": [],
                "content": "主角突然眼神变冷，开始观察周围环境，隐藏着危险的气息",
            },
        ],
    }


def create_test_data_with_style_drift():
    """创建包含风格漂移问题的测试数据"""
    return {
        "title": "风格漂移测试",
        "characters": [
            {
                "name": "老人",
                "public_persona": "慈祥的老人",
                "hidden_layer": "",
                "speech_style": "缓慢深沉",
                "visible_state": "慈祥温和",
                "hidden_state": "",
                "state_transition_trigger": "",
                "persona_layer_guardrail": "保持慈祥人设",
            },
        ],
        "props": [],
        "scenes": [
            {
                "name": "场景1",
                "characters": ["老人"],
                "props": [],
                "content": "老人缓慢地说：孩子，慢慢来。",
            },
            {
                "name": "场景2",
                "characters": ["老人"],
                "props": [],
                "content": "老人快速地说：快点！没时间了！",
            },
        ],
    }


def test_hidden_layer_detection():
    """测试隐藏层检测（返回True表示通过）"""
    print("=" * 60)
    print("测试1: 隐藏层检测")
    print("=" * 60)
    
    story_data = create_test_data_with_hidden_layer_issues()
    scene_cards = [
        {
            "name": scene["name"],
            "characters": scene["characters"],
            "props": scene.get("props", []),
            "content": scene.get("content", ""),
        }
        for scene in story_data["scenes"]
    ]
    
    facts = extract_facts_from_foundation({
        "character_state_cards": story_data["characters"],
        "prop_cards": story_data["props"],
        "scene_goal_cards": [{"scene_name": s["name"], "characters": s["characters"], "props": s.get("props", []), "content": s.get("content", "")} for s in story_data["scenes"]],
    })
    
    engine = StructuralRepairEngine(
        story_fact_sheet=facts,
        scene_execution_cards=scene_cards,
    )
    
    packet = engine.pre_generation_validation()
    
    print(f"  约束违反: {len(packet.constraint_violations)} 个")
    print(f"  道具问题: {len(packet.prop_issues)} 个")
    print(f"  角色问题: {len(packet.character_issues)} 个")
    
    hidden_layer_issues = [
        v for v in packet.constraint_violations
        if "隐藏层" in v.message or "HIDDEN" in v.constraint_id
    ]
    
    if hidden_layer_issues:
        print(f"  [PASS] 检测到隐藏层问题: {len(hidden_layer_issues)} 个")
        for issue in hidden_layer_issues:
            print(f"    - {issue.message}")
        return True  # 检测到问题 = 测试通过
    else:
        print("  [FAIL] 未检测到隐藏层问题")
        return False


def test_style_drift_detection():
    """测试风格漂移检测（返回True表示通过）"""
    print("\n" + "=" * 60)
    print("测试2: 风格漂移检测")
    print("=" * 60)
    
    story_data = create_test_data_with_style_drift()
    scene_cards = [
        {
            "name": scene["name"],
            "characters": scene["characters"],
            "props": scene.get("props", []),
            "content": scene.get("content", ""),
        }
        for scene in story_data["scenes"]
    ]
    
    facts = extract_facts_from_foundation({
        "character_state_cards": story_data["characters"],
        "prop_cards": story_data["props"],
        "scene_goal_cards": [{"scene_name": s["name"], "characters": s["characters"], "props": s.get("props", []), "content": s.get("content", "")} for s in story_data["scenes"]],
    })
    
    engine = StructuralRepairEngine(
        story_fact_sheet=facts,
        scene_execution_cards=scene_cards,
    )
    
    packet = engine.pre_generation_validation()
    
    print(f"  约束违反: {len(packet.constraint_violations)} 个")
    print(f"  道具问题: {len(packet.prop_issues)} 个")
    print(f"  角色问题: {len(packet.character_issues)} 个")
    
    style_drift_issues = [
        v for v in packet.constraint_violations
        if "风格" in v.message or "STYLE" in v.constraint_id
    ]
    
    if style_drift_issues:
        print(f"  [PASS] 检测到风格漂移问题: {len(style_drift_issues)} 个")
        for issue in style_drift_issues:
            print(f"    - {issue.message}")
        return True
    else:
        print("  [FAIL] 未检测到风格漂移问题")
        return False


def test_validation_logic_coverage():
    """测试验证逻辑覆盖率（返回True表示通过）"""
    print("\n" + "=" * 60)
    print("测试3: 验证逻辑覆盖率")
    print("=" * 60)
    
    from core.repair.fact_constraints import FactConstraintValidator
    
    validator = FactConstraintValidator([], [], [])
    
    methods = [
        "_validate_character_consistency",
        "_validate_prop_uniqueness",
        "_validate_prop_continuity",
        "_validate_evidence_visibility",
        "_validate_state_transitions",
        "_scene_shows_hidden_layer",
        "_has_trigger_in_scene",
        "_dialogue_style_drifts",
        "_has_prop_transfer_explanation",
    ]
    
    implemented_methods = []
    placeholder_methods = []
    
    for method_name in methods:
        if hasattr(validator, method_name):
            method = getattr(validator, method_name)
            import inspect
            source = inspect.getsource(method)
            if "return False" in source and source.count("return") == 1:
                placeholder_methods.append(method_name)
            elif "return []" in source and source.count("return") == 1:
                placeholder_methods.append(method_name)
            else:
                implemented_methods.append(method_name)
    
    print(f"  已实现的方法: {len(implemented_methods)} 个")
    for method in implemented_methods:
        print(f"    - {method}")
    
    print(f"  占位符方法: {len(placeholder_methods)} 个")
    for method in placeholder_methods:
        print(f"    - {method}")
    
    coverage = len(implemented_methods) / len(methods) * 100 if methods else 0
    print(f"  覆盖率: {coverage:.1f}%")
    
    return coverage >= 100


def test_character_state_machine_coverage():
    """测试角色状态机覆盖率（返回True表示通过）"""
    print("\n" + "=" * 60)
    print("测试4: 角色状态机覆盖率")
    print("=" * 60)
    
    from core.repair.character_state_machine import CharacterStateMachine
    
    machine = CharacterStateMachine()
    
    methods = [
        "validate_transitions",
        "_check_layer_confusion",
        "_has_reveal_seeding",
        "_check_speech_style_drift",
    ]
    
    implemented_methods = []
    placeholder_methods = []
    
    for method_name in methods:
        if hasattr(machine, method_name):
            method = getattr(machine, method_name)
            import inspect
            source = inspect.getsource(method)
            if "return []" in source and source.count("return") == 1:
                placeholder_methods.append(method_name)
            else:
                implemented_methods.append(method_name)
    
    print(f"  已实现的方法: {len(implemented_methods)} 个")
    for method in implemented_methods:
        print(f"    - {method}")
    
    print(f"  占位符方法: {len(placeholder_methods)} 个")
    for method in placeholder_methods:
        print(f"    - {method}")
    
    coverage = len(implemented_methods) / len(methods) * 100 if methods else 0
    print(f"  覆盖率: {coverage:.1f}%")
    
    return coverage >= 100


def main():
    """主测试函数"""
    print("开始全面问题测试...\n")
    
    results = []
    
    results.append(("隐藏层检测", test_hidden_layer_detection()))
    results.append(("风格漂移检测", test_style_drift_detection()))
    results.append(("验证逻辑覆盖率", test_validation_logic_coverage()))
    results.append(("角色状态机覆盖率", test_character_state_machine_coverage()))
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {name}")
    
    print(f"\n  通过: {passed}/{total}")
    
    if passed == total:
        print("\n  [PASS] 所有测试通过")
    else:
        print("\n  [INFO] 发现需要改进的地方")
        print("  建议:")
        print("    1. 完善 _scene_shows_hidden_layer 方法")
        print("    2. 完善 _has_trigger_in_scene 方法")
        print("    3. 实现 _dialogue_style_drifts 方法")
        print("    4. 实现 _check_speech_style_drift 方法")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
