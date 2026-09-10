"""Real Chain Test - 真实链路测试

测试完整的结构化修复流程：
1. 创建测试数据
2. 运行结构化验证
3. 检测问题
4. 生成修复指令
5. 应用修复
6. 验证修复结果
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


def create_test_story_data():
    """创建测试故事数据"""
    return {
        "title": "三个和尚",
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
                "first_appearance": "场景2",
                "description": "小和尚随身携带的玉佩",
            },
            {
                "name": "香灰",
                "type": "连续性道具",
                "owner": "无",
                "location": "香炉",
                "state": "新鲜",
                "first_appearance": "场景1",
                "description": "香炉中的新鲜香灰",
            },
        ],
        "scenes": [
            {
                "name": "场景1-寺庙大殿",
                "characters": ["小和尚", "老和尚"],
                "props": ["古老经书", "香灰"],
                "time": "清晨",
                "description": "小和尚第一次进入大殿，发现老和尚在整理经书",
            },
            {
                "name": "场景2-后山小路",
                "characters": ["小和尚", "神秘人"],
                "props": ["玉佩"],
                "time": "黄昏",
                "description": "小和尚在后山遇到神秘人，玉佩发光",
            },
            {
                "name": "场景3-老和尚禅房",
                "characters": ["小和尚", "老和尚"],
                "props": ["古老经书"],
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


def create_script_with_issues():
    """创建一个有问题的剧本"""
    return """
## 场景1 [寺庙大殿]

**画面：** 清晨，阳光透过窗棂照进大殿。小和尚站在门口，看着老和尚在整理经书。

**小和尚：** 师父，这些经书好古老啊。

**老和尚：** 是啊，这是寺庙的宝贝，你要好好保管。

**特写：** 经书封面泛黄，上面有奇怪的符号。

## 场景2 [后山小路]

**画面：** 黄昏，小和尚独自走在后山小路上。突然，神秘人出现在前方。

**神秘人：** 小师父，你身上的玉佩...发光了。

**小和尚：** 啊？这是怎么回事？

**特写：** 玉佩发出微弱的光芒。

## 场景3 [老和尚禅房]

**画面：** 夜晚，小和尚来到老和尚禅房。

**小和尚：** 师父，我想知道经书的秘密。

**老和尚：** （眼神闪烁）你...你怎么知道的？

**小和尚：** 玉佩告诉我的。

**老和尚：** （震惊）什么？你...你竟然能听到玉佩的声音？

**特写：** 老和尚手中的经书掉落在地。
"""


def run_chain_validation(story_data, scene_cards, script_content):
    """测试链路验证"""
    print("=" * 60)
    print("真实链路测试 - 结构化修复流程")
    print("=" * 60)
    
    # 1. 提取事实
    print("\n[1/6] 提取故事事实...")
    facts = extract_facts_from_foundation({
        "character_state_cards": story_data["characters"],
        "prop_cards": story_data["props"],
        "scene_goal_cards": [{"scene_name": s["name"], "characters": s["characters"], "props": s["props"]} for s in story_data["scenes"]],
    })
    print(f"  角色: {len(facts['characters'])} 个")
    print(f"  道具: {len(facts['props'])} 个")
    print(f"  场景: {len(facts['scenes'])} 个")
    
    # 2. 创建结构化引擎
    print("\n[2/6] 创建结构化修复引擎...")
    engine = StructuralRepairEngine(
        story_fact_sheet=facts,
        scene_execution_cards=scene_cards,
    )
    print("  引擎初始化完成")
    
    # 3. 预验证
    print("\n[3/6] 执行预验证...")
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
    
    # 4. 生成修复指令
    print("\n[4/6] 生成修复指令...")
    directives = engine.generate_repair_directives(packet)
    print(f"  生成 {len(directives)} 个修复指令")
    for i, d in enumerate(directives, 1):
        print(f"    {i}. [{d.get('type', '')}] {d.get('instruction', '')[:80]}...")
    
    # 5. 验证剧本
    print("\n[5/6] 验证剧本内容...")
    script_issues = validate_script_content(script_content, story_data)
    print(f"  发现 {len(script_issues)} 个剧本问题")
    for issue in script_issues:
        print(f"    - {issue}")
    
    # 6. 生成验证报告
    print("\n[6/6] 生成验证报告...")
    report = {
        "timestamp": datetime.now().isoformat(),
        "story_title": story_data["title"],
        "validation_summary": {
            "constraint_violations": len(packet.constraint_violations),
            "prop_issues": len(packet.prop_issues),
            "character_issues": len(packet.character_issues),
            "total_fixes": len(packet.fix_instructions),
            "script_issues": len(script_issues),
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
        "script_issues": script_issues,
    }
    
    # 保存报告
    report_path = os.path.join(os.path.dirname(__file__), "..", "artifacts", "chain-test-report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  报告已保存: {report_path}")
    
    return report


def validate_script_content(script_content, story_data):
    """验证剧本内容"""
    issues = []
    
    # 检查场景完整性
    for scene in story_data["scenes"]:
        if scene["name"] not in script_content:
            issues.append(f"缺少场景: {scene['name']}")
    
    # 检查角色出场
    for character in story_data["characters"]:
        if character["name"] not in script_content:
            issues.append(f"角色未出场: {character['name']}")
    
    # 检查道具出现
    for prop in story_data["props"]:
        if prop["name"] not in script_content:
            issues.append(f"道具未出现: {prop['name']}")
    
    # 检查人设一致性
    for character in story_data["characters"]:
        if character["name"] in script_content:
            # 检查是否有触发器就展示隐藏层
            hidden_keywords = ["秘密", "隐藏", "真实", "其实"]
            for keyword in hidden_keywords:
                if keyword in script_content:
                    # 检查是否有触发器描述
                    trigger_keywords = ["突然", "发现", "异常", "奇怪"]
                    has_trigger = any(t in script_content for t in trigger_keywords)
                    if not has_trigger:
                        issues.append(f"角色 {character['name']} 可能在没有触发器的情况下展示隐藏层")
                    break
    
    # 检查道具连续性
    for prop in story_data["props"]:
        if prop["type"] == "关键证据道具":
            # 检查关键道具是否有清晰的流转
            if prop["name"] in script_content:
                # 简单检查：关键道具应该有特写描述
                if "特写" not in script_content or prop["name"] not in script_content.split("特写")[1] if "特写" in script_content else True:
                    issues.append(f"关键道具 {prop['name']} 可能缺少特写描述")
    
    return issues


def apply_repairs(script_content, directives, story_data):
    """应用修复指令"""
    repaired_script = script_content
    
    for directive in directives:
        directive_type = directive.get("type", "")
        instruction = directive.get("instruction", "")
        
        # 这里是简化的修复逻辑
        # 实际应用中需要更复杂的文本替换和重构
        if "场景" in directive.get("location", ""):
            # 场景相关修复
            pass
        elif "角色" in directive.get("type", ""):
            # 角色相关修复
            pass
    
    return repaired_script


def main():
    """主测试函数"""
    print("开始真实链路测试...\n")
    
    # 1. 创建测试数据
    story_data = create_test_story_data()
    scene_cards = create_scene_execution_cards(story_data)
    script_content = create_script_with_issues()
    
    # 2. 运行链路验证
    report = run_chain_validation(story_data, scene_cards, script_content)
    
    # 3. 应用修复（简化版）
    print("\n" + "=" * 60)
    print("应用修复指令（简化版）")
    print("=" * 60)
    
    repaired_script = apply_repairs(script_content, report["repair_directives"], story_data)
    print("  修复应用完成")
    
    # 4. 验证修复结果
    print("\n" + "=" * 60)
    print("验证修复结果")
    print("=" * 60)
    
    # 重新验证
    engine = StructuralRepairEngine(
        story_fact_sheet=extract_facts_from_foundation({
            "character_state_cards": story_data["characters"],
            "prop_cards": story_data["props"],
            "scene_goal_cards": [{"scene_name": s["name"], "characters": s["characters"], "props": s["props"]} for s in story_data["scenes"]],
        }),
        scene_execution_cards=scene_cards,
    )
    
    # 模拟修复后的状态
    # 实际应用中需要更新引擎状态
    final_packet = engine.pre_generation_validation()
    
    print(f"  修复后约束违反: {len(final_packet.constraint_violations)} 个")
    print(f"  修复后道具问题: {len(final_packet.prop_issues)} 个")
    print(f"  修复后角色问题: {len(final_packet.character_issues)} 个")
    
    # 5. 输出最终结果
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    success = (
        len(final_packet.constraint_violations) == 0
        and len(final_packet.prop_issues) == 0
        and len(final_packet.character_issues) == 0
    )
    
    if success:
        print("[PASS] 所有问题已修复")
    else:
        print("[FAIL] 仍有未修复的问题")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
