# Director Quality V2.2 — First-Pass Stability & Repair Cost Reduction
# Repository Audit（Step 1）

> 审计日期：2026-09-13  
> 分支：`codex/unify-formal-workspace`  
> 本地 HEAD：`bb5a71592d3cc44fee1d4ab4de424cfd2973856a`  
> 远程 HEAD：`ca6fcf79a1f794effebf7f33fb921bb17075f835`  
> 审计对象：当前仓库中的 Director Quality V2/V2.1 Contract-First 实现及最终 V2.1 MiMo Pilot artifact。  
> 审计输入：`artifacts/director-quality-v2-1-mimo-pilot-20260913T093747Z.json`、`artifacts/director-quality-v2-1-report.md`、`artifacts/director-quality-v2-1-gap-audit.md`、相关 `core/`、`scripts/`、`tests/`。  
> 安全边界：本阶段仅完成审计；未调用 MiMo/其它真实 LLM、生图、视频、对象存储；未写入生产数据库、Storyboard 或媒体；未处理 GitHub Actions/CI；未删除或覆盖历史产物。

## 1. Repository 状态与基线核验

- 已执行 `git fetch origin` 与 `git pull --ff-only`，结果为 `Already up to date.`。
- 当前本地分支比远程多 2 个提交；远程没有待合并的新提交。
- V2.1 的代码、Golden、最终 Pilot artifact、报告和 V2.1 Gap Audit 均已被 Git 跟踪；本地仍存在大量历史未跟踪 artifacts 和临时文件，本次不清理、不纳入审计提交。
- 最近一次提交 `bb5a715` 只记录了此前 Production Materializer 的验证报告；它不是 V2.2 实现。
- V2.2 新模块 `core/director_patch_normalizer.py` 与 `core/director_patch_deterministic_repair.py` 当前均不存在，说明本轮尚未开始实现。

## 2. V2.1 Baseline Audit（真实 Pilot 证据）

### 2.1 总体指标

来自最终 artifact 的权威 telemetry：

| 指标 | V2.1 实测值 |
|---|---:|
| 场景数 | 12 |
| 总调用 | 45 |
| Planner 调用 | 12 |
| Repair 调用 | 33 |
| 首轮 schema/parse pass | 10/12 |
| 最终 Contract pass | 12/12 |
| Patch fallback | 15 |
| Auxiliary rejection | 0 |
| 缓存命中率 | 79.07% |
| 平均延迟 | 12,247.68 ms |
| Planner prompt 平均 | 约 5,612 tokens |
| Repair prompt 平均 | 约 2,536 tokens |
| Repair/Planner prompt 比 | 约 45.2% |
| 生产数据库/Storyboard/媒体/对象存储副作用 | 0 |

`RepairAttempt` 记录按 artifact 中每个 scene 的 `repair_records[].attempts[]` 计数为 33，与 stage telemetry 的 `director_patch_repair.total_calls=33` 一致。

### 2.2 当前调用与责任边界

当前真实运行器 `scripts/run_director_quality_v2_1_mimo_pilot_authorized.py` 的顺序是：

```text
MiMo Planner
  → build_creative_patch_candidate / parse_creative_patch_partial
  → apply_partial_acceptance
  → 对诊断项逐项调用 repair_failed_patch 或 repair_failed_auxiliary_proposal
  → 再次 apply_partial_acceptance
  → deterministic baseline fallback
```

已有的安全能力：

- Contract / immutable / allowed path 验证仍是 fail-closed；事实越权不被修成另一事实。
- `apply_partial_acceptance` 已做到合法 patch 保留、失败 patch 单项回退，不再丢弃整场景。
- `repair_failed_patch` 和 `repair_failed_auxiliary_proposal` 最多两次尝试，不重跑整个场景。
- Pilot 只写 benchmark artifact，不进入 Production Pipeline V2 默认路径。

尚未具备的 V2.2 能力：

- 没有独立的 Level 0 canonical normalizer；等价格式在进入 LLM repair 前仍可能被判为 schema 错误。
- 没有独立的 Level 1 deterministic semantic repair/router；重复、排序、明确安全的别名/范围问题仍会走 LLM 或直接失败。
- repair ledger 尚未记录 `repair_level`、`repair_engine`、`fallback_reason`、`token_usage`、`latency_ms` 等 V2.2 字段。
- 指标没有完整的 raw → normalized → deterministic → LLM → final 分阶段序列，也没有 creative retention/full creative scene success。

## 3. 33 次 repair 的逐类归因

下表以最终 artifact 的 `repair_records` 为准；每个 patch 的两次相同 rejection 都单独计为一次外部调用。

### 3.1 30 次 patch repair（全部失败）

| 场景 | 失败 patch | 初始 Planner 诊断 | Repair 调用 | 两次终止错误 | 结论 |
|---|---|---|---:|---|---|
| `book990402:e2:回声照相馆` | S01、S02、S03、S05、S06、S08、S11 | `DIRECTOR_PATCH_FIELD_FORBIDDEN`；`patches[i].patch` 使用等价 JSON-Patch wildcard `/shots/*/camera/shot_size` | 7 × 2 = 14 | `DIRECTOR_PATCH_SCHEMA_INVALID: plan_shot_id is required` | 初始格式/path 可规范化，却错误进入 LLM；repair 响应又丢失身份 |
| `book990402:e2:暗房门口的试探` | S01–S08 | `DIRECTOR_PATCH_FIELD_FORBIDDEN`；使用 `/shots/Sxx/camera/shot_size` 的 operation envelope | 8 × 2 = 16 | `DIRECTOR_PATCH_SCHEMA_INVALID: plan_shot_id is required` | 已有明确目标镜头，但 operation/path envelope 未被等价归一化；repair 重复失败 |
| **合计** | **15 个 patch** |  | **30** |  | **全部 fallback baseline** |

说明：artifact 没有保存 MiMo 原始正文，只保存了 schema diagnostics、fingerprint 与修复结果。因此“初始格式/path 错误”是由 `model_info.schema_rejections` 证实的；不能把它误判为 15 个独立的创意质量失败。Repair 请求实际携带 `failed_patch`，但 repair 输出两次均没有 `plan_shot_id`，导致身份校验在 schema 边界直接失败。

### 3.2 3 次 auxiliary proposal repair（全部成功）

| 场景 | proposal | 结果 | 证据限制 |
|---|---|---|---|
| `book990402:e2:回声照相馆` | `AUX_S01` | 1 次，accepted | artifact 只保留 accepted 记录，没有持久化触发它的原始 rejection 详情 |
| `book990402:e2:回声照相馆` | `AUX_S02` | 1 次，accepted | 同上 |
| `book990402:e3:暗房惊魂` | `AUX_S01` | 1 次，accepted | 同上 |

这 3 次共构成 telemetry 中剩余的 3 次 repair 调用。其结果证明 proposal 级 repair 已存在，但原始 issue code、before/after proposal fingerprint 没有进入 Pilot artifact，是 V2.2 的审计可观测性缺口；本审计不臆造具体触发原因。

## 4. 15 个 fallback patch 的逐项根因

### 4.1 `book990402:e2:回声照相馆`（7 个）

`S01、S02、S03、S05、S06、S08、S11` 均：

1. Planner 输出的 patch envelope 使用 `/shots/*/camera/shot_size`，schema 将其报告为 `DIRECTOR_PATCH_FIELD_FORBIDDEN`；该 path 与 `plan_shot_id + camera.shot_size` 在本协议中具有可证明的等价关系，理论上属于 Level 0 normalization，而非 LLM repair。
2. 对每个 patch 发送两次 repair；两次结果均为 `plan_shot_id is required`。
3. 最终 `status=fallback`、`fallback_to_baseline=true`。

Fallback taxonomy（V2.2 应记录双层原因）：

- `primary_root_cause=FORBIDDEN_PATH`（初始 operation/path envelope）；
- `terminal_root_cause=LLM_REPAIR_CONTRACT_FAILURE`（repair 响应缺少不可替代的 patch identity）；
- `final_action=FALLBACK_BASELINE_PATCH`。

### 4.2 `book990402:e2:暗房门口的试探`（8 个）

`S01、S02、S03、S04、S05、S06、S07、S08` 的模式完全一致：

- 初始 path 分别为 `/shots/S01/...` 至 `/shots/S08/...`，其目标镜头明确；schema 仍在 V2.1 边界将 operation envelope 判为 `DIRECTOR_PATCH_FIELD_FORBIDDEN`。
- 每个 patch 两次 repair，均返回缺少 `plan_shot_id`。
- 最终回退 baseline。

Fallback taxonomy：

- `primary_root_cause=FORBIDDEN_PATH`；
- `terminal_root_cause=LLM_REPAIR_CONTRACT_FAILURE`；
- `final_action=FALLBACK_BASELINE_PATCH`。

### 4.3 Fallback 不是创意拒绝

本次 15 个 fallback 不能解释为“模型提出的镜头创意全部不合格”。至少在 S01–S08 等项中，模型确实提供了可解析的镜头目标与 camera 值；失败主要发生在协议等价格式和 repair identity 上。若 V2.2 直接删除这些 patch 或放宽 validator，都会错误地掩盖稳定性问题，损害 Creative Retention。

## 5. 哪些错误不需要 LLM

以下问题有唯一、无创意语义变化的处理方式，应在 LLM 之前完成或直接 reject：

- `/shots/S03/camera/shot_size`、`shots.S03.camera.shot_size`、`plan_shot_id=S03 + camera.shot_size` 等已知等价路径。
- `patch[]` wrapper、单 operation wrapper、nested creative object 与 canonical `changes` 的结构转换。
- 白名单别名（如 `shotSize→shot_size`、`cameraMovement→movement`、`cutReason→cut_reason`），仅限协议已明确定义者。
- Camera Library 已声明等价的 enum（如 `close-up/close_up/CU`）以及首尾空白、大小写、schema 明确的 numeric 字段转换。
- 同一个 shot/path、同一 value 的重复 patch；不冲突的重复 patch 合并；合法 patch 的稳定排序。
- schema 明确允许的 singleton/list 转换；明确允许的数值范围 clamp。
- immutable/fact override、unknown `plan_shot_id`、invalid source beat、无法绑定的 auxiliary proposal：这些没有安全的创意修复答案，应直接 reject/fallback，不调用 LLM 绕过边界。

## 6. Level 0 Canonical Normalization 候选

新增集中模块 `core/director_patch_normalizer.py`，只做 deterministic、可逆、可审计的格式等价转换：

1. canonical path 解析为 `{plan_shot_id, path}`；必须验证 path 中的镜头与声明 ID 一致，不能猜测。
2. 白名单字段 alias 归一化。
3. 已有 Camera Library/schema 白名单内的 enum alias 归一化；未知值保留错误。
4. schema 明确要求 number 时执行安全字符串转数值。
5. trim/规定 casing；不改变自由文本创意内容。
6. nested camera/composition/emotion/edit 等 creative object flatten 为 dotted `changes`。
7. 记录 `before_fingerprint`、`after_fingerprint`、`normalization_reason`、`source_format`。

Level 0 明确禁止选择新的镜头景别、情绪、表演、运镜或剧情信息。

## 7. Level 1 Deterministic Semantic Repair 候选

新增集中模块 `core/director_patch_deterministic_repair.py`，只处理唯一安全答案：

- identical duplicate merge；
- non-conflicting duplicate merge；
- canonical path 后的稳定 patch order；
- schema 明确允许的 array/singleton 转换；
- 已有 enum alias 与明确允许的 range normalization；
- 其它能由 contract/schema 给出唯一答案的结构修复。

Level 1 不得：自己选择 shot size、emotion、performance direction、why_this_shot、dramatic function、camera movement 或新增辅助镜头；这些属于创意语义。

## 8. 仅哪些错误才可进入 Level 2 LLM Repair

只有没有唯一确定答案、需要重新选择创意值的问题可调用 LLM：

- `UNMOTIVATED_SHOT`；
- `EMOTIONAL_FLATLINE`；
- `POWER_SHIFT_NOT_VISUALIZED`；
- `INFORMATION_REVEAL_CONFLICT`；
- `GRATUITOUS_CAMERA_MOVEMENT`；
- 无唯一 deterministic 答案的 `REDUNDANT_SHOT`；
- 需要重新选择创意值的 invalid creative value；
- 其它明确的 creative semantic conflict。

以下永远不得进入 Level 2：`DIRECTOR_FACT_OVERRIDE`、immutable violation、`UNKNOWN_PLAN_SHOT_ID`、invalid source beat、无法精确绑定的 auxiliary proposal。

Level 2 request 只应包含 failed patch/proposal、issue、target shot、source beat、相关 Scene Strategy 子节、allowed paths 与 immutable constraints；不得默认重新发送完整 ScriptIR、Treatment、Blocking、ShotPlan 或 Scene。

## 9. 当前 repair 上下文与重复问题

### 9.1 上下文仍偏大

V2.1 telemetry：Planner 总 prompt 67,349 tokens；Repair 总 prompt 83,688 tokens。按调用数计算，Planner 约 5,612 tokens/次，Repair 约 2,536 tokens/次，repair/planner 比约 45.2%，高于方案目标 `<35%`。

当前 `core/director_patch_repair.py` 虽然有 `_contract_subset()`，但请求仍包含完整 `source_beat_map`、完整 `strategy` 对象及目标 shot；`_repair_prompt()` 再将整个 request JSON 序列化。下一阶段应按 issue 选择 strategy subsection 与 source beat，不是简单删除安全约束。

### 9.2 Retry 确实重复修同一问题

15 个 fallback patch 的 attempt 1/2 均为同一 `DIRECTOR_PATCH_SCHEMA_INVALID: plan_shot_id is required`；artifact 中 repair request fingerprint/场景信息显示没有基于第一次错误的 adaptive correction。两次调用既没有先做 identity injection/normalization，也没有在同错误重复时停止，因此产生 30 次无收益的外部调用。

V2.2 应在 Level 0/1 先消除可确定错误，并对相同 `(target, issue_code, request_fingerprint, error_signature)` 做 bounded dedupe；不得以增加重试次数换取成功率。

## 10. Fallback 粒度现状

V2.1 已达到 patch-level fallback：15 个失败 patch 回到 baseline，其他合法 patch 和 auxiliary proposal 保留，场景最终仍可 Contract pass。它不是整场景 fallback，这是正确方向，应保持。

但当前 fallback taxonomy 尚未标准化；`repair_records` 只提供 `kind/identity/status/attempts/fallback_to_baseline`，没有稳定的 `scene_id`、`plan_shot_id/proposal_id`、`root_cause`、`repair_level_attempted`、`final_action` 字段。V2.2 需要在不改变 patch-level 行为的前提下补齐审计信息。

建议 taxonomy：`SCHEMA_PARSE_FAILURE`、`FORBIDDEN_PATH`、`FACT_OVERRIDE`、`INVALID_VALUE`、`CROSS_PATCH_CONFLICT`、`STRATEGY_CONFLICT`、`AUXILIARY_BINDING_FAILURE`、`QUALITY_REPAIR_EXHAUSTED`、`LLM_REPAIR_PARSE_FAILURE`、`LLM_REPAIR_CONTRACT_FAILURE`、`UNKNOWN`。

## 11. First-Pass 指标审计

当前指标有 `schema_pass`、`parse_success`、最终 `contract_pass`、stage calls、token/cache/latency，以及部分场景的 baseline/before/after quality；但不足以定位 V2.2 目标：

- 没有 `raw_parse_pass`；
- 没有 `normalized_parse_pass`；
- 没有 `first_pass_schema_pass` 与 `first_pass_contract_pass` 的同一口径逐场景分母；
- 没有 `post_normalization_contract_pass`；
- 没有 `post_deterministic_repair_pass`；
- 没有 `post_llm_repair_pass` 的阶段计数；
- 没有 `normalization_events`、`deterministic_repair_events`、`llm_repair_calls_per_failed_patch`、平均 repair attempts、repair token/latency、fallback-after-repair；
- 没有 `Creative Retention Rate` 或 `Full Creative Scene Success Rate`；
- 没有把每个 auxiliary 的 issue、proposal fingerprint、repair level 与最终动作稳定写入 artifact；
- 真实 Pilot 的逐场景十维 quality 明细存在于部分嵌套结构，但没有与每个阶段、每个 patch 的 retention 统一聚合。

V2.2 必须新增上述阶段指标，而不是通过放宽 validator 或减少候选 patch 来提高数字。`Fact Override Accepted` 与 `Auxiliary Unbound Accepted` 继续保持 0。

## 12. V2.2 需要修改的文件（最小范围）

### 必须新增

1. `core/director_patch_normalizer.py`：Level 0 canonical normalization。
2. `core/director_patch_deterministic_repair.py`：Level 1 deterministic repair、冲突与排序。
3. V2.2 定向 unit/integration tests。
4. `artifacts/director-quality-v2-2-report.md`、`artifacts/director-quality-v2-2-metrics.json` 及带时间戳的 Stage A/B Pilot artifacts（仅在后续阶段）。

### 可能需要修改

- `core/director_creative_planner.py`：先 normalize/repair，再进入 Contract；保持兼容入口及 shadow-only 语义。
- `core/director_patch_schema.py`：把等价 envelope 的解析委托/对齐到 Level 0，同时保留严格边界。
- `core/director_patch_compiler.py`、`core/director_patch_validator.py`：消费 canonical patch，强化 target/path guard。
- `core/issue_router.py`：增加 V2.2 issue code → Level 0/1/2/reject 的正式路由表。
- `core/director_patch_repair.py` / `core/director_local_repair.py`：仅 Level 2 局部 repair，缩减上下文并防止重复错误重试。
- `core/director_quality_metrics.py`、`core/pilot_instrumentation.py`：增加阶段指标、repair cost、creative retention、full creative scene success。
- `core/repair_ledger.py` 与必要的 runtime 序列化：补齐 `repair_level`、`repair_engine`、`fallback_reason` 等 metadata；先评估是否可复用现有 `revalidation_details`，避免不必要 schema 变更。
- `scripts/run_director_quality_v2_1_mimo_pilot_authorized.py`：后续 V2.2 runner/metrics 接线，不能覆盖 V2.1 artifact。

### 明确不修改

Production Pipeline V2 默认主链、SceneBlocking V2 规则、媒体/对象存储调用、GitHub Actions/CI；不新增 book/scene/shot 特例，不修改质量评分规则，不删除 deterministic fallback，不覆盖旧 Pilot artifacts。

## 13. Migration 判断

当前不需要数据库 migration：

- patch/proposal、fingerprint、阶段指标和 fallback taxonomy 可先保存在 candidate `model_info`、pilot artifact 与 `RepairAttempt.revalidation_details` metadata；
- `RepairAttempt` 已有 `issue_code`、target、fingerprints、attempt、model、prompt fingerprint；V2.2 首轮只需扩展序列化 metadata，先不扩大表结构；
- V2.2 是 shadow/benchmark-only，不要求生产查询新列。

只有后续出现高频按 `repair_level`/质量维度查询、独立 Strategy 版本管理或大规模在线审计需求时，才重新评估 migration。

## 14. V2.2 测试计划（实现后才能执行）

### Unit

- canonical path normalization；
- alias、enum、numeric、whitespace normalization；
- nested patch flatten；
- identical duplicate merge；
- non-conflicting duplicate merge；
- conflicting duplicate reject；
- deterministic safe repair；
- Level 0/Level 1 时 mock LLM，断言调用次数为 0；
- Level 2 local repair 可调用且仅返回一个目标 patch/proposal；
- repair scope minimization 与同错误 dedupe；
- fallback root-cause taxonomy；
- creative retention、full creative scene success；
- first-pass staged metrics；
- immutable/fact/unknown target/source beat fail-closed。

### Integration

```text
Raw MiMo-like output
 → Level 0 Normalize
 → Level 1 Deterministic Repair
 → Contract Validation
 → Level 2 LLM Local Repair（仅真正创意问题）
 → Partial Acceptance
 → Patch-level Fallback
 → Final Creative ShotPlan
```

必须证明：

- normalization/deterministic 问题不会调用 LLM；
- Planner/patch repair 失败不会改变 Structural ShotPlan；
- 不创建 StoryboardShot，不触发生产数据库、媒体或对象存储；
- mock `StoryboardAgent.run()` 为异常时，production API 正常路径调用次数仍为 0；
- Contract blocker、Fact Override、Unknown target 和 Auxiliary unbound 仍 fail-closed。

### Regression（真实调用前）

- Director V2.2 targeted tests；
- 全部 V2.1 tests；
- Production Pipeline、SceneBlocking V2、Golden、production gate 相关测试；
- `python -m compileall -q api core scripts`；
- `git diff --check`。

在上述本地测试全绿前，禁止再次调用真实 MiMo。

## 15. V2.2 实施顺序与进入 Stage A 的门槛

1. **Audit（本文件）**：仅记录真实根因，保持 V2.1 artifact 不变。
2. **Level 0**：实现 normalizer 与等价格式测试。
3. **Level 1**：实现 deterministic repair、冲突/排序/唯一安全答案测试。
4. **Repair routing**：明确 Level 0/1/2/reject，缩减 Level 2 上下文，禁止重复错误 retry。
5. **Metrics/Ledger**：阶段指标、repair cost、fallback taxonomy、creative retention。
6. **Regression**：V2.2 + V2.1 + Production + SceneBlocking + Golden 全绿。
7. **Stage A 真实 MiMo Pilot**：仅 benchmark-only、12 个与 V2.1 尽量同口径场景；只写新 artifact，不写生产对象。
8. 若 Stage A 未退化，再评估 Stage B（≥24 场景）；不自动开启 Production Shadow。

### Stage A 比较基线

| 指标 | V2.1 基线 | V2.2 必须报告 |
|---|---:|---:|
| Repair calls | 33 | 总量、每场景、每失败 patch |
| Fallback patches | 15 | 数量、rate、root cause |
| First schema pass | 10/12 | raw/normalized/first schema 分阶段 |
| Final Contract pass | 12/12 | 保持 100% |
| Creative retention | 未记录 | 必须新增，目标 ≥90% |
| Full creative scene success | 未记录 | 必须新增，目标 ≥85% |
| Avg latency | 12.25s | 与同口径比较 |
| Cache hit | 79.07% | 不低于目标 70% |

## 16. 审计结论（Baseline；Final As-Built 尚未开始）

V2.1 已证明 Contract-First、patch-level partial acceptance、最终 Contract pass 和生产副作用隔离是可行的；但 33 次 repair 中 30 次是可避免的 schema/identity 重试，15 个 fallback 主要源于协议等价格式未在 LLM 前归一化以及 repair identity 丢失。当前 repair prompt 比例约 45.2%，first-pass 与 retention 指标也不足以判断质量是否真的保留。

因此 V2.2 的首要收益点不是继续扩充 Prompt，也不是放宽 Validator，而是：

1. 把已知等价格式移到 Level 0；
2. 把唯一安全答案移到 Level 1；
3. 只把真实创意冲突交给 Level 2；
4. 在相同错误重复出现时停止无效 retry；
5. 用阶段化和 creative retention 指标证明“少 repair”没有换来“少创意”。

本文件完成后，方可进入 V2.2 Level 0 实现。当前 **未开始 Final As-Built Verification**，也不满足 Production Shadow 条件；不得执行真实 MiMo Pilot。

## 17. Final As-Built Verification（本地闭环）

本节与上文 Baseline Audit 分开记录；上文保留的是实施前事实，本节记录当前仓库实际构建结果。

### 已落地

- Level 0：`core/director_patch_normalizer.py`，覆盖 canonical path、白名单 alias、enum/numeric/whitespace 规范化、嵌套结构 flatten、before/after fingerprint 与 fail-closed 未知字段。
- Level 1：`core/director_patch_deterministic_repair.py`，覆盖重复 patch 合并、非冲突合并、冲突拒绝和稳定排序。
- 路由与指标：`core/issue_router.py`、`core/director_quality_metrics.py`、`core/repair_ledger.py` 已记录 repair level/engine、fallback taxonomy、阶段门禁、repair cost 与 creative retention。
- Level 2 边界：`core/director_quality_v22.py` 仅向明确的创意语义问题开放局部 repair；Level 0/1、事实越权、未知目标不会调用 LLM。
- Partial acceptance：`core/director_patch_compiler.py` 在 partial 模式按字段保留合法 sibling；原子编译默认行为不变，事实/权限错误仍拒绝。
- 离线回放：`scripts/run_director_quality_v2_2_benchmark.py` 只读取冻结 V2.1 evidence 与候选文档，明确输出 `llm_provider_calls=0`、媒体/存储/生产写入均为 0。
- Stage A 入口：`scripts/run_director_quality_v2_2_mimo_pilot_authorized.py` 已实现显式 `--execute-real`、精确 confirmation token 与 MiMo profile 三重门禁；导入和默认 CLI 均不初始化 provider。

### 本地证据

- V2.2 定向、V2.1、Production、SceneBlocking V2、Materializer gate：`81 passed`。
- 全仓库后端 pytest：`820 passed`，无失败。
- `python -m compileall -q api core scripts`：通过。
- `git diff --check`：通过。
- 离线回放 12 场景：raw/normalized/schema/contract/final 均 `12/12`，fallback `0`，creative retention `100%`；该结果仅证明回放管线，不代表真实 MiMo 指标。
- V2.2 guarded MiMo runner authorization/mock tests：`7 passed`；默认 CLI `preflight_only`，真实 provider 调用 `0`。

### 尚未满足 / 明确不宣称

- 本地验证尚未替代 Stage A 真实 MiMo 12 场景 A/B Pilot；尚未生成 `director-quality-v2-2-stage-a-mimo-pilot-<timestamp>.json`。
- 当前可执行命令需要操作者明确提供 `CONFIRM_DIRECTOR_V22_REAL_MIMO_PILOT` 与已保存的 MiMo profile；未获得该确认前不会产生外部调用或费用。
- 因缺少真实 V2.2 Pilot 的 repair/token/latency/cache/quality 数据，不能宣称达到 Stage A 目标，也不进入 Stage B 或 Production Shadow。
- Final As-Built 结论：**NOT_READY_FOR_PRODUCTION_SHADOW**（原因是外部 Pilot 证据尚缺，不是本地安全门失败）。

### 变更提交

- `cb727c1`：字段级 partial acceptance 与 V2.2 pipeline/test 收口。
- `6a3ce78`：离线 V2.2 benchmark replay runner、回放测试及 pipeline 可观测字段。

## 18. Final As-Built Verification（Stage A 真实 MiMo）

本节记录在完成本地门禁后、经操作者明确确认执行的真实 MiMo Stage A Pilot；与第 1–16 节的 Baseline Audit 及第 17 节的 Local As-Built Verification 分开。Pilot 只读取冻结 Golden evidence，严格限制为 12 个场景，未修改生产数据或历史产物。

### 18.1 执行与边界证据

- Artifact：`artifacts/director-quality-v2-2-stage-a-mimo-pilot-20260913T145407Z.json`。
- `pilot_mode=real_mimo_benchmark_only`，模型为已保存 profile 的 `mimo-v2.5`。
- `scene_count=12`；`production_shadow.enabled=false`。
- `side_effects`：production rows、Storyboard shots、media、object storage 全部为 `0`。
- Artifact 未包含 API key 或 bearer token；仅保留 profile/model、host、指纹、用量和延迟遥测。
- 真实调用总数 26（Planner 12、Repair 14），所有 HTTP 状态均为成功且可解析；无 retry。

### 18.2 Stage A 实测指标

| 指标 | V2.1 基线 | V2.2 Stage A | 判断 |
|---|---:|---:|---|
| 首轮 Schema Pass | 10/12 | 10/12 | 持平 |
| 最终 Contract Pass | 12/12 | 12/12 | 通过 |
| Repair 调用 | 33 | 14 | 改善 |
| Fallback patch | 15 | 27（20.93%） | 退化 |
| Creative Retention | 未记录 | 78.29% | 未达 90% |
| Full Creative Scene Success | 未记录 | 75% | 未达 85% |
| Director Quality 平均 | 56.98 | 58.70（+1.72） | 内部指标上升 |
| Cache hit | 79.07% | 46.05% | 未达 70% |
| 平均延迟 | 12.25s | 17.19s | 退化 |

Fallback 共 27 个：17 个 `FORBIDDEN_PATH / DIRECTOR_PATCH_FIELD_FORBIDDEN`，10 个 `LLM_REPAIR_CONTRACT_FAILURE / INVALID_PATCH_VALUE`。9 个场景为 `valid`，3 个为 `partial`；最终 Contract 仍为 12/12，说明结构安全边界保持，但创意候选保留不足。

### 18.3 Release 判断

**NOT_READY_FOR_PRODUCTION_SHADOW**。Stage A 已完成但未达到方案门槛：Creative Retention、Full Creative Scene Success、Cache hit 未达目标，fallback 与延迟相对 V2.1 退化。不得据此开启 Production Shadow 或切换 Production default。

下一轮仅允许在修复以下通用根因后，以同口径重新 benchmark：

1. 扩充 canonical normalizer 对真实 MiMo operation/path envelope 的等价覆盖，降低 17 个 `FORBIDDEN_PATH`。
2. 强化 Level 2 repair 的 patch identity 与字段级 contract，降低 10 个 `INVALID_PATCH_VALUE` fallback，同时保持事实越权 fail-closed。
3. 稳定 planner/repair 前缀并去重 repair 请求，恢复 cache hit 与延迟；不得通过 fallback baseline 或放宽 validator 制造虚高指标。

本次真实 Pilot 仅新增上述带时间戳 artifact 与本报告/metrics/audit 更新；未清理、覆盖或删除任何既有历史 artifact。
