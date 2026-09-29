# Production UI V3 Final Visual Language Report

**阶段：`PHASE_PRODUCTION_UI_V3_FINAL_VISUAL_LANGUAGE`**
**目标状态：`PRODUCTION_UI_V3_FINAL_VISUAL_LANGUAGE_COMPLETE`**
**验证日期：2026-09-29**
**基线 Remote / Local HEAD：`e019119`**
**分支：`codex/visual-authoring-provider-canary-reconcile`**

## 1. 交付摘要

产品负责人已选择 Final Hybrid V3：

```text
A = 主视觉语言
C = 高密度生产交互结构
B = 导演 / 剧本 Editorial 模式
```

已建立 [`prototypes/ui-v3/final/index.html`](../../prototypes/ui-v3/final/index.html)，包含：

- Production Dashboard
- Shot Studio
- Review Inbox
- Director Workspace
- Asset Library
- Delivery

本原型继续与 `web/src/` 隔离，未进入生产 React。

## 2. Final Hybrid 取舍

| 来源 | 最终采用 | 明确舍弃 |
|---|---|---|
| A | 深色低饱和 Canvas、媒体优先、空间层级、铜色创作强调、Dashboard Hero、Large Media Preview | 低密度 Navigator；铜色承担所有 Primary |
| C | Scene grouping、40+ Shot 可扫描 Navigator、filters、Review Inbox 三栏、状态 rail、cyan 生产 CTA | 将媒体压缩到无法判断；把技术阻塞混入 Review Inbox |
| B | Director Treatment、Story Beat、AI Why、Director Intent 局部 serif | Production UI 大面积 serif；暴露内部 reasoning 对象名 |

正式 token、颜色、字体、间距和 motion 见 [`FINAL_DESIGN_TOKENS.md`](FINAL_DESIGN_TOKENS.md)。

## 3. 组件和文案交付

- [`FINAL_VISUAL_LANGUAGE_SPEC.md`](FINAL_VISUAL_LANGUAGE_SPEC.md)：React 实施唯一视觉依据。
- [`FINAL_COMPONENT_BLUEPRINT.md`](FINAL_COMPONENT_BLUEPRINT.md)：WorkspaceShell、GlobalNav、ShotNavigator、ShotPipeline、MediaCanvas、KeyframeCard、ReviewQueue、ReviewDesk、DecisionBar、ProductionDetailsDrawer、NextBestAction、EpisodeProgressRail、ActivityPanel、BlockerPanel 及状态契约。
- [`FINAL_UX_COPY.md`](FINAL_UX_COPY.md)：固定核心中文文案和状态语言。

截图索引见 [`FINAL_VISUAL_EVIDENCE_INDEX.md`](FINAL_VISUAL_EVIDENCE_INDEX.md)，包括 Dashboard、Shot Studio、Review Inbox、Director Workspace 的 1440×900 证据，以及 Shot Studio 的 1920×1080、1280×900 证据。

## 4. QA fixture 覆盖

- 42 Shot：实际填入 Navigator，包含 Scene grouping、滚动、搜索、状态扫描。
- 100 Shot：原型内可切换 stress fixture，用于 layout、导航和滚动压力检查，不用于主截图。
- 20 review items：Review Inbox 结构为 20 item stress-ready，并展示四种 review 类型。
- Long text：长场景名称、长角色名和长导演意图已加入 fixture，布局使用截断、换行和可滚动容器。
- Empty：Review Inbox 可切换到空队列，文案固定为“当前没有需要你审核的内容。系统会继续处理已经批准的任务。”
- Loading：状态样本提供 skeleton，不使用整页 spinner。
- Async / stale：生成中、已提交、模型处理中、等待结果、上游内容已更新和需要重新确认均有文字状态。

## 5. Browser verification

已实际检查以下 viewport：

```text
1440×900
1920×1080
1280×900
```

检查内容：

- 5 个一级导航均可用；Dashboard → Shot Studio、Review → 下一条 Review 可用。
- Shot 选择、Scene grouping、搜索、Episode / Scene / State filter、阶段选择、Pipeline 历史提示、详情展开、Context collapse 均可用。
- Review 选择、Keyframe / Image / Video / Director 四种 Review、批准、要求修改、空队列、生产详情均可用。
- A / R / Space / ↑↓ / ←→ 快捷键可用；聚焦 input、select 或 drawer 时不会触发危险审核动作。
- 所有可见按钮有可读名称；状态由 marker + text + color 表达。
- 控制台错误为 `0`；1440、1280、760 宽度横向溢出检查为 `false`。
- 实测 fixture：Navigator 默认 `42` 条、Scene group `20` 个；打开 100 Shot stress 后为 `100` 条；Review stress queue 为 `20` 条；空队列和恢复队列均可用。
- 1440px 下可见按钮 `31` 个，未命名按钮 `0`；Image stage、Production Details drawer、Review approve → next review 均通过。
- 使用 CSS zoom 代理检查 `90% / 100% / 110%`，主 CTA 和 5 个一级导航均保持可见，横向溢出为 `false`。
- 90%、100%、110% 缩放的正式 QA 需在 React 实施阶段与真实组件一起复核；原型已使用可收起 Context、可滚动 Navigator 和 drawer 降级结构。

## 6. 工程边界和验证

- `web/src/` mutations：`0`
- 后端 Runtime / API / 数据库 mutations：`0`
- real LLM calls：`0`
- real SHAPI calls：`0`
- real MiniMax calls：`0`
- prototype backend calls / database writes：`0`

执行检查：

```text
prototype browser verification: PASS
npm --prefix web run build: PASS
npm --prefix web test: PASS (53 files / 318 tests)
git diff --check: PASS
```

## 7. 后续边界

Final Spec、Component Blueprint 和 UX Copy 已锁定 A / B / C 的组合，后续实现不得重新混合三套方向。下一阶段才允许修改 `web/src/`，并将本规范逐步接入真实 Runtime；正式实现仍需以现有 API 对 approve / compile / refresh / undo 能力做契约核对。
