# 结构化修复引擎 - 改进计划文档（已对齐项目蓝图）

## 文档信息

- **创建时间**: 2026-08-16
- **版本**: v2.0（已对齐项目蓝图）
- **状态**: 待执行
- **对齐文档**: 
  - `docs/产品重构蓝图.md`
  - `docs/产品重构阶段任务与验收标准.md`
  - `docs/2026-08-14-script-skill-general-remediation-plan.md`

---

## 1. 项目背景与对齐

### 1.1 项目蓝图核心原则

根据 `docs/产品重构蓝图.md` 和 `docs/产品重构阶段任务与验收标准.md`，项目当前的核心原则是：

> **停止继续堆启发式规则，转向结构化生成**

具体要求：
1. 先生成结构，再编译成剧本
2. QA 以结构检查为主，不再主要依赖标题关键词命中
3. Rewrite 以结构回写为主，不再继续扩大样本导向补丁库

### 1.2 结构化生成整改目标

根据 `docs/产品重构阶段任务与验收标准.md` 阶段 S1 和 S2：

**阶段 S1：剧本结构中间层落地**
- 在 Script Skill foundation 中新增 `story_fact_sheet`
- 在 Script Generation Brief 中新增 `scene_execution_cards`
- 在 Execution Plan 中新增结构化编译阶段

**阶段 S2：结构校验优先化**
- 增加事实层一致性校验
- 增加场景执行卡兑现校验
- QA 输出优先映射到结构缺口

### 1.3 本改进计划的定位

本改进计划是**结构化修复引擎**的实现细节，直接服务于项目蓝图的结构化生成整改目标。

---

## 2. 当前状态总结

### 2.1 已完成的功能

| 模块 | 文件 | 状态 | 与蓝图对齐 |
|------|------|------|------------|
| 事实约束验证器 | `core/repair/fact_constraints.py` | 部分完成 | ✅ 服务于阶段 S2 |
| 道具追踪器 | `core/repair/prop_tracker.py` | 已完成 | ✅ 服务于事实层校验 |
| 角色状态机 | `core/repair/character_state_machine.py` | 部分完成 | ✅ 服务于角色状态系统 |
| 结构化修复引擎 | `core/repair/structural_repair_engine.py` | 已完成 | ✅ 整合框架 |
| 集成模块 | `core/repair/integration.py` | 已完成 | ✅ 接口正常 |
| 验证集成 | `core/repair/structural_validation_integration.py` | 已完成 | ✅ 集成正常 |

### 2.2 已通过的测试

| 测试文件 | 状态 | 说明 |
|----------|------|------|
| test_structural_repair.py | PASS | 核心模块单元测试 |
| test_complete_integration.py | PASS | 完整集成测试 |
| test_chain_with_issues.py | PASS | 带问题的链路测试 |
| test_full_pipeline.py | PASS | 完整流水线测试 |

### 2.3 已检测到的问题

通过 `test_comprehensive_issues.py` 测试发现：

| 问题类型 | 测试状态 | 严重程度 | 与蓝图关系 |
|----------|----------|----------|------------|
| 隐藏层检测 | FAIL | 高 | 阻塞阶段 S2 |
| 风格漂移检测 | FAIL | 高 | 阻塞阶段 S2 |
| 验证逻辑覆盖率 | 88.9% | 中 | 影响阶段 S2 |
| 角色状态机覆盖率 | 100% | 低 | 已完成 |

---

## 3. 发现的问题详细分析

### 3.1 数据流问题（关键）

**问题描述**：场景内容（`content`字段）没有被正确传递到验证器。

**问题位置**：`core/repair/structural_validation_integration.py` 第57-65行

**与蓝图的关系**：
- 阻塞阶段 S2 的"事实层一致性校验"
- 阻塞阶段 S2 的"场景执行卡兑现校验"

**修复方案**：
```python
# 修复后
scene_cards = foundation.get("scene_goal_cards", [])
for card in scene_cards:
    story_fact_sheet["scenes"].append({
        "name": card.get("scene_name", ""),
        "characters": card.get("characters", []),
        "props": card.get("props", []),
        "content": card.get("content", ""),  # 添加content字段
    })
```

### 3.2 验证器实现不完整

**问题描述**：部分验证方法是占位符，没有实际实现。

**与蓝图的关系**：
- 阻塞阶段 S2 的"事实层一致性校验"
- 阻塞阶段 S2 的"人设公开面连续性"检查

**修复方案**：
需要实现基于NLP的风格分析，或使用更精确的规则匹配。

### 3.3 关键词匹配过于简单

**问题描述**：当前验证器依赖简单的关键词匹配，而不是语义理解。

**与蓝图的关系**：
- 违背蓝图原则"停止继续堆启发式规则"
- 需要转向结构化检查

**修复方案**：
1. 扩展关键词列表
2. 使用上下文匹配，而不是简单的关键词存在性检查
3. 考虑使用LLM进行语义分析

### 3.4 测试数据不够全面

**问题描述**：测试数据没有覆盖所有边界情况。

**与蓝图的关系**：
- 影响阶段 S2 的验收标准
- 需要"真实样本回归"

**修复方案**：
创建更全面的测试数据，覆盖所有验证规则。

---

## 4. 改进计划（对齐蓝图阶段）

### 4.1 第一阶段：修复数据流问题（优先级：高）

**目标**：确保场景内容被正确传递到验证器。

**与蓝图的关系**：
- 服务于阶段 S1："在 Script Skill foundation 中新增 `story_fact_sheet`"
- 服务于阶段 S2："增加事实层一致性校验"

**任务清单**：

| 任务 | 文件 | 预计时间 | 蓝图对齐 |
|------|------|----------|----------|
| 修改 extract_facts_from_foundation 函数 | structural_validation_integration.py | 1小时 | S1 |
| 更新测试数据，包含content字段 | tests/test_comprehensive_issues.py | 1小时 | S2 |
| 运行测试验证修复效果 | - | 30分钟 | S2 |

**验收标准**：
- [ ] 场景内容被正确传递到验证器
- [ ] `_scene_shows_hidden_layer()` 能够检测到隐藏层行为
- [ ] `_has_trigger_in_scene()` 能够检测到触发器
- [ ] 测试用例通过

### 4.2 第二阶段：完善验证逻辑（优先级：高）

**目标**：实现占位符方法，提高验证覆盖率。

**与蓝图的关系**：
- 服务于阶段 S2："增加事实层一致性校验"
- 服务于阶段 S2："人设公开面连续性"
- 服务于阶段 S2："隐藏层触发器存在性"

**任务清单**：

| 任务 | 文件 | 预计时间 | 蓝图对齐 |
|------|------|----------|----------|
| 实现 `_dialogue_style_drifts()` 方法 | fact_constraints.py | 4小时 | S2 |
| 实现 `_check_speech_style_drift()` 方法 | character_state_machine.py | 4小时 | S2 |
| 创建风格分析工具 | core/repair/style_analyzer.py | 8小时 | S2 |
| 编写风格分析测试 | tests/test_style_analysis.py | 4小时 | S2 |

**验收标准**：
- [ ] `_dialogue_style_drifts()` 能够检测到说话风格漂移
- [ ] `_check_speech_style_drift()` 能够检测到风格变化
- [ ] 验证逻辑覆盖率达到100%
- [ ] 测试用例通过

### 4.3 第三阶段：增强关键词匹配（优先级：中）

**目标**：提高关键词匹配的准确性，减少误报和漏报。

**与蓝图的关系**：
- 需要平衡"结构化检查"和"关键词匹配"
- 遵循蓝图原则"停止继续堆启发式规则"

**任务清单**：

| 任务 | 文件 | 预计时间 | 蓝图对齐 |
|------|------|----------|----------|
| 扩展隐藏层关键词列表 | fact_constraints.py | 2小时 | S2 |
| 扩展触发器关键词列表 | fact_constraints.py | 2小时 | S2 |
| 实现上下文匹配逻辑 | fact_constraints.py | 4小时 | S2 |
| 创建关键词匹配测试 | tests/test_keyword_matching.py | 2小时 | S2 |

**验收标准**：
- [ ] 关键词列表覆盖所有常见场景
- [ ] 上下文匹配逻辑正确工作
- [ ] 误报率降低50%
- [ ] 漏报率降低50%
- [ ] 测试用例通过

### 4.4 第四阶段：创建全面测试数据（优先级：中）

**目标**：创建覆盖所有验证规则的测试数据。

**与蓝图的关系**：
- 服务于阶段 S2 的验收标准
- 需要"真实样本回归"

**任务清单**：

| 任务 | 文件 | 预计时间 | 蓝图对齐 |
|------|------|----------|----------|
| 创建隐藏层检测测试数据 | tests/test_data/hidden_layer.json | 2小时 | S2 |
| 创建风格漂移测试数据 | tests/test_data/style_drift.json | 2小时 | S2 |
| 创建道具连续性测试数据 | tests/test_data/prop_continuity.json | 2小时 | S2 |
| 创建状态转换测试数据 | tests/test_data/state_transition.json | 2小时 | S2 |
| 更新综合测试脚本 | tests/test_comprehensive_issues.py | 2小时 | S2 |

**验收标准**：
- [ ] 测试数据覆盖所有验证规则
- [ ] 每个规则至少有3个测试用例
- [ ] 测试数据包含边界情况
- [ ] 综合测试脚本通过

### 4.5 第五阶段：集成到实际流程（优先级：低）

**目标**：测试与实际API和Agent的集成。

**与蓝图的关系**：
- 服务于阶段 S1："让 Rewrite / QA 开始读取这些新结构"
- 服务于阶段 S2："QA 输出优先映射到结构缺口"

**任务清单**：

| 任务 | 文件 | 预计时间 | 蓝图对齐 |
|------|------|----------|----------|
| 修改API服务器，集成结构化验证 | api/server.py | 4小时 | S1 |
| 修改Rewrite Agent，使用结构化验证 | agents/rewrite.py | 4小时 | S1 |
| 创建端到端测试 | tests/test_e2e_integration.py | 8小时 | S2 |
| 性能测试和优化 | tests/test_performance.py | 4小时 | S2 |

**验收标准**：
- [ ] API服务器能够调用结构化验证
- [ ] Rewrite Agent能够使用验证结果
- [ ] 端到端测试通过
- [ ] 性能测试通过

### 4.6 第六阶段：增强内容分析（优先级：低）

**目标**：使用LLM进行语义分析，提高验证准确性。

**与蓝图的关系**：
- 服务于阶段 S2 的高级校验需求
- 需要平衡"结构化检查"和"LLM分析"

**任务清单**：

| 任务 | 文件 | 预计时间 | 蓝图对齐 |
|------|------|----------|----------|
| 创建LLM分析接口 | core/repair/llm_analyzer.py | 8小时 | S2 |
| 实现隐藏层语义分析 | core/repair/llm_analyzer.py | 4小时 | S2 |
| 实现风格漂移语义分析 | core/repair/llm_analyzer.py | 4小时 | S2 |
| 创建LLM分析测试 | tests/test_llm_analysis.py | 4小时 | S2 |

**验收标准**：
- [ ] LLM分析接口正常工作
- [ ] 隐藏层语义分析准确率>90%
- [ ] 风格漂移语义分析准确率>90%
- [ ] 测试用例通过

---

## 5. 优先级排序（对齐蓝图）

| 阶段 | 优先级 | 预计时间 | 蓝图对齐 | 依赖关系 |
|------|--------|----------|----------|----------|
| 第一阶段：修复数据流问题 | 高 | 2.5小时 | S1, S2 | 无 |
| 第二阶段：完善验证逻辑 | 高 | 20小时 | S2 | 第一阶段 |
| 第三阶段：增强关键词匹配 | 中 | 10小时 | S2 | 第一阶段 |
| 第四阶段：创建全面测试数据 | 中 | 10小时 | S2 | 第一阶段 |
| 第五阶段：集成到实际流程 | 低 | 20小时 | S1, S2 | 第二阶段 |
| 第六阶段：增强内容分析 | 低 | 20小时 | S2 | 第二阶段 |

**总计预计时间**：82.5小时

---

## 6. 验收标准（对齐蓝图）

### 6.1 功能标准

- [ ] 所有验证规则都能正确检测
- [ ] 验证逻辑覆盖率达到100%
- [ ] 误报率<10%
- [ ] 漏报率<10%

### 6.2 性能标准

- [ ] 单次验证时间<1秒
- [ ] 内存使用<100MB
- [ ] 支持并发验证

### 6.3 集成标准

- [ ] 能够集成到API服务器
- [ ] 能够集成到Rewrite Agent
- [ ] 端到端测试通过

### 6.4 蓝图对齐标准

- [ ] 验证器能检测到事实层缺口
- [ ] 验证器能检测到场景执行层缺口
- [ ] QA 输出能映射到结构字段缺口
- [ ] Rewrite 能回写结构缺口

---

## 7. 风险评估

| 风险 | 影响 | 可能性 | 缓解措施 |
|------|------|--------|----------|
| LLM分析成本过高 | 高 | 中 | 使用缓存，限制调用频率 |
| 关键词匹配不准确 | 中 | 高 | 人工审核，持续优化 |
| 测试数据不充分 | 中 | 中 | 持续补充测试用例 |
| 集成到实际流程复杂 | 高 | 中 | 分阶段集成，逐步验证 |

---

## 8. 附录

### 8.1 相关文件列表

```
core/repair/
├── __init__.py
├── fact_constraints.py              # 事实约束验证器
├── prop_tracker.py                  # 道具追踪器
├── character_state_machine.py       # 角色状态机
├── structural_repair_engine.py      # 结构化修复引擎
├── integration.py                   # 集成模块
├── structural_validation_integration.py  # 验证集成
├── README.md                        # 模块说明
├── USAGE_GUIDE.md                   # 使用指南
├── IMPLEMENTATION_SUMMARY.md        # 实现总结
└── IMPROVEMENT_PLAN.md              # 改进计划文档（本文档）

tests/
├── test_structural_repair.py        # 核心模块测试
├── test_complete_integration.py     # 完整集成测试
├── test_chain_with_issues.py        # 带问题的链路测试
├── test_full_pipeline.py            # 完整流水线测试
└── test_comprehensive_issues.py     # 全面问题测试

artifacts/
├── chain-test-report.json           # 链路测试报告
├── chain-test-report.md             # 链路测试报告(Markdown)
├── chain-test-with-issues-report.json  # 带问题的链路测试报告
└── full-pipeline-test-report.json   # 完整流水线测试报告
```

### 8.2 参考文档

- [产品重构蓝图](docs/产品重构蓝图.md)
- [产品重构阶段任务与验收标准](docs/产品重构阶段任务与验收标准.md)
- [Script Skill General Remediation Plan](docs/2026-08-14-script-skill-general-remediation-plan.md)
- [结构化修复引擎README](core/repair/README.md)
- [使用指南](core/repair/USAGE_GUIDE.md)
- [实现总结](core/repair/IMPLEMENTATION_SUMMARY.md)
- [链路测试报告](artifacts/chain-test-report.md)

---

**文档结束**
