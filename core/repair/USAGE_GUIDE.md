# 结构化修复框架使用指南

## 概述

本指南说明如何在现有剧本生成系统中使用新的结构化修复框架。

## 快速开始

### 1. 在 Rewrite Agent 中使用

```python
from core.repair import (
    build_structural_validation_block,
    format_structural_validation_for_prompt,
)

# 在构建修复包时
def build_repair_packet_with_structural_validation(
    foundation: dict,
    scene_execution_cards: list,
) -> dict:
    # 构建结构化验证块
    validation_block = build_structural_validation_block(
        foundation=foundation,
        scene_execution_cards=scene_execution_cards,
    )
    
    # 格式化为 prompt 块
    validation_prompt = format_structural_validation_for_prompt(validation_block)
    
    return {
        "structural_validation": validation_block["structural_validation"],
        "structural_repair_directives": validation_block["repair_directives"],
        "structural_validation_prompt": validation_prompt,
    }
```

### 2. 在 QA Agent 中使用

```python
from core.repair import StructuralRepairEngine

def run_structural_qa(story_fact_sheet: dict, scene_execution_cards: list) -> dict:
    # 创建结构化引擎
    engine = StructuralRepairEngine(
        story_fact_sheet=story_fact_sheet,
        scene_execution_cards=scene_execution_cards,
    )
    
    # 执行验证
    packet = engine.pre_generation_validation()
    
    return {
        "constraint_violations": packet.constraint_violations,
        "prop_issues": packet.prop_issues,
        "character_issues": packet.character_issues,
        "fix_instructions": packet.fix_instructions,
    }
```

### 3. 在生产技能系统中使用

```python
from core.production_skill import build_script_skill_repair_packet

# 现有的 repair_packet 已经包含结构化验证
repair_packet = build_script_skill_repair_packet(
    book_id=book_id,
    episode_outline=episode_outline,
    qa_issues=qa_issues,
    script_content=script_content,
)

# 新增的字段
structural_validation = repair_packet.get("structural_validation", {})
structural_directives = repair_packet.get("structural_repair_directives", [])
structural_prompt = repair_packet.get("structural_validation_prompt", "")
```

## 验证规则

### 约束验证规则

| 规则ID | 说明 | 严重程度 |
|--------|------|----------|
| CHAR_HIDEN_NO_TRIGGER | 角色展示隐藏层但没有触发器 | ERROR |
| CHAR_STYLE_DRIFT | 角色说话风格漂移 | WARNING |
| PROP_LOCATION_CONFLICT | 关键道具位置冲突 | ERROR |
| PROP_TRANSFER_MISSING | 道具转移缺少说明 | WARNING |
| EVIDENCE_NOT_ON_SCREEN | 关键证据未在画面展示 | ERROR |
| TRANSITION_NO_TRIGGER | 状态转换缺少触发器 | ERROR |

### 道具连续性规则

- 关键证据道具必须有明确的转移说明
- 转移方式必须合理（交给、偷走、发现等）
- 道具位置变化必须有转移记录

### 角色状态规则

- 隐藏层揭示前必须有铺垫
- 状态转换必须有触发器
- 说话风格必须与人设一致

## 修复指令格式

```python
{
    "type": "CONSTRAINT_FIX | PROP_FIX | CHARACTER_FIX",
    "priority": 1,  # 1=高, 2=中, 3=低
    "location": "场景名称",
    "instruction": "具体修复指令",
    "affected_entities": ["受影响的实体"],
}
```

## 集成到现有流程

### 生成前验证

```python
# 在生成剧本前
validation_block = build_structural_validation_block(foundation, scene_cards)

if validation_block["structural_validation"]["validation_summary"]["total_fixes"] > 0:
    # 有需要修复的问题
    print("警告：发现结构化问题，需要修复")
    # 可以选择暂停生成或继续
```

### 生成后验证

```python
# 在生成剧本后
engine = StructuralRepairEngine(story_fact_sheet, scene_cards)
packet = engine.post_generation_validation(generated_script)

if packet.fix_instructions:
    # 有需要应用的修复
    for fix in packet.fix_instructions:
        print(f"修复: {fix['instruction']}")
```

## 测试

运行所有测试：
```bash
cd D:\Work\Project\screenplay-agent-refactor-v2
python -m tests.test_structural_repair
python -m tests.test_complete_integration
```

## 故障排除

### 常见问题

1. **导入错误**
   ```
   ImportError: cannot import name 'StructuralRepairEngine'
   ```
   解决：确保 `core/repair` 目录存在且包含所有必要文件

2. **验证结果为空**
   检查 `story_fact_sheet` 和 `scene_execution_cards` 是否正确格式化

3. **修复指令不正确**
   检查 `ConstraintViolation` 的 `fix_suggestion` 字段是否正确设置

## 下一步工作

1. 完善文本替换逻辑
2. 添加更多场景-specific验证规则
3. 性能优化和缓存
4. 与现有测试套件集成
