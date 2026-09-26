# Model Adapter Design

## 1. 目标

ModelAdapter 把 Production Runtime 的 canonical generation request 转换为现有 provider transport 调用，并把异构 provider response 归一化为可持久化的 execution/candidate 结果。

它不管理模型配置、不管理 provider catalog、不管理资产、不创建任务队列。

## 2. 现有代码边界

当前已有三层能力：

1. api/model_registry.py：KV profile/default 配置、provider 校验、凭据配置状态。
2. core/provider_execution_profile.py：把 broad profile 投影为 typed、allowlisted、secret-free execution profile。
3. core/provider_transport_registry.py + api/generation_adapters.py：按 provider、target_media、transport binding 调用 image/video submit/poll。

core/model_adapter.py 当前还承担 ShotIR 到稳定视觉 Prompt 的确定性适配。它不是 provider 管理器。Production ModelAdapter 应组合该 Prompt adapter 和现有 transport registry，不能把两种职责重新混成一个 Model Registry。

## 3. 接口

建议的领域接口：

generate(
  model_profile,
  prompt_version,
  generation_params
) -> ModelAdapterResult

输入：

- 显式 model_profile_id 解析后的 profile
- 合格的 PromptIR/ProductionPromptVersion projection
- target_media 和 generation_mode
- reference authority bindings
- typed generation parameters
- execution/request fingerprint

输出：

{
  provider,
  model,
  provider_request_id,
  provider_task_id,
  terminal_status,
  media_uri_or_storage_identity,
  provider_response_projection,
  provider_response_hash,
  logical_provider_calls,
  transport_retry_count,
  latency_ms,
  error_code,
  error_message
}

ModelAdapterResult 不包含 api_key、authorization header 或 runtime credential。

## 4. 调用流程

1. Orchestrator 要求 model_profile_id，拒绝 AUTO/DEFAULT 或缺失 profile。
2. Model Registry 返回 profile；校验 capability 与 target_media 一致、enabled、credential 和 base_url/model_name。
3. ProviderExecutionProfile 对 default_params 做 allowlist 和类型归一化；禁止 profile 注入 negative_prompt/style 等创作语义。
4. 根据 provider + target_media + transport_binding_id 解析 ProviderTransportBinding。
5. 组合已冻结的 GenerationPayload；不在 Adapter 中改写 Prompt 或资产事实。
6. sync provider 一次调用后返回；async provider 由 submit/poll 适配器保存 provider_task_id 并等待 terminal result。
7. Adapter 只返回 normalized result；Orchestrator 写 GenerationExecutionRecord，storage ingestion 写 MediaCandidateRecord。

## 5. Provider 映射

| target | 现有 transport |
|---|---|
| IMAGE | openai-compatible.image.v1、poyo-async.image.v1、shapi-openai-images.image.v1、shapi-gemini-image.image.v1 |
| VIDEO | poyo-async.video.v1、minimax-h3-async.video.v1、75api-minimax-h3.video.v1 |
| local/dev | prototype-task-adapter 的 mock image/video |

绑定必须精确匹配 provider 和 target_media；不存在绑定时 fail closed。Adapter 不能根据模型名称猜测协议。

## 6. 错误与重试

- 配置错误、能力不匹配、缺少 PromptIR/reference authority：provider_calls=0，执行不进入 RUNNING。
- claim 冲突：读取已有 winner，不重复调用 provider。
- provider transport retry：只更新 transport_retry_count，不能创建新的业务 execution。
- provider terminal failure：FAILED，保存稳定 failure_code/message。
- provider 已提交但响应丢失：RECONCILE_REQUIRED，通过 provider_task_id 查询；禁止盲目再次提交。
- 用户要求的新生成：新 execution_id，保留 parent_execution_id 的 lineage 语义。

## 7. 凭据和可观测性

凭据从 Registry/credential source 进入短生命周期 runtime profile，在 transport 边界使用后销毁。request snapshot、fingerprint、audit log、workspace projection 均只包含脱敏配置。日志必须带 execution_id、provider_request_fingerprint、provider_task_id、adapter_version 和 latency，不记录 token。

## 8. 兼容策略

旧 creative generation endpoint 先把 request 转成 canonical payload，再调用同一个 ModelAdapter。旧 adapter 函数保留为 protocol implementation；Production Runtime 不再在 api/server.py 复制 provider 分支。
