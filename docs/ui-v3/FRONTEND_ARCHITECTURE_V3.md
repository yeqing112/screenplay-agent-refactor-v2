# Frontend Architecture V3

## Boundary

V3 是现有 React 工作台之上的信息架构和呈现编排层。继续复用现有 hooks、service、domain snapshot 和 API，不引入新的后端资源。

## Layers

```text
App / CanvasPage
  → WorkspaceShell
    → Section routes
      → View model adapters
        → Existing hooks and services
          → Existing API projections
```

## Required V3 boundaries

- **Shell**：项目身份、视图模式、数据新鲜度、全局快捷键和错误边界。
- **Navigation**：V3 一级入口、对象上下文、深链和返回位置，不承载生产规则。
- **Production State Resolver**：把现有 snapshot、readiness、task、stale 和 blocker 归一成 `currentStage / nextAction / blockers / activity`。
- **Review Components**：Director、Storyboard、Keyframe、Image、Video 共用 Review Inbox、Review Card、Review Drawer 和决策记录。
- **Media Components**：Media Viewer、Compare、播放器、候选网格和正式版本 rail。
- **Shot Components**：Shot List、Shot Pipeline、Keyframe Card、Asset Context、Continuity Context。
- **Service Layer**：复用 `web/src/services`；补缺时新增 service function，不把 fetch 和重试规则散落到组件。
- **Domain Layer**：复用 `web/src/domain` 的 schema/normalize/validation；不把后端状态码直接作为用户文案。

## Feature flag and coexistence

迁移期间使用 `production_ui_v3`（或现有 feature flag 系统）按项目/用户启用。旧 UI 和 V3 共享 service、domain 和 API projection；不复制一套生产规则。每个 V3 页面提供“返回旧工作台”回退入口，直到满足 parity、production regression pass 和 UX acceptance pass。

## View model adapters

建议增加纯函数适配器（可放在现有 `components` 或 `domain` 目录）：

- `toNextAction(snapshot)`
- `groupBlockers(snapshot)`
- `toHumanState(rawState, mode)`
- `buildShotContext(snapshot, selection)`
- `buildReviewEvidence(candidate, lineage, execution)`

适配器只做排序、聚合、文案和路由参数转换，不写入源数据。

## State management

- URL 保存 section、episode、scene、shot、step。
- 页面本地 state 保存临时编辑草稿和抽屉状态。
- 服务层负责 fetch、校验、normalize 和 refresh。
- mutation 后重新读取权威投影，不通过本地 optimistic state 冒充正式状态。

## Modes

`standard`：面向导演、编剧、制片的业务语言。

`professional`：显示实体名、内部 code、版本指纹、provider 和 API 证据。

## Error handling

统一将网络错误、投影校验错误、上游阻塞和业务拒绝映射为 `ErrorNotice`，并保留原始诊断供专业视图查看。

## Component disposition

| 处理 | 当前组件 | 原因 |
|---|---|---|
| KEEP | `ProductWorkspaceShell`、`productionWorkspace.ts`、`services/productionWorkspace.ts`、`ProductWorkspaceDirectorTreatmentPanel` | 已有上下文、校验、版本和人工确认能力 |
| REFACTOR | `ProductWorkspaceDashboardSection`、`ProductWorkspaceTasksSection`、`ProductionWorkspaceV2Panel`、`ProductWorkspaceStoryboardSection`、`ProductWorkspaceAssetsSection`、`ProductWorkspaceModelsSection` | 复用数据和动作，重排为 V3 页面和标准/专业视图 |
| REPLACE | 当前一级 section 菜单、重复 blocker 卡片、文本型候选审核 | 需要用户工作流和视觉审核的全新组织方式 |
| REMOVE | 重复挂载的旧 V2 状态面板、标准视图的 API proxy/内部 code、跳页找生成按钮交互 | 仅在 V3 parity 和回归验证后删除 |
