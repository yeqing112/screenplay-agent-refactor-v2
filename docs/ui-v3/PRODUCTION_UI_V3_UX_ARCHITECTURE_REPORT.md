# Production UI V3 UX Architecture Report

## Executive summary

本轮完成正式产品工作台的 UX/UI 架构审计和 V3 设计基线。结论是：现有 Runtime、真实数据投影、候选与正式媒体分离、版本和任务深链基础可复用；主要问题集中在信息层级、状态语言、重复 blocker 和镜头页职责过载。

## Audited evidence

真实项目“潮汐回声”（990402）在项目列表、项目控制台、任务中心、资产中心、模型管理、剧本工作台、内容准备和镜头工作台中完成浏览审计。截图位于 `output/playwright/`。

观测到的样本状态包括：项目 10 章、约 0.3 万字、3 集、42 镜；Production Workspace V2 显示 9%，当前因剧本过期、正式资产缺失和导演方案未完成而阻塞；任务中心显示 56 个任务、50 个等待上游。

## Architecture

V3 采用“项目 → 集 → 场 → 镜头 → 资产/提示词/媒体 → 审核”的对象层级。项目首页只做全局判断，任务中心只做行动队列，镜头工作台只做单镜头生产与审核。所有页面共享 canonical state、Next best action、BlockerGroup、VersionRail 和 ReviewDrawer。

## Files audited

- `web/src/App.tsx`
- `web/src/pages/ProjectsPage.tsx`
- `web/src/pages/CanvasPage.tsx`
- `web/src/components/ProductWorkspace.tsx`
- `web/src/components/ProductWorkspaceShell.tsx`
- `web/src/components/ProductWorkspaceSectionContent.tsx`
- `web/src/components/ProductWorkspaceDashboardSection.tsx`
- `web/src/components/ProductWorkspaceTasksSection.tsx`
- `web/src/components/ProductWorkspaceStoryboardSection.tsx`
- `web/src/components/ProductWorkspaceAssetsSection.tsx`
- `web/src/components/ProductionWorkspaceV2Panel.tsx`
- `web/src/components/ProductWorkspaceDirectorTreatmentPanel.tsx`
- `web/src/components/ProductWorkspaceDirectorRuntimePanel.tsx`
- `web/src/domain/productionWorkspace.ts`
- `web/src/services/productionWorkspace.ts`
- `web/src/services/agent.ts`
- `web/src/hooks/useProductionWorkspace.ts`
- `api/automatic_storyboard_api.py`, `api/automatic_keyframe_api.py`, `api/keyframe_image_production_api.py`, `api/episode_rendering_api.py`

## Screens audited

项目列表空态、项目列表真实数据、项目控制台、镜头工作台、任务中心、资产中心、模型管理、剧本工作台、内容准备；截图和样本数据见 [AUDIT_EVIDENCE.json](AUDIT_EVIDENCE.json)。

## Component disposition

### KEEP

`ProductWorkspaceShell`、production workspace domain/service、快照校验与 normalize、导演方案证据预览/候选恢复/人工确认、QA/导出版本和回退记录。

### REFACTOR

`ProductWorkspaceDashboardSection`、`ProductWorkspaceTasksSection`、`ProductionWorkspaceV2Panel`、`ProductWorkspaceStoryboardSection`、`ProductWorkspaceAssetsSection`、`ProductWorkspaceModelsSection`。保留数据和动作，改为 V3 resolver、Shot Studio、Review Inbox 和业务语言。

### REPLACE

当前按功能拼接的一级导航、重复 blocker 卡片、文本/工程字段型候选审核、把项目动态和任务混排的列表。

### REMOVE

仅在 V3 functional parity、production regression pass 和 UX acceptance pass 后删除：重复挂载的旧 V2 状态面板、标准视图 API proxy/内部 code、跳页找生成按钮的旧交互。

## Runtime UI gaps

- AutomaticKeyframePlan、Keyframe Review、Keyframe Image Production 当前只有后端 API，没有对应的前端一级工作面。
- StoryboardMaterialization 只在状态中体现，没有物化集合和编译门的用户审核。
- Image Candidate Review 已能验证/晋升，但缺少视觉网格、Compare 和一致性说明。
- Video Candidate Review 缺少播放器、START/END 对照、批注和统一决策。
- Episode Automatic Production 后端能力存在，前端缺少“预计范围 → 开始 → 活动流 → 人工节点”的可见流程。
- Real Episode Pilot、Stale/Recovery、Production Observability 只有零散组件或工程状态，没有统一用户入口。

## Core workflows

创建项目与导入内容、AI 导演、分镜审核、关键帧审核、图片审核、视频审核、Episode 自动制作、QA 与交付均已写入 [USER_JOURNEY_V3.md](USER_JOURNEY_V3.md)，核心页面规格见 [CORE_SCREEN_SPECS_V3.md](CORE_SCREEN_SPECS_V3.md)。

## Governance

- Source Fact、ScriptIR 和既有权威投影保持只读事实边界。
- 用户编辑进入草稿或新版本。
- AI 仅生成建议或候选，人工批准后才形成正式版本。
- Prompt lineage、provider metadata、execution record 和审核记录在专业视图可追踪。

## Primary UX risks

1. 重复状态来源继续并存，用户仍无法判断唯一下一步。
2. 关键帧/媒体审核缺失会使 Runtime 能力继续停留在工程页面。
3. 业务语言与内部 code 边界不清，可能让普通用户误操作模型或恢复流程。
4. 自动制作若没有范围预览和活动流，会退化为不可解释的一键黑盒。
5. 旧 UI 删除过早可能破坏生产回退，因此必须受 feature flag 和验收门控制。

## Implementation order

1. 状态语言与 blocker 聚合。
2. 项目首页唯一下一步。
3. 任务中心按行动分层。
4. 镜头工作台三栏结构与审核抽屉。
5. QA、导出和模型设置统一组件。

## Acceptance checklist

- [x] 完成真实 UI 截图证据。
- [x] 输出用户旅程、信息架构、Screen inventory。
- [x] 输出 Shot Studio、Review、状态语言和设计系统规格。
- [x] 输出前端架构和迁移计划。
- [x] 明确禁止真实 provider 调用、后端迁移和自动改剧本。
- [ ] 后续实施阶段完成组件重排和可用性验证。

## Working tree state at publication

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Commit: `634b5cd`（文档和审计截图已推送）
- No React implementation, API rewrite, database migration or real provider call was made in this phase.
- No backend mutation was performed; all runtime checks were read-only audits and browser evidence capture.
- `git diff --check` passed before commit.

## Completion marker

`PRODUCTION_UI_V3_UX_ARCHITECTURE_COMPLETE`
