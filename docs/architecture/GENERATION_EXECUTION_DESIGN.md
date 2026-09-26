# Generation Execution Design

## 1. 设计目标

GenerationExecution 是一次可审计、可幂等、可恢复的 provider 执行边界。它把 Prompt、模型选择、资产引用、provider 请求和最终候选媒体绑定在一起，避免旧路径中“Prompt 直接写 Asset”以及进程内任务状态成为事实源。

当前代码已有 models/generation_execution.py 的 GenerationExecutionRecord。本文中的 GenerationExecution 是该记录的领域投影和状态协议，不是新建第二张执行表。

## 2. Entity

逻辑实体：

{
  id: execution_id,
  shot_id: storyboard_shot_id,
  prompt_version_id: prompt_ir_version_id,
  model_profile_id: model_profile_id,
  status: PREVIEWED | RUNNING | SUCCEEDED | FAILED | STALE | REUSED,
  request_payload: secret-free request snapshot,
  response_payload: secret-free provider response projection,
  error_message: failure_message,
  retry_count: transport_retry_count plus separately tracked business retry lineage,
  created_at: created_at,
  completed_at: completed_at
}

已有字段映射：

| 领域字段 | 当前持久化映射 |
|---|---|
| id | generation_execution_records.execution_id |
| shot_id | storyboard_shot_id + book_id + episode |
| prompt_version_id | prompt_ir_version_id；ProductionPromptVersion 通过 PromptIR materialization/lineage 关联 |
| model_profile_id | model_profile_id |
| request_payload | request_snapshot_json，必须脱敏 |
| response_payload | provider/provider_request_id/provider_task_id/provider_response_hash 等 projection；原始 secret 不落库 |
| error_message | failure_code + failure_message |
| retry_count | transport_retry_count；人工业务 retry 使用独立 retry lineage，不覆盖原执行 |
| candidate | candidate_id，指向 MediaCandidateRecord |
| identity | generation_payload_fingerprint、generation_policy_fingerprint、model_profile_fingerprint、provider_request_fingerprint |
| adapter | provider_adapter_id + provider_adapter_version |
| time | created_at、submitted_at、completed_at、updated_at |

必须保留 target_media、reference_bindings_fingerprint、confirmation_binding_hash 和 logical_provider_calls。它们是执行审计和幂等判断的一部分。

## 3. 状态机

执行状态与资产/审核状态分离。

Execution 状态：

CREATED（领域请求，尚未生成预览）
→ PREVIEWED（请求已冻结，未调用 provider）
→ AUTHORIZED（确认 token 合法，可执行）
→ RUNNING（单 worker 已 claim）
→ SUCCEEDED（provider 返回且 candidate 已持久化）
→ REUSED（同 fingerprint 命中可复用执行）

异常分支：

PREVIEWED/AUTHORIZED → STALE（PromptIR、资产引用、模型 profile 或确认绑定变化）
RUNNING → FAILED（provider 或持久化失败）
FAILED → RETRYING → 新的 PREVIEWED execution（新的 execution_id，保留 parent lineage）
RUNNING → RECONCILE_REQUIRED（进程/网络中断，provider task 可能已提交）

下游媒体状态：

SUCCEEDED → MEDIA_CANDIDATE → VALIDATION_PENDING → VALIDATED
VALIDATED → REVIEW_PENDING → OFFICIAL_PROMOTED
VALIDATED → REJECTED
OFFICIAL_PROMOTED → superseded（新 revision 产生，不覆盖历史）

当前 canonical canary 已实现 PREVIEWED、RUNNING、SUCCEEDED、REUSED、FAILED、STALE 的关键转换；AUTHORIZED、RECONCILE_REQUIRED 和 REVIEW_PENDING 是统一 Runtime 需要显式固化的领域语义，不代表本轮已经实现。

状态转换规则：

- PREVIEWED 只能由当前 PromptIR、profile、payload 和 confirmation binding 验证通过后进入 AUTHORIZED。
- 同一 provider_request_fingerprint 只能有一个胜出的执行；并发 claim 使用条件更新，失败者读取胜者。
- FAILED 不能复用原 confirmation token；retry 必须创建新执行。
- SUCCEEDED 必须已经有自洽的 MediaCandidateRecord，不能只凭 provider response 标记成功。
- candidate validation 或 review 失败不回写为 provider FAILED，而是在下游记录拒绝原因。
- stale execution 不允许继续调用 provider。

## 4. API 设计

### 创建/预览

POST /generation/executions

请求核心字段：

{
  book_id, episode, shot_id,
  target_media: IMAGE | VIDEO,
  model_profile_id,
  generation_mode,
  reference_bindings
}

响应：

{
  execution,
  generation_payload,
  provider_request_snapshot,
  confirmation_token,
  provider_calls: 0,
  reused,
  media_generated
}

现有等价入口是 /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/preview；稳定 API 可作为 facade，不能另建一套执行逻辑。

### 执行确认

POST /generation/executions/{id}/execute

请求：

{
  execute: true,
  confirmation_token,
  preview_execution_id
}

现有等价入口是 /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation/execute。确认 token 必须绑定 execution、PromptIR version、payload fingerprint、model profile 和 provider request fingerprint。

### 查询状态

GET /generation/executions/{id}

响应包含 execution、candidate（如有）、validation/official projection（如有）、failure_code/message、provider task id 和下一步允许动作。当前 canonical canary 返回 execution projection，但尚无独立 GET route；该 GET 是统一 Runtime 的必要读接口，不应让前端读取数据库或 process-local state。

### 重试

POST /generation/executions/{id}/retry

请求：

{
  reason,
  confirmed: true,
  override_model_profile_id: optional
}

默认从 immutable request snapshot 生成新的 PREVIEWED execution；不修改失败执行，不自动更改 PromptIR 或 official pointer。视频 continuity retry 继续复用现有人工确认边界，但应统一映射到该 lineage。

### 媒体验证与晋级

现有 /api/media-authority/candidates/{candidate_id}/validate 和 /api/media-authority/promote 继续作为下游 authority API。Generation Runtime 只创建 candidate，不绕过验证直接 promote。

## 5. Task 集成

TaskRun 继续表示 pipeline 级任务。GenerationExecution 不作为 BackgroundTasks 的临时字典，而是 provider 执行唯一事实源。最小 worker 机制：

1. 创建/确认 execution 后，以数据库条件更新 claim。
2. claim 成功者调用 ModelAdapter。
3. 对异步 provider 保存 provider_task_id，轮询或恢复 worker 继续 reconcile。
4. 每次 terminal transition 都写 execution 和 candidate。
5. 重启时扫描 RUNNING/RECONCILE_REQUIRED，而不是依赖 _creative_tasks。

外部队列不是本设计前提；在没有独立 worker 时可以先使用数据库 claim + 周期 reconcile，但必须把重复执行和恢复语义落到持久记录。

## 6. 幂等与安全

- provider_request_fingerprint 是唯一幂等边界。
- confirmation_token 是一次预览绑定，不是长期权限。
- request/response snapshot 脱敏，API key 只在 provider transport 短生命周期存在。
- transport retry 与业务 retry 分开计数。
- 任意 PromptIR、模型 profile、reference authority 变化都会使预览 stale。
