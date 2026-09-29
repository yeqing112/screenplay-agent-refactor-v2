# Final V3 Design Tokens

这是 Final Hybrid V3 原型和后续 React 实施共享的视觉 token。它把 A 的电影制作气质、C 的生产扫描效率和 B 的创作阅读局部组合成一个固定系统。

## Colors

| Token | Value | 用途 |
|---|---|---|
| `canvas` | `#0E1214` | 全局画布 |
| `surface-1` | `#141A1D` | 卡片、工作区 |
| `surface-2` | `#1A2225` | 选中、输入、次级区域 |
| `surface-3` | `#202A2D` | hover、当前行 |
| `border` | `#2A3437` | 克制分隔线 |
| `text-primary` | `#EDF1EF` | 主文本 |
| `text-secondary` | `#A9B4B3` | 说明、辅助信息 |
| `text-muted` | `#728082` | 时间、版本、次级元数据 |
| `accent-copper` | `#D8A47C` | 创作强调、当前选择、高级感 |
| `accent-cyan` | `#8BC9D9` | 生产操作、主要 CTA、焦点 |
| `accent-blue` | `#8CAEDC` | 参考、图片阶段 |
| `status-official` | `#9FCBAB` | 正式 / 完成 |
| `status-review` | `#C4B5E5` | 待审核 |
| `status-running` | `#8BC9D9` | 生成中 |
| `status-waiting` | `#DBB36F` | 等待上游 |
| `status-blocked` | `#DF8E8C` | 真正阻塞 |
| `status-stale` | `#D68F62` | 上游已更新 |
| `editorial` | `#E7CFA5` | Director Intent、Story Beat、AI Why |

Copper 不承担所有 Primary CTA；批准、继续、生产操作使用 cyan。每个状态必须同时有 marker、文字和颜色。

## Typography

- Production UI：系统无衬线 / `Noto Sans SC`，正文 13px，辅助信息 9–11px。
- Headings：无衬线，重量 500–600，避免大面积 serif。
- Editorial 局部：`Georgia` / `Noto Serif SC`，只用于导演意图、Story Beat、Creative Treatment、Script Reading、AI Why。
- 小于 10px 的文字只用于时间、版本和辅助标签，不承载决策内容。

## Spacing / Shape

- 基础间距：`4 / 8 / 12 / 16 / 24` px。
- Workspace gutter：1440px 默认 24px；移动端 12px。
- Panel radius：3px；不使用大圆角营销卡片。
- Border：1px 实线，使用 `border` token；避免强阴影。
- Elevation：仅 drawer 和 toast 使用低强度阴影；媒体工作区依靠层级和边框。

## Motion / Focus

- 页面切换：短距离、低幅度；不使用整页 spinner。
- Loading：使用 skeleton shimmer。
- Toast：轻量反馈，批准后保持 Review Inbox 并进入下一条。
- Focus：2px cyan outline，所有可操作项可通过 Tab 访问。
