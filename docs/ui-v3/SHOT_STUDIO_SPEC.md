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

## Automatic keyframe review

关键帧是 Shot Pipeline 的人工门。Main Canvas 以 START / MIDDLE / END 三张 Storyboard Card 呈现，不要求用户阅读 JSON 或编辑内部计划对象。每张卡显示：

- 时间点和镜头总时长
- 画面描述和动作变化
- 人物状态、场景状态和情绪
- 景别、机位、镜头运动
- 使用的正式资产和来源版本
- 当前关键帧计划版本与 stale 原因

主动作是“批准并继续”，次动作是“要求修改”，高级动作才是“驳回”。批准后必须按 `review → compile → refresh production state` 顺序调用现有 API。

## Image candidate review

图片候选采用视觉网格：候选 A/B/C 显示大图、生成时间、当前关键帧、人物一致性、场景一致性和正式版本标记。支持 Grid、Compare、Select；`采用` 进入 media authority validate/promote，未通过技术验证时解释缺失项。

## Video candidate review

视频候选采用播放器优先布局，旁边显示 START/END 对照、Prompt 摘要、ShotDirection 摘要和连续性结果。主动作是“通过”，次动作是“要求重做”；provider、执行记录、任务号和 lineage 只在“生产详情”抽屉出现。

## Stage resolver

```text
导演方案待审核 → 查看导演方案
场面调度待审核 → 审核场面调度
镜头计划待确认 → 审核镜头计划
关键帧待审核 → 审核关键帧
图片候选待审核 → 审核图片
视频候选待审核 → 审核视频
正式视频已建立 → 查看正式结果
技术/依赖异常 → 查看阻塞
```

同一时间只显示一个主 CTA；其余阶段作为 pipeline 节点和上下文，不再各自抢主按钮。

## Interaction rules

- 保存镜头计划创建新版本，保留上一版只读。
- 生成按钮只创建候选，不自动晋升正式版本。
- 任何“正式”操作都打开审核抽屉并要求原因。
- 缺少资产时，主 CTA 为“去绑定资产”，生成按钮保持禁用并解释原因。
- 专业诊断显示 `shot_id`、`PromptIR`、`GenerationExecution`、provider 和 request id。

## Required API compatibility

现有服务继续使用：`/api/books/{bookId}/production-workspace-v2`、`/storyboard/{episode}/{shotId}/generate-frame`、`generate-video`、`prompt-versions`、`acceptance-records`。V3 只改变编排和呈现。
