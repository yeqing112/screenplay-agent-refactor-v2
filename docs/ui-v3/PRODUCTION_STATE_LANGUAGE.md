# Production State Language

## Canonical states

| Code | 标准中文 | 用户含义 | 主动作 |
|---|---|---|---|
| empty | 尚未建立 | 还没有任何记录 | 开始建立 |
| needs_input | 待补信息 | 用户需要提供内容 | 补充并保存 |
| ready | 可以继续 | 上游条件满足 | 执行下一步 |
| running | 处理中 | 系统正在执行 | 查看进度 |
| review | 待审核 | 候选已产生，等待人审 | 打开审核 |
| waiting_upstream | 等待上游 | 当前页面无法解除依赖 | 查看依赖 |
| blocked | 暂不能继续 | 存在明确阻塞 | 处理阻塞 |
| stale | 需要重新确认 | 上游事实变化使当前版本过期 | 重新确认 |
| failed | 执行失败 | 最近一次执行未成功 | 查看原因 / 重试 |
| official | 已确认为正式版本 | 当前版本可供下游使用 | 查看版本 |

## Backend-to-user mapping

| Backend / runtime state | 标准中文 | CTA | 专业详情 |
|---|---|---|---|
| `REVIEW_REQUIRED` | 待你审核 | 打开审核 | review type, source version |
| `PROVIDER_PENDING` / `queued` / `running` | 视频生成中 / 正在处理 | 查看活动 / 继续等待已有任务 | provider task, polling state |
| `STALE` | 上游内容已更新，需要重新生成 | 查看变化 / 重新生成 | source fingerprint, stale reasons |
| `PROMPT_AUTHORITY_STALE` | 提示词已经更新，需要重新生成本镜头 | 查看提示词变化 | PromptIR pointer and revision |
| `MISSING_FORMAL_ASSET` / `FORMAL_ASSET_BINDINGS` | 正式资产未准备 | 去绑定资产 | authority id, binding set |
| `MEDIA_CANDIDATE` | 候选待审核 | 打开图片/视频审核 | candidate id, validation |
| `OFFICIAL` / promoted | 已确认为正式版本 | 查看正式结果 | promotion record, target version |
| `PROVIDER_UNAVAILABLE` | 模型暂时不可用 | 查看模型中心 / 重试 | provider, request id |
| `DEPENDENCY_ERROR` | 上游条件未满足 | 查看依赖 | dependency graph, task id |
| HTTP 409 | 当前版本已变化，请刷新后继续 | 刷新并查看变化 | HTTP code and response body |

普通用户文案不显示 API code、provider 名称或 request id；这些字段只进入“生产详情”。

## Copy rules

- 状态标题用业务语言，原因用完整句。
- 每个 blocker 必须有 `原因 + 影响 + 推荐动作`。
- “需要更新”仅在确实存在旧版本时使用；否则用“尚未建立”。
- “待处理”只能表示用户动作，不用于系统等待。
- 内部 code 只在专业详情、复制链接和日志中出现。

## Freshness

全局显示“已同步于 HH:mm”或“数据可能已过期”。stale 状态必须说明触发它的上游版本或时间。
