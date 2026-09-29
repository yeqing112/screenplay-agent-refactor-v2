# Review System Spec

## Review model

审核对象统一为 `reviewable`：方向、剧本、ShotPlan、资产、图片候选、视频候选、导出包。每次决策写入独立记录，不覆盖事实。

## Decisions

| 决策 | 含义 | 后续 |
|---|---|---|
| approve | 当前版本成为正式版本 | 解除对应 blocker |
| request_changes | 保留版本但要求修改 | 创建待处理任务 |
| reject | 当前候选不可用 | 记录原因，可重新生成 |
| skip | 明确跳过当前对象 | 需要用户理由和权限 |

## Review drawer

审核抽屉必须包含：对象身份、输入事实、生成意图、候选预览、版本号、prompt lineage、上游依赖、QA 结果、评论、决策按钮、历史记录。

## Human control

- AI 草案默认是“建议”，不可直接写入正式版本。
- 批准按钮显示写入目标和版本号。
- 退回必须选择原因，可补充文本。
- 决策后提供撤销窗口和历史回退。

## Evidence requirements

审核通过需要记录 reviewer、时间、source version、target version、reason、changed fields、upstream fingerprints 和 provider metadata。没有证据时按钮显示为 disabled，并解释缺失项。

