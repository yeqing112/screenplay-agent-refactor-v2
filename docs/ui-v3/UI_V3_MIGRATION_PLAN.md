# UI V3 Migration Plan

## Phase 0 — Evidence freeze

- 固定现有页面截图和真实项目样本。
- 确认不修改 React、API、数据库和 provider 调用。
- 建立状态词表、对象层级和路由参数约定。

## Phase 1 — Shell and state language

- 替换项目入口的 API proxy 展示。
- 引入 `NextActionCard`、`StateBadge`、`BlockerGroup` 的纯视图适配器。
- 标准视图隐藏工程词汇，专业视图保留详情。

## Phase 2 — Dashboard and tasks

- 项目首页只保留一个主行动。
- 任务中心按用户行动分区和聚合重复 blocker。
- 所有任务深链带上 episode/scene/shot/task。

## Phase 3 — Shot Studio

- 将镜头页改为计划、资产、IMAGE、VIDEO、连续性五个工作面。
- 把审核移入统一抽屉。
- 保持现有 production workspace v2 和 storyboard API 不变。

## Phase 4 — Review and delivery

- 统一 reviewable 记录和版本轨迹的呈现。
- QA 和导出中心复用审核组件。
- 增加回退和证据导出入口。

## Exit criteria

- 标准视图中没有未解释的工程 code。
- 任意页面 5 秒内能回答“我在哪、现在什么状态、下一步是什么”。
- 所有生成结果仍先进入候选，人工批准后才成为正式版本。
- Source Fact、ScriptIR 和既有 API 契约不变。

