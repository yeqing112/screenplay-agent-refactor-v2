# Production Runtime Architecture

设计状态：ARCHITECTURE_DESIGN_COMPLETE
设计基线：codex/visual-authoring-provider-canary-reconcile @ e479074
依据：docs/audit/ 全部审计报告

## 1. 架构状态判断

选择：状态 B，已有部分生成能力，需要 Adapter 和统一 Production Runtime 编排。

原因：

1. portrait、scene_setup、storyboard、prompt_synthesizer 已能调用 LLM，生成角色、场景、道具、分镜和 Prompt，但它们不直接完成图片/视频生产。
2. 旧 creative task 已能调用 generation_adapters.py，并维护进程内任务状态；canonical generation canary 已能冻结 PromptIR、模型 profile、adapter、payload fingerprint，并写入 GenerationExecutionRecord 与 MediaCandidateRecord。
3. Model Registry 只负责 profile/default/configuration，不能承担 claim、submit、poll、reconcile、candidate 或 review。
4. Asset Authority、Version、Pointer、Binding、Review 和 Prompt Lineage 已存在，因此缺少的是统一执行边界，而不是新的资产或模型管理系统。
5. 当前旧路径与 canonical 路径并行，重试、状态来源和媒体晋级尚未收敛。

## 2. 总体架构

目标链路：

StoryboardShot
→ ProductionGenerationIntent
→ ProductionPromptVersion（创作谱系）
→ Prompt Compiler / PromptIR materialization
→ PromptIRVersion + PromptIRPointer（可执行权威）
→ GenerationExecution
→ GenerationOrchestrator
→ ModelAdapter
→ Model Registry + Provider Transport Binding
→ External Model API
→ MediaCandidateRecord
→ MediaValidationRecord
→ OfficialMediaVersion / OfficialMediaAuthority / OfficialMediaPointer
→ Review Workflow / Production Asset

模块边界：

| 模块 | 复用实现 | 生产职责 |
|---|---|---|
| 创作输入 | StoryboardShot、StoryboardPromptVersion | 提供编辑输入和兼容读取面 |
| Prompt 谱系 | ProductionPromptVersion、ProductionGenerationIntent、ProductionPromptLineage | 保存不可变创作意图和来源 |
| Prompt 执行权威 | PromptIRVersion、PromptIRAuthority、PromptIRPointer | 为具体 shot/media 生成合格、可指纹化 payload |
| 执行记录 | GenerationExecutionRecord | 固化一次执行及其幂等身份 |
| 编排 | 设计中的 GenerationOrchestrator | readiness、确认、claim、submit、poll、reconcile、retry |
| 模型边界 | Model Registry、ProviderExecutionProfile、ProviderTransportBinding、generation_adapters.py | 解析 profile、校验参数、调用 provider |
| 资产治理 | VisualAssetVersion/Pointer、MediaCandidateRecord、OfficialMedia* | 候选、版本、权威和指针 |
| 人工审核 | production asset reviews/history、media validation、authoring decisions | 决定是否进入生产 |
| 前端读模型 | production_workspace_projection_v2 | 统一展示执行、候选、验证、官方媒体 |

不创建 ModelManager、ProviderManager、AssetManager，也不创建第二套 Task/Queue 系统。

## 3. 生产执行数据流

1. 用户在 Production Workspace 选择 shot。
2. 后端读取当前 shot、generation intent、fresh asset/reference bindings 和 target-media PromptIRPointer。
3. Prompt compiler 将旧 storyboard/editor 输入物化为 ProductionPromptVersion，再生成并校验 PromptIRVersion。
4. Orchestrator 解析显式 model_profile_id，生成 typed ProviderExecutionProfile，冻结 payload/policy/profile/adapter/reference fingerprints。
5. 系统先创建 PREVIEWED 的 GenerationExecution，并返回脱敏 request snapshot 与 confirmation token；此阶段 provider_calls 为 0。
6. 用户确认后，Orchestrator 以 provider_request_fingerprint 做幂等 claim，状态转为 RUNNING。
7. ModelAdapter 通过精确的 provider + target_media + transport_binding 调用现有 image/video adapter；凭据只在 transport 边界注入。
8. provider 返回的媒体先写入 MediaCandidateRecord，保存 storage identity、checksum、尺寸/时长、provider response hash 和完整 lineage。
9. Media Authority 做技术验证；验证通过后，人工或授权晋级创建 OfficialMediaVersion/Authority 并移动 OfficialMediaPointer。
10. Workspace v2 读取 canonical projection；legacy UI 不再直接把 provider response 当作正式资产。

## 4. 读写边界

- PromptIRPointer 是可执行 Prompt 的唯一入口。
- ProductionPromptVersion 是创作谱系，不绕过 compiler 直接作为 provider 请求。
- GenerationExecution 是执行事实源；TaskRun 只表示上层脚本/视觉 pipeline。
- MediaCandidate 是 provider 成功后的候选事实；OfficialMediaPointer 才是生产读取事实。
- provider response 不得直接覆盖 VisualAssetPointer 或 OfficialMediaPointer。
- 所有 request snapshot、fingerprint、response projection 均不得包含 API key 或 runtime credential。

## 5. 兼容路线

旧的 generate-frame、generate-video 和 creative task 入口保留为兼容 facade：先转换为 canonical generation selection，再进入同一 Orchestrator。旧字段 visual_prompt_*、StoryboardPromptVersion 和旧 asset_links 作为 read/rollback projection，经过回填和 parity 证明后停止直接写入。

## 6. 核心架构原则

创作智能负责想什么；Prompt compiler 负责把创作意图物化为可执行结构；Production Runtime 负责怎么生成、如何重试和恢复；Asset Governance 负责如何保存和选择结果；Review Workflow 负责如何进入生产。

## 7. 数据关系

Project/Book
→ Episode/Chapter
→ StoryboardShot
→ ProductionGenerationIntent
→ ProductionPromptVersion
→ PromptIRVersion + PromptIRPointer
→ GenerationExecutionRecord
→ Model Profile（Model Registry 的逻辑关联）
→ MediaCandidateRecord
→ MediaValidationRecord / Review
→ OfficialMediaVersion + OfficialMediaPointer
→ Production Asset

关系边界：

- Project/Book、Episode/Chapter 和 StoryboardShot 是创作与镜头范围。
- GenerationIntent 保存 shot-derived constraints；Prompt lineage 保存创作来源；PromptIRPointer 决定可执行版本。
- Model 不建立新的 SQL 外键表；execution 通过显式 model_profile_id、profile fingerprint、adapter/version 和 transport binding 形成逻辑关系。
- MediaCandidate 是执行结果的候选版本，Review/validation 决定是否能够创建 OfficialMediaVersion 并移动 pointer。
- Production Asset 是由现有 Visual Asset Authority/Official Media Authority 读取出的正式结果，不是新建的资产实体。

ARCHITECTURE_DESIGN_COMPLETE
