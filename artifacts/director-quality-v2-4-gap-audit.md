# Director Quality V2.4 — Repository Gap Audit

审计日期：2026-09-14  
仓库：`yeqing112/screenplay-agent-refactor-v2`  
分支：`codex/unify-formal-workspace`  
Baseline Audit HEAD（审计起点）：`a50cb36e2c61b9609d922bf554978ede882b228b`  
说明：本文件第 1–8 节保留该起点的历史基线事实；不要将其误读为当前 HEAD。  
Final As-Built Verification source commit：`17e6af9`（代码验证基线；后续仅有文档索引提交）

## 1. 审计边界与方法

本轮严格执行 V2.4 Step 1，仅进行 Repository Audit：

- 读取 Director Quality V2.3 B1/B2 实现、测试和 artifacts；
- 不修改业务代码；
- 不调用真实 MiMo、生图、视频或对象存储；
- 不写入 Production/Storyboard；
- 不开启 Production Shadow；
- 不处理 GitHub Actions/CI；
- 不针对任何 `book_id`、scene name 或 fixture 写特例；
- 不覆盖或清理历史产物。

远程 fetch 已尝试两次，均因当前环境无法连接 GitHub 443 失败；本地远程跟踪 ref 仍与已推送提交 `a50cb36` 一致，未发现可用的新远程基线。

审计对象包括：

- `core/director_opportunity_detector.py`
- `core/director_opportunity_model.py`
- `core/director_opportunity_planner.py`
- `core/director_creative_value.py`
- `core/director_creative_planner.py`
- `core/director_creative_contract.py`
- `core/director_patch_compiler.py`
- `core/director_patch_validator.py`
- `core/scene_directing_strategy.py`
- `core/director_quality_trace.py`
- `core/director_quality_v23_benchmark.py`
- `core/director_quality_validator.py`
- `core/director_shadow_gate.py`
- `core/director_tail_root_cause.py`
- `core/director_tail_repair.py`
- `core/director_patch_repair.py`
- `core/local_repair.py`
- `core/qualification_loop.py`
- `core/repair_ledger.py` 与 `models/repair.py`
- `scripts/run_director_quality_v2_3_phase_b1_pilot.py`
- `scripts/run_director_quality_v2_3_phase_b2_pilot.py`
- `scripts/finalize_director_quality_v2_3_phase_b_report.py`
- V2.3 B1/B2 artifacts、metrics、opportunity/tail analysis 与 gap audit

## 2. V2.3 B2 事实基线

权威结果：`artifacts/director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json`。

| 指标 | B2 实际值 |
|---|---:|
| 场景 | 24/24 |
| MiMo 调用 / 解析成功 / 重试 | 24 / 24 / 0 |
| Cache hit rate | 72.74% |
| Contract Pass | 87.50%（21/24） |
| Director Quality mean / median / P10 / min | 62.8513 / 50.3 / 28.45 / 28.39 |
| Creative Value mean | 60.4852 |
| Eligible / ACT / Useful Accepted / Valid Skip / Missed | 185 / 176 / 29 / 9 / 0 |
| UCA V2 | 15.68%（29/185） |
| Edit / Emotion / Information eligible coverage | 25.22% / 3.92% / 14.52% |
| Tail trigger / attempted | 62.50% / 0 |
| Unknown root cause | 0 |
| Over-directing / shot inflation | 0.69% / 0% |
| Production / Storyboard / Media / Object Storage side effects | 0 / 0 / 0 / 0 |
| Production Shadow | disabled |

质量呈明显双峰：`<60` 为 14 个场景，`>=90` 为 9 个场景。B2 已证明机会检测和安全隔离可运行，但没有证明机会可以稳定转化为合法且有价值的干预。

## 3. Audit 问题结论（对应 V2.4 A–L）

### A/B. Tail Repair 为什么只触发、不执行

当前 `build_tail_repair_plan` 只生成 `triggered/root_causes/scopes/attempts`；`apply_tail_repair` 只是对已给定的字典 patch 做路径范围校验和应用，不负责：

`Tail Trigger → Root Cause → Scope → Minimal Context → MiMo → Compile → Contract Validate → Quality Rescore → Accept/Rollback`。

V2.3 B1 runner 在场景记录中明确写入 `repair_calls=0`，并将 `tail_repair.attempts` 初始化为 0；B2 仅复用该 runner。因此 B2 的 15 个触发场景没有 runtime executor，`tail_repair_attempted_count=0` 不是“修复全部失败”，而是“从未执行”。

已有 `director_patch_repair.py` 可以对单个失败 patch 做最多两次替换式修复，并能写入通用 `RepairAttempt` ledger，但它没有接收 Tail root cause、最小场景上下文、目标维度 delta 或尾部接受策略，尚未成为 Tail Repair runtime。

**分类：runtime execution gap。**

### C. Root Cause primary 的固定顺序偏置

`classify_tail_root_cause` 按 `causes` 追加顺序直接取 `causes[0]`。当前顺序通常是：UNKNOWN → missing opportunity → edit → emotion → information → UCA → over/under directing → patch quality …。当一个场景同时存在多个缺陷时，primary 不是按严重度、机会优先级、受影响机会数或预期质量影响排序，而是由代码顺序决定。

此外，当质量高于阈值且没有 cause 时，函数返回 `UNKNOWN_ROOT_CAUSE`；V2.4 要求这类非 Tail 场景应为 `NOT_APPLICABLE` 或 null，UNKNOWN 只允许表示“确实是 Tail 但无法解释”。

**分类：metric semantic bug / diagnosis correctness bug。**

### D. Opportunity Detector 的通用性问题

当前 detector 是确定性的，但尚未有第二层 Eligibility Validator；`_candidate` 将所有候选直接写成 `eligible=True`。具体风险：

- **denominator inflation / false eligibility**：`OPP_ACTION_ACCELERATION` 对 action/chase/acceleration 等类型或少量词命中即产生；多个连续 beat 可被全部计入机会。
- **entry/exit false inference**：用相邻 beat 的 participant 集合增减推断入场/退场；参与者集合变化不等于物理进入/离开。没有优先验证 SceneBlocking entry/exit、participant presence state 或 explicit action beat。
- **scene button 泛化**：只要最后 beat 或 scene 有 `state_out/plot_result/scene_button/button` 即 eligible，没有验证是否确有 release、cliffhanger、reaction hold、visual punctuation 或 transition 需要导演处理。
- **dialogue pressure 泛化**：有对白且类型属于 dialogue/confrontation/question，或文本出现“质问/逼问/对话压力”即可生成，不要求 conflict escalation、interruption、dominance change、subtext tension 等证据。
- **evidence_ref 不精确**：部分规则把引用写成 `treatment.beat_map[{beat_id}].information_change`，但 `beat_id` 不是数组索引；`withhold/withholds/audience_should_not_know_yet` 命中时仍泛指 `information_change`。这会使回放无法准确定位触发字段。

目前没有 `ELIGIBLE/NOT_APPLICABLE/REDUNDANT/WEAK_EVIDENCE/ALREADY_COVERED` 的第二层判定，也没有各状态的 evidence、reason 和可复核计数。

**分类：metric semantic bug；部分属于 detector correctness gap。**

### E. Creative Value 因果归因错误

`evaluate_useful_creative_acceptance` 只要求 `quality_delta > 0` 且 `dimension_deltas` 中任意一个维度为正，即可判定 `USEFUL_ACCEPTED`。它没有把 `opportunity.recommended_directing_dimensions` 映射到 scorer 的权威维度后再判断目标维度是否正向。

因此，一个 Emotion Turn 机会即使只改善了 SHOT_DIVERSITY，也可能被错误记为 useful。当前没有版本化的 dimension attribution map，也没有 opportunity-level 的 before/after target-dimension evidence。

**分类：metric semantic bug。**

### F. VALID_SKIP 是否被 UCA 惩罚

是。V2.3 UCA 的分母是全部 eligible opportunities，公式为 `useful_accepted / eligible`；`SKIPPED_VALID_REASON` 不增加 useful，但仍留在分母，因此会降低 UCA。它被单独统计为 `valid_skip_rate`，但没有 V2.4 要求的 `ACT Realization Rate` 与 `Opportunity Address Rate`，也没有 UCA V3 的版本化口径。

V2.4 应保留历史 UCA V2 供比较，同时新增：

- `ACT Realization Rate = USEFUL_ACCEPTED / ACT`
- `Opportunity Address Rate = (USEFUL_ACCEPTED + VALID_SKIP) / eligible`
- `UCA V3`：只在明确 ACT 的机会中计算。

**分类：metric semantic bug。**

### G. 是否存在完整 Opportunity → Applied → Delta trace

不存在。当前有三段彼此松散的记录：

- opportunity/outcome：包含 opportunity id、planner decision、最终状态和粗粒度 delta；
- `director_quality_trace`：shot × dimension 的阶段缺失诊断；
- patch compiler/ledger：保存部分 patch、指纹和修复尝试。

缺少统一的 `strategy_id`、`patch_ids`、`auxiliary_proposal_ids`、`compile_results`、`validation_results`、`applied_patch_ids`、`rejected_patch_ids`、`repair_attempt_ids`、目标维度 before/after，以及将这些字段以 opportunity id 串联的不可变记录。当前 outcome 的 `evidence_fingerprint` 在 B2 多数为空，无法作为稳定关联键。

**分类：runtime/observability gap。**

### H. B2 Contract Failure 的具体场景与当前可见原因

B2 有 3 个场景未通过 Contract：

| 场景 | rejected patch 数 | 当前 artifact 可见信息 |
|---|---:|---|
| `book990402:e1:...` | 12 | 仅保留 rejected_patch_count=12 |
| `FIXTURE_SILENT_01` | 4 | 仅保留 rejected_patch_count=4 |
| `fixture:action_blocking` | 4 | 仅保留 rejected_patch_count=4 |

当前 runner 没有把 compiler 返回的 rejected patch 列表、error code、path、target shot、immutable mismatch 等写入 artifact；`pipeline_diagnostics` 只有计数，无法回答每个 patch 的确切原因。因此这 3 个场景的“具体原因”在现有权威 artifact 中不可复核，这是 V2.4 必须先补的 provenance/contract taxonomy 缺口，而不能凭猜测归因。

现有编译器内部已有若干异常类型，但没有统一的 `ContractFailure` 分类和 patch-level 首次/最终通过率。必须至少覆盖：`PARSE_FAILURE`、`ENVELOPE_SCHEMA_ERROR`、`FORBIDDEN_PATCH_PATH`、`FACT_OVERRIDE_ATTEMPT`、`UNKNOWN_PLAN_SHOT_ID`、`INVALID_PATCH_VALUE`、`INVALID_CHARACTER_REFERENCE`、`AUXILIARY_UNBOUND_BEAT`、`AUXILIARY_BUDGET_EXCEEDED`、`CONTRACT_FINGERPRINT_MISMATCH`、`OTHER_KNOWN`、`UNKNOWN_CONTRACT_FAILURE`。

**分类：observability gap；contract repair gap。**

### I. Phase A/B1/B2 provenance 是否正确

不正确或不完整：

- B1/B2 pilot artifact 顶层没有 `commit_sha`、`branch`、`scene_manifest_hash`、`evidence_hash`、`source_artifacts`、`source_artifact_hashes`、`gate_version`、`metric_schema_version`。
- B2 `source_evidence.path` 使用 Windows 绝对路径/不稳定路径语义，而不是 repo-relative POSIX path。
- final metrics 的 `sources.phase_a` 与 `sources.phase_b1` 都指向 B1 artifact；`phase_a` 实际上通过 `_pilot_summary(b1)` 复用了 B1，不代表真实 Phase A。最终 metrics 没有独立的 `phase_b1` 数据块。
- `artifacts/director-quality-v2-3-opportunity-analysis.json` 与 `...tail-analysis.json` 只保存 `{protocol_version,status,source}`；由于 writer 对 pilot 中的 list 使用 `_dict`，实际 source 数据为空，不能独立回放。

**分类：audit correctness bug / provenance bug。**

### J. Shadow Gate 阈值是否单一来源

当前 `core/director_shadow_gate.py` 内部集中定义了大部分阈值，但 Contract 安全条件 `contract_pass_rate == 1.0` 和各价值阈值仍以函数体字面量存在，没有独立的、版本化的 `DirectorShadowGatePolicy`。报告、最终 metrics 和 runner 通过 gate 结果间接消费，但没有输出 policy/gate version，也没有把 failure reason 从 checks 结构化传播出来。

因此目前不能证明 V2.4 所要求的“唯一权威策略 + 报告/metrics/runner 全部读取同一 policy”。V2.4 必须建立 SSOT，并让 Contract final pass 明确保持 100%，不得降阈值。

**分类：audit correctness gap / policy drift risk。**

### K. NOT_READY 时 reasons 是否完整

不完整。B2 gate 为 `NOT_READY`，但 final metrics writer 输出 `reasons: []`；`evaluate_shadow_gate` 只输出布尔 checks 和 thresholds，没有生成结构化 reasons。V2.4 必须由 gate checks 自动生成 `{code,actual,required}`，并确保任何 NOT_READY 都有非空 reasons。

**分类：audit correctness bug。**

### L. Standalone opportunity/tail artifacts 是否包含来源和数据

不包含。B2 pilot 顶层 `artifacts.opportunity_analysis` 是 list，`artifacts.tail_analysis` 是 dict；final writer 使用 `_dict(...)` 读取 opportunity/tail source，导致独立 JSON 只有空 source。它们不能脱离 pilot artifact 重建机会分布、outcome、tail bucket 或 root-cause 数据。

**分类：artifact writer correctness bug。**

## 4. 问题分类汇总

### Audit correctness bugs

1. artifact 缺少 commit/branch/evidence/source/gate/schema provenance；
2. Phase A/B1/B2 source 语义混淆，final metrics 缺少独立 B1 区块；
3. standalone opportunity/tail writer 丢失实际 source；
4. `NOT_READY + reasons=[]`；
5. Contract failure 只记录计数，无法复核失败原因；
6. 非 Tail 场景可被标成 UNKNOWN_ROOT_CAUSE。

### Runtime execution gaps

1. 没有 Tail Repair Executor；
2. 没有 Tail Repair 的 MiMo → compile → validate → rescore → accept/rollback 闭环；
3. 没有统一 opportunity intervention trace；
4. 已有 RepairAttempt ledger 不能覆盖 Tail root-cause 级字段与完整 before/after/rollback 证据。

### Metric semantic bugs

1. detector 把候选直接算 eligible，缺 Eligibility V2；
2. entry/exit、scene button、dialogue pressure 规则证据不足；
3. evidence_refs 不能精确指向真正触发字段；
4. UCA V2 把 VALID_SKIP 留在分母；
5. Creative Value 使用任意正向维度 delta，未按推荐维度做因果归因；
6. root cause primary 由固定代码顺序决定；
7. 没有 conversion funnel、UCA V3 和 patch-level contract metrics。

### Model quality issues

1. B2 质量双峰且 14 个场景低于 60，显示部分输入下模型输出仍偏模板化/低价值；
2. B2 3 个场景出现大量 patch rejection，但缺乏可解释错误数据，当前不能把它们归因给模型还是契约 envelope；
3. 低情绪/信息策略覆盖与低 UCA 说明“机会 → 可执行干预”的提示与返回契约仍不足；
4. 这些是待通过 V2.4 修复链和对照实验验证的模型质量问题，不能用降低阈值解决。

## 5. 预计修改文件（编码阶段）

以下是按执行顺序的预期文件，不代表本轮已修改：

- `core/director_shadow_gate.py`：引入版本化 SSOT policy、final contract 100% 和结构化 reasons；
- `core/director_quality_provenance.py`（新增）：commit/branch/manifest/source/hash/gate/schema 元数据；
- `core/director_contract_failure.py`（新增）：ContractFailure taxonomy 与 patch-level aggregation；
- `core/director_patch_compiler.py`、`core/director_patch_validator.py`、`core/director_patch_repair.py`：单 patch 局部修复、错误保留和 final pass 统计；
- `core/director_opportunity_eligibility.py`（新增）：第二层 ELIGIBLE/NOT_APPLICABLE/REDUNDANT/WEAK_EVIDENCE/ALREADY_COVERED；
- `core/director_opportunity_detector.py`：修正 entry/exit、scene button、dialogue pressure 和 evidence refs；
- `core/director_intervention_trace.py`（新增）：Opportunity → Decision → Strategy → Patch → Compile → Validate → Apply → Delta；
- `core/director_creative_value.py`：版本化 dimension attribution、UCA V3、ACT realization 和 address rate；
- `core/director_tail_root_cause.py`：severity ranker V2 与非 Tail NOT_APPLICABLE；
- `core/director_tail_repair.py`、`core/director_tail_repair_executor.py`（新增）：最小修复上下文、预算、目标范围和回滚；
- `core/repair_ledger.py`、`models/repair.py`：补齐 Tail RepairAttempt 字段/JSON envelope；
- `scripts/run_director_quality_v2_4_tail_repair_pilot.py`（新增）：冻结 B2、只跑触发 Tail 场景；
- `scripts/run_director_quality_v2_4_full_pilot.py`（新增）：仅在 targeted pilot 达标后使用；
- `scripts/finalize_director_quality_v2_4_report.py`（新增）：完整 funnel、success/tail、provenance 和 gate decision；
- 对应 unit/integration/regression tests；
- V2.4 artifacts，不覆盖 V2.3 artifacts。

## 6. 测试方案

编码前必须先加入 provider-free 测试：

1. provenance source correctness、POSIX path、hash、commit/branch；
2. gate reasons 非空和阈值单一来源；
3. ContractFailure taxonomy；
4. `19 valid + 1 invalid` 只修 invalid patch，失败则 baseline fallback，场景最终 pass；
5. eligibility 状态、entry/exit presence、scene button、dialogue pressure、精确 evidence refs；
6. recommended dimension → scorer dimension 因果归因；
7. VALID_SKIP、ACT Realization、Opportunity Address Rate、UCA V2/V3；
8. root cause severity ranking 和非 Tail NOT_APPLICABLE；
9. Tail Executor 的 scope、attempt budget、compile/validate/rescore、accept/rollback、ledger；
10. complete intervention trace 和 conversion funnel；
11. success/tail comparison；
12. B2 frozen candidate → mocked Tail Repair integration，确保不触发任何生产/媒体/存储副作用；
13. 全量历史回归保持不退化。

在所有测试通过前，不允许真实 MiMo。真实调用顺序必须是：Targeted Tail Pilot → 评估 → 若未证明价值则停止；只有证明价值后才可执行 Full 24 Pilot。两轮都禁止生图、视频、对象存储、Production Shadow 与 Production Storyboard 写入。

## 7. Targeted Tail Pilot 方案

1. 冻结 B2 evidence 和 B2 candidate，不重新运行 first-pass planner；
2. 选择 B2 中约 15 个 `tail_repair.triggered=true` 场景；
3. 对每个场景执行 Root Cause Ranker V2，最多选择 2 个高严重 root causes；
4. 每个 root cause 最多 2 次 MiMo repair attempt；上下文只包含 root cause、目标维度、相关机会/beat/shot、strategy 子集、immutable contract 子集、validator findings、previous intervention；
5. 每次 repair 必须经过 patch compile、contract validation、quality validation、rescore；
6. 只有同时满足 contract pass、fact override=0、目标维度正向 delta、无重大 DQ/CV 回退、无新 structural blocker、over-directing/shot inflation 受控，才接受；否则 rollback；
7. 每场输出 Before/After DQ、CV、delta、root cause、scope、attempts、contract status、target dimension、accepted/rollback、ledger ids；
8. Targeted gate 观察目标：execution coverage 100%（除非有明确 non-repairable reason）、success ≥80%、DQ/CV mean delta ≥+15、fact override=0、new blocker=0。若未证明价值，停止，不执行 Full 24。

## 8. 审计结论

V2.3 已完成机会发现、策略覆盖、价值评估和安全隔离的第一版链路，但 B2 结果显示真正缺口在“价值干预的可执行闭环”与“证据/指标的可审计性”：Tail Repair 当前只计划不执行，Contract 失败不可解释，eligible/UCA/causal attribution 仍有语义问题，provenance 和 NOT_READY reasons 也不完整。

因此 V2.4 的第一个编码阶段应从 Artifact/Provenance 与 Gate correctness 开始，随后按 Contract Local Repair → Eligibility → Intervention Trace → Funnel/UCA V3 → Root Cause Ranker → Tail Executor 的顺序推进。任何修复都必须通用化，不得写 book/scene 特例；在 Targeted Tail Pilot 证明价值前，不得重跑 24 场景或开启 Shadow。

**审计结论：Step 1 Repository Audit 已完成。随后已按顺序完成 Step 2 Artifact/Provenance correctness 与 Step 3 Gate reason/threshold SSOT 的第一版实现；其余 V2.4 milestone 仍未宣称完成。**

### Step 2/3 执行检查点

- 新增 `core/director_quality_provenance.py`，并将 provenance envelope 接入 B1/B2 runner；模型 profile 经过 secret redaction，source path 为 repo-relative POSIX。
- 最终 metrics writer 现在区分 `phase_a`、`phase_b1`、`phase_b2`，并保留独立 source path；standalone opportunity/tail writer 保留实际 source 数据。
- `core/director_shadow_gate.py` 引入版本化 policy 与结构化 `reasons`；Contract final pass threshold 保持 `1.0`，未降低任何门槛。
- 新增 `core/director_contract_failure.py`，并将 compiler/validator/B1 runner 接入稳定 ContractFailure category 与 patch-level 首次/最终通过率字段；未放宽任何事实边界。
- 定向测试：`22 passed`；Step 2/3/4 touched Python compileall 通过；Step 3 收口后的全量回归：`940 passed`。

## 9. Final As-Built Verification（本地闭环）

本节与上文 Baseline Audit 分开记录，避免把“发现的问题”和“已实现的修复”混为一谈。

### 已落地并验证

- `core/director_contract_local_repair.py`：字段级局部契约修复，最多 2 次尝试，失败回退 baseline；
- `core/director_opportunity_eligibility.py`：第二层资格判定与完整状态统计；
- `core/director_intervention_trace.py`：Opportunity → Decision → Strategy → Patch → Compile → Validate → Apply → Measure；
- `core/director_conversion_funnel.py`：逐层计数、比例和 drop reason；
- `core/director_creative_value.py`：版本化维度归因与 UCA V3；
- `core/director_tail_root_cause.py`：证据加权 Root Cause Ranker V2 与非 Tail `NOT_APPLICABLE`；
- `core/director_tail_repair_executor.py`、`core/director_tail_repair_acceptance.py`：最小上下文、范围、预算、rescore、accept/rollback；
- `core/repair_ledger.py`：Tail Repair V2.4 运行元数据；
- `core/director_quality_v24_pipeline.py`：将上述模块串为 provider-neutral scene pipeline；
- `scripts/run_director_quality_v2_4_offline_replay.py`：从冻结 B2 产物生成可回放审计报告；
- `scripts/run_director_quality_v2_4_targeted_tail_pilot.py`：15 个 Tail 场景的严格 preflight 与显式授权边界。
- Targeted Pilot 结果契约已补齐逐场景 Before/After DQ、CV 测量边界、目标维度前后值、delta、最终 contract 状态及 accepted/rollback 列表；CV 未重放时明确标记 `not_replayed_after_tail_repair`，不伪造价值提升。

### 本地证据

- 全量回归：`974 passed, 890 warnings`；本轮 V2.4 定向专项：`17 passed`；
- V2.4 专项与离线回放测试：全部通过；
- 离线回放场景数：24；
- Shadow Gate：`NOT_READY`，结构化 reasons 非空；
- 副作用：production/storyboard/media/object_storage/production_shadow 均为 0；
- 旧 B2 仅保留拒绝数量而未保留字段级错误，因此回放报告将 20 条拒绝标记为 `UNKNOWN_CONTRACT_FAILURE`，没有伪造具体 path 或原因。

### 尚未完成（不得误报为完成）

- Targeted Pilot 的默认输入已在 `c7812d0` 修正为带 provenance 的 `artifacts/director-quality-v2-4-b2-freeze.json`；历史 V2.3 pilot 仍可通过 `--pilot` 显式指定，仅用于审计/回放。最新 provider-free preflight 已选中 15 个 Tail 场景且不再误报 `SOURCE_PROVENANCE_MISSING`。
- Targeted Tail Real MiMo Pilot 尚未执行；最新 provider-free preflight 已使用模型管理中的 `local-llm-2vydoz`（`mimo-v2.5`），选中 15 个 Tail 场景，`ready_for_confirmation=true` 且无阻塞码。真实调用仍必须经过用户显式确认；
- 因 Targeted Pilot 尚未证明修复价值，不能执行 Full 24 V2.4 Pilot，也不能开启 Production Shadow；
- Final Report 与 Shadow Gate 最终决策仍需在 Targeted Pilot 完成后生成。

### Targeted Tail Real MiMo Pilot（2026-09-14）

- 已按用户显式确认执行，结果见 `artifacts/director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json` 与配套报告；
- 15/15 场景执行，Execution Coverage `100%`，但 Success Rate `0%`，DQ 平均变化 `0`，CV 未重放；所有模型输出因不符合 `director_creative_patch_v1` 顶层契约而被拒绝并回退；
- 失败原因主要是模型返回描述性/自定义结构而非白名单 envelope（53 次 forbidden fields，1 次 target dimension 未改善）；没有事实覆盖接受或生产/媒体/存储副作用；
- 依据计划已 STOP：不得执行 Full 24、不得开启 Production Shadow、不得自动重试真实 MiMo。若要重试，需先完成结构化输出与调用观测补强，并重新取得显式确认。
