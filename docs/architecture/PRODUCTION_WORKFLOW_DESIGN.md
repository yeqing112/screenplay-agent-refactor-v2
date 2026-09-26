# Production Workflow Design

## 1. 用户工作流

选择 Shot
→ 查看 Generation Intent
→ 查看当前 Prompt Version / PromptIR readiness
→ 选择显式模型 profile
→ 预览生成请求
→ 确认 provider 调用
→ 查看 execution 状态
→ 查看 candidate 媒体
→ 运行技术验证
→ 人工审核
→ 采用为 Production Asset

任何一步的 blocker 都必须显示稳定 reason code；前端不能根据空字段猜测 ready。

## 2. 前端与后端交互

| 用户动作 | 当前/目标前端 | 当前/目标 API | 返回投影 |
|---|---|---|---|
| 打开工作区 | ProductWorkspace*.tsx + productionWorkspace.ts | GET /api/books/{book_id}/production-workspace-v2 | shot、PromptIR、model、adapter、execution、candidate、official |
| 查看生成意图 | workspace domain projection | workspace v2 中的 generation intent/readiness | requirements、constraints、stale reasons |
| 选择模型 | ModelRegistryModal、modelRegistry.ts | GET /api/model-registry | profiles/defaults，脱敏 |
| 预览 | 新 generation service | POST /generation/executions；兼容 /api/books/.../generation/preview | PREVIEWED execution、payload、token |
| 确认生成 | 新 generation service | POST /generation/executions/{id}/execute；兼容 /api/books/.../generation/execute | RUNNING/SUCCEEDED/FAILED |
| 轮询状态 | execution service | GET /generation/executions/{id} | execution + candidate + validation/official |
| 验证媒体 | media authority service | POST /api/media-authority/candidates/{candidate_id}/validate | validation |
| 人工采用 | review/media authority UI | POST /api/media-authority/promote | official version/authority/pointer |
| 重试 | execution/retry panel | POST /generation/executions/{id}/retry | 新 PREVIEWED execution 与 parent lineage |

当前 workspace 已有 model registry 和 production workspace projection，但旧 storyboard media panels 仍能调用 legacy generate-frame/generate-video；接线目标是让它们成为 canonical facade 的调用方。

## 3. 页面状态

### Ready

- 当前 Shot 存在 fresh PromptIRPointer。
- generation policy 与 target_media 一致。
- explicit model profile enabled、credential/configuration valid。
- 所有 required asset/reference authority fresh、locked、storage identity 可用。
- 没有同 fingerprint 的 RUNNING 冲突。

### Previewed

显示脱敏 prompt payload、模型、provider、references、fingerprints 摘要和费用/外部调用提示；provider_calls 必须为 0。用户确认后才允许 execute。

### Running

显示 execution_id、provider/task 状态、开始时间、poll/reconcile 信息。页面刷新后从 GET execution 恢复，不依赖本地 task state。

### Candidate / Review pending

显示 candidate preview、checksum、尺寸/时长、validation diagnostics、来源 lineage。用户可验证、批准或拒绝；不能直接覆盖官方媒体。

### Blocked / Failed / Stale

显示 reason code、可执行动作和是否需要新 preview。失败 retry 生成新 execution；Prompt/asset/model 变化要求重新预览。

## 4. 后端时序

1. workspace projection 返回 readiness 和 current pointers。
2. 前端提交 preview；Orchestrator 重新从数据库解析权威对象，不信任前端复制的 Prompt 或资产内容。
3. preview 创建 GenerationExecutionRecord，返回 confirmation token。
4. execute 做 token、URL shot、PromptIR、asset/reference currentness 验证，再条件 claim。
5. ModelAdapter submit/poll，结果写 candidate 和 execution。
6. 前端读取 execution status；验证与 promotion 走现有 media authority API。
7. workspace projection 更新 official pointer 和历史记录。

## 5. 与现有任务运行时的关系

脚本、视觉设置、storyboard 等上层 Pipeline 仍使用 TaskRun；媒体执行不再把 BackgroundTasks 的进程内字典作为唯一状态。短期可由现有 API background worker 驱动，但每个 provider call 都必须先有 durable GenerationExecutionRecord，重启后按 RUNNING/RECONCILE_REQUIRED 进行恢复。

## 6. 迁移策略

### Phase 0：兼容读

不改 schema。workspace 使用 v2 projection；legacy Prompt/asset 字段只作为来源和诊断。

### Phase 1：统一写路径

legacy generate-frame/generate-video 转 canonical preview/execute；所有新 provider 调用必须产生 GenerationExecutionRecord 和 MediaCandidateRecord。

### Phase 2：Prompt authority

将 StoryboardPromptVersion/visual_prompt_final 通过 compiler 生成 ProductionPromptVersion，再物化合格 PromptIRPointer；旧字段变为 read-only projection。

### Phase 3：Runtime 恢复

在真实多 worker 部署前，单独规划 execution claim lease、provider reconciliation 和 retry lineage 的 schema/worker 迁移。此设计不创建 migration。

### Phase 4：收敛读取

前端只读 production workspace v2 和 official media authority；完成 parity 后停止 legacy direct media writes。

## 7. 验收重点

- 同一 fingerprint 并发请求只产生一次 provider call。
- 无 PromptIR/reference/model readiness 时零 provider call。
- provider 成功只生成 candidate，必须经过 validation/promotion 才成为 official。
- 刷新页面、进程重启和 provider polling 不丢失执行状态。
- retry 不修改旧 execution、Prompt 或 official pointer。
- workspace、media authority 和审计 projection 对同一 execution 显示一致 lineage。

ARCHITECTURE_DESIGN_COMPLETE
