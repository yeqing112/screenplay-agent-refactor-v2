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

## Review type contracts

| 类型 | 用户看到的证据 | 通过后的下一步 |
|---|---|---|
| Director Review | 剧情节拍、视觉策略、摄影策略、情绪曲线、AI 为什么这样拍 | 解锁场面调度 |
| Storyboard Review | 场景空间、镜头目的、景别、机位、运动、时长、连续性 | 允许关键帧计划 |
| KeyframePlan Review | START/MIDDLE/END Storyboard Cards、人物/场景状态、情绪、摄影 | 编译关键帧序列 |
| Image Candidate Review | 候选 Grid、当前关键帧、人物和场景一致性、资产版本 | 形成正式图片并解锁视频 |
| Video Candidate Review | 播放器、START/END 对照、Prompt/ShotDirection 摘要、连续性 | 形成正式视频 |

## Review Inbox rules

- Human Review 是一级入口，不能只作为“阻塞任务”的一种状态。
- `REVIEW_REQUIRED` 显示为“待你审核”；`PROVIDER_PENDING` 显示为“视频生成中”；`STALE` 显示为“上游内容已更新，需要重新生成”。
- 批量审核只允许同类型、同版本且证据完整的项目；预计产生费用的批量生成先显示图片/视频请求数量。
- 审核完成后队列自动前进，用户可以撤销或查看历史，但不可修改已批准的源事实。

## Keyboard and safety

`A` = approve、`R` = request changes、`Space` = preview、箭头 = previous/next shot。驳回、批量付费生成和正式版本替换需要二次确认；焦点始终回到当前 review item。
