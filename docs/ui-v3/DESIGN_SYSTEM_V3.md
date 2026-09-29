# Design System V3

## Principles

1. 先显示对象和下一步，再显示系统细节。
2. 状态颜色只表达语义，不承担唯一信息。
3. 候选、正式、失败和等待必须视觉可区分。
4. 专业信息可展开，不污染标准视图。

## Tokens

| Token | 用途 |
|---|---|
| `surface.base` | 深色工作台背景 |
| `surface.panel` | 卡片和工作区 |
| `state.ready` | emerald |
| `state.review` | violet |
| `state.waiting` | amber |
| `state.blocked` | rose |
| `state.stale` | orange |
| `state.official` | blue |

颜色旁必须有文字、图标或 aria-label。按钮高度不低于 36px，主要 CTA 只允许一个视觉主色。

## Components

- `WorkspaceShell`：项目身份、页面标题、数据新鲜度、视图模式。
- `NextActionCard`：唯一下一步、原因、目标页面。
- `StateBadge`：canonical state + human label。
- `BlockerGroup`：聚合 blocker、数量和影响范围。
- `VersionRail`：版本、时间、作者、回退。
- `ReviewDrawer`：证据、候选、决策、历史。
- `TechnicalDetails`：专业视图的内部 code、API 和 request id。

## Accessibility

键盘可达、focus ring 清晰；禁用按钮仍提供原因；所有图片区分 alt 和媒体状态；动态任务更新使用 aria-live；表格和卡片提供可读名称。

