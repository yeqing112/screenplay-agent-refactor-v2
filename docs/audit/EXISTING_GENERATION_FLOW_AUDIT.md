# Existing Generation Flow Audit

## 结论

当前系统是旧 creative task/storyboard 链、canonical generation canary 链、visual authoring proposal 链的组合。图片和视频已有 provider adapter，但只有 canonical 路径能证明完整的请求冻结、执行指纹和候选媒体审计边界。

## 真实链路

### 旧 creative task 链

用户在 workspace 点击生成 → ProductWorkspaceStoryboardMediaPanel.tsx 或 ProductWorkspaceStoryboardSection.tsx → POST /api/books/{book_id}/storyboard/{episode}/{shot_id}/generate-frame 或 generate-video → api/server.py::generate_image/generate_reference_image/generate_video → _enqueue_creative_task → process-local _creative_tasks + FastAPI BackgroundTasks → generation_adapters.py::generate_image_asset/generate_video_asset → provider response/storage reference → task status、legacy asset output、必要时 retry snapshot。

### Canonical generation 链

PromptIRPointer/PromptIRVersion + explicit model_profile_id → ProductionGenerationSelection → canonical_request_fingerprint → ProviderExecutionProfile → exact ProviderTransportBinding → generation adapter submit/poll → GenerationExecutionRecord → MediaCandidateRecord → MediaValidationRecord → OfficialMediaVersion/Authority/Pointer。

证据模块：core/canonical_generation.py、core/provider_execution_profile.py、core/provider_transport_registry.py、models/generation_execution.py、models/media_authority.py、api/generation_canary_api.py。

### Visual authoring proposal 链

VisualAssetAuthority request → /visual-assets/.../authoring-requests → /authoring-proposals/canary → model_registry.get_profile → core.llm.call_llm_json → VisualAuthoringProposal(REVIEW_REQUIRED) → human approve/reject → VisualAuthoringDecision。该链产生 authoring proposal/decision，不是 image/video media candidate；批准不会直接创建版本或移动 pointer。

## Agent 判断

run_script_pipeline、run_visual_setup、run_storyboard 在 api/server.py 中通过 asyncio.to_thread 执行 agent。多数 agent 产出结构化文本、Prompt、shot plan 和约束，provider 调用集中在 generation_adapters.py 与 canonical transport 层。因此旧 agent 路径是 A/B 混合，canonical 路径已有类型 C 骨架，但尚未统一所有入口。

## 关键断点

1. storyboard prompt compile、legacy shot fields 与 PromptIR pointer 并行。
2. creative task 状态依赖进程内字典，TaskRun 不是所有生成入口的唯一事实源。
3. provider 返回后的 storage ingestion、validation、official promotion 在旧入口与 canonical 入口之间不一致。
4. BackgroundTasks 不等同于跨进程 durable worker queue。
5. legacy generate-frame/generate-video 尚未全部经过 canonical readiness gate。

## 目标收敛链

User action → frontend service/component → canonical preview/confirm → PromptIR pointer + Production Prompt Lineage → GenerationOrchestrator → GenerationExecution → ModelAdapter/transport → provider submit/poll/reconcile → MediaCandidate → validation → authority promotion → OfficialMediaPointer。

