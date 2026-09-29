# Shot Studio Spec

## Purpose

镜头工作台是单镜头的生产和审核空间。它只负责把一个 Shot 从计划推进到候选和正式媒体，不承担项目级任务聚合。

## Layout

```text
┌──────────────────────────────────────────────┐
│ 面包屑 / 镜头身份 / 状态 / 版本              │
├──────────────┬────────────────┬──────────────┤
│ 镜头列表     │ 主工作区        │ 审核抽屉     │
│ episode/scene│ 计划 | 资产     │ 证据 | 决策   │
│ blocker摘要  │ IMAGE | VIDEO   │ 历史 | 回退   │
└──────────────┴────────────────┴──────────────┘
```

## Main workspaces

1. **计划**：shot type、camera、lens、movement、composition、emotion、action。
2. **资产**：人物、场景、道具绑定，显示正式资产和缺失原因。
3. **IMAGE**：prompt lineage、模型上下文、候选、正式图片。
4. **VIDEO**：来源图片、视频提示词、候选、正式视频。
5. **连续性**：入场/出场状态、继承规则、允许变化和禁止变化。

## Interaction rules

- 保存镜头计划创建新版本，保留上一版只读。
- 生成按钮只创建候选，不自动晋升正式版本。
- 任何“正式”操作都打开审核抽屉并要求原因。
- 缺少资产时，主 CTA 为“去绑定资产”，生成按钮保持禁用并解释原因。
- 专业诊断显示 `shot_id`、`PromptIR`、`GenerationExecution`、provider 和 request id。

## Required API compatibility

现有服务继续使用：`/api/books/{bookId}/production-workspace-v2`、`/storyboard/{episode}/{shotId}/generate-frame`、`generate-video`、`prompt-versions`、`acceptance-records`。V3 只改变编排和呈现。

