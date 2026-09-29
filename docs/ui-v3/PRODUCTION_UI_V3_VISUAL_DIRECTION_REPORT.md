# Production UI V3 Visual Direction Report

**阶段状态：`PRODUCTION_UI_V3_VISUAL_DIRECTION_READY_FOR_SELECTION`**\r\n**验证日期：2026-09-29**\r\n**分支：`codex/visual-authoring-provider-canary-reconcile`**\r\n**远程 HEAD（本轮开始）：`aaa4852`**

## 1. 本轮交付

本轮完成三套隔离的 Production UI V3 视觉原型，使用同一业务 fixture 和同一核心流程，供产品负责人逐屏比较并选择或混合组合：

| 方向 | 视觉语言 | 适用重点 | 原型 |
|---|---|---|---|
| A · Cinematic Command | 深色、沉浸、媒体优先的电影制作控制台 | Shot 创作、关键帧和视频审核 | [`prototypes/ui-v3/direction-a/index.html`](../../prototypes/ui-v3/direction-a/index.html) |
| B · Editorial Studio | 编辑型创作工作室，阅读导演意图后作决定 | 剧本、导演方案和跨角色协作 | [`prototypes/ui-v3/direction-b/index.html`](../../prototypes/ui-v3/direction-b/index.html) |
| C · Precision Production | 高密度、可扫描的专业制片操作台 | 40+ 镜头、并行任务和连续审核 | [`prototypes/ui-v3/direction-c/index.html`](../../prototypes/ui-v3/direction-c/index.html) |

三套方向均覆盖：制片台、镜头工坊、待我处理、Shot 214 关键帧审核、START / MIDDLE / END、批准、要求修改、生产详情和快捷键提示。

## 2. 视觉证据

完整截图索引见 [`VISUAL_EVIDENCE_INDEX.md`](VISUAL_EVIDENCE_INDEX.md)，方向对比见 [`VISUAL_DIRECTION_BOARD.md`](VISUAL_DIRECTION_BOARD.md)。共 15 张截图：每个方向包含 Dashboard、Shot Studio、Review Inbox（`1440×900`），以及 Shot Studio 的 `1920×1080` 和 `1280×900` 响应式样本。

核心截图：

- [A · Dashboard](visual-direction/direction-a-dashboard-1440.png) · [A · Shot Studio](visual-direction/direction-a-shot-studio-1440.png) · [A · Review Inbox](visual-direction/direction-a-review-inbox-1440.png)
- [B · Dashboard](visual-direction/direction-b-dashboard-1440.png) · [B · Shot Studio](visual-direction/direction-b-shot-studio-1440.png) · [B · Review Inbox](visual-direction/direction-b-review-inbox-1440.png)
- [C · Dashboard](visual-direction/direction-c-dashboard-1440.png) · [C · Shot Studio](visual-direction/direction-c-shot-studio-1440.png) · [C · Review Inbox](visual-direction/direction-c-review-inbox-1440.png)

## 3. 验证结果

- 15/15 PNG 已用 PIL 核对尺寸和 RGB 模式。
- A / B / C 均在本地浏览器实际打开；导航、镜头选择、审核选择、阶段切换、详情抽屉打开/关闭均通过。
- 1440、1280、760 宽度横向溢出检查：全部 `false`。
- 1440 宽度首屏可见按钮均有可读名称：A `7`、B `6`、C `11`；关闭生产详情按钮已增加 `aria-label="关闭生产详情"`。
- 三个方向控制台错误：`0`；所有动作只改变浏览器内存状态。
- 状态同时提供文字标签和颜色；审核快捷键及媒体控制占位可见。对比度以截图和 CSS 颜色人工复核，未引入只依赖颜色的状态表达。

执行检查：

```text
PIL image-size audit: PASS
Browser interaction / console audit: PASS
git diff --check: PASS
npm --prefix web run build: PASS
npm --prefix web test: PASS (`53` files / `318` tests)
```

## 4. 生产边界

- 生产前端 `web/src/`：改动 `0`。
- 后端 Runtime / API / 数据库：改动 `0`。
- 真实 LLM、图像或视频 Provider 调用：`0`。
- 原型中的 Provider、Model、Prompt version、Execution、Request ID 和 Source lineage 仅为可追踪性展示 fixture，不产生外部请求。
- `.playwright-cli/` 已加入 `.gitignore`，浏览器临时产物不进入提交。

## 5. 选择方式

本轮不指定 winner。请按以下维度逐屏选择，或混合采用不同方向：信息层级、审核效率、长时间使用舒适度、40+ 镜头扩展性、视觉高级感、媒体聚焦、学习成本、无障碍和实施复杂度。允许组合例如：A 的 Shot Studio + B 的 Dashboard + C 的 Review Inbox。

用户选择方向后，下一阶段再把选定的视觉语言映射到生产 UI 组件；本轮原型不会自动进入生产前端。

## 6. 工作树和推送

本轮仅提交：`prototypes/ui-v3/`、`docs/ui-v3/` 的视觉方向交付物、截图和 `.gitignore` 规则。已完成 `git diff --check`、提交并推送当前分支；远程分支地址：<https://github.com/yeqing112/screenplay-agent-refactor-v2/tree/codex/visual-authoring-provider-canary-reconcile>。
