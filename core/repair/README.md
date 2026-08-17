# 结构化修复框架实现总结

## 概述

本框架将剧本生成系统的修复机制从**启发式关键词匹配**重构为**确定性结构化验证**。

### 核心改进

| 原系统（启发式） | 新系统（结构化） |
|------------------|------------------|
| QA发现问题 → 关键词分类 → LLM重写 → 再QA | 生成前验证 → 生成中检查 → 生成后验证 → 确定性修复 |
| 依赖LLM理解"人设漂移" | 结构化状态机追踪角色层级 |
| 依赖关键词匹配"道具连续性" | 道具追踪器验证转移链 |
| 修复建议是自然语言 | 修复指令是确定性操作 |

## 模块结构

```
core/repair/
├── __init__.py                    # 模块导出
├── fact_constraints.py            # 事实约束验证器
├── prop_tracker.py                # 道具/证据追踪器
├── character_state_machine.py     # 角色状态机
├── structural_repair_engine.py    # 结构化修复引擎
└── integration.py                 # 集成接口
```

## 核心模块说明

### 1. Fact Constraint Validator (fact_constraints.py)

**功能**：验证事实层级约束

**验证规则**：
- 角色人设一致性：公开层/隐藏层不混淆
- 道具唯一性：关键道具不重复/不丢失
- 证据可见性：关键证据必须在画面中
- 状态转换：转换必须有触发器

**使用示例**：
```python
from core.repair import FactConstraintValidator, CharacterFact, PropFact

# 创建验证器
validator = FactConstraintValidator(
    characters=[CharacterFact(...)],
    props=[PropFact(...)],
    scenes=[...],
)

# 执行验证
violations = validator.validate_all()
```

### 2. Prop Tracker (prop_tracker.py)

**功能**：追踪道具在场景间的流转

**验证规则**：
- 关键道具位置冲突检测
- 道具转移链完整性验证
- 转移方式合理性检查

**使用示例**：
```python
from core.repair import PropTracker, PropRecord, PropType

tracker = PropTracker()

# 注册道具
tracker.register_prop(PropRecord(
    name="玉佩",
    prop_type=PropType.KEY_EVIDENCE,
    ...
))

# 记录场景出现
tracker.add_scene_prop("场景1", "玉佩", holder="主角A")

# 验证连续性
issues = tracker.validate_continuity()
```

### 3. Character State Machine (character_state_machine.py)

**功能**：追踪角色状态转换

**验证规则**：
- 状态转换触发器验证
- 人设层级混淆检测
- 隐藏层揭示铺垫检查

**使用示例**：
```python
from core.repair import CharacterStateMachine, CharacterState, TransitionType

machine = CharacterStateMachine()

# 注册角色
machine.register_character(CharacterState(
    name="主角A",
    public_persona="懒散的守卫",
    hidden_layer="隐藏的高手",
    ...
))

# 记录转换
machine.record_transition(
    "主角A",
    from_state="懒散",
    to_state="警觉",
    transition_type=TransitionType.REVEAL,
    trigger="压力触发",
    scene="场景2",
)

# 验证转换
issues = machine.validate_transitions()
```

### 4. Structural Repair Engine (structural_repair_engine.py)

**功能**：整合所有验证器，提供统一接口

**使用示例**：
```python
from core.repair import StructuralRepairEngine

# 创建引擎
engine = StructuralRepairEngine(
    story_fact_sheet={...},
    scene_execution_cards=[...],
)

# 预验证
packet = engine.pre_generation_validation()

# 生成修复指令
directives = engine.generate_repair_directives(packet)

# 后验证（生成剧本后）
packet = engine.post_generation_validation(generated_script)
```

## 集成到现有系统

### 在 Rewrite Agent 中使用

```python
from core.repair import build_structural_repair_context

# 在生成前构建上下文
context = build_structural_repair_context(
    book_id=book_id,
    episode=episode,
    story_fact_sheet=story_fact_sheet,
    scene_execution_cards=scene_execution_cards,
)

# 将修复指令注入prompt
repair_directives = context["repair_directives"]
prompt = f"{base_prompt}\n\n## Structural Repair Directives\n{format_directives(repair_directives)}"

# 生成剧本后验证
engine = context["engine"]
validation_result = validate_generated_script(engine, generated_script)
```

### 在 QA Agent 中使用

```python
from core.repair import StructuralRepairEngine

# 创建引擎
engine = StructuralRepairEngine(story_fact_sheet, scene_execution_cards)

# 执行验证
packet = engine.pre_generation_validation()

# 合并LLM分析结果
structural_issues = packet.constraint_violations + packet.prop_issues + packet.character_issues
llm_issues = llm_result.get("issues", [])

# 去重并排序
merged_issues = merge_and_deduplicate(structural_issues, llm_issues)
```

## 测试

运行测试：
```bash
cd D:\Work\Project\screenplay-agent-refactor-v2
python -m tests.test_structural_repair
```

## 后续工作

1. **完善文本替换逻辑**：实现 `apply_structural_repair_directives` 中的具体替换规则
2. **扩展验证规则**：添加更多场景-specific的验证规则
3. **性能优化**：缓存验证结果，避免重复计算
4. **与现有生产技能集成**：修改 `production_skill.py` 使用新的结构化验证
