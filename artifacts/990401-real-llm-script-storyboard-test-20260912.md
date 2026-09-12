# 990401 真实 LLM 剧本与分镜测试报告

- 项目：`潮汐回声·生产链路测试样本`
- book_id：`990401`
- 模型：模型管理中的当前默认 MiMo（未切换模型）
- 测试范围：导入小说 → 剧本生成 → 剧本 QA → 10 集分镜生成 → 只读生产审计
- 外部媒体调用：未调用 GPT Image 2、MiniMax H3 或对象存储

## 结果

- 剧本任务：完成，10/10 集，QA 已完成。
- 分镜任务：完成，10/10 集，164 个镜头，0 失败、0 回退、0 警告。
- 每集镜头数：`16, 17, 16, 6, 15, 16, 16, 21, 27, 14`。
- 剧本 QA：45 条待处理问题（高 7 / 中 26 / 低 12），全部保持 `pending`，未自动忽略。
- 可拍性只读回放：143 pass、7 warning、14 blocked；164 个镜头均被标记为需要新版 Prompt Compiler 重编译。
- Prompt 只读审计：422 errors、1418 warnings；主要问题是缺少结构化场景资产、静态/运动提示词过短、未形成新版分层 Prompt sections。
- 生产就绪只读检查：warning；164 个镜头缺少 Prompt 诊断/可拍性派生状态，7 个人物资产仍为 draft 且没有锁定参考图。
- 批量修复预检（10 个代表性镜头、临时克隆）：修复前 30 errors / 30 warnings，修复后 3 errors / 4 warnings；真实项目 apply 阻断 10 项，未写入 `990401`。
- 场景资产审计：0 个可用 `VisualLocation`，19 个场景名缺失绑定，影响全部 164 个镜头，生产状态 `blocked`。
- 场景参考图计划：因当前没有任何 `VisualLocation` 草案，计划无法生成参考图条目；需先从剧本/分镜建立场景资产草案，再进入参考图生成确认。

## 发现与处理

1. 真实 LLM 主链路可以完成剧本和分镜生成，任务进度与数据库镜头记录一致。
2. 新样本真实暴露出质量门禁问题：剧本 QA 仍有连续性、视觉证据和节奏问题，不能直接进入媒体生产。
3. `ShotPlan` readiness 接口对 Markdown/非结构化剧本存在通用健壮性缺陷，已修复为安全返回 `200 + blocked`，并补充回归测试；正在运行的服务需重新加载代码后生效。

## 证据

- [可拍性回放 JSON](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/990401-shot-executability-replay.json>)
- [可拍性回放 Markdown](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/990401-shot-executability-replay.md>)
- [Prompt 只读审计 JSON](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/storyboard-prompt-real-sample-audit-2026-09-12T14-31-33-530Z.json>)
- [批量修复预检 JSON](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/storyboard-batch-repair-preflight-20260912T150727Z.json>)
- [批量修复预检 Markdown](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/storyboard-batch-repair-preflight-20260912T150727Z.md>)
- [场景资产审计 JSON](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/storyboard-scene-asset-readiness-20260912T150837Z.json>)
- [场景资产审计 Markdown](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/storyboard-scene-asset-readiness-20260912T150837Z.md>)
- [场景参考图计划 JSON](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/990401-scene-reference-plan.json>)
- [场景参考图计划 Markdown](<D:/Work/Project/screenplay-agent-refactor-v2/artifacts/990401-scene-reference-plan.md>)
- 回归测试：`python -m pytest -q tests/test_shot_plan.py`（8 passed）

## 结论

本次“真实 LLM 剧本 → 分镜”测试已完成，但 `990401` 当前是质量审查样本，不是可直接生图/生视频的生产样本。下一阶段应先处理 QA 阻断项、结构化场景/资产绑定和 Prompt Compiler 重编译，再考虑锁定资产及媒体灰度。
