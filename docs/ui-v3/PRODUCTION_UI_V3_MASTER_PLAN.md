# Production UI V3 Master Plan

## North star

让创作成员围绕“当前对象、当前证据、唯一下一步”工作，同时让专业成员可以追踪版本、血缘和执行记录。

## Current problems

- 现有 11 个入口按功能和 Runtime 投影拼接，用户工作流被拆散。
- 项目首页、资产页、镜头页和任务中心重复显示生产状态与 blocker。
- 普通用户看到 PromptIR、GenerationExecution、FORMAL_ASSET_BINDINGS 等工程概念。
- 关键帧、图片候选、视频候选和集级自动制作没有完整的一级审核与活动体验。
- Provider pending、stale、recovery 和 technical blocked 没有统一的业务语言。

详见 [CURRENT_UI_UX_AUDIT.md](CURRENT_UI_UX_AUDIT.md)。

## Product principles

1. 用户永远知道现在在哪、发生了什么、为什么停、下一步是什么。
2. 默认隐藏工程概念，专业详情保留完整 lineage。
3. Human Review 是一级产品能力。
4. 每个关键页面只有一个主 CTA。
5. UI V3 复用 Runtime、service、domain 和 API，不建立第二套生产规则。

## New information architecture

```text
项目
├─ 制片台
├─ 剧本与导演
├─ 镜头工坊
├─ 资产库
└─ 交付与设置
```

该结构由当前导航、组件挂载和真实页面证据验证，详见 [INFORMATION_ARCHITECTURE_V3.md](INFORMATION_ARCHITECTURE_V3.md)。

## Core journeys

创建项目 → 导入内容 → AI 导演 → 分镜审核 → 关键帧审核 → 图片审核 → 视频审核 → Episode 自动制作 → QA → 交付。每个阶段都通过对象上下文和深链承接，不要求用户理解任务 id 或恢复机制。

## Screen map

| V3 screen | Core responsibility |
|---|---|
| 制片台 / Production Dashboard | Episode progress、Review Inbox、Active Generation、Blocking Issues、Recent Results |
| 剧本与导演 | 内容、方向、导演方案、场面调度、剧本审核 |
| 镜头工坊 / Shot Studio | Shot list、导演、关键帧、图片、视频、连续性、审核 |
| 资产库 / Asset Library | 人物、场景、道具、风格、媒体和版本 |
| 交付与设置 | QA、导出、模型中心、存储设置 |

## Design system

采用安静、专业、电影感的桌面工作台语言：深色中性 surface、低饱和状态色、有限主色、媒体优先、无廉价发光和大面积渐变。Typography、spacing、radius、elevation、status pills、media viewer、timeline、shot/review card 见 [DESIGN_SYSTEM_V3.md](DESIGN_SYSTEM_V3.md)。

## Review system

Director、Storyboard、KeyframePlan、Image Candidate、Video Candidate 共享 Review Inbox、Review Card、Review Drawer、Approve/Revise/Reject 决策和版本证据。详见 [REVIEW_SYSTEM_SPEC.md](REVIEW_SYSTEM_SPEC.md)。

## Shot Studio

Shot 是基本工作单元，固定导演 → 关键帧 → 图片 → 视频 → 完成的 pipeline；关键帧以 START/MIDDLE/END Storyboard Card 审核，图片和视频以视觉对照审核。详见 [SHOT_STUDIO_SPEC.md](SHOT_STUDIO_SPEC.md)。

## Product decisions

1. 项目首页是进度和决策入口，不是所有模块的堆叠。
2. 任务中心是行动队列，不是数据库状态浏览器。
3. 镜头工作台是单镜头生产与审核空间。
4. 资产和模型设置是支持性页面，不抢占创作主线。
5. 任何 AI 产出都必须经过人工审核和版本化。

## Implementation phases

1. Evidence freeze、状态语言和 feature flag。
2. 新 shell、Production State Resolver、唯一下一步。
3. 制片台、Episode cards、Review Inbox、Activity。
4. Shot Studio、关键帧/图片/视频审核。
5. 资产库、模型中心、QA/交付统一。
6. 视觉方向确认、React 实施、UX QA、切换默认、删除旧 shell。

## Deliverables

- 统一 shell、状态语言和 blocker 聚合。
- V3 镜头工作台和审核抽屉规格。
- 标准/专业双视图。
- 迁移期间的旧页面回退路径和证据链接。

## Non-goals

- 不新增后端 API。
- 不替换已有 Runtime、Production Workspace V2 或 provider。
- 不自动调用真实 LLM、图像或视频 provider。
- 不自动修改剧本或 Source Fact。

## Acceptance criteria

- 5 秒内知道项目当前生产状态。
- 从 blocker 或 review item 一次点击进入正确处理界面。
- 每个关键页面最多一个明确主 CTA。
- 默认视图零 Runtime vocabulary；工程信息只在高级生产详情。
- 用户不需要知道 TaskRun、provider task 或恢复点才能继续工作。
- Review 10 秒内能理解审核对象、AI 做了什么、结果是否正确、通过后会发生什么。
- Shot 3 秒内能看到当前阶段、已有结果、待办和下一步。
- 付费批量操作显示能力和预计请求数量。
- 无 backend rewrite、数据库迁移、真实 provider 调用或自动改剧本。

## Document index

- [CURRENT_UI_UX_AUDIT.md](CURRENT_UI_UX_AUDIT.md)
- [USER_JOURNEY_V3.md](USER_JOURNEY_V3.md)
- [INFORMATION_ARCHITECTURE_V3.md](INFORMATION_ARCHITECTURE_V3.md)
- [SCREEN_INVENTORY_V3.md](SCREEN_INVENTORY_V3.md)
- [CORE_SCREEN_SPECS_V3.md](CORE_SCREEN_SPECS_V3.md)
- [SHOT_STUDIO_SPEC.md](SHOT_STUDIO_SPEC.md)
- [REVIEW_SYSTEM_SPEC.md](REVIEW_SYSTEM_SPEC.md)
- [PRODUCTION_STATE_LANGUAGE.md](PRODUCTION_STATE_LANGUAGE.md)
- [DESIGN_SYSTEM_V3.md](DESIGN_SYSTEM_V3.md)
- [FRONTEND_ARCHITECTURE_V3.md](FRONTEND_ARCHITECTURE_V3.md)
- [UI_V3_MIGRATION_PLAN.md](UI_V3_MIGRATION_PLAN.md)
- [AUDIT_EVIDENCE.json](AUDIT_EVIDENCE.json)

## Completion marker

`PRODUCTION_UI_V3_UX_ARCHITECTURE_COMPLETE`
