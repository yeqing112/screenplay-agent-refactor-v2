# 结构化修复框架 - 实现总结

## 项目概述

本项目将剧本生成系统的修复机制从**启发式关键词匹配**重构为**确定性结构化验证**。

## 核心改进

### 原系统（启发式）
```
QA发现问题 → 关键词分类 → LLM重写 → 再QA验证
     ↓              ↓                ↓
  发现6个问题    "人设"→character    "修复人设漂移"    可能引入新问题
  但fact层没防住   "道具"→prop        "修复道具连续性"
```

### 新系统（结构化）
```
生成前验证 → 生成中检查 → 生成后验证 → 确定性修复
     ↓              ↓                ↓
  发现潜在问题    实时状态追踪      结构化验证      确定性操作
  在fact层就防住
```

## 实现的模块

### 核心模块 (`core/repair/`)

| 文件 | 大小 | 功能 |
|------|------|------|
| `fact_constraints.py` | 14KB | 事实约束验证器 |
| `prop_tracker.py` | 11KB | 道具/证据追踪器 |
| `character_state_machine.py` | 9KB | 角色状态机 |
| `structural_repair_engine.py` | 10KB | 结构化修复引擎 |
| `structural_validation_integration.py` | 6KB | 生产技能集成 |
| `integration.py` | 2KB | 通用集成接口 |
| `__init__.py` | 2KB | 模块导出 |

### 测试文件

| 文件 | 功能 |
|------|------|
| `test_structural_repair.py` | 核心模块测试 |
| `test_complete_integration.py` | 完整集成测试 |

### 文档

| 文件 | 功能 |
|------|------|
| `README.md` | 模块说明文档 |
| `USAGE_GUIDE.md` | 使用指南 |

## 验证规则

### 约束验证
- **CHAR_HIDEN_NO_TRIGGER**: 角色展示隐藏层但没有触发器 (ERROR)
- **CHAR_STYLE_DRIFT**: 角色说话风格漂移 (WARNING)
- **PROP_LOCATION_CONFLICT**: 关键道具位置冲突 (ERROR)
- **PROP_TRANSFER_MISSING**: 道具转移缺少说明 (WARNING)
- **EVIDENCE_NOT_ON_SCREEN**: 关键证据未在画面展示 (ERROR)
- **TRANSITION_NO_TRIGGER**: 状态转换缺少触发器 (ERROR)

### 道具连续性
- 关键证据道具必须有明确的转移说明
- 转移方式必须合理（交给、偷走、发现等）
- 道具位置变化必须有转移记录

### 角色状态
- 隐藏层揭示前必须有铺垫
- 状态转换必须有触发器
- 说话风格必须与人设一致

## 集成到现有系统

### 1. 生产技能系统 (`production_skill.py`)

已集成到 `build_script_skill_repair_packet` 函数：
```python
# 新增字段
"structural_validation": {...},
"structural_repair_directives": [...],
"structural_validation_prompt": "...",
```

### 2. Rewrite Agent (`rewrite.py`)

已集成结构化验证到重写流程：
- 在构建修复包时调用结构化验证
- 将验证结果注入到重写 prompt 中

### 3. QA Agent (`qa_structural.py`)

已创建新的结构化 QA Agent：
- 结合结构化验证和 LLM 分析
- 生成更准确的修复指令

## 测试结果

```
=== 测试约束验证器 ===
发现 1 个违反
  [warning] 关键道具-玉佩 从 场景1 转移到 场景2 缺少转移说明

=== 测试道具追踪器 ===
发现 1 个连续性问题
  [INVALID_TRANSFER_METHOD] 道具 玉佩 的转移方式 '放在桌上' 不合理

=== 测试状态机 ===
发现 1 个转换问题
  [NO_REVEAL_SEEDING] 角色 主角A 在场景 场景2 揭示隐藏层，但之前没有铺垫

=== 集成测试 ===
约束违反: 1
道具问题: 0
角色问题: 0
修复指令: 1
```

## 使用方法

### 快速开始

```python
from core.repair import build_structural_validation_block, format_structural_validation_for_prompt

# 构建验证块
validation_block = build_structural_validation_block(foundation, scene_cards)

# 格式化为 prompt
prompt = format_structural_validation_for_prompt(validation_block)
```

### 完整流程

```python
from core.repair import StructuralRepairEngine

# 创建引擎
engine = StructuralRepairEngine(story_fact_sheet, scene_cards)

# 预验证
packet = engine.pre_generation_validation()

# 生成修复指令
directives = engine.generate_repair_directives(packet)

# 后验证
packet = engine.post_generation_validation(generated_script)
```

## 后续工作

1. **完善文本替换逻辑**: 实现确定性的文本修复操作
2. **扩展验证规则**: 添加更多场景-specific的验证规则
3. **性能优化**: 缓存验证结果，避免重复计算
4. **与现有测试集成**: 将结构化验证测试集成到 CI/CD 流程

## 文件结构

```
D:\Work\Project\screenplay-agent-refactor-v2\
├── core\
│   └── repair\
│       ├── __init__.py
│       ├── fact_constraints.py
│       ├── prop_tracker.py
│       ├── character_state_machine.py
│       ├── structural_repair_engine.py
│       ├── structural_validation_integration.py
│       ├── integration.py
│       ├── README.md
│       └── USAGE_GUIDE.md
├── agents\
│   ├── qa_structural.py
│   └── rewrite.py (已更新)
└── tests\
    ├── test_structural_repair.py
    └── test_complete_integration.py
```

## 结论

本实现成功将剧本生成系统的修复机制从启发式重构为结构化：
- **确定性验证**: 使用结构化验证器替代关键词匹配
- **实时追踪**: 道具和角色状态的实时追踪
- **精确修复**: 生成确定性的修复指令而非自然语言建议
- **集成完整**: 已集成到现有生产技能系统和 Agent 中
