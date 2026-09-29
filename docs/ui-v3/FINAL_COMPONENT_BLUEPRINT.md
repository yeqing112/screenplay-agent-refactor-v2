# Final Hybrid V3 Component Blueprint

以下组件构成正式 React 实施边界。原型只提供行为和视觉契约，不修改 `web/src/`。

## Workspace shell

| Component | Responsibility | Required states |
|---|---|---|
| `WorkspaceShell` | canvas、sticky header、route surface、toast / drawer host | loading, ready |
| `GlobalNav` | 制片台、剧本与导演、镜头工坊、资产库、交付 | active, focus |
| `ProductionDetailsDrawer` | 专业视图的 provider、model、execution、lineage | closed, open |

## Production surfaces

| Component | Responsibility | Required states |
|---|---|---|
| `NextBestAction` | 唯一下一步、预计耗时、进入审核 | ready, review |
| `EpisodeProgressRail` | Scene-aware segmented rail；超过 50 Shot 聚合 / 缩放 | official, review, running, waiting, blocked, stale |
| `ActivityPanel` | 正在生成、自动刷新、执行阶段 | running, waiting, official, failed |
| `BlockerPanel` | 真正技术阻塞，独立于 Review Inbox | blocked, stale, empty |

## Shot Studio

| Component | Responsibility | Required states |
|---|---|---|
| `ShotNavigator` | Scene grouping、Episode / Scene / State filter、搜索、virtualized list contract | loading, empty, ready, 40+, 100+ |
| `ShotPipeline` | 导演 → 关键帧 → 图片 → 视频 → 完成的 production state rail | done, current, waiting, blocked |
| `MediaCanvas` | 当前媒体最大区域，按阶段呈现证据 | keyframe, image, video, official |
| `KeyframeCard` | START / MIDDLE / END、核心动作、展开状态信息 | ready, expanded, stale |
| `TimelineContinuity` | motion / emotion transition 和时间轴 | ready, preview |
| `ShotContext` | Director Intent、角色、场景、时长、连续性、版本 | ready, collapsed |

## Review

| Component | Responsibility | Required states |
|---|---|---|
| `ReviewQueue` | 连续审核列表，固定行结构和版本上下文 | loading, empty, ready, 20+ |
| `ReviewDesk` | 大媒体预览、原因、AI 建议、证据 | keyframe, image, video, director |
| `DecisionBar` | 批准、要求修改、更多 / 驳回，固定位置 | review, approved, request-changes |

## Editorial / supporting surfaces

| Component | Responsibility | Required states |
|---|---|---|
| `DirectorWorkspace` | Story / Scene、Treatment、Evidence / Review | loading, ready, empty |
| `AssetLibrary` | 视觉、身份、正式版本、使用镜头、一致性 | loading, empty, ready |
| `DeliveryWorkspace` | Episode、Official media、交付检查 | ready, blocked |

## State contract

- `loading`：局部 skeleton；不可用内容不显示假数据。
- `empty`：解释当前没有内容和下一步，不使用整页 spinner。
- `ready`：显示对象、阶段、版本和可用操作。
- `running`：已提交、模型处理中、进度或等待结果。
- `review`：显示审核原因、版本、证据和固定决策栏。
- `waiting`：明确等待的上游对象。
- `blocked`：说明真实阻塞原因和查看入口。
- `stale`：显示“上游内容已更新 / 当前结果需要重新确认”。
- `failed`：显示错误原因、重试或恢复入口；不隐藏 lineage。
- `official`：显示正式版本、只读标识和完整血缘。
