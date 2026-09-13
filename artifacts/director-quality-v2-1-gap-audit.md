# Director Quality V2.1 — Contract-First Creative Planner
# Repository Audit（Step 1）

> 审计日期：2026-09-13  
> 分支：`codex/unify-formal-workspace`  
> 本地 HEAD：`ca6fcf79a1f794effebf7f33fb921bb17075f835`  
> 远程 HEAD：`ca6fcf79a1f794effebf7f33fb921bb17075f835`  
> 审计范围：Director Quality V2 → V2.1 Contract-First Creative Planner 迁移前的真实仓库状态。  
> 审计约束：本阶段只读审计；未调用真实 LLM、MiMo、生图、视频或对象存储；未处理 GitHub Actions/CI；未清理或覆盖历史 artifacts。

## Executive Summary

当前 V2 已经具备一个可工作的“确定性 ShotPlan 基线 + 受控创意候选”原型，但它仍然是 **完整 Creative ShotPlan 输出 + 事后事实检查**。这与 V2.1 要求的 **Immutable Director Contract → CreativePatch[] → Deterministic Patch Compiler → Patch Validator → Partial Acceptance → Patch-level Repair** 之间存在架构断层。

当前最关键的事实：

1. `core/director_creative_planner.py` 仍将完整 Treatment、SceneBlocking、FactSnapshot、SceneCanonical 和结构化 ShotPlan 投影放进 evidence，并允许 LLM 返回 `shots` 数组。
2. `scene_name`、`unknowns`、完整 Shot 字段仍在候选解析路径中可见；事实越权是在 LLM 返回后由 `_merge_llm_creative()` / `validate_creative_candidate()` 发现，而不是在输出协议层被阻断。
3. 新增辅助镜头虽有 `source_beat_id`、类型和动机的基本检查，但没有独立 `AuxiliaryShotProposal` 协议，也没有验证 source beat 必须存在于当前 Treatment，更没有 patch 级部分接受。
4. 真实 MiMo V2 Pilot 的 6 次调用结果为 4/6 通过；事实字段越权 1 次、辅助镜头契约错误 1 次，正好验证了上述缺口。证据见 `artifacts/director-quality-v2-mimo-pilot-20260913T012652Z.json`。
5. 离线 V2 scorer 已计算 10 维分数，但真实 Pilot 仅保存场景 overall/baseline/planner 结果和调用 telemetry，没有按每个候选保存 Baseline、Before Repair、After Repair 的十维明细。
6. 现有 `core/local_repair.py` 和 `RepairAttempt` Ledger 可以复用，但当前 Director Repair 仍以完整 candidate 为上下文，尚未做到只重试失败 patch，也没有失败 patch 的独立 discard/partial-accept 结果。

结论：V2.1 应从 Contract 和 Patch 协议开始，不应继续在现有完整 ShotPlan JSON 上增加更多事后字段检查。现阶段不得切换 Production default，也不满足 Production Shadow Candidate 门槛。

## Baseline Audit（按 V2.1 §3 要求）

### 1. 当前 Planner 输入是什么？

当前公开入口是 `build_creative_shot_plan_candidate()`（`core/director_creative_planner.py`）。输入参数包括：

- `structural_shot_plan`：由 `core/shot_plan.py::build_shot_plan()` 生成的确定性 ShotPlan；
- `treatment`：包括 `scene_name`、`scene_id`、`character_intents`、`beat_map`、状态和 prompt fingerprint；
- `blocking`：包括 `participants`、`unknowns`、`source_spatial_facts`、状态和 evidence fingerprint；
- 可选 `fact_snapshot`；
- 可选 `scene_canonical`；
- 可选已返回的 `llm_output`；或注入的 `llm_callable`；
- 外部调用门槛 `confirmed` + `allow_external_call`；
- `mode`（当前主要是 `shadow`）。

Planner 内部重新构造的 evidence 包包含：

```text
protocol_version
treatment（完整副本）
blocking（完整副本）
fact_snapshot（完整副本）
scene_canonical（完整副本）
structural_plan（immutable projection）
```

证据包指纹为 `creative_evidence_fingerprint`。`api/shot_plan_api.py` 的 `creative-llm-draft` 路由还会将候选的完整 `shots` 再放入 user prompt，并要求 `required_keys={"shots"}`。

### 2. 当前 Planner 输出是否仍为完整 ShotPlan？

是。当前 `_normalise_llm_output()` 接受：

- `{ "candidate": {...} }`；
- `list[shot]`（包装成 `{ "shots": [...] }`）；
- 任意 JSON object。

`_merge_llm_creative()` 逐个合并完整 shot object，最后输出带有：

- `scene_name`；
- `shots`；
- `unknowns`；
- `schema_version`；
- `status`；
- `director_mode`；
- `model_info`；
- `creative_validation`；
- `structural_plan_fingerprint`；

的完整候选。它不是 V2.1 要求的 `CreativePatch[] + AuxiliaryShotProposal[]`，也没有 patch provenance、patch-level status 或 partial acceptance 计数。

### 3. 哪些 immutable 字段目前仍暴露给 LLM？

当前暴露面明显大于 V2.1 所需的最小事实摘要：

1. 完整 Treatment：场景名、Scene ID、character intents、全部 beat map、beat event、information/emotion change 等。
2. 完整 SceneBlocking：participants、source spatial facts、unknowns、空间证据和状态。
3. 完整 `FactSnapshot` 和 `SceneCanonical`（若调用者提供）。
4. `structural_plan` 的 immutable projection：`scene_name`、每个 shot 的 `plan_shot_id`、`scene_id`、`beat_id`、`event`、`participants`、`action_beats`、`entry_state`、`exit_state`、`asset_bindings`、`continuity_contract`、`continuity`、`spatial_source`、`duration_hint_seconds`，以及 `unknowns`。
5. API 的 LLM user prompt 还包含完整的 `shots` candidate，而不是只给每个 shot 的允许 patch 目标。

`IMMUTABLE_SHOT_FIELDS` 已经列出一部分保护字段，这是可复用的事实清单；但目前只是“传入完整对象后比较差异”，不是输出 schema 层的不可写结构。

仍未纳入同等强度保护或独立协议的字段包括：

- `scene_name` / `unknowns` 仍是允许解析的 top-level 字段；
- 新辅助镜头的 `participants`、`asset_bindings`、`event`、`action_beats`、`entry_state`、`exit_state`、`continuity_contract` 没有被独立 proposal policy 完整约束；
- 没有显式 source beat map / allowed patch path map。

### 4. Fact Override 是在哪个阶段被发现？

当前时序为：

```text
LLM call_llm_json
  → _normalise_llm_output
  → _merge_llm_creative
  → validate_creative_candidate
  → API catch DirectorFactOverride
```

具体表现：

- `_merge_llm_creative()` 允许先读取完整候选，再检查 top-level 和 shot-level 字段；
- 若输出包含改变后的 `scene_name`、`unknowns`、immutable shot field 或未列入 creative field 的字段，才抛出 `DirectorFactOverride`；
- `creative-llm-draft` 路由在真实模型调用完成后才捕获该异常并返回 HTTP 409。

因此 Fact Override 当前是 **post-response detection**，不是 schema/contract-level prevention。真实 V2 Pilot 中 `红伞幻影（二）` 的输出含 `scene_name`、`unknowns`，被记录为：

```text
S01 contains forbidden fields: scene_name, unknowns
```

这正是 V2.1 要改为 `forbidden_field_attempt` 并只拒绝违规 patch、保留合法 patch 的场景。

### 5. 当前辅助镜头失败的具体原因是什么？

当前新增镜头是在 `_merge_llm_creative()` 中通过“某个 `plan_shot_id` 不在 baseline”来推断 auxiliary shot。它要求：

- `source_beat_id` 或 `beat_id` 非空；
- `auxiliary_type` 属于 `reaction | insert | establishing | transition`；
- `why_this_shot` 非空；
- 同一 source beat 最多 2 个（在后续 candidate validation 中统计）。

缺口和真实失败分别是：

1. 没有独立 `AuxiliaryShotProposal` schema；辅助镜头仍混在 `shots` 数组里。
2. 没有验证 source beat ID 是否真的存在于当前 Treatment 的 beat map；当前只统计字符串，不做 source map 解析。
3. 没有强制 `insert_after_plan_shot_id`，所以插入位置只能依赖返回数组顺序，无法形成稳定的插入契约。
4. 新辅助镜头仍可携带部分完整事实字段，缺少“不新增人物/剧情结果/关键道具事实”的独立验证。
5. 真实 Pilot 中 `暗房门口的试探` 返回了一个无来源绑定的辅助镜头（错误为 `auxiliary shot 06 requires source_beat_id and a bounded auxiliary_type`），整个场景候选被判为 `DirectorCreativeError`；不存在 patch-level discard 或其余合法 patch 保留。

### 6. 当前 Planner prompt 中哪些内容稳定，哪些内容随场景变化？

#### 稳定内容

- `PROTOCOL_VERSION`；
- 系统提示中“只能修改 camera、composition、performance_direction、edit、information_strategy、why_this_shot”等规则；
- 保留事实、beat 顺序、资产绑定、首尾状态、连续性合同、无生产副作用等原则；
- JSON 输出和 `required_keys={"shots"}` 的调用约束；
- `core.llm` 的消息格式、请求指纹和 token/latency 审计外壳。

#### 随场景变化内容

- 完整 Treatment、SceneBlocking、FactSnapshot、SceneCanonical；
- beat 数量、事件、信息变化、情绪变化、参与者和空间事实；
- Structural ShotPlan 的镜头数量、镜头 ID、动作、首尾状态、资产绑定；
- `book_id`、episode、scene_name 等审计上下文；
- 真实模型输出长度和结构。

当前没有独立的 `Scene Directing Strategy` 层，因此每个场景都直接从事实数据请求完整 ShotPlan 创意重写；稳定前缀也没有拆成 V2.1 所需的 Contract、Output Schema、Allowed Paths、Auxiliary Policy、Quality Rules 五个明确区段。

### 7. 当前 quality scoring 是否记录真实 10 维分数？

部分满足，不能满足 V2.1 要求。

- `core/director_quality_validator.py::score_director_quality()` 确实计算并返回十维：
  `DRAMATIC_CLARITY`、`SHOT_MOTIVATION`、`EMOTIONAL_PROGRESSION`、`VISUAL_STORYTELLING`、`SPATIAL_CLARITY`、`PERFORMANCE_DIRECTION`、`EDIT_RHYTHM`、`INFORMATION_STRATEGY`、`POWER_DYNAMICS`、`SHOT_DIVERSITY`。
- 离线 `scripts/run_director_quality_v2_benchmark.py` 保存了每个场景的 baseline/planner quality 和聚合 `dimension_averages`。
- 真实 MiMo artifact 只保存每个场景的 `baseline_score`、`planner_score`（通过样本）、`delta`、状态和 telemetry；Pilot 顶层也只有 `baseline_average_director_quality_score` 和 `planner_average_director_quality_score`。
- 真实 Pilot 没有保存每个候选的 `dimensions`，也没有 `Before Repair` / `After Repair` 两组十维分数；当前没有真实 patch repair 轨迹。

因此 V2.1 必须新增逐候选结构：`baseline_quality`、`first_candidate_quality`、`after_repair_quality`，并分别记录十维、overall、issues 和 contract status。

### 8. 当前 repair 是否能只重试单个 patch？

不能。

现有 `core/director_local_repair.py::qualify_director_candidate()` 接收完整 candidate，通过 `validate_director_quality()` 生成所有 issue，再将确定性 repair patch 应用到 candidate。它虽然 patch path 可能指向单个 `/shots/{index}/...`，但：

- 没有 `CreativePatch` 独立对象；
- 没有按 `plan_shot_id` 隔离失败 patch 的请求/状态；
- 没有给 LLM 的 patch-level repair request；
- `core/qualification_loop.py` 每轮重新验证整个 candidate；
- 失败后只能返回整个 candidate 的 `needs_review`，没有“丢弃失败 patch、保留其他 patch”的显式结果。

所以它是“对完整候选执行局部 JSON patch”，而不是 V2.1 要求的“只重试失败 patch”。

### 9. 当前是否已有 JSON Patch / patch apply 工具可复用？

有基础实现，可以复用但必须加 Contract 层约束：

- `core/local_repair.py::apply_local_repair()`：支持 `add`、`replace`、`remove`，生成 before/after fingerprint 和完整 rollback candidate；
- `core/local_repair.py::rollback_local_repair()`：支持带 fingerprint guard 的回滚；
- `core/director_local_repair.py::_assert_creative_patch()`：当前可拦截 Director Repair 对 structural field 的修改；
- `core/qualification_loop.py::qualify_candidate()`：提供 bounded attempts、issue routing 和 recorder hook；
- `core/repair_ledger.py::record_repair_attempt()`：已能写入 `RepairAttempt`；
- `core/repair/` 目录有更广泛的旧 repair 工具，但不应把旧的泛化策略直接接入 Director Contract。

当前 `apply_local_repair()` 是内部 JSON-like patch，不是完整 RFC JSON Patch 实现；它对路径存在性、数组索引和 immutable path 没有通用 contract 校验。因此 V2.1 应在其上游新增 deterministic Patch Compiler/Validator，而不是让 LLM 直接调用该函数。

### 10. 是否需要数据库 migration？

当前判断：**第一轮不需要 migration**。

理由：

- `ShotPlan.shots` 可保存结构化 candidate 或 patch-compiled shots；
- `ShotPlan.model_info` 可保存 contract fingerprint、strategy fingerprint、patch provenance、contract metrics 和 fallback 信息；
- `ShotPlan.evidence_fingerprint`、`schema_version`、`quality_status`、`production_status` 已存在；
- `RepairAttempt` 已有 `issue_code`、`target_layer`、`target_id`、`scene_id`、`shot_id`、before/after fingerprint、attempt、revalidation、model、prompt fingerprint；
- V2.1 仍是 shadow/benchmark，不需要将十维评分做成可查询列。

后续只有在需要按维度检索大量历史评分、独立保存 Scene Strategy 版本或高频查询 patch 状态时，才评估新增表。不得为了本轮协议改造扩大 migration 范围。

### 11. 哪些现有模块可以直接复用？

可直接复用：

| 模块 | 可复用内容 | V2.1 需要的适配 |
|---|---|---|
| `core/shot_plan.py` | deterministic structural baseline、稳定 `plan_shot_id`、beat/action/entry/exit/asset/continuity 字段 | 不改默认行为，仅作为 Patch Compiler 输入和 fallback |
| `core/scene_blocking.py` | `SOURCE_FACT`、`CREATIVE_CHOICE`、`DERIVED_CONSTRAINT`、spatial evidence、conflict/unknowns | Contract 读取其 source facts，不重新规划 Blocking |
| `core/director_creative_planner.py` | fingerprint、creative field 列表、外部调用门槛、事实 fail-closed、fallback 语义 | 拆出 Contract、Patch parse/merge，停止接受完整 ShotPlan 作为新协议 |
| `core/director_quality_validator.py` | 十维维度、权重、质量诊断 | 扩展 patch/candidate 分层记录，保持质量与 contract 分离 |
| `core/director_benchmark.py` | baseline/planner 对比和 structural/creative 分离 | 增加 first/final/contract 指标，不改旧字段语义 |
| `core/local_repair.py` | JSON-like apply、fingerprint、rollback | 作为 patch compiler/repair 的底层执行器，增加路径及 target guard |
| `core/qualification_loop.py` | bounded attempts、issue routing、repair recorder | 改为 patch-level qualification/partial acceptance |
| `core/repair_ledger.py` + `models/repair.py` | RepairAttempt 持久化结构 | target_layer=`DIRECTOR_CREATIVE`，补充 patch/proposal target context |
| `core/issue_router.py` | Director creative layer 路由 | 增加 V2.1 issue codes，保持事实/结构责任边界 |
| `core/pilot_instrumentation.py` + `core/llm.py` | request/system/user fingerprint、tokens、latency、cache usage | 为 strategy/patch/repair stage 增加 stage tags，仍不记录密钥/正文 |
| `api/shot_plan_api.py` | shadow preview、显式真实 LLM gate、draft-only persistence | 改为 strategy/patch draft API，生产默认不接线 |
| `core/storyboard_materializer.py` / `api/storyboard_materializer_api.py` | deterministic materialization 与生产 fail-closed | 保持不改，V2.1 只输出 validated creative candidate |

### 12. 本轮建议修改文件列表

按最小直接相关范围建议：

1. 新增 `core/director_creative_contract.py`：Immutable/Editable fields、allowed paths、source beat map、auxiliary policy、contract fingerprint。
2. 新增 `core/director_patch_schema.py`（或等价模块）：`CreativePatch`、`AuxiliaryShotProposal` 的纯结构化解析/归一化。
3. 新增 `core/director_patch_compiler.py`：仅将合法 patch 应用到 structural baseline，并记录 provenance。
4. 新增 `core/director_patch_validator.py`：Contract blocker 与 Director quality warning 分离。
5. 新增 `core/scene_directing_strategy.py`：场景级策略 schema、确定性验证和只读候选输出。
6. 修改 `core/director_creative_planner.py`：保留兼容入口，但新增 Contract-First 路径；禁止新路径接受/生成完整 Scene/Treatment/Blocking/ShotPlan。
7. 修改 `core/director_local_repair.py`：新增 patch/proposal 级 bounded repair，不破坏旧 V2 API。
8. 修改 `core/director_benchmark.py`：记录 contract reliability 和 Baseline/First/Final 三组质量明细。
9. 修改 `core/repair_ledger.py`（必要时仅扩展 metadata 序列化，不改表）：确保每次 patch repair 都实时进入 Ledger。
10. 修改 `api/shot_plan_api.py`：增加 shadow-only Contract-First preview/draft/repair endpoint；保持 `production` 默认不调用 Planner。
11. 新增或修改 `tests/test_director_quality_v2_1_*.py`：覆盖 §28 unit 和 §29 integration。
12. 新增 `scripts/run_director_quality_v2_1_benchmark.py`、`scripts/run_director_quality_v2_1_mimo_pilot.py`。
13. 新增 `artifacts/director-quality-v2-1-metrics.json`、`artifacts/director-quality-v2-1-report.md`，不得覆盖 V2 artifact。

本轮明确不修改：Production Pipeline V2 主链、SceneBlocking V2 规则、Materializer、Prompt Compiler 主链、数据库 schema、GitHub Actions/CI、媒体供应商调用。

### 13. 测试计划

#### Unit（先于任何真实调用）

- Contract immutable field projection/fingerprint；
- allowed path 通过；
- forbidden path → `DIRECTOR_PATCH_PATH_FORBIDDEN`；
- immutable fact → `DIRECTOR_FACT_OVERRIDE`；
- unknown `plan_shot_id` → `UNKNOWN_PLAN_SHOT_ID`；
- invalid patch value/type → `INVALID_PATCH_VALUE`；
- invalid character reference → `INVALID_CHARACTER_REFERENCE`；
- 合法 CreativePatch deterministic apply；
- 非法 patch 的 partial reject，合法 patch 保留；
- Auxiliary proposal 合法 source beat；
- 缺失/不存在 source beat；
- 每 beat auxiliary budget；非法 auxiliary type；shot-count expansion；
- Scene Strategy schema、emotional curve、camera repetition、redundant/unmotivated shot、power shift、information reveal；
- patch-level local repair 仅重试失败目标，最多 2 次；
- fallback mode 标记；
- RepairAttempt Ledger 实时记录、revalidation 和 fingerprint。

#### Integration

```text
Qualified/approved upstream evidence
 → Structural ShotPlan
 → Immutable Director Contract
 → Scene Directing Strategy
 → CreativePatch/AuxiliaryProposal
 → Patch Compiler
 → Contract Validator
 → Director Quality Validator
 → Patch-level Repair / Partial Acceptance
 → Executability
 → Materializer（只做离线/模拟验证）
```

必须证明：Planner 或某个 patch 失败不会改变原 Structural ShotPlan，不会创建 StoryboardShot，不会触发媒体/对象存储；同时反向 mock `StoryboardAgent.run()` 为异常，production API 正常路径调用次数仍为 0。

#### Regression

- 现有 Production Pipeline V2 后端测试；
- SceneBlocking V2 测试；
- Director Quality V2 测试；
- Golden Regression；
- 前端只有在 API/type 受影响时才运行对应 Vitest/build；
- 不修改旧测试预期来掩盖回归。

### 14. Real MiMo Pilot 计划

真实调用必须在 V2.1 Unit、Integration、Regression 全部通过后执行，且只生成 benchmark artifacts：

1. 至少 12 个场景，不重新写小说；优先使用《潮汐回声》现有批准场景与既有 Golden fixtures。
2. 覆盖双人对话、悬疑、信息揭示、情绪转折、权力变化、人物入场、关键道具、无对白、多人物、快动作、慢情绪、强反应镜头。
3. 每场景固定同一 Qualified ScriptIR、FactSnapshot、Approved Treatment、Approved SceneBlocking 和 Structural ShotPlan。
4. 每场景保存三组：Deterministic Baseline、Planner First Candidate、Planner Final After Local Repair。
5. 真实模型只输出/尝试输出 Strategy、CreativePatch、AuxiliaryProposal；禁止写 approved ShotPlan、StoryboardShot、图片、视频和对象存储。
6. 每次调用记录 model、stage、scene/episode、request/system/user prompt fingerprint、prompt/cached/completion/total tokens、latency、retry、parse、contract、repair、accepted/rejected patch 数量；绝不记录 API key 或正文。
7. 失败 patch 只进入本 patch 的 Local Repair，最多 2 次；仍失败则 discard，其他合法 patch 保留并标记 `partial_acceptance`。
8. 真实 Pilot 报告必须如实记录 Contract Parse/Pass、Fact Override Attempt/Accepted、Auxiliary Binding、First/Final Patch Success、Repair Yield、Fallback、十维质量和 cache observation。

## V2 → V2.1 差距矩阵

| V2.1 要求 | 当前状态 | 结论 |
|---|---|---|
| Immutable Director Contract | 仅有 planner 内部 immutable field set/fingerprint | 缺正式 Contract 模块 |
| LLM 仅输出 CreativePatch[] | 当前输出完整 candidate/shots | 未满足 |
| AuxiliaryShotProposal 独立协议 | 混在 shots，基本字段检查 | 未满足 |
| Scene Directing Strategy | 无独立层，单次直接规划 shots | 未满足 |
| Deterministic Patch Compiler | 只有通用 local repair apply | 未满足 |
| Patch Validator blocker/warning 分层 | merge/quality 两套检查但无 patch schema validator | 未满足 |
| Partial Acceptance | 非法创意 proposal 多数回退/整场失败 | 未满足 |
| Patch-level Local Repair | 完整 candidate 上的局部 JSON patch | 未满足 |
| 10 维 Before/After/Repair 真实记录 | 离线有维度；真实 Pilot 只有 overall | 未满足 |
| Runtime Repair Ledger | 已有通用 Ledger/RepairAttempt | 可复用，需接 patch/proposal 生命周期 |
| Production default 不切换 | 当前为 shadow/benchmark | 已满足，必须保持 |
| 无媒体/对象存储副作用 | V2 Pilot 为 0 | 已满足，V2.1 继续保持 |

## 当前已知指标基线（不可冒充 V2.1 成果）

来源：`artifacts/director-quality-v2-mimo-pilot-20260913T012652Z.json`、`artifacts/director-quality-v2-metrics.json`。

- V2 Real MiMo calls：6；成功候选：4/6（66.7%）；
- Fact Override：1；创意契约失败：1；
- MiMo prompt tokens：30,702；cached tokens：0；completion：18,633；total：49,335；
- 平均延迟：49,457.54ms；数据库/生图/视频/对象存储副作用：0；
- 真实通过样本 planner 平均质量：62.41；baseline：36.78；delta：+25.63；
- 离线 V2 Golden：8 场景；planner surrogate 平均 86.13，baseline 41.91，delta +44.22；
- 离线十维平均中最弱的是 `SHOT_DIVERSITY=2.92`、`EDIT_RHYTHM=6.04`、`EMOTIONAL_PROGRESSION=7.36`；该分数不能替代真实 V2.1 候选分数。

上述数据只作为 V2 baseline，不代表 V2.1 已达到：Contract Pass ≥95%、Patch Final Success ≥95%、Scene Planner Success ≥90%、Director Quality ≥70 等门槛。

## 审计结论与下一步放行条件

### 当前最大瓶颈

1. 输出协议仍以完整 ShotPlan 为中心，事实字段暴露和事后拦截导致模型稳定性不足；
2. 辅助镜头没有独立来源绑定协议；
3. 没有 patch-level partial acceptance/retry，因此单个失败可能拖累整场；
4. 质量分数与 Contract Reliability 尚未按候选生命周期分开记录；
5. Prompt 还没有稳定前缀/策略/场景数据的清晰层级，当前 cache 基线为 0%。

### 允许进入 Step 2 的条件

- 本 Audit 文件写入完成；
- 已确认远程 HEAD 与本地基线一致；
- 保持现有 V2/Production 代码和历史 artifacts；
- Step 2 仅新增 `core/director_creative_contract.py` 和对应纯单元测试，先不接真实 LLM，不切 Production default。

### 明确不做

- 不修改评分阈值以提高通过率；
- 不对特定 `book_id`、scene name、shot id 写特例；
- 不删除 deterministic fallback；
- 不把 V2.1 planner 接入 Production default；
- 不调用真实 MiMo、生图、视频或对象存储，直到所有本地测试/回归完成。

---

## Final As-Built Verification（2026-09-13）

本节与上文 **Baseline Audit** 分开，记录本轮实际落地结果；不覆盖或改写基线结论。

### 已落地

- `core/director_creative_contract.py`：immutable/editable 字段、allowed patch paths、source beat map、contract fingerprint。
- `core/director_patch_schema.py`：严格 `director_creative_patch_v1`，拒绝完整 `shots`，并校验归一化 fingerprint。
- `core/director_patch_compiler.py`：按 `plan_shot_id` 的确定性路径编译、嵌套容器补齐、before/after fingerprint 和 provenance。
- `core/director_auxiliary.py`：独立 AuxiliaryShotProposal 来源 beat、插入锚点、参与者、类型和预算校验。
- `core/scene_directing_strategy.py`：Scene Directing Strategy schema、beat/character 引用校验与确定性构造。
- `core/director_creative_planner.py`：新增只输出 CreativePatch 的 V2.1 shadow 入口；旧 V2 完整候选入口保留兼容，未接 Production default。
- `core/director_patch_validator.py`：Contract blocker 与 Director Quality warning 分离，支持 shot-count、路径、事实和辅助提案校验。
- `core/director_partial_acceptance.py`：合法 patch 保留、非法 patch 单独拒绝并记录 fallback 计数。
- `core/director_patch_repair.py`：失败 patch 最小上下文、最多 2 次、失败回退 baseline，并可实时写入 RepairAttempt Ledger。
- `core/director_quality_metrics.py`：Baseline / Before Repair / After Repair 三组十维质量与 Contract Reliability 指标。
- `api/shot_plan_api.py`：新增 shadow-only `creative-patch-preview` 与显式确认的 `creative-patch-llm-draft`，不创建版本、不触发媒体。
- `core/director_prompt.py`：抽离稳定的 Role/Contract/Output Schema/Allowed Paths/Forbidden Paths/Auxiliary Policy/Quality Rules 前缀；场景证据与策略进入动态上下文；输出 system/user/prefix/request fingerprint，且不携带密钥或 provider-specific cache 参数。

### 验证证据

- V2.1 核心单元/集成测试：`41 passed`。
- Production Storyboard Gate / Materializer / SceneBlocking 回归：`15 passed`。
- 全仓库后端回归：`764 passed`（仅已有 Deprecation/PytestReturnNotNone warnings）。
- 离线 V2.1 Golden：`12` 场景，生成 `artifacts/director-quality-v2-1-metrics.json` 与 `artifacts/director-quality-v2-1-report.md`；provider/media/object-storage calls 均为 `0`。
- 未调用真实 LLM、MiMo、生图、视频或对象存储；未处理 GitHub Actions/CI；未删除历史 artifacts。
- Prompt builder 回归：`tests/test_director_prompt.py` 与 `tests/test_director_runtime_e2e.py` 覆盖稳定前缀、规范化动态证据、非敏感模型快照及 hash/telemetry 接线；相关测试全部通过。
- Patch planner 现在把严格 schema 拒绝记录为 `schema_pass=false`、`schema_error_code` 与 `forbidden_field_attempt`，不会把非法完整 ShotPlan 响应伪装成创意成功。
- 新增 `parse_creative_patch_partial()`：在非致命协议错误下逐项保留合法 patch/辅助提案，非法项带路径与错误码进入诊断；版本或 fingerprint 错误仍 fail-closed。

### 尚未满足的放行条件

- 真实 MiMo 12-scene benchmark-only pilot 尚未执行（当前约束明确禁止），因此不能宣称真实 Contract Stability、Director Quality 或 Production Shadow Candidate。
- 真实 telemetry、cache 命中、latency、Blind Judge 结果仍待后续在本地回归通过且获得明确授权后单独执行。

### Final As-Built Verification Update（2026-09-13）

- 稳定 Prompt 前缀及 schema-failure telemetry 已完成；Contract-First LLM 草案路径记录 `system_prompt_hash`、`user_prompt_hash`、`prompt_prefix_fingerprint`、`schema_pass` 和 `forbidden_field_attempt`。
- 定向 V2.1/Prompt/Runtime 测试：`7 passed`；全仓库后端回归：`767 passed`（仅已有 Deprecation/PytestReturnNotNone warnings）。
- 本更新仍未调用真实 LLM/MiMo、生图、视频或对象存储，也未改变 Production Pipeline V2 默认路径。

### Final As-Built Verification Update 2（2026-09-13）

- `api/shot_plan_api.py` 现在在 V2.1 preview 与 confirmed LLM draft 响应中统一返回：
  `partial_acceptance`、`contract_reliability`、`rejected_patches`；schema 层被逐项丢弃的非法 patch 不再只藏在 `model_info`，而是进入可审计的拒绝计数与错误列表。
- `contract_reliability` 明确区分 `schema_pass`、`patch_path_pass`、`fact_override_attempt_count`、`forbidden_field_attempt_count`、`schema_rejection_count`、`auxiliary_binding_pass` 与 `parse_success`，不会把创意质量分数当作契约通过。
- `core/director_quality_metrics.py` 会把 `schema_rejections` 规范化并提升到最终 Contract Reliability metrics，同时保留十维 Baseline / Before Repair / After Repair 结构。
- `core/director_local_repair.py::qualify_director_candidate()` 在收到运行时 `session` 或 `repair_context` 时自动接线 `RepairAttempt` Ledger；纯函数调用仍无数据库副作用。记录包含 `DIRECTOR_CREATIVE` 层、目标、attempt、before/after repair 信息，并沿用 model/prompt fingerprint 上下文。
- 新增 API partial-acceptance 与 runtime-ledger 回归覆盖；V2.1 定向集合 `17 passed`，模型注册表测试 `26 passed`，全仓库后端回归 `773 passed`（仅既有 warnings），前端相关测试 `10 passed`，前端 build 成功。
- 新增 `repair_failed_auxiliary_proposal()`：只接收单个 proposal 的最小上下文，固定 `proposal_id` 与 `source_beat_id`，最多两次尝试；成功或失败均可实时写入 `DIRECTOR_CREATIVE` RepairAttempt Ledger，失败时回退而不影响其他 patch。
- 辅助提案 Local Repair 定向测试新增后为 `9 passed`（与 patch repair 合计）；该修复入口仍为 shadow/local-only，不会物化 StoryboardShot。
- 本次 V2.1 完整定向集合（Contract / Schema / Compiler / Validator / Partial Acceptance / Repair / Metrics / Integration / Runtime）为 `31 passed`；Python 语法检查通过。
- 本更新仍未调用真实 LLM/MiMo、生图、视频或对象存储，也未改变 Production Pipeline V2 默认路径；真实 MiMo 12-scene Pilot 仍因当前约束未执行。

### Final As-Built Verification Update 3（2026-09-13）

- 在包含 Contract-First、partial acceptance、patch/proposal repair、Runtime Repair Ledger 及模型目录校验改动的当前工作区，全仓库后端回归为 `775 passed`；仅已有 Deprecation/PytestReturnNotNone warnings。
- 模型注册表定向回归为 `26 passed`；前端全量 Vitest 为 `291 passed`（49 files），TypeScript/Vite production build 成功；`git diff --check` 无空白错误。
- 本更新仍未调用真实 LLM/MiMo、生图、视频或对象存储，未处理 GitHub Actions/CI，未切换 Production Pipeline V2 默认路径。真实 MiMo 12-scene Pilot、独立 Blind Judge 和线上 token/latency/cache 证据仍未完成，不能宣称 Production Shadow Candidate。

### Final As-Built Verification Update 4（2026-09-13）

- Contract-First ShotPlan API 已补齐证据投影：批准的 ScriptIR 场景、confirmed FactSnapshot、VisualLocation canonical/state/look/board 信息及场景声明的资产绑定会进入 `immutable_projection`，并参与 `contract_fingerprint`；没有这些记录时仍不伪造事实。
- 运行时证据链回归（Contract、V2.1 integration、Director Runtime API）：`6 passed`；Python compileall 与 `git diff --check` 通过。
- 该改动只强化 shadow/benchmark 证据边界，不改变 Production Pipeline V2 默认路径、不物化 StoryboardShot，也不触发任何外部供应商调用。

### Final As-Built Verification Update 5（2026-09-13）

- 证据链改动后的全仓库后端回归最终为 `775 passed`（887 个既有 warnings）；未出现失败或新增外部调用。

### Final As-Built Verification Update 6（2026-09-13）

- 按当前工作区重新执行完整本地回归：后端 `775 passed`；前端 Vitest `291 passed`（49 files）；前端 production build 成功；离线 V2.1 Golden `12/12` 场景通过；`git diff --check` 通过。
- Production release gate 的确定性回归、Golden Regression、运行时配置校验和 gate invariant 均通过；门禁仍真实阻断在开发环境安全配置、active 样本仅 `3/30`、缺少 `needs_information`/`conflict` 覆盖，以及真实浏览器样本不足 `1/3`，未通过降低阈值绕过。
- V2.1 benchmark 仍保持 `offline_only=true`、MiMo/provider/media/object-storage calls 均为 `0`；真实 MiMo 12-scene Pilot 与 Blind Judge 未执行，因此仍不能宣称 Production Shadow Candidate。

### Final As-Built Verification Update 7（2026-09-13）

- 修正离线 Golden 样本选择：保留最多 6 个已批准场景，并始终保留完整 12 类导演挑战 fixture；重新生成后证据包共 18 个场景，12 类挑战全部覆盖。
- 新增 `scripts/run_director_quality_v2_1_mimo_pilot.py`，该命令明确为 preflight-only，不导入供应商客户端、不联网、不写生产数据；本次 preflight 状态为 `ready_for_authorized_real_pilot`，并记录 `real_mimo_calls=0`。
- preflight 已验证三组候选、十维评分、Contract Reliability 字段、12 类场景覆盖和零外部副作用；真实 Pilot 仍需单独授权后执行，不能用该 preflight 结果替代真实指标。

### Final As-Built Verification Update 8（2026-09-13）

- Golden 样本选择修复后的完整后端回归为 `777 passed`（新增 preflight 测试 2 条）；Golden Regression `5/5`、Production gate invariant、前端 Vitest `291 passed` 和 production build 均通过。
- 最新 preflight artifact：`director-quality-v2-1-mimo-pilot-preflight-20260913T054620Z.json`，状态 `ready_for_authorized_real_pilot`，外部调用计数仍全部为 `0`。

### Final As-Built Verification Update 9（2026-09-13）

- 重新运行离线 V2.1 Golden benchmark：`scene_count=18`，Contract Parse/Pass、Patch First/Final Success、Scene Planner Success 均为 `100%`；12 类导演挑战全部覆盖。
- 重新运行 Pilot preflight：状态 `ready_for_authorized_real_pilot`；`real_mimo_calls=0`、provider/media/object-storage calls 均为 `0`。
- 本次仅刷新离线证据，不调用真实 LLM/MiMo，不写生产数据，不改变 Production Pipeline V2 默认路径。

### Final As-Built Verification Update 10（2026-09-13）

- Golden artifact 现在保存每个场景的冻结、脱敏 `evidence`（Treatment、SceneBlocking、Director Contract、Scene Strategy），供未来 benchmark-only Pilot 重放；不包含密钥，不写生产记录。
- Pilot preflight 新增 evidence 完整性与 contract/strategy fingerprint 一致性校验；缺失或不一致时 fail-closed。
- 定向 preflight 测试：`3 passed`；离线 benchmark 仍为 18 场景、12 类挑战覆盖，真实外部调用保持 `0`。

### Final As-Built Verification Update 11（2026-09-13）

- 新增受控运行器 `scripts/run_director_quality_v2_1_mimo_pilot_authorized.py`：默认仅执行 preflight；真实路径必须同时满足显式执行开关、精确确认令牌和 MiMo profile 校验。
- 运行器只读取冻结 Golden evidence、逐场景记录非敏感 telemetry 并写 benchmark artifact；不会写 ShotPlan/Storyboard、触发媒体或对象存储。
- 运行器授权边界测试与 preflight 合计 `7 passed`；本轮未执行真实供应商调用。

### Final As-Built Verification Update 12（2026-09-13）

- 真实 Pilot 运行器进一步要求 `openai-compatible` provider、非空 `base_url`、启用的 LLM profile 和 MiMo 模型名，避免误把其它供应商配置当作 Pilot 目标。
- 运行器默认路径仍为离线 preflight；授权边界测试 `4 passed`，未触发任何外部请求。

### Final As-Built Verification Update 13（2026-09-13）

- 使用 mock LLM 对授权运行器执行 12 场景离线回放：逐场景调用路径、冻结 evidence 重放和零生产副作用均通过。
- 回放结果明确标记为离线验证，不计入真实 MiMo Contract/Quality 指标；新增运行器测试后总计 `5 passed`。

### Final As-Built Verification Update 14（2026-09-13）

- 对 V2.1 Golden、metrics、report 及 Pilot 运行器执行凭据扫描，未发现 API Key、Bearer token 或 provider credential。
- 该安全扫描为只读检查；结果为 `credential_scan=clean`，未改变任何生产数据。

### Final As-Built Verification Update 15（2026-09-13）

- 受控 Pilot 运行器现在为每个场景生成匿名化 Version A/B blind-review packet，隐藏 baseline/planner 角色且不预填偏好。
- 盲审包只作为评审输入，不调用 Judge、不改变质量分数；运行器测试仍全部通过。

### Final As-Built Verification Update 16（2026-09-13）

- 修复盲审信息泄漏：`prepare_blind_review()` 及受控 Pilot 生成的 Version A/B payload 不再携带预计算的 `director_quality` 分数，评审者只能看到匿名候选内容、镜头数量和镜头数据。
- 定向盲审与 Pilot runner 回归：`15 passed`；`python -m compileall -q core scripts api` 通过；`git diff --check` 无空白错误。
- 本次只强化 blind-review 完整性，未调用真实 LLM/MiMo、生图、视频或对象存储，也未改变 Production Pipeline V2 默认路径。

### Final As-Built Verification Update 17（2026-09-13）

- 当前工作区完整后端回归：`783 passed`（仅既有 Deprecation/PytestReturnNotNone warnings）。
- 离线 V2.1 Golden benchmark：`18` 场景、12 类导演挑战全覆盖，Contract Parse/Pass、Patch First/Final Success、Scene Planner Success 均为 `100%`；Director Quality 平均 `43.99`，未因评分不足而调整阈值。
- Pilot preflight：`ready_for_authorized_real_pilot`；真实 MiMo/provider/media/object-storage calls 均为 `0`。真实 12 场景 Pilot 与独立 Blind Judge 仍未执行，Production Shadow Candidate 结论保持未满足。

### Final As-Built Verification Update 18（2026-09-13）

- 受控授权运行器默认路径实跑仍为 `preflight_only=true`，冻结证据 `18` 场景、必需挑战全覆盖，`no_external_side_effects=true`。
- 未提供 `--execute-real`、确认令牌或 MiMo profile 时不会导入 provider client，不会发起网络请求；真实 Pilot 仍保持显式授权门槛。

### Final As-Built Verification Update 19（2026-09-13）

- 对 V2.1 Golden、metrics、报告、所有 Pilot JSON 产物及受控运行器执行凭据扫描：`credential_scan=clean`（共 15 个文件）。
- 未发现 API Key、Bearer token 或 SecretKey 模式；该检查为只读，不改变生产数据或历史 artifacts。

### Final As-Built Verification Update 20（2026-09-13）

- Production Materializer 关键门禁回归：`14 passed`，覆盖 `StoryboardAgent.run()` 反向 mock（调用次数为 0）、Approved ShotPlan 一对一物化、前置证据缺失 fail-closed、Qualification blocker 阻断 `ready`、以及 Phase A 状态。
- 本次仅验证 Production V2 不变量，未修改其默认行为、未调用真实 LLM/媒体/对象存储。

### Final As-Built Verification Update 21（2026-09-13）

- 修复 Production Storyboard Materializer 的结构保留缺口：除遗留关系列外，完整 `camera` 对象现在写入 `meta_info`，保留 `shot_size`、`camera_side` 等结构化字段，供 Prompt/导出/回放消费者使用。
- 新增完整 camera 保留断言；Materializer/Production gate 回归：`8 passed`，未增加镜头、未改变事实，也未触发外部调用。

### Final As-Built Verification Update 22（2026-09-13）

- camera 元数据保留改动后的全仓库后端回归：`783 passed`（887 个既有 warnings，无失败）。
- Production V2 与 Director Quality V2.1 默认路径保持不变；真实 MiMo、媒体和对象存储调用仍为 `0`。

### Final As-Built Verification Update 23（2026-09-13）

- 最新 Production revision 选择与完整 camera 保留改动后的全仓库后端回归：`783 passed`（887 个既有 warnings，无失败）。
- Materializer 现在对未指定版本的请求按场景选择最新 approved ShotPlan，并在显式 `plan_id` 时保持精确版本语义；该行为已由新增回归覆盖。

### Final As-Built Verification Update 24（2026-09-13）

- 增加已物化镜头与新 approved ShotPlan revision 的冲突门禁：相同 `plan_shot_id` 但来源 `shot_plan_id` 不同会返回 409，并保留历史 StoryboardShot，不静默跳过或覆盖。
- 版本冲突回归及全量后端回归通过：`785 passed`（889 个既有 warnings，无失败）。

### Final As-Built Verification Update 25（2026-09-13）

- 增加历史 StoryboardShot 缺少 `shot_plan_ref` 的 fail-closed 门禁；避免无法证明来源时重复物化。
- 最新 Production 相关回归：`10 passed`；全量后端回归：`786 passed`（890 个既有 warnings，无失败）。
- 不自动迁移或删除历史产物；仍未调用真实 LLM/MiMo、媒体或对象存储。

### Final As-Built Verification Update 26（2026-09-13）

- 增加同一 approved ShotPlan 的幂等重放断言：第二次确认返回 `mutated=false`、`materialized_count=0`，不产生重复 StoryboardShot。
- Production gate 回归仍为 `8 passed`；该测试只扩展验证范围，不改变运行时逻辑。

### Final As-Built Verification Update 27（2026-09-13）

- 前端全量 Vitest：`291 passed`（49 files）；TypeScript/Vite production build 成功。
- 本轮仅涉及后端 Production 物化门禁与测试，前端行为保持兼容；未调用真实模型或媒体供应商。

### Final As-Built Verification Update 28（2026-09-13）

- 模型注册表对 OpenAI-compatible 目录探测进行了本地回归：服务可达与模型可用性现在明确分离；远端目录存在但未包含配置 ID 时返回 fail-closed 结果，并提供远端完整模型 ID 建议，不把“连接成功”误报为模型可用。
- 火山配置的产品别名 `doubao-seed-2.0-lite` 已按远端目录契约改为完整模型 ID（当前保存值为 `doubao-seed-2-0-lite-260428`）；未调用真实火山接口，仅核验本地持久化值与脱敏注册表响应。
- 模型注册表后端测试 `26 passed`、模型管理前端定向测试 `10 passed`、全仓库后端回归 `786 passed`；前端 production build 成功。既有 warnings 为历史弃用/测试返回值警告，未发现失败。
- 已重启本地后端以加载最新诊断逻辑；Director Quality V2.1 仍保持 shadow/benchmark-only，未调用真实 MiMo、生图、视频或对象存储，也未改变 Production Pipeline V2 默认行为。

### Final As-Built Verification Update 29（2026-09-13）

- 重新执行受控 MiMo Pilot preflight：`status=ready_for_authorized_real_pilot`，冻结 evidence 为 18 个场景，12 类导演挑战全部覆盖。
- 三阶段候选、十维评分、Contract Reliability、场景覆盖和零外部副作用检查均为通过；`real_mimo_calls=0`、`provider_calls=0`、`media_calls=0`、`object_storage_calls=0`。
- 本次仍未执行真实 MiMo Pilot 或独立 Blind Judge；未改变 Production Pipeline V2 默认路径，也未写入任何生产 Storyboard/媒体记录。

### Final As-Built Verification Update 30（2026-09-13）

- 反向生产门禁与火山模型目录匹配回归：`3 passed`；Production materializer 在 `StoryboardAgent.run()` 被 mock 为异常时调用次数仍为 `0`，完整模型 ID 可通过，产品别名与版本化目录不匹配时 fail-closed。
- 本次只执行本地 mock/确定性测试，未访问火山或其它真实供应商。

### Final As-Built Verification Update 31（2026-09-13）

- 模型连接测试响应新增统一密钥脱敏：即使测试使用已配置 API Key，返回的 `profile` 只保留 `key_configured`，不会回显 `api_key`。
- 新增安全回归后模型注册表测试 `27 passed`；全仓库后端回归 `787 passed`（890 个既有 warnings，无失败）。
- 未改变模型目录匹配、Contract-First、Production Materializer 或 Production Pipeline V2 默认行为；未调用真实 LLM/MiMo、媒体或对象存储。

### Final As-Built Verification Update 32（2026-09-13）

- 重启本地后端后复核 `/api/model-registry`：火山配置仍为 `doubao-seed-2-0-lite-260428`、保持默认 LLM，响应中不包含 `api_key`。
- 前端入口返回 HTTP 200；本次仅验证本地运行时状态，未访问真实模型供应商。

### Final As-Built Verification Update 33（2026-09-13）

- 综合运行时核验：本地 `/api/model-registry` 返回火山完整模型 ID、默认 LLM 状态正确且无 `api_key` 字段；远程 `codex/unify-formal-workspace` HEAD 与本地 HEAD 均为 `ca6fcf7`。
- 本次仅读取本地接口和 Git 元数据；未触发真实 LLM/MiMo、媒体、对象存储或 CI。

### Final As-Built Verification Update 34（2026-09-13）

- 模型注册表定向回归：`28 passed`；新增 HTTP 路由级断言，确认连接测试响应不会回显 API Key。
- 全仓库后端回归：`788 passed`（既有弃用/测试返回值 warnings，无失败）；`python -m compileall -q api core scripts` 与 `git diff --check` 均通过。
- 火山目录匹配仍按 fail-closed 语义执行：服务可达不等于模型可用；产品别名 `doubao-seed-2.0-lite` 不会被当作远端完整 ID，需使用目录返回的版本化模型 ID。未调用真实火山或其它供应商。

### Final As-Built Verification Update 35（2026-09-13）

- 离线 Director Quality V2.1 benchmark 重新执行完成：18 个 Golden 场景，Contract Parse/Pass、Patch First/Final、Scene Planner 均为 100%，Director Quality 平均 `43.99`。
- 离线运行器明确记录 `mimo_pilot.status=not_run_by_instruction`、真实/媒体/对象存储调用均为 `0`；该结果不替代真实 MiMo Pilot，也不宣称 Production Shadow Candidate。

### Final As-Built Verification Update 36（2026-09-13）

- 受控 MiMo Pilot preflight（`scene_limit=12`）通过：证据场景 18 个、12 类导演挑战齐全，三阶段候选、十维指标、Contract Reliability 和零外部副作用检查均通过。
- preflight 仍保持只读：`real_mimo_calls=0`、`provider_calls=0`、`media_calls=0`、`object_storage_calls=0`；真实 Pilot 仍需单独的明确授权与确认 token。

### Final As-Built Verification Update 37（2026-09-13）

- V2.1 Pilot preflight、runner guard 与端到端 Contract-First 集成定向测试：`9 passed`。
- 验证范围包括：未提供显式真实调用开关时保持 preflight-only、12 场景证据覆盖、三阶段候选结构、十维指标和无生产副作用；未调用真实模型或媒体供应商。

### Final As-Built Verification Update 38（2026-09-13）

- 新增 V2.1 “候选 → Materializer”完整离线集成回归，验证结构镜头一对一物化，并保留 `plan_shot_id`、`shot_plan_ref`、camera、动作节拍、首尾状态、资产绑定和连续性合同。
- 定向集成测试：`2 passed`；全仓库后端回归：`789 passed`（既有 warnings，无失败）；`compileall` 与 `git diff --check` 通过。
- 该改动不触碰 Production 默认行为、不删除历史产物，未调用真实 LLM/MiMo、媒体或对象存储。

### Final As-Built Verification Update 39（2026-09-13）

- 交付物库存核验：V2.1 所需 29 个核心模块、测试和 artifact 文件全部存在；Golden 场景数与 metrics 均为 18，`offline_only=true`。
- 对 Golden/metrics JSON 执行凭据模式扫描：未发现 API Key、Bearer token 或 SecretKey 值；报告文本中的安全术语仅为审计说明。
- 离线 metrics 中 MiMo、媒体、对象存储调用总数为 `0`；真实 Pilot 仍未执行，未改变 Production 默认路径。

### Final As-Built Verification Update 40（2026-09-13）

- 模型目录探测新增通用响应归一化：支持标准 `data[]`、顶层列表、`models[]` 和嵌套 `data.models[]`，仅接受显式 `id/model_id`，避免兼容服务返回形状差异导致“服务可达但模型未发现”的误判。
- 模型注册表定向回归：`30 passed`；全仓库后端回归：`791 passed`（既有 warnings，无失败）；`compileall` 与 `git diff --check` 通过。
- 本次改动不依赖具体供应商或 book/scene 特例，未调用真实模型或媒体服务。

### Final As-Built Verification Update 41（2026-09-13）

- 目录归一化边界继续扩展为通用 `data.items[]` 形状，并新增 `model_id` 字段回归；不会把嵌套目录误判为空目录。
- 模型注册表定向测试：`31 passed`；编译检查与 `git diff --check` 通过。此前全量回归基线 `791 passed` 保持有效，本次仅变更目录解析与对应测试。
- 未调用真实供应商，不改变模型默认选择及真实调用门禁。

### Final As-Built Verification Update 42（2026-09-13）

- 目录响应归一化改动后的全仓库后端回归：`792 passed`（既有 warnings，无失败）。
- 该回归覆盖模型管理、V2.1 Contract-First、Production Materializer、Golden/Preflight 及既有业务链路；真实 LLM/MiMo、媒体和对象存储调用仍为 `0`。

### Final As-Built Verification Update 43（2026-09-13）

- **Baseline Audit 与 Final As-Built Verification 已分开记录**：本文件前段保留 Repository Audit 的原始缺口；本次验证针对已实现的 Contract-First 运行器与 MiMo 真实 Pilot，不回写或覆盖历史产物。
- 修复并验证了 provider 输出规范化：嵌套创意字段、单个 JSON-Patch operation、`patch[]` wrapper、按 `plan_shot_id` 的 `/shots/<id>/...` 路径，以及同一镜头的非冲突 patch 合并；冲突路径、未知镜头、不可变字段、非法辅助 proposal 仍 fail-closed，并记录 `normalization_metadata`/`_source_format`。
- 新增 patch/proposal 级 Local Repair：每次只携带失败项，最多 2 次，成功才合并，失败回退 baseline；不重跑场景，不写 ShotPlan/Storyboard，不触发媒体或对象存储。定向回归 `22 passed`。
- 真实 MiMo Pilot（12 场景，benchmark-only）artifact：`artifacts/director-quality-v2-1-mimo-pilot-20260913T093747Z.json`。HTTP 成功由供应商返回记录为 45 次调用中的 45 次 200；planner 12 次、repair 33 次；production rows / StoryboardShot / media / object storage 均为 `0`。
- 真实 Pilot 指标：首轮 schema pass `10/12`、parse success `10/12`；最终 validator contract pass `12/12`；repair 记录 18 条，其中 3 个场景存在 fallback（15 个 patch fallback），辅助 proposal rejected `0`；Director Quality 平均从 baseline `44.71`、修复前 `56.98` 到修复后 `56.98`，平均相对 baseline `+12.27`。
- MiMo token/cache/latency：prompt `151,037`、cached `119,424`、completion `21,018`、total `172,055`、cache hit rate `79.07%`、平均延迟 `12,247.68ms`；这些值只来自本次真实 Pilot，不用于修改 Production 默认策略。
- **结论**：Contract-First 的最终安全门禁通过，但首轮契约稳定性与 fallback 率尚未达到 Production Shadow Candidate；不得把本次 Pilot 宣称为生产放量依据。下一步应优化稳定输出契约/repair 成本后再做第二轮灰度，而不是放宽 validator。
