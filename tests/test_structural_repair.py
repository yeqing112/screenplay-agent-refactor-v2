"""Test Structural Repair Engine - 测试结构化修复引擎"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.repair import (
    FactConstraintValidator,
    ConstraintSeverity,
    FactLayer,
    CharacterFact,
    PropFact,
    PropTracker,
    PropType,
    PropRecord,
    CharacterStateMachine,
    CharacterState,
    CharacterLayer,
    TransitionType,
    StructuralRepairEngine,
)


def test_constraint_validator():
    """测试约束验证器"""
    print("=== 测试约束验证器 ===")

    # 创建测试数据
    characters = [
        CharacterFact(
            name="主角A",
            public_persona="懒散的守卫",
            hidden_layer="隐藏的高手",
            speech_style="慢吞吞",
            visible_state="懒散",
            hidden_state="警觉",
            state_transition_trigger="",
            persona_layer_guardrail="保持懒散人设",
        ),
    ]

    props = [
        PropFact(
            name="关键道具-玉佩",
            prop_type="关键证据",
            owner="主角A",
            location="主角A身上",
            state="完好",
            first_appearance="场景1",
        ),
    ]

    scenes = [
        {
            "name": "场景1",
            "characters": ["主角A"],
            "props": ["关键道具-玉佩"],
            "content": "主角A懒散地站着，突然眼神变冷，开始搜身",
        },
        {
            "name": "场景2",
            "characters": ["主角A"],
            "props": ["关键道具-玉佩"],
            "content": "主角A继续搜身",
        },
    ]

    # 创建验证器
    validator = FactConstraintValidator(characters, props, scenes)

    # 执行验证
    violations = validator.validate_all()

    print(f"发现 {len(violations)} 个违反")
    for v in violations:
        print(f"  [{v.severity.value}] {v.message}")
        print(f"    修复建议: {v.fix_suggestion}")

    return violations


def test_prop_tracker():
    """测试道具追踪器"""
    print("\n=== 测试道具追踪器 ===")

    tracker = PropTracker()

    # 注册道具
    prop = PropRecord(
        name="玉佩",
        prop_type=PropType.KEY_EVIDENCE,
        material="翡翠",
        appearance="圆形玉佩",
        owner="主角A",
        current_holder="主角A",
        current_location="主角A身上",
        first_appearance_scene="场景1",
    )
    tracker.register_prop(prop)

    # 记录场景出现
    tracker.add_scene_prop("场景1", "玉佩", holder="主角A", location="主角A身上")
    tracker.add_scene_prop("场景2", "玉佩", holder="主角A", location="桌上")
    tracker.add_scene_prop("场景3", "玉佩", holder="主角B", location="主角B身上")

    # 记录转移
    tracker.record_transfer(
        "玉佩",
        from_scene="场景1",
        to_scene="场景2",
        from_holder="主角A",
        to_holder="主角A",
        method="放在桌上",
    )

    # 验证连续性
    issues = tracker.validate_continuity()

    print(f"发现 {len(issues)} 个连续性问题")
    for issue in issues:
        print(f"  [{issue['type']}] {issue['message']}")
        print(f"    修复建议: {issue['fix']}")

    return issues


def test_state_machine():
    """测试状态机"""
    print("\n=== 测试状态机 ===")

    machine = CharacterStateMachine()

    # 注册角色
    char = CharacterState(
        name="主角A",
        public_persona="懒散的守卫",
        hidden_layer="隐藏的高手",
        speech_style="慢吞吞",
        current_public_state="懒散",
        current_hidden_state="警觉",
    )
    machine.register_character(char)

    # 记录场景状态
    machine.add_scene_character("场景1", "主角A", public_state="懒散")
    machine.add_scene_character("场景2", "主角A", public_state="警觉")
    machine.add_scene_character("场景3", "主角A", public_state="懒散")

    # 记录转换
    machine.record_transition(
        "主角A",
        from_state="懒散",
        to_state="警觉",
        layer=CharacterLayer.HIDDEN,
        transition_type=TransitionType.REVEAL,
        trigger="压力触发",
        scene="场景2",
    )

    # 验证转换
    issues = machine.validate_transitions()

    print(f"发现 {len(issues)} 个转换问题")
    for issue in issues:
        print(f"  [{issue['type']}] {issue['message']}")
        print(f"    修复建议: {issue['fix']}")

    return issues


def test_structural_engine():
    """测试结构化修复引擎"""
    print("\n=== 测试结构化修复引擎 ===")

    # 构建测试数据
    story_fact_sheet = {
        "characters": [
            {
                "name": "主角A",
                "public_persona": "懒散的守卫",
                "hidden_layer": "隐藏的高手",
                "speech_style": "慢吞吞",
                "visible_state": "懒散",
                "hidden_state": "警觉",
            },
        ],
        "props": [
            {
                "name": "玉佩",
                "type": "关键证据道具",
                "owner": "主角A",
                "location": "主角A身上",
            },
        ],
    }

    scene_execution_cards = [
        {
            "name": "场景1",
            "characters": ["主角A"],
            "props": ["玉佩"],
        },
        {
            "name": "场景2",
            "characters": ["主角A"],
            "props": ["玉佩"],
        },
    ]

    # 创建引擎
    engine = StructuralRepairEngine(story_fact_sheet, scene_execution_cards)

    # 执行验证
    packet = engine.pre_generation_validation()

    print(f"约束违反: {len(packet.constraint_violations)}")
    print(f"道具问题: {len(packet.prop_issues)}")
    print(f"角色问题: {len(packet.character_issues)}")
    print(f"修复指令: {len(packet.fix_instructions)}")

    # 生成修复指令
    directives = engine.generate_repair_directives(packet)

    print(f"\n生成 {len(directives)} 个修复指令:")
    for d in directives:
        print(f"  [{d.get('type', 'UNKNOWN')}] {d.get('instruction', '')[:50]}...")

    return packet, directives


if __name__ == "__main__":
    print("开始测试结构化修复引擎...\n")

    test_constraint_validator()
    test_prop_tracker()
    test_state_machine()
    test_structural_engine()

    print("\n测试完成!")
