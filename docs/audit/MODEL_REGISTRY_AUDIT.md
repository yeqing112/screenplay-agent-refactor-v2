# Model Registry Audit

## 数据模型与持久化

Model Registry 没有独立 SQLAlchemy 表；api/model_registry.py 使用 runtime KV：model_registry_profiles、model_registry_defaults。环境变量和内建 profile 在读取时合并。

主要字段：id、name、capability（llm/embedding/image/video）、provider、base_url、model_name、default_params、enabled、builtin/source、generation_capability、adapter_id/version、credential_ref、credential_configured、runtime_binding_id、transport_binding_id。api_key 仅内部读取，列表响应默认脱敏。

内建 profile 包括环境 LLM、环境 embedding、mock image、mock video；provider allowlist 包括 openai-compatible、ollama、poyo-async、minimax-h3-async、75api-minimax-h3、shapi-openai-images、shapi-gemini-image、prototype-task-adapter。

## API

- GET /api/model-registry：返回 profiles、defaults、default_profiles；profile 列表默认去掉 api_key。
- GET /api/model-registry/defaults：返回 defaults 和 default_profiles。
- PUT /api/model-registry：请求体为 profiles[] 和 defaults{}；每个 profile 至少含 name、capability、provider，非 mock provider 还需合法 base_url/model_name；响应为保存后的同一 registry projection。
- POST /api/model-registry/test：请求体为 profile_id 或内联 profile；响应为连接测试结果、脱敏 provider/model 信息和错误诊断，不创建 generation execution。
- GET/PUT /api/agent/model-config：旧 agent 兼容面

## 前端

web/src/services/modelRegistry.ts 封装请求；ProjectsPage.tsx 打开 ModelRegistryModal；AgentModelConfigPanel.tsx 读取同一 registry；Product Workspace 组件使用 profile/default 作为生成前置选择和诊断信息。

## 能力判断

结论：A，Model Registry 是配置中心，并额外提供 profile/adapter/transport 选择投影，不是完整 Runtime。

依据：

1. 持久化是 KV 配置，不负责 task lease、submit/poll、执行状态、媒体 ingestion 或官方晋级。
2. provider 调用在 api/generation_adapters.py 和 core/provider_transport_registry.py。
3. 执行审计和媒体候选由 GenerationExecutionRecord、MediaCandidateRecord、MediaValidationRecord 管理。
4. core/provider_execution_profile.py 只是 typed、secret-free、allowlisted execution projection。

## 建议

保持 Registry 为配置/选择层；生产执行要求显式 profile id，并冻结 profile fingerprint、adapter version、transport binding；凭据只在 transport 边界短暂注入；禁止在 Registry 中新增 ModelManager、队列或资产写入职责。
