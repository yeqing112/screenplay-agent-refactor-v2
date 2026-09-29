# Visual Evidence Index

截图路径统一位于 `docs/ui-v3/visual-direction/`，每张图由隔离 Prototype 在浏览器中实际打开后生成。

| Direction | Screen | Resolution | Fixture state | File |
|---|---|---:|---|---|
| A · Cinematic Command | Dashboard | 1440×900 | Episode 1 overview | `direction-a-dashboard-1440.png` |
| A · Cinematic Command | Shot Studio | 1440×900 | Shot 214 · keyframe review | `direction-a-shot-studio-1440.png` |
| A · Cinematic Command | Review Inbox | 1440×900 | 4 review items | `direction-a-review-inbox-1440.png` |
| A · Cinematic Command | Shot Studio | 1920×1080 | Shot 214 · keyframe review | `direction-a-shot-studio-1920.png` |
| A · Cinematic Command | Shot Studio | 1280×900 | Shot 214 · keyframe review | `direction-a-shot-studio-1280.png` |
| B · Editorial Studio | Dashboard | 1440×900 | Episode 1 overview | `direction-b-dashboard-1440.png` |
| B · Editorial Studio | Shot Studio | 1440×900 | Shot 214 · keyframe review | `direction-b-shot-studio-1440.png` |
| B · Editorial Studio | Review Inbox | 1440×900 | 4 review items | `direction-b-review-inbox-1440.png` |
| B · Editorial Studio | Shot Studio | 1920×1080 | Shot 214 · keyframe review | `direction-b-shot-studio-1920.png` |
| B · Editorial Studio | Shot Studio | 1280×900 | Shot 214 · keyframe review | `direction-b-shot-studio-1280.png` |
| C · Precision Production | Dashboard | 1440×900 | Episode 1 overview | `direction-c-dashboard-1440.png` |
| C · Precision Production | Shot Studio | 1440×900 | Shot 214 · keyframe review | `direction-c-shot-studio-1440.png` |
| C · Precision Production | Review Inbox | 1440×900 | 4 review items | `direction-c-review-inbox-1440.png` |
| C · Precision Production | Shot Studio | 1920×1080 | Shot 214 · keyframe review | `direction-c-shot-studio-1920.png` |
| C · Precision Production | Shot Studio | 1280×900 | Shot 214 · keyframe review | `direction-c-shot-studio-1280.png` |

## Accessibility evidence

原型包含可聚焦按钮、命名导航、键盘快捷键提示、文字状态和媒体控件占位。截图用于视觉比较；键盘、对比度和按钮名称另通过浏览器 DOM 检查记录在视觉方向报告中。

## Verification results · 2026-09-29

- 15/15 PNG 已用 PIL 核对尺寸：Dashboard / Shot Studio / Review Inbox 为 `1440×900`；Shot Studio 响应式样本为 `1920×1080` 和 `1280×900`；全部为 RGB。
- A / B / C 均在 `http://127.0.0.1:4177/direction-{a,b,c}/` 实际打开并完成导航、Shot Studio、Review Inbox、详情抽屉、审核选择和阶段切换检查。
- 三个方向的浏览器控制台错误均为 `0`；1440、1280、760 宽度的横向溢出检查均为 `false`。
- 1440 宽度首屏可见按钮均有可读名称（A `7`、B `6`、C `11`）；关闭生产详情按钮补充了 `aria-label="关闭生产详情"`。
- 状态同时以文字和颜色表达；START / MIDDLE / END、A / R / Space 及生产详情占位均在页面中可见。所有动作只改变浏览器内存状态。
