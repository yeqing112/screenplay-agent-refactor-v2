# Production UI V3 Shot Studio Read Surface Report

**阶段：** `PHASE_PRODUCTION_UI_V3_SHOT_STUDIO_READ_SURFACE`  
**完成标记：** `PRODUCTION_UI_V3_SHOT_STUDIO_READ_SURFACE_COMPLETE`  
**验证日期：** 2026-09-30  
**基线：** `13c9ffccef58070a37573f24ee53c7a995fff3cc`  
**分支：** `codex/visual-authoring-provider-canary-reconcile`

## 1. Scope

本轮交付 Shot Studio V3 的只读观察面。范围包括 Shot Navigator、媒体检查、生产链路、Shot Context、只读 Production Details、状态筛选、URL 选中状态和 loading / empty / unavailable 状态。

本轮没有扩展后端、API、数据库或 Runtime；没有绑定 SHAPI、MiniMax、真实 LLM、图片生成或视频生成。

## 2. Architecture

实现位于 `web/src/components/ProductWorkspaceShotStudioV3.tsx`，通过现有 `productionUiV3` canonical adapter 消费：

```text
ProductionWorkspaceV2Snapshot
  ↓
toShotStudioViewModels()
  ↓
ShotStudioViewModel
  ↓
Shot Navigator / Media Canvas / Shot Pipeline / Shot Context
```

组件不复制 legacy Storyboard 的生产事实，也不使用 legacy `adopted` 字段推断正式版本。

## 3. Canary Entry

显式 URL 参数启用 V3：

```text
?section=storyboard&ui_v3=shot-studio
```

路由函数为 `isShotStudioCanaryEnabled()`。启用后仅渲染 Shot Studio V3；没有参数时继续渲染现有 Legacy Storyboard 与 `ProductionWorkspaceV2Panel`。两套 surface 互斥展示。

## 4. Canonical Data Flow

Shot Studio 使用已有的 `ProductionWorkspaceV2Snapshot`、`ProductionWorkspaceLoadState`、`ProductionWorkspaceViewMode` 和 `toShotStudioViewModels()`。状态、候选、正式版本、authority、pointer、prompt version、execution 和 blockers 均从 canonical projection 读取。

正式版本只在 `official.isCanonicalOfficial` 为真时展示。候选媒体显示为“候选 · 不是正式版本”，不会被提升为正式版本。

## 5. Components Added

新增：

- `ProductWorkspaceShotStudioV3.tsx`
- `ProductWorkspaceShotStudioV3.test.tsx`

修改：

- `ProductWorkspaceSectionContent.tsx`
- `ProductWorkspaceSectionContent.test.ts`

没有新增依赖，没有删除 legacy Storyboard 组件。

## 6. Shot Navigator

Navigator 支持：

- Episode filter
- Scene filter
- Production state filter
- shot id / scene / action 搜索
- 按 episode + scene 分组
- Scene 折叠 / 展开
- Shot 选择和选中态
- 筛选后自动选择第一个可见镜头

浏览器实测：fixture 的 2 个镜头可按集数、场景、状态筛选；折叠场景后可见镜头数量从 2 变为 0；搜索镜头 `2` 后 URL 和 Context 均同步到 shot `2`。

## 7. Media Canvas

Media Canvas 提供 IMAGE / VIDEO inspection toggle。媒体展示规则：

- canonical official preview：可查看正式预览
- review eligible candidate：明确标记为候选
- 没有可安全展示的 URL：显示状态和证据说明
- 没有 fake image、fake video 或 fake thumbnail

视频使用原生 controls，图片使用可访问 alt 文本。

## 8. Shot Pipeline

Pipeline 显示：

- 素材 / asset readiness
- IMAGE 状态
- VIDEO 状态
- 正式版本建立情况
- 当前动作和未映射的 Director / Keyframe rail

Pipeline 是读面，没有提交、生成、验证、提升或批准 handler。

## 9. Shot Context

Context 显示 shot id、scene、duration、camera angle、camera movement、camera speed、action、next action、asset readiness、IMAGE mode 和 VIDEO mode。

选中镜头写回现有 `onSelectShot`，并将 `episode` / `shot` 写入 URL query。刷新页面后选中 shot 恢复。

## 10. Professional Details

Standard mode 只显示必要生产上下文。Professional mode 或手动展开后显示只读证据：

- authority source
- backend next action
- raw blockers
- asset readiness
- IMAGE / VIDEO model、provider、execution、request fingerprint
- official version、authority、pointer
- reason codes
- legacy projection 标记

不会通过 legacy adopted 状态推断正式性。

## 11. Loading / Empty / Error

已实现并测试：

- loading：结构化 skeleton
- empty：无镜头说明
- unavailable / error：fail closed，不安全展示生产状态，并提供重新同步入口
- 无 preview URL：显示 evidence placeholder，而不是伪造媒体

## 12. Responsive Behavior

已使用真实浏览器检查：

- 1440×900
- 1920×1080
- 1280×900

1280px 检查结果：

```text
innerWidth = 1280
scrollWidth = 1280
horizontal overflow = false
```

布局在窄宽度下通过可滚动 Navigator、可收起 Context 和媒体区域的 `min-w-0` 降级。

## 13. 42 / 100 Shot Stress

React 测试创建了 100-shot stress snapshot，并验证 Shot Studio 可渲染 `100 shots`。普通分组列表在 100 条规模下通过静态渲染检查。

本轮没有引入 virtualization 或 server pagination；这两项保留到后续性能阶段。42-shot 目标与既有 V3 视觉规范一致，当前 fixture 浏览器样本为 2 shots。

## 14. Accessibility

已提供：

- semantic buttons、select、label
- aria-label / aria-expanded / aria-current / aria-pressed
- 搜索输入的可访问名称
- 状态使用 marker + text，不依赖颜色单独表达
- focus-visible ring
- video captions track
- image alt 文本
- 场景折叠按钮可通过键盘操作

## 15. Visual Evidence

截图证据：

- [1440px Shot Studio](shot-studio-read/shot-studio-v3-1440.png)
- [1920px Shot Studio](shot-studio-read/shot-studio-v3-1920.png)
- [1280px Shot Studio](shot-studio-read/shot-studio-v3-1280.png)

截图基于现有 blocked fixture，不包含伪造媒体。

## 16. Tests

定向测试：

```text
ProductWorkspaceShotStudioV3.test.tsx: 5 passed
ProductWorkspaceSectionContent.test.ts: 3 passed
```

全量测试：

```text
55 test files passed
340 tests passed
```

构建与静态检查：

```text
npm --prefix web run build: PASS
git diff --check: PASS
```

## 17. Explicitly Disabled Mutations

本轮明确保持只读：

- Generate image: disabled
- Generate video: disabled
- Retry provider execution: disabled
- Approve / promote candidate: disabled
- Validate candidate: disabled
- Provider submission: 0
- Production writes: 0
- Real LLM / SHAPI / MiniMax calls: 0

浏览器网络检查未发现 Shot Studio 发起 provider、generation、candidate validation 或 promotion 请求。页面已有的 agent reconcile POST 属于工作台既有启动流程，不由本组件触发。

## 18. Deferred Phase 2 Actions

以下能力不在本轮启用：

- Director / Keyframe rail
- provider adapter submission
- generation execution controls
- candidate validation / promotion
- review mutation
- server pagination / virtualization
- 真实媒体生产操作

这些动作必须在后续阶段通过明确 API 契约和人工审核流程接入。

## 19. Known Gaps

- 当前浏览器 fixture 只有 2 个镜头，42 / 100 shot 主要由 React stress surface 覆盖。
- 真实 official preview、candidate preview 和 provider execution 依赖后端 canonical projection；blocked fixture 会显示状态证据而不是媒体。
- V3 当前为 URL canary，尚未替换默认 Storyboard surface。
- Director / Keyframe 数据尚未映射到本只读面。

## 20. Completion Status

```text
PRODUCTION_UI_V3_SHOT_STUDIO_READ_SURFACE_COMPLETE
```

本轮实现、测试、浏览器验证和文档已完成。提交前需确认工作树仅包含本轮源码、测试、截图和报告，然后推送分支 `codex/visual-authoring-provider-canary-reconcile`。
 
