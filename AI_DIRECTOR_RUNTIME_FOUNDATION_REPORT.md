# AI Director Runtime Foundation 最终报告

## 结果

`AI_DIRECTOR_RUNTIME_FOUNDATION_COMPLETE`

本阶段已经在现有 ScriptIR、Episode、Scene、Shot、CharacterProfile、SceneIdentity、VisualStyleProfile、ShotDirection、PromptLineage 和 GenerationExecution 之上建立 provider-free 的 AI Director Runtime 基础层：

```text
ScriptIR → DirectorPlan → ScenePlan → ShotPlan → ShotDirection → GenerationIntent
```

## 已交付

### Production UI 衔接增量（2026-10-02）

- 新增 ScriptIR production preparation facade 与剧本工作台人工确认入口。
- Production preparation 复用既有 ScriptIR authority activation、FactSnapshot 和版本链；不调用 LLM/媒体 provider。
- 导演方案、SceneBlocking、ShotPlan UI 在准备完成后携带 production profile 与 scene identity；分镜生成优先调用 canonical materializer。
- 该增量已通过 Web 445 tests、production authority 定向 24 tests、TypeScript build 与 Python compileall；完整浏览器业务链仍保留 `PARTIAL / ASSET_BLOCKED` 结论，未提前宣称全链路完成。

- `director_plan(script_ir, episode_context, character_profiles, scene_profiles)` 确定性 Adapter，返回结构化 JSON。
- 版本化 `DirectorPlan` 与 `ScenePlan` 持久化；ShotPlan 继续复用现有 canonical 表。
- ShotDirection 与 GenerationIntent 候选包含 source hash、direction fingerprint 和 prompt lineage。
- API：
  - `POST /episodes/{id}/director-plan`
  - `GET /episodes/{id}/director-plan`
  - `POST /shots/{id}/director-revise`
- 生成结果默认 `DRAFT` / `REVIEW_REQUIRED`，人工审核后才可进入后续 authority 与媒体流程。
- 生产图像 provider registry 保持 SHAPI：`https://www.shapi.vip/`；本阶段未调用 provider。

## 事实与安全边界

- LLM 调用：`0`
- Image 调用：`0`
- Video 调用：`0`
- 不自动生成视频或图片。
- 不修改 Source Fact 或 ScriptIR 原始事实。
- 所有计划和修订均版本化，旧版本保留。
- 人工修改仅允许白名单 shot 字段，且会生成新的 DirectorPlan 版本。

## 本轮 canary 决策

丢弃：`V3-CANARY-DISPOSABLE-20261001-R2`（Book `990403`）。它是通过正式 Book/Script bootstrap API 创建的 disposable canary，最适合作为清理对象。

- 删除方式：`DELETE /api/books/990403`
- 删除结果：`orphan_rows=0`
- `990400`：保留，未修改
- `998755`：未恢复

## 验证记录

- Director Runtime focused regression：`49 passed`
- 全后端回归：`2002 passed`
- Web：`63 files / 445 tests passed`
- Web build：`PASS`
- migration chain：`PASS`
- compileall：`PASS`
- `git diff --check`：`PASS`
- 真实 LLM、图片、视频 provider：均未调用

## 远程提交

- 分支：`codex/visual-authoring-provider-canary-reconcile`
- 代码提交：`cf5717a`；报告提交：`248c4f7`
- 远程仓库：[yeqing112/screenplay-agent-refactor-v2](https://github.com/yeqing112/screenplay-agent-refactor-v2)
