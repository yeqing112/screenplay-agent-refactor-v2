# Project Architecture & Runtime Audit

审计状态：AUDIT_COMPLETE
审计日期：2026-09-26
分支：codex/visual-authoring-provider-canary-reconcile
基线提交：62797ff

## 范围与方法

本轮只读审计，没有修改业务代码、数据库迁移或测试。Git 跟踪文件共 3,343 个；重点实现范围为 api、core、models、alembic、scripts 和 web/src，共 652 个文件，其中 backend 465、frontend 157、Alembic migration 50。

## 核心模块

- API：api/server.py、api/generation_canary_api.py、api/media_authority_api.py、api/visual_asset_authority_api.py、api/visual_authoring_provider_api.py
- 规范与编排：core/canonical_generation.py、core/provider_execution_profile.py、core/provider_transport_registry.py、core/production_workspace_projection*.py
- Provider：api/generation_adapters.py、core/model_adapter.py
- 持久化：models/prompt.py、models/generation_execution.py、models/media_authority.py、models/production_prompt_lineage.py、models/task.py、models/visual.py
- 前端：web/src/services/modelRegistry.ts、web/src/services/productionWorkspace.ts、web/src/domain/productionWorkspace.ts、web/src/pages/ProjectsPage.tsx、web/src/components/ProductWorkspace*.tsx

## 已确认能力

1. Storyboard、PromptIR、生成策略和资产绑定已有结构化持久化边界。
2. Model Registry 支持 LLM、embedding、image、video profile，默认模型解析和 provider/transport 绑定。
3. Canonical generation 已有显式 model_profile_id、目标媒体、请求 fingerprint、provider adapter/version、引用绑定 fingerprint。
4. GenerationExecutionRecord、MediaCandidateRecord、媒体验证、Official Media Version/Authority/Pointer 已形成候选到官方媒体的审计链。
5. Production Prompt Lineage 已能把 shot、prompt version、generation intent 和 asset version 串成不可变边。
6. Visual Asset Authority 已有 identity/version/pointer、reference authority、semantic review 和 provider proposal 人审边界。
7. FastAPI BackgroundTasks、TaskRun、进程内 creative task state、provider polling、人工确认 retry 均已存在。

## 主要架构结论

- Model Registry 是配置中心与 profile/adapter/transport 选择层，不是完整 Runtime。
- 当前有旧 creative task/storyboard 链和较新的 canonical generation canary 链，两者尚未完全收敛到一个生产编排入口。
- Task 有持久记录但没有被代码证明的独立 queue/worker/scheduler；生成运行时主要依赖 BackgroundTasks、asyncio 和进程内状态。
- Prompt 权威存在并行模型：StoryboardShot.visual_prompt_*、StoryboardPromptVersion、PromptIRVersion/Pointer、新 ProductionPromptVersion。
- 资产治理强于生成执行；Authority/version/pointer/review/provenance/checksum 已较完整，Runtime 收敛仍是下一阶段重点。

## 未确认风险

- 多进程部署时进程内 task state 与 TaskRun 可能分叉。
- 重启、租约、跨进程 claim、死信和调度器未被当前代码证明。
- 旧 endpoint 可能在缺少 canonical fingerprint 或显式 profile 时继续接受 legacy payload。
- 旧 Prompt 字段与 Production Prompt Lineage 的双写及读取优先级没有单一规范。
- storage identity 与真实对象存储、公开 URL、checksum 的统一 ingestion 尚需运行环境证据。

## 下一阶段建议

以 GenerationExecution 为唯一执行记录，以 GenerationOrchestrator 负责 preview、confirm、submit、poll、reconcile，以 ModelAdapter/transport binding 负责 provider 协议；旧入口只做兼容转换。随后统一 Prompt authority，再扩展更多 provider 或视频能力。

AUDIT_COMPLETE
