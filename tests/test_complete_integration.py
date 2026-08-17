"""Test Complete Integration - 测试完整集成"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.repair import (
    StructuralRepairEngine,
    build_structural_validation_block,
    format_structural_validation_for_prompt,
    extract_facts_from_foundation,
)


def test_complete_integration():
    """测试完整集成流程"""
    print("=== 测试完整集成流程 ===\n")

    # 1. 模拟 foundation 数据
    foundation = {
        "character_state_cards": [
            {
                "name": "主角A",
                "public_persona": "懒散的守卫",
                "hidden_layer": "隐藏的高手",
                "speech_style": "慢吞吞",
                "visible_state": "懒散",
                "hidden_state": "警觉",
                "state_transition_trigger": "压力触发",
                "persona_layer_guardrail": "保持懒散人设",
            },
            {
                "name": "配角B",
                "public_persona": "热心的村民",
                "hidden_layer": "",
                "speech_style": "热情",
                "visible_state": "热心",
                "hidden_state": "",
                "state_transition_trigger": "",
                "persona_layer_guardrail": "保持热心人设",
            },
        ],
        "prop_cards": [
            {
                "name": "玉佩",
                "type": "关键证据道具",
                "owner": "主角A",
                "location": "主角A身上",
                "state": "完好",
                "first_appearance": "场景1",
            },
            {
                "name": "信件",
                "type": "连续性道具",
                "owner": "配角B",
                "location": "配角B身上",
                "state": "完好",
                "first_appearance": "场景2",
            },
        ],
        "scene_goal_cards": [
            {
                "scene_name": "场景1",
                "characters": ["主角A"],
                "props": ["玉佩"],
            },
            {
                "scene_name": "场景2",
                "characters": ["主角A", "配角B"],
                "props": ["玉佩", "信件"],
            },
        ],
    }

    # 2. 模拟 scene_execution_cards
    scene_execution_cards = [
        {
            "name": "场景1",
            "characters": ["主角A"],
            "props": ["玉佩"],
        },
        {
            "name": "场景2",
            "characters": ["主角A", "配角B"],
            "props": ["玉佩", "信件"],
        },
    ]

    # 3. 测试 extract_facts_from_foundation
    print("1. 测试 extract_facts_from_foundation")
    facts = extract_facts_from_foundation(foundation)
    print(f"   角色数量: {len(facts['characters'])}")
    print(f"   道具数量: {len(facts['props'])}")
    print(f"   场景数量: {len(facts['scenes'])}")

    # 4. 测试 build_structural_validation_block
    print("\n2. 测试 build_structural_validation_block")
    validation_block = build_structural_validation_block(foundation, scene_execution_cards)
    print(f"   验证块 keys: {list(validation_block.keys())}")
    
    validation = validation_block.get("structural_validation", {})
    print(f"   约束违反: {validation.get('validation_summary', {}).get('constraint_violations', 0)}")
    print(f"   道具问题: {validation.get('validation_summary', {}).get('prop_issues', 0)}")
    print(f"   角色问题: {validation.get('validation_summary', {}).get('character_issues', 0)}")

    # 5. 测试 format_structural_validation_for_prompt
    print("\n3. 测试 format_structural_validation_for_prompt")
    prompt_block = format_structural_validation_for_prompt(validation_block)
    print(f"   Prompt 长度: {len(prompt_block)} 字符")
    print(f"   第一行: {prompt_block.split(chr(10))[0]}")

    # 6. 测试 StructuralRepairEngine
    print("\n4. 测试 StructuralRepairEngine")
    engine = StructuralRepairEngine(
        story_fact_sheet=facts,
        scene_execution_cards=scene_execution_cards,
    )
    packet = engine.pre_generation_validation()
    print(f"   约束违反: {len(packet.constraint_violations)}")
    print(f"   道具问题: {len(packet.prop_issues)}")
    print(f"   角色问题: {len(packet.character_issues)}")
    print(f"   修复指令: {len(packet.fix_instructions)}")

    # 7. 生成修复指令
    print("\n5. 生成修复指令")
    directives = engine.generate_repair_directives(packet)
    print(f"   修复指令数量: {len(directives)}")
    for i, d in enumerate(directives[:3], 1):
        print(f"   {i}. [{d.get('type', '')}] {d.get('instruction', '')[:60]}...")

    print("\n=== 集成测试完成 ===")


if __name__ == "__main__":
    test_complete_integration()
