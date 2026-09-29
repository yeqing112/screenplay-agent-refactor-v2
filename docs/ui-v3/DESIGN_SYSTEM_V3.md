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

## Baseline tokens

| 类别 | V3 基线 |
|---|---|
| Typography | Inter/系统无衬线；标题 24/32、页面标题 20/28、正文 14/22、辅助 12/18、技术详情等宽 11/16 |
| Spacing | 4px 基础单位；卡片内边距 16/20；页面栅格 24；桌面栏间距 16 |
| Radius | 6px 控件、10px 卡片、14px 面板、18px 媒体容器；避免每个元素都圆角 |
| Elevation | `shadow-1` 用于卡片，`shadow-2` 用于 drawer/modal；不使用发光阴影表达状态 |
| Color tokens | base/slate surfaces，文字 slate-200/400/600，主动作 sky/violet，状态色按语义固定 |
| Status pills | 文案 + 图标 + 状态色；review、running、stale、blocked、official 有独立图标 |

## Component contracts

- **Button**：primary/secondary/quiet/danger；主按钮只在页面中出现一次，危险动作带确认。
- **Card**：项目卡、Episode Card、Shot Card、Review Card；标题、状态、对象身份和 CTA 顺序固定。
- **Panel**：生产状态、资产详情、活动流；面板不重复渲染同一权威状态。
- **Drawer**：Review Drawer、Production Details Drawer；支持 Esc、焦点陷阱和深链恢复。
- **Modal**：只用于不可逆或付费确认，不用于普通编辑。
- **Media Viewer**：图片 Compare、视频播放器、START/END 对照，提供键盘控制和 alt/字幕入口。
- **Timeline**：Episode Production Activity 和 Shot Pipeline，状态节点可点击并显示原因。
- **Shot Card**：缩略图、镜头号、场景、时长、阶段、警告、唯一下一步。
- **Review Card**：类型、集/镜头、预览、审核原因、AI 建议、版本和决策。

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
