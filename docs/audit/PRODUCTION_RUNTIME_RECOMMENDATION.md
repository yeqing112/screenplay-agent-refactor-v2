# Production Runtime Recommendation

## 选择：B — 需要 Adapter，并完成一个收敛的 Orchestrator

不应重写 Model Manager、Asset Manager 或 Provider Manager。项目已有 canonical primitives，但旧入口尚未全部经过同一执行状态机；应包装已有能力并收敛为 Production Runtime。

## 可复用能力

ProductionGenerationSelection、canonical_request_fingerprint、PromptIR pointer、ProviderExecutionProfile、ProviderTransportBinding、generation_adapters image/video submit/poll、GenerationExecutionRecord、MediaCandidateRecord、validation/official authority、production workspace v2 projection。

## 三个允许的职责

### GenerationExecution

固定 preview/confirm/claim/submit/poll/terminal 状态和 immutable request snapshot；以 provider_request_fingerprint 幂等；禁止 secret 进入 snapshot。

### GenerationOrchestrator

负责 readiness gate、confirm binding、claim/lease、submit/poll/reconcile、terminal state、retry policy；不解析业务 Prompt，不直接维护 asset pointer。

### ModelAdapter / transport binding

保留 provider-specific protocol 在 generation_adapters.py，由显式 provider + target_media + binding_id 选择；统一 submit/poll/result normalization/error codes；凭据只在 transport 边界注入。

## 生产边界

缺少合格 PromptIR pointer、显式 profile、fresh asset/reference 或 generation payload 时拒绝执行；provider 成功只产生 candidate，经 validation 和授权才移动 official pointer；retry 默认使用 immutable snapshot；legacy endpoint 先转换为 canonical request。

## 不建议

新增 ModelManager、AssetManager、ProviderManager；把 Registry 变成队列；在前端拼 provider 请求；让 provider 响应直接覆盖 canonical pointer；状态机未统一前继续增加 provider。
