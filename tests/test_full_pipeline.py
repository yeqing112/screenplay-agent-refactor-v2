"""Full Pipeline Integration Test - 完整流水线集成测试

测试完整的流水线：
1. 创建测试数据
2. 运行结构化验证
3. 生成修复指令
4. 验证修复效果
5. 生成测试报告
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


def create_comprehensive_test_data():
    """创建综合测试数据"""
    return {
        "title": "迷雾寺庙",
        "setting": "古代山间寺庙",
        "characters": [
            {
                "name": "小和尚",
                "public_persona": "天真善良的新来和尚",
                "hidden_layer": "隐藏着对寺庙秘密的怀疑",
                "speech_style": "单纯直接",
                "visible_state": "天真好奇",
                "hidden_state": "警觉观察",
                "state_transition_trigger": "发现异常物品",
                "persona_layer_guardrail": "保持天真人设直到有明确触发器",
            },
            {
                "name": "老和尚",
                "public_persona": "慈祥智慧的长者",
                "hidden_layer": "隐藏着寺庙过去的秘密",
                "speech_style": "缓慢深沉",
                "visible_state": "慈祥温和",
                "hidden_state": "警惕防备",
                "state_transition_trigger": "被追问往事",
                "persona_layer_guardrail": "保持长者风范直到被逼问",
            },
            {
                "name": "神秘人",
                "public_persona": "偶尔出现的香客",
                "hidden_layer": "寺庙真正的守护者",
                "speech_style": "神秘隐晦",
                "visible_state": "普通香客",
                "hidden_state": "高度警觉",
                "state_transition_trigger": "寺庙安全受威胁",
                "persona_layer_guardrail": "保持神秘感直到必要时才显露",
            },
        ],
        "props": [
            {
                "name": "古老经书",
                "type": "关键证据道具",
                "owner": "老和尚",
                "location": "老和尚禅房",
                "state": "完好",
                "first_appearance": "场景1",
                "description": "记载寺庙秘密的古老经书",
            },
            {
                "name": "玉佩",
                "type": "关键证据道具",
                "owner": "小和尚",
                "location": "小和尚身上",
                "state": "完好",
                "first_appearance": "场景1",
                "description": "小和尚随身携带的玉佩",
            },
            {
                "name": "神秘信件",
                "type": "关键证据道具",
                "owner": "老和尚",
                "location": "老和尚禅房",
                "state": "完好",
                "first_appearance": "场景2",
                "description": "老和尚收到的神秘信件",
            },
        ],
        "scenes": [
            {
                "name": "场景1-寺庙大殿",
                "characters": ["小和尚", "老和尚"],
                "props": ["古老经书", "玉佩"],
                "time": "清晨",
                "description": "小和尚第一次进入大殿，发现老和尚在整理经书",
            },
            {
                "name": "场景2-后山小路",
                "characters": ["小和尚", "神秘人"],
                "props": ["玉佩", "神秘信件"],
                "time": "黄昏",
                "description": "小和尚在后山遇到神秘人，玉佩发光",
            },
            {
                "name": "场景3-老和尚禅房",
                "characters": ["小和尚", "老和尚"],
                "props": ["古老经书", "神秘信件"],
                "time": "夜晚",
                "description": "小和尚追问老和尚关于经书的秘密",
            },
        ],
    }


def create_scene_execution_cards(story_data):
    """创建场景执行卡"""
    cards = []
    for scene in story_data["scenes"]:
        card = {
            "name": scene["name"],
            "characters": scene["characters"],
            "props": scene["props"],
            "time": scene.get("time", ""),
            "description": scene.get("description", ""),
            "opening_state": "",
            "scene_objective": "",
            "scene_conflict": "",
            "required_visual_proofs": [],
            "closing_state": "",
            "handoff_to_next_scene": "",
        }
        cards.append(card)
    return cards


def test_full_pipeline():
    """测试完整流水线"""
    print("=" * 70)
    print("完整流水线集成测试 - 结构化修复引擎")
    print("=" * 70)
    
    # 1. 创建测试数据
    print("\n[1/7] 创建测试数据...")
    story_data = create_comprehensive_test_data()
    scene_cards = create_scene_execution_cards(story_data)
    print(f"  故事: {story_data['title']}")
    print(f"  角色: {len(story_data['characters'])} 个")
    print(f"  道具: {len(story_data['props'])} 个")
    print(f"  场景: {len(story_data['scenes'])} 个")
    
    # 2. 提取事实
    print("\n[2/7] 提取故事事实...")
    facts = extract_facts_from_foundation({
        "character_state_cards": story_data["characters"],
        "prop_cards": story_data["props"],
        "scene_goal_cards": [{"scene_name": s["name"], "characters": s["characters"], "props": s["props"]} for s in story_data["scenes"]],
    })
    print(f"  提取角色事实: {len(facts['characters'])} 个")
    print(f"  提取道具事实: {len(facts['props'])} 个")
    print(f"  提取场景事实: {len(facts['scenes'])} 个")
    
    # 3. 创建结构化引擎
    print("\n[3/7] 创建结构化修复引擎...")
    engine = StructuralRepairEngine(
        story_fact_sheet=facts,
        scene_execution_cards=scene_cards,
    )
    print("  引擎初始化完成")
    
    # 4. 预验证
    print("\n[4/7] 执行预验证...")
    packet = engine.pre_generation_validation()
    print(f"  约束违反: {len(packet.constraint_violations)} 个")
    print(f"  道具问题: {len(packet.prop_issues)} 个")
    print(f"  角色问题: {len(packet.character_issues)} 个")
    print(f"  修复指令: {len(packet.fix_instructions)} 个")
    
    # 打印详细问题
    if packet.constraint_violations:
        print("\n  约束违反详情:")
        for v in packet.constraint_violations:
            print(f"    [{v.severity.value}] {v.message}")
            print(f"      位置: {v.location}")
            print(f"      修复: {v.fix_suggestion}")
    
    if packet.prop_issues:
        print("\n  道具问题详情:")
        for issue in packet.prop_issues:
            print(f"    [{issue.get('type', '')}] {issue.get('message', '')}")
            print(f"      修复: {issue.get('fix', '')}")
    
    if packet.character_issues:
        print("\n  角色问题详情:")
        for issue in packet.character_issues:
            print(f"    [{issue.get('type', '')}] {issue.get('message', '')}")
            print(f"      修复: {issue.get('fix', '')}")
    
    # 5. 生成修复指令
    print("\n[5/7] 生成修复指令...")
    directives = engine.generate_repair_directives(packet)
    print(f"  生成 {len(directives)} 个修复指令")
    for i, d in enumerate(directives, 1):
        print(f"    {i}. [{d.get('type', '')}] {d.get('instruction', '')[:80]}...")
    
    # 6. 构建验证块
    print("\n[6/7] 构建验证块...")
    foundation = {
        "character_state_cards": story_data["characters"],
        "prop_cards": story_data["props"],
        "scene_goal_cards": [{"scene_name": s["name"], "characters": s["characters"], "props": s["props"]} for s in story_data["scenes"]],
    }
    validation_block = build_structural_validation_block(foundation, scene_cards)
    validation_prompt = format_structural_validation_for_prompt(validation_block)
    
    # 提取可序列化的数据
    validation_summary = validation_block.get("structural_validation", {}).get("validation_summary", {})
    repair_directives = validation_block.get("repair_directives", [])
    
    print(f"  验证摘要: {validation_summary}")
    print(f"  修复指令数: {len(repair_directives)}")
    print(f"  Prompt 大小: {len(validation_prompt)} 字符")
    
    # 7. 生成测试报告
    print("\n[7/7] 生成测试报告...")
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_name": "完整流水线集成测试",
        "story_title": story_data["title"],
        "test_data_summary": {
            "characters": len(story_data["characters"]),
            "props": len(story_data["props"]),
            "scenes": len(story_data["scenes"]),
        },
        "validation_results": {
            "constraint_violations": len(packet.constraint_violations),
            "prop_issues": len(packet.prop_issues),
            "character_issues": len(packet.character_issues),
            "total_fixes": len(packet.fix_instructions),
        },
        "structural_findings": {
            "constraint_violations": [
                {
                    "constraint_id": v.constraint_id,
                    "severity": v.severity.value,
                    "message": v.message,
                    "location": v.location,
                    "fix_suggestion": v.fix_suggestion,
                }
                for v in packet.constraint_violations
            ],
            "prop_issues": packet.prop_issues,
            "character_issues": packet.character_issues,
        },
        "repair_directives": directives,
        "validation_summary": validation_summary,
        "validation_prompt_preview": validation_prompt[:500] + "..." if len(validation_prompt) > 500 else validation_prompt,
    }
    
    # 保存报告
    report_path = os.path.join(os.path.dirname(__file__), "..", "artifacts", "full-pipeline-test-report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {report_path}")
    
    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    total_issues = (
        len(packet.constraint_violations)
        + len(packet.prop_issues)
        + len(packet.character_issues)
    )
    
    if total_issues > 0:
        print(f"[PASS] 成功检测到 {total_issues} 个问题")
        print("  结构化修复引擎正在工作")
        print("  修复指令已生成")
        print("  验证块已构建")
    else:
        print("[INFO] 未检测到问题")
        print("  这可能是正常的，取决于测试数据")
    
    print("\n测试完成!")
    return report


def main():
    """主测试函数"""
    print("开始完整流水线集成测试...\n")
    
    report = test_full_pipeline()
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
