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

