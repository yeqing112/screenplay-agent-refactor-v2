# Production Pipeline V2 — Repository Audit

审计日期：2026-09-13  
基线：`codex/unify-formal-workspace` @ `ce0ad6976c2ed80e04b52c1023c8fc3fa31b4a6a`  
范围：仓库实现、Alembic 迁移、现有测试与 API 契约；本审计阶段不修改业务代码、不调用真实 LLM/图片/视频/对象存储。

## 审计方法与基线事实

- 已检查 `models/`、`core/`、`api/`、`agents/`、`alembic/versions/`、`tests/`、`docs/` 和 `CHANGELOG.md`。
- 仓库检测到约 2,355 个文件、约 10,033,566 词；其中大量是历史截图、运行报告和媒体产物，不能视为生产实现。审计结论以源码、迁移和测试为准。
- 现有后端全量回归：`pytest -q --disable-warnings` → **652 passed**，**864 warnings**，215.34s。通过不等于满足 V2 不变量；下文列出缺口。
- 当前工作树已有用户/历史运行产物变更：`artifacts/chain-test-with-issues-report.json`、`artifacts/full-pipeline-test-report.json` 以及大量未跟踪报告。审计未清理、未覆盖这些文件。
- 当前 Alembic 最新链为 `i2c3e4f5g6g7`（layered prop semantics）；尚无 `script_ir_versions`、`fact_snapshots` 或统一 artifact 状态字段迁移。

## Milestone 状态总览

| Milestone | 状态 | 结论 |
|---|---|---|
| M0 状态模型与 Production Profile | **未满足** | 仍以各表 legacy `status` 和 `REQUIRE_SHOT_PLAN_BY_DEFAULT` 为主，没有统一三态状态协议与 profile 门禁。 |
| M1 ScriptIR | **未满足** | `Script.content` 仍是 Markdown/自由 JSON 混合；无 ScriptIR 模型、版本表和 renderer。 |
| M2 FactSnapshot | **未满足** | 有 DecisionPacket 证据语义，但无统一 FactRecord/FactSnapshot、权威与 unknown 路由。 |
| M3 Asset Registry 自动资产化 | **部分满足** | 有 Visual* 与分层语义字段及场景审计，但 Qualified ScriptIR 不会自动同步 Canonical 主卡。 |
| M4 ShotPlan V2 | **部分满足** | 有 ShotPlan/preview/confirm/回滚，但 builder 输出 `camera=None`、`duration_hint_seconds=None`，不是完整生产中间层。 |
| M5 Executability 前移 | **部分满足** | 有 `core/shot_executability.py` 和回放脚本，但未形成 ShotPlan→修复→Approved ShotPlan 门禁。 |
| M6 Storyboard Materializer | **未满足** | 正式 API 仍调用 `StoryboardAgent` 自由生成，再附加 ShotPlan provenance。 |
| M7 Prompt Compiler A/B | **部分满足** | 有 Prompt IR、deterministic/LLM 路径和诊断，但没有 StoryboardShot 创建即强制 Phase A 状态。 |
| M8 First-Pass Qualification Loop | **未满足** | 没有统一 qualification_loop/issue_router/local_repair 闭环。 |
| M9 Root Cause Aggregator | **未满足** | 现有报告以症状计数为主，无稳定根因 ID 与跨镜头聚合。 |
| M10 QA 职责重构 | **部分满足** | 已有多类 QA、预检和审计，但 Validator/Director QA/Human Review 的责任边界尚未成为统一生产门禁。 |

## 逐项差距审计

### M0 — 状态模型与 Production Profile（未满足）

**已满足/可复用**

- `config.py` 已有 `DEPLOYMENT_ENV`、`REQUIRE_SHOT_PLAN_BY_DEFAULT`、旧执行层开关及生产安全配置。
- 各模型保留 legacy `status`，部分表已有 `draft/approved/superseded`。
- 可复用生产门禁与 readiness 逻辑：`api/server.py`、`api/shot_plan_api.py`、`tests/test_production_readiness.py`、`tests/test_production_security_config.py`。

**缺口**

- `models/storyboard.py`、`models/script.py`、`models/director_treatment.py`、`models/scene_blocking.py`、`models/shot_plan.py` 没有统一 `execution_status`、`quality_status`、`production_status`、`workflow_profile`。
- `/api/pipeline/storyboard` 只有 `generation_mode`、`force_llm`、`require_shot_plan`；客户端参数仍可在开发默认下选择自由 LLM 路径。
- 没有集中式 `core/production_policy.py` 及可行动 blocking reasons。

**需新增/修改**

- 新增 `core/production_policy.py`、`tests/test_production_policy.py`。
- 对上述 artifact 表增加兼容字段和索引；新增 Alembic 迁移（保留旧 `status`）。
- 在 storyboard、treatment、blocking、shot-plan API 统一调用 policy；`creative_draft` 永远 `production_status=blocked`。

**风险/API 冲突**

- 直接把 `REQUIRE_SHOT_PLAN_BY_DEFAULT=true` 当最终修复会破坏现有兼容调用，且不能解决 ScriptIR/Compiler 缺失；应采用显式 profile + fail-closed production gate。

### M1 — ScriptIR（未满足）

**已满足/可复用**

- `agents/scriptwriter.py`、`core/screenplay_compiler.py`、`core/production_skill.py` 已有剧本生成与结构化技能。
- `Script` 及 `EpisodeOutline` 可保留为人类可读兼容表；现有 Director Treatment/Blocking/ShotPlan API 可作为迁移入口。

**缺口**

- 没有 `models/script_ir.py`、`core/script_ir.py`、`core/script_renderer.py` 和 `script_ir_versions` 表。
- Director Runtime 在 `api/director_treatment_api.py`、`api/scene_blocking_api.py`、`api/shot_plan_api.py` 通过 `Script.content` 读取 `scenes`；Markdown 与 JSON 混用，形成协议断层。

**需新增/修改**

- 新增 ScriptIR schema、版本化持久化、hash/source fingerprint 和 Markdown renderer；Script.content 仅保留渲染结果。
- 改造 `agents/scriptwriter.py`、`core/screenplay_compiler.py` 先产出 ScriptIR，再渲染 Markdown。
- 新增 Alembic `script_ir_versions`，并为旧 Markdown 提供一次性 `legacy_reconstruction`（`needs_review`，不得直接 qualified）。
- 新增 `tests/test_script_ir.py`、`tests/test_script_ir_renderer.py`、`tests/test_script_ir_director_runtime.py`。

**风险/API 冲突**

- 旧客户端可能直接写 Markdown；兼容层必须明确标记来源和 stale，而不是静默解析成权威事实。

### M2 — FactSnapshot（未满足）

**已满足/可复用**

- `core/decision_packet.py` 和 `models/visual.py` 已使用 `locked_fact`、`approved_fact`、`derived_fact`、`unknown` 等证据层级。
- 资产治理与脚本 QA 已有受控草案、指纹和确认门。

**缺口**

- 无 `FactRecord`、`FactSnapshot`、`fact_snapshot_versions` 模型/迁移；无统一 authority、conflict group、unknown routing。
- 性别、关系、道具归属、时间顺序等跨 Script/Asset/Storyboard 事实仍可能由下游重新猜测。

**需新增/修改**

- 新增 `models/fact_snapshot.py`、`core/fact_snapshot.py`（或等价单一实现），Alembic 迁移及 `tests/test_fact_snapshot.py`、`tests/test_fact_authority.py`、`tests/test_unknown_routing.py`。
- 将 DecisionPacket 作为证据载体复用，FactSnapshot 只保存规范化权威结果及 source fingerprint；变更触发下游 stale。

**风险/API 冲突**

- 不应再造平行 DecisionPacket；需定义 FactSnapshot 与现有 decision packet 的引用关系，避免双重真相。

### M3 — Asset Registry 自动资产化（部分满足）

**已满足/可复用**

- `models/visual.py` 已有 `VisualMakeup`、`VisualLocation`、`VisualProp`、`VisualReferenceAsset`。
- `VisualLocation`/`VisualProp` 已有 `canonical_facts`、`state_variants`、`look_profile`；场景另有 `board_spec`。
- `core/scene_reference_plan.py`、`scripts/plan-storyboard-scene-reference-assets.py`、`scripts/audit-storyboard-scene-asset-readiness.py` 已提供计划与审计。

**缺口**

- 没有从 Qualified ScriptIR 自动同步 Character/Scene/Prop Canonical 的 registry service；`VisualLocation` 不会因 ScriptIR 场景自动创建。
- reference requirement 与 `ir_ready/reference_optional/reference_required/locked/production_ready` 尚未统一为协议。

**需新增/修改**

- 新增 `core/asset_registry_sync.py` 及迁移字段（必要时扩展现有 Visual*，不新造 SceneCanonical 表）。
- 新增 `tests/test_asset_registry_sync.py`、`tests/test_scene_asset_readiness_from_script_ir.py`；验证幂等、不重复、optional 不阻断、required 无 locked reference fail-closed。

**风险/API 冲突**

- 资产主卡创建不能隐式触发生图或上传；必须与媒体生成链解耦。

### M4 — ShotPlan V2（部分满足）

**已满足/可复用**

- `models/shot_plan.py`、`core/shot_plan.py`、`api/shot_plan_api.py` 有 preview/persist/confirm、证据指纹、版本 supersede 与 rollback anchor。
- `tests/test_shot_plan.py` 已验证只读预览、unknown 阻断、确认和 scene scope。

**缺口**

- `core/shot_plan.py::build_shot_plan()` 明确输出 `camera=None`、`duration_hint_seconds=None`，把景别/机位/时长留给人工 unknown。
- shots 缺 `scene_id`、完整 camera contract、action beat 时间窗口、entry/exit state、asset bindings、continuity contract。
- SceneBlocking 字段没有完整 materialize 到每个 shot；当前仅记录 `spatial_source`/继承说明。

**需新增/修改**

- 扩展 ShotPlan schema/模型 payload，新增 `core/shot_plan_v2.py` 或在现有模块内版本化；新增 Alembic 字段/JSON schema 迁移。
- 新增 `tests/test_shot_plan_v2.py`、`tests/test_shot_plan_asset_bindings.py`、`tests/test_shot_plan_continuity_contract.py`。

**风险/API 冲突**

- 旧确认请求只提交简单 shots；需保留兼容解析但 production profile 必须要求 V2 完整字段。

### M5 — Executability 前移（部分满足）

**已满足/可复用**

- `core/shot_executability.py` 已能识别动作超载、对白预算、状态缺失、运动提示词漂移。
- `core/shot_planner.py`、`scripts/audit-shot-executability-replay.py`、`tests/test_shot_executability.py`、`tests/test_shot_executability_replay_gate.py` 可复用。

**缺口**

- 可拍性检查仍主要在 storyboard/回放审计层发生，未成为 ShotPlan approval 的必经步骤。
- 没有统一 `core/executability.py` 的 ShotPlan V2 输入、repair plan、重验证与 max-attempt 策略。

**需新增/修改**

- 将现有规则适配 ShotPlan V2；在 confirm 前强制 preflight，失败返回可行动 repair options。
- 新增 `tests/test_executability_preflight.py`；用静态 golden fixture 覆盖已知 4 秒多动作失败，不调用供应商。

**风险/API 冲突**

- 不能通过缩短 Prompt 或删除 warning 掩盖动作超载；修复只能改 ShotPlan 层，关键动作不得静默丢失。

### M6 — Storyboard Materializer（未满足）

**已满足/可复用**

- `agents/storyboard.py`、`api/server.py` 已有生成任务、断点恢复、场景重试和 deterministic fallback。
- `api/shot_plan_api.py` 的 provenance attach/diff 可作为迁移期间审计工具。

**缺口**

- `POST /api/pipeline/storyboard` 在 `require_shot_plan=true` 时只检查某集存在 approved ShotPlan，然后仍调用 `StoryboardAgent.run`；随后才附加 `shot_plan_ref`。
- 无 `core/storyboard_materializer.py`，因此无法保证 production StoryboardShot 与 ShotPlan 100% 一一映射、无额外镜头。

**需新增/修改**

- 新增 `core/storyboard_materializer.py`、`tests/test_storyboard_materializer.py`、`tests/test_storyboard_shot_plan_compliance.py`、`tests/test_production_storyboard_gate.py`。
- API 按 profile 分流：creative_draft 可保留 Agent；production 只能 Approved ShotPlan→Materializer。

**风险/API 冲突**

- 旧 `generation_mode=director_llm` 不能覆盖 production policy；`StoryboardAgent` 应降级为 draft generator，不得直接进入媒体生产。

### M7 — Prompt Compiler Phase A/B（部分满足）

**已满足/可复用**

- `core/prompt_ir.py`、`core/model_adapter.py`、`api/server.py` 已有 deterministic 编译、LLM verbalizer、模型能力和 compiler diagnostics。
- 已有 Prompt Version、证据包、修复、导出及测试族（如 `test_storyboard_prompt_compile*.py`）。

**缺口**

- StoryboardShot 生成后没有强制 `ShotIR`、`AssetBindings`、`Executability`、`CompilerDiagnostics`、Phase A fingerprint；历史样本可出现全部缺失。
- Phase B fallback 与 Phase A 状态未形成单一 invariant，生产媒体门禁仍依赖下游审计。

**需新增/修改**

- 新增/整理 `core/prompt_ir_compiler.py`，在 materialize 后同步写入 phase_a 状态；Phase B 失败仅回退 deterministic verbalizer。
- 新增 `tests/test_prompt_compiler_phase_a.py`、`tests/test_prompt_verbalizer_fallback.py`、`tests/test_storyboard_compiler_invariant.py`。
- 迁移可先使用 `meta_info` backfill 标记 `recompile_required`，不删除旧 Prompt Version/媒体。

**风险/API 冲突**

- 不能把导演推理重新堆进 Prompt Compiler；ShotPlan/ShotIR 是输入事实，Compiler 只负责表达与校验。

### M8 — First-Pass Qualification Loop（未满足）

**已满足/可复用**

- 现有 validator、repair、DecisionPacket 草案和多类专项脚本提供局部能力：`core/validators/*`、`core/repair/*`、`core/decision_packet.py`。

**缺口**

- 无 `core/qualification_loop.py`、`core/issue_router.py`、`core/local_repair.py`；不存在统一候选→结构/事实/资产/连续性/可拍性/ShotPlan/Prompt IR→修复→再验证的最多两轮闭环。
- 当前不同 API/脚本各自修复，责任层可能漂移，无法输出统一 qualified/needs_review 状态。

**需新增/修改**

- 新增上述三个核心模块及 `tests/test_qualification_loop.py`、`tests/test_issue_router.py`、`tests/test_local_repair.py`。
- Repair 输出必须包含 issue code、target layer/id、before/after fingerprint、可回滚 patch；跨层修改拒绝。

**风险/API 冲突**

- 不能把所有 unknown 设 blocker，也不能把结构错误路由给 Prompt 文本修复；责任层必须由 issue router 固化。

### M9 — Root Cause Aggregator（未满足）

**已满足/可复用**

- 现有生产 readiness、Prompt audit、可拍性回放和发布门禁都产生结构化诊断，可作为输入。

**缺口**

- 没有 `core/root_cause_aggregator.py`、root cause taxonomy 或跨场景/镜头计数；UI/报告仍容易把大量症状直接展示为问题数量。

**需新增/修改**

- 新增聚合器及 `tests/test_root_cause_aggregator.py`；输出稳定 root_cause_id、severity、影响场景/镜头数、症状数和 recommended_action。
- 现有 release gate 和 UI 只读消费聚合结果，不删除底层诊断。

**风险/API 冲突**

- 聚合规则必须可追溯到原始诊断；不能因聚合而隐藏 blocker 或降低数量。

### M10 — QA 职责重构（部分满足）

**已满足/可复用**

- 已有 Script QA、Storyboard/Pprompt audit、Executability audit、Media preflight、Continuity review、QA Workbench。
- 已有 release gate、生产 readiness、回归脚本和审计报告。

**缺口**

- Validator（对不对）、Director QA（好不好）、Human Review（我要不要这样拍）尚未在 API、状态和 UI 中明确分层。
- 结构问题仍可能延迟到 QA/Prompt Audit，production pass 指标未由统一 qualification 结果驱动。

**需新增/修改**

- 将 Validator 结果接入 M8/M9，Director QA 仅处理创作质量建议，Human Review 处理显式确认；新增职责层测试和 UI 状态映射。
- 复用现有 QA 表/日志，避免重复建系统。

**风险/API 冲突**

- 现有 QA API 兼容性要求高；应新增字段/聚合视图，保留原始 QA 记录和回放，而非删除旧数据。

## API 冲突清单

1. `POST /api/pipeline/storyboard` 的 `generation_mode`/`force_llm` 与 production profile 冲突：必须由 policy 覆盖请求参数，不能由客户端绕过。
2. `require_shot_plan` 当前是可选兼容开关，不等于 Approved ShotPlan→Materializer；需要在 production profile 下强制物化。
3. Director Treatment、Scene Blocking、ShotPlan API 当前从 `Script.content` 读取 `scenes`；M1 后正式路径必须读取 ScriptIR，旧 Markdown 只能走明确 legacy reconstruction。
4. ShotPlan confirm 现有 payload 允许旧的简化 shot 对象；M4 后 production confirm 需 V2 schema，同时保留 draft/legacy 兼容返回。
5. Prompt draft/LLM/finalize API 已有 DecisionPacket 确认门；M7/M8 不能重复创建另一套确认或绕过现有版本回滚链路。
6. 现有 QA/readiness 接口返回症状列表；M9 应增加聚合字段并保持旧字段，避免前端一次性破坏。

## 数据模型与迁移计划（审计结论）

按顺序预计需要的 Alembic 迁移：

1. M0：统一 artifact 状态字段与 `workflow_profile`（兼容旧 `status`）。
2. M1：`script_ir_versions` 及 Script 当前版本引用。
3. M2：`fact_snapshots`/`fact_records`（或单表 JSON 规范化实现）及版本指纹。
4. M3：扩展现有 Visual* readiness/registry provenance 字段；不新建平行 SceneCanonical 表。
5. M4：ShotPlan V2 schema/version 与必要索引；保留旧 shots JSON 读取。
6. M7：如不全部落 `meta_info`，增加 Prompt Phase A 状态/指纹列；历史数据只做可追溯 backfill。
7. M8–M10：优先复用现有诊断/审计表；若需持久化 qualification/root-cause，再新增版本化报告表。

所有迁移必须可升级/降级，写入保留 previous revision、rollback anchor 和 source/evidence fingerprint；不得删除历史 Prompt Version、生成媒体或 QA 记录。

## 当前测试覆盖与缺口

**已有覆盖**：DecisionPacket 草案确认、Prompt Compiler/修复/导出、ShotPlan shadow preview/confirm、SceneBlocking/Treatment、Executability、资产 readiness、媒体 preflight、Agent Chat/附件、生产安全配置、发布门禁、数据库备份恢复等；全量 `652 passed`。

**明确缺口测试**：

- `test_production_policy.py`
- `test_script_ir.py`、`test_script_ir_renderer.py`、`test_script_ir_director_runtime.py`
- `test_fact_snapshot.py`、`test_fact_authority.py`、`test_unknown_routing.py`
- `test_asset_registry_sync.py`、`test_scene_asset_readiness_from_script_ir.py`
- `test_shot_plan_v2.py`、`test_shot_plan_asset_bindings.py`、`test_shot_plan_continuity_contract.py`
- `test_executability_preflight.py`
- `test_storyboard_materializer.py`、`test_storyboard_shot_plan_compliance.py`、`test_production_storyboard_gate.py`
- `test_prompt_compiler_phase_a.py`、`test_prompt_verbalizer_fallback.py`、`test_storyboard_compiler_invariant.py`
- `test_qualification_loop.py`、`test_issue_router.py`、`test_local_repair.py`
- `test_root_cause_aggregator.py` 及 M10 职责分层测试
- `tests/fixtures/golden_failure/990401/` 结构化 fixture（当前仅有通用 golden 场景，未有该目录）

## 风险排序

**P0（生产边界）**

1. Production storyboard 仍可由自由 LLM 生成，未保证 ShotPlan 一一物化。
2. Script 没有机器权威 ScriptIR，事实可能跨阶段漂移。
3. StoryboardShot 缺少 Phase A compiler state，媒体门禁可能过晚发现结构错误。

**P1（质量与可维护性）**

4. ShotPlan camera/duration/action/asset/continuity 合同不完整。
5. Executability 与局部修复未前移为统一门禁。
6. 没有统一状态协议和根因聚合，任务 done 与内容合格仍易混淆。

**P2（兼容与运营）**

7. Legacy Markdown/旧 payload 迁移和 stale/invalidation 传播。
8. 现有 864 warnings（含 datetime 弃用及测试返回值警告）需在不隐藏问题的前提下治理。
9. 大量历史产物污染仓库视图，应另行制定 artifact 归档/忽略策略；本审计不擅自删除。

## 实际执行顺序与阶段门

严格执行：`M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10`。

每阶段固定流程：

1. 先写/改实现与 Alembic（仅 deterministic/mock/fixture）。
2. 新增该阶段单元/集成测试。
3. 运行阶段测试 + 相关回归；失败则停留在当前阶段。
4. 更新 `CHANGELOG.md`、架构文档和本审计状态；记录真实结果。
5. 通过后才进入下一阶段。

推荐提交顺序沿用执行计划第 22 节的 13 个独立 commits；不把多个 Milestone 混成不可回滚的大提交。

## 审计结论

当前仓库具备较丰富的局部能力和较好的确定性测试基础，但尚未满足 Production Pipeline V2 的生产不变量。首个未满足 Milestone 是 **M0**；Audit 完成后应从 M0 开始，不得先改 M1/M6 或用配置开关跳级。所有后续实现必须保持 fail-closed、可回滚、可追溯，并且不调用真实外部供应商。

## M0 完成后复核（2026-09-13）

- 已新增 `core/production_policy.py`、统一状态字段及 Alembic `j3d4e5f6g7h8`；`StoryboardRequest.workflow_profile=production` 现在在证据不足时 fail-closed，`require_shot_plan=false` 不能绕过。
- M0 专项测试：`pytest -q tests/test_production_policy.py` → **6 passed**；关联 Treatment/Blocking/ShotPlan/Storyboard 回归 → **29 passed**；发布门禁纯函数回归 → **passed**。
- 未调用真实 LLM、图片、视频或对象存储。M1 仍是下一个未满足 Milestone，只有 M0 通过后才可开始。

## M1 完成后复核（2026-09-13）

- 已新增 ScriptIR v1 schema、版本表/迁移、确定性 renderer 与 build/confirm/read API；production Director Runtime 对无 qualified ScriptIR 的请求 fail-closed。
- M1 专项测试：**6 passed**；关联 Treatment/Blocking/ShotPlan 回归：**21 passed**。旧 Markdown 兼容路径显式标记 legacy reconstruction/needs_review。
- 未调用真实 LLM、图片、视频或对象存储。M2 是下一个未满足 Milestone。

## M2 完成后复核（2026-09-13）

- 已新增 FactSnapshot/FactRecord 版本化模型、authority 校验、unknown 路由及 deterministic API；冲突与未确认锁定事实 fail-closed。
- M2 专项测试：**7 passed**。未调用真实 LLM、图片、视频或对象存储。M3 是下一个未满足 Milestone。

## M3 完成后复核（2026-09-13）

- 已新增 ScriptIR→Visual* 幂等 registry sync 与确认门；复用现有分层语义字段，不创建平行 SceneCanonical 系统。
- M3 专项测试：**2 passed**。未调用真实 LLM、图片、视频或对象存储。M4 是下一个未满足 Milestone。

## M4 完成后复核（2026-09-13）

- ShotPlan V2 已物化完整生产合同并保留旧 JSON 兼容；新增 schema version 迁移。
- M4 专项及关联回归：**11 passed**。未调用真实供应商。M5 仍是下一个待完成阶段。

## M5 完成后复核（2026-09-13）

- ShotPlan confirm 已接入确定性 Executability preflight，blocked 时返回责任层为 SHOT_PLAN 的 repair plan。
- M5 专项及关联回归：**14 passed**。未调用真实供应商。M6 已实现并待提交复核。

## M6 完成后复核（2026-09-13）

- Approved ShotPlan→StoryboardShot Materializer 已实现并提供显式确认 API；重复物化按 `plan_shot_id` 幂等跳过。
- M6 专项及关联回归：**11 passed**。未调用真实供应商。M7 是下一个待完成阶段。

## M7 完成后复核（2026-09-13）

- Materializer 已在生产镜头落库时同步 Phase A Prompt IR、Executability、诊断与指纹；Phase B 有 deterministic fallback。
- M7 专项及关联回归：**5 passed**。未调用真实供应商。M8 是下一个待完成阶段。
