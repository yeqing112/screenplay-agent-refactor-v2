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

run_script_pipeline、run_visual_setup、run_storyboard 在 api/server.py 中通过 asyncio.to_thread 执行 agent。对目标 agent 的实际行为核对如下：

- agents/portrait.py（以及 portrait_base.py、portrait_stages.py）：调用 core.llm.call_llm_json 生成 CharacterProfile/VisualMakeup 的人物事实和提示词，写入数据库与输出 Markdown；没有 image model call，因此属于类型 A/B 的“文本提示词 + LLM”，不是图片生成 Runtime。
- agents/scene_setup.py：era_scan、run_props、run_locations、makeup 等调用 call_llm_json，将 VisualEraSpec、VisualProp、VisualLocation、VisualMakeup 写入数据库；输出视觉规格和 Prompt，不直接产出媒体，属于类型 A/B。
- agents/storyboard.py：用 call_llm/call_llm_json 生成场景和 StoryboardShot，包含 LLM 解析失败重试和结构化 fallback；写入 StoryboardShot 及资产绑定，不直接调用 image/video provider，属于类型 A/B。
- agents/prompt_synthesizer.py：从 StoryboardShot.asset_links 合成 visual_prompt_final，并写回 shot；在 asset_links 未就绪时 Phase 1 直接返回空列表，仍不调用 image/video provider，属于类型 A。

因此，旧 agent 层总体是类型 A（Prompt/结构化资产准备）并夹有 LLM model call；类型 C 只出现在后续 creative task/canonical generation 路径。provider 调用集中在 generation_adapters.py 与 canonical transport 层，尚未统一所有入口。

## 关键断点

1. storyboard prompt compile、legacy shot fields 与 PromptIR pointer 并行。
2. creative task 状态依赖进程内字典，TaskRun 不是所有生成入口的唯一事实源。
3. provider 返回后的 storage ingestion、validation、official promotion 在旧入口与 canonical 入口之间不一致。
4. BackgroundTasks 不等同于跨进程 durable worker queue。
5. legacy generate-frame/generate-video 尚未全部经过 canonical readiness gate。

## 目标收敛链

User action → frontend service/component → canonical preview/confirm → PromptIR pointer + Production Prompt Lineage → GenerationOrchestrator → GenerationExecution → ModelAdapter/transport → provider submit/poll/reconcile → MediaCandidate → validation → authority promotion → OfficialMediaPointer。
