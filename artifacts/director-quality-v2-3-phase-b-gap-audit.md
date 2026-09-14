# Director Quality V2.3 Phase B — Repository Audit

审计日期：2026-09-14  
分支：`codex/unify-formal-workspace`  
基线：远程与本地 `99f9f1693c0d8af169e626518238668672cb8220` 一致。

## 审计范围与约束

本审计只读取当前实现、测试和 Phase A artifacts；没有修改业务代码，没有调用 MiMo/生图/视频/对象存储，也没有进入 Production Shadow。Phase A artifact 保留不变。

审计对象：

- `core/director_creative_planner.py`
- `core/director_creative_contract.py`
- `core/director_patch_compiler.py`
- `core/director_patch_validator.py`
- `core/scene_directing_strategy.py`
- `core/director_quality_validator.py`
- `core/director_quality_metrics.py`
- `core/director_quality_trace.py`
- `core/director_benchmark.py`
- `core/local_repair.py`
- `core/qualification_loop.py`
- `scripts/run_director_quality_v2_3_mimo_pilot_authorized.py`
- `core/director_quality_v23_benchmark.py`
- Phase A artifacts listed below

本地回归基线：`873 passed`（仅既有弃用/测试告警）。

## Phase A 结果基线

权威样本：`artifacts/director-quality-v2-3-smoke-pilot-20260913T213216Z.json`。

- 真实 MiMo 模型：`mimo-v2.5`
- 场景数：12
- Contract Pass：12/12（100%）
- Fact Override Accepted：0
- Unknown Root Cause：0
- Director Quality Mean：79.3925
- Director Quality Median：89.6
- MiMo calls：28（含 planner/repair）
- Cached tokens：27,136；Cache hit rate：22.4313%
- Production / Storyboard / Media / Object Storage side effects：均为 0
- 场景状态：8 `valid`、4 `partial`；`partial` 表示创意候选部分接收，不等于结构 Contract 失败

按 after-repair Director Quality 的当前 12 场景分布（近似最近秩分位数）：

| 指标 | 数值 |
|---|---:|
| Min | 29.86 |
| P10 | 52.40 |
| P25 | 52.49 |
| Median | 89.60 |
| P75 | 92.20 |
| P90 | 94.80 |
| Max | 94.80 |

最低三个样本为：

1. `book990402:e2:...` — 29.86
2. `book990402:e3:...` — 52.40
3. `book990402:e3:...` — 52.49

（artifact 中部分中文 scene name 已因历史编码显示为替换字符；scene_id、分数和 trace 仍可复核。）

结论：存在明显 long-tail。Mean 已接近目标，但 P10/Min 远低于 Shadow Gate，不能用平均分掩盖尾部风险。

## 当前实现审查

### 1. Creative planner / contract / compiler

现有 `director_creative_contract.py` 已建立事实不可变投影、可编辑字段白名单、JSON Pointer 路径和有界 auxiliary shot 策略；`director_creative_planner.py` 及 patch compiler/validator 能保持 beat、镜头顺序、资产绑定、动作和连续性等事实不被创意层覆盖，并对外部 LLM 调用实施 `confirmed && allow_external_call` 门槛。这部分是 Phase A 的安全基础，Phase B 不应放宽。

现有 planner 只接收 Strategy 或直接处理 provider patch；它没有“机会对象”输入，也没有要求每个 eligible opportunity 输出 `ACT` 或 `SKIP_WITH_REASON`。因此模型并不知道哪些导演介入机会真正值得处理，静默漏掉机会也无法区分。

现有 auxiliary proposal 允许受限的 reaction/insert/establishing/transition/detail 类型，但不产生机会级证据、优先级、结果和价值增益记录。

### 2. Scene Directing Strategy

`scene_directing_strategy.py` 已有 V2 beat-bound 字段：`performance_arc`、`rhythm_curve`、`emotion_curve`、`information_plan` 和 camera language，并验证 beat/character 引用。

但当前 V2 builder 是保守的确定性映射：按 beat type 赋默认 pace、情绪强度、信息计划和通用表演描述。它没有读取/输出 CreativeOpportunity，也没有区分适用与不适用策略；因此会为每个 beat 生成策略条目，即使该 beat 没有相应导演机会。

### 3. Edit Strategy 当前检测

当前 `build_director_quality_v23_coverage_metrics` 的 `_valid_edit` 只要求 `cut_reason` 非空且 duration 为正数；分母是全部 shots。现有质量 validator 主要检测镜头动机、相机重复和冗余镜头，没有以下 Phase B 代码：`EDIT_STRATEGY_MISSING`、`UNMOTIVATED_CUT`、`REACTION_CUT_TOO_EARLY/LATE`、`RHYTHM_FLATLINE`、`SCENE_BUTTON_MISSING`、`OVER/UNDER_CUTTING`。

因此当前 `edit_strategy_coverage=0.6136` 是字段存在率，不是 eligible opportunity coverage，也不是剪辑决策有效率。

### 4. Emotion Arc 当前检测

当前 `_valid_emotion` 只检查 `shot.emotion.intensity` 是 0–10 数值；`_emotion_progression_consistency` 只比较 strategy 与 shot intensity 是否接近，并在单点曲线时返回 unavailable。没有 rise/fall/plateau/spike/release 结构、峰值可视化、无动机跳变或 reaction performance 支撑检查。

因此当前 `emotion_arc_coverage=0.772` 不能回答“有情绪机会的 beat 是否被有效导演化”。

### 5. Information Strategy 当前检测

当前 `_valid_information` 只检查 `reveals/withholds/audience_focus` 任一字段非空；Strategy V2 的 `information_plan` 由 beat event/information_change 生成。没有 `known_to_audience/withheld/reveal_plan/reaction_priority` 的机会级绑定，也没有 `EARLY_REVEAL`、`LATE_REVEAL`、`REVEAL_WITHOUT_SETUP`、`MISSING_REACTION_TO_REVEAL`、`AUDIENCE_FOCUS_CONFLICT` 等校验。

因此当前 `information_strategy_coverage=0.772` 同样是字段覆盖，不是信息机会处理率。

### 6. Useful Creative Acceptance 当前计算

当前 `build_director_quality_v23_coverage_metrics` 以 `accepted_patch_document.patches` 与 `proposed_patch_document.patches` 的 shot id 交集为基础，再按修改根字段是否产生有效字段计数；分母是 proposed patch 数量。它没有 opportunity id，也没有同时要求：ACT、合法、最终应用、至少一个 Director Quality 维度正向增益、无新 blocker、无 Fact/Contract 违反。

Phase A provider 输出中存在完整 shot/auxiliary envelope 与部分 patch 形态差异，当前统计在该 artifact 中为 `useful_creative_acceptance_rate=0.0`。这既暴露真实价值不足，也暴露了旧指标无法区分“无机会”“机会被跳过”“patch 被接受但无测量增益”和“统计输入不对齐”。Phase B 必须新增 V2 指标并保留旧指标供回归对照，不修改历史 acceptance 规则。

### 7. Eligible 与 non-applicable

当前 trace taxonomy 有 `NOT_APPLICABLE`，但它表示某个 shot × dimension 没有可追踪信号；不是由证据包推导的“该场景确实不存在此类机会”。当前 performance 使用 key-shot 启发式分母，edit 使用全部 shots，emotion/information 使用 strategy entries，三者分母语义不一致。

审计结论：当前没有可靠的 `eligible_opportunity` / `non-applicable` 机制，必须新增证据驱动的 Opportunity Detector 和明确分母。

### 8. Planner 是否知道哪里值得介入

否。Planner 目前知道 approved beat 和 Strategy 条目，但没有 opportunity_id、reason、evidence_refs、priority，也不要求显式 ACT/SKIP_WITH_REASON。高优先级机会可以被静默忽略，无法形成 `MISSED_OPPORTUNITY`。

### 9. 场景级 Opportunity 模型

不存在 `core/director_opportunity_detector.py` 或等价的场景级机会模型。现有质量 trace 是 shot × dimension 的事后诊断，不能替代机会发现。

### 10. Local Repair

`core/local_repair.py` 和 `qualification_loop.py` 支持按 validator issue 应用通用 JSON patch、记录前后指纹、回滚候选和有限 attempts；它们不是 Phase B Tail Repair：没有按 root cause 路由，只修 edit/emotion/information/漏机会对应的最小子空间，也没有“最多 2 attempts / root cause”的独立预算与成功率统计。现有 Phase A 的 LLM repair 主要修 schema/value，不是创意价值尾部修复。

## Gap 清单（按 Phase B 执行顺序）

| Gap | 当前状态 | Phase B 必须交付 |
|---|---|---|
| Opportunity model/detector | 缺失 | 证据驱动 `CreativeOpportunity[]`，至少覆盖规范中的机会类型 |
| Eligible / non-applicable | 缺失/语义不一致 | 明确 eligible denominator、valid skip、missed opportunity |
| ACT / SKIP contract | 缺失 | 每个 eligible opportunity 必须显式决策与理由 |
| UCA V2 | 缺失 | opportunity-level value acceptance 与 outcome |
| Edit Strategy V2 | 仅 cut_reason+duration | cut/hold/reaction/rhythm/scene button 及 validator |
| Emotion Arc V2 | 仅 intensity | arc 形状、峰值、反应支撑及 validator |
| Information Strategy V2 | 仅字段存在 | reveal/withhold/setup/focus 及 validator |
| Creative Value Score | 缺失 | 与 Director Quality 分离的 0–100 分数 |
| Tail distribution/root cause | 仅 mean/median 等基础统计 | min/P10/P25/median/P75/P90/max、bucket、root cause |
| Tail Repair | 缺失 | 按低分 root cause 的局部修复，2 attempts/root cause |
| Over-directing / shot inflation | 仅相机重复/冗余诊断 | 专门检测与受控阈值 |
| Phase B metrics/report | 缺失 | B1/B2 artifacts、完整 gate 报告 |

## 本轮修改文件清单

本审计阶段实际只新增本文件，未修改业务代码。后续按步骤预计新增/修改（进入编码阶段前再次确认 diff）：

- 新增 `core/director_opportunity_detector.py`
- 修改 `core/scene_directing_strategy.py`、`core/director_creative_contract.py`（仅增补机会引用/决策契约，不放宽事实边界）
- 修改 `core/director_creative_planner.py`、`core/director_patch_compiler.py`、`core/director_patch_validator.py`
- 修改 `core/director_quality_metrics.py`、`core/director_quality_validator.py`、`core/director_quality_trace.py`
- 新增/修改 `core` 中的 Phase B value/tail/repair 模块
- 新增对应 unit/integration/regression tests
- 新增 Phase B runner/report artifacts；不覆盖 Phase A artifacts

## Migration 判断

Phase B1/B2 的机会、outcome、tail 指标可作为只读 pilot JSON artifacts 保存，不需要数据库 migration。若未来将 opportunity outcome 持久化到生产数据库，应采用新增 JSON/audit 字段的显式迁移；本阶段不做该迁移，也不写入 Production Storyboard。

## Phase B Pilot 样本计划

严格分两阶段：

1. **B1（12 场景）**：用于 Opportunity Detector、eligible denominator、ACT/SKIP、UCA V2、Tail Repair 和指标链路 smoke；只在 Unit/Integration/Regression 全部通过后，且用户再次明确授权时调用真实 MiMo。
2. **B2（≥24 场景）**：使用现有 approved scenes、18 个 Golden scenes、已存在 fixtures 的并集去重；必须覆盖双人/多人对话、悬疑、信息揭示、情绪爆发/压抑、权力反转、入场/退出、关键道具、无对白、快动作/慢节奏、空间隔离、reaction-heavy、reveal-heavy。不得新写 book 特例，不调用媒体供应商。

两阶段均只写 Phase B pilot artifacts，禁止写 Production/Storyboard/Media/Object Storage。Phase A artifact 不覆盖。

## Shadow Gate 建议

当前安全门可判定为 PASS：Contract Pass 100%、Fact Override Accepted 0、Unknown Root Cause 0、无生产/媒体/存储副作用。但价值门仍为 NOT_READY：Phase A Mean 79.3925 < 80，P10 52.40 < 70，Min 29.86 < 60，且当前 UCA 与三项策略覆盖的语义尚未达到 Phase B 定义。

Phase B 必须以规范阈值重新计算并只输出三态之一：`NOT_READY`、`SAFE_BUT_NOT_VALUABLE`、`VALUABLE_ENOUGH_TO_SHADOW`。即使达到最后一态，也不得自动开启 Shadow 或进入 Media Pilot。

## Baseline Audit 结论

Phase A 已证明事实/契约安全和 provider 调用隔离有效，但没有证明“模型能发现并完成有价值的导演介入”。下一步必须从 Step 2 Opportunity Model 开始，先建立证据驱动机会对象，再逐步接入 Planner、价值评估和尾部修复；不得通过提高 Contract Pass、降低阈值、硬编码镜头或修改历史 acceptance 规则来制造价值门通过。

## Final As-Built Verification（Phase B2 完成后）

核验日期：2026-09-14  
权威 B1 artifact：`artifacts/director-quality-v2-3-phase-b1-pilot-20260914T030654Z.json`  
权威 B2 artifact：`artifacts/director-quality-v2-3-phase-b2-pilot-20260914T040506Z.json`

本节只记录已完成实现与真实灰度结果，不回写或覆盖 Baseline Audit 的历史判断。

### 执行完整性与安全隔离

- B2 场景数：`24/24`，场景 ID 唯一数 `24`；每个场景恰好 1 次 planner 调用，telemetry 总调用 `24`。
- 模型：`mimo-v2.5`（profile `local-llm-2vydoz`）；HTTP `200`、解析成功 `24/24`、重试 `0`。
- B2 真实 MiMo 调用只产生机会/策略候选与审计记录；未写入 Production/Storyboard/Media/Object Storage。
- 汇总副作用：`production=0`、`storyboard=0`、`media=0`、`object_storage=0`。
- `production_shadow.enabled=false`，未自动开启 Shadow。
- `unknown_root_cause_count=0`，`missed_opportunity_count=0`；机会决策均有可验证记录。

### B2 指标结果

| 指标 | B2 结果 | Shadow Gate 目标 | 判定 |
|---|---:|---:|---|
| Contract Pass Rate | 0.8750 | ≥ 0.95 | 未达标 |
| Director Quality mean / median / P10 / min | 62.8513 / 50.3 / 28.45 / 28.39 | 80 / 85 / 70 / 60 | 未达标 |
| Creative Value mean | 60.4852 | ≥ 75 | 未达标 |
| Useful Creative Acceptance | 0.1568 | ≥ 0.75 | 未达标 |
| Edit / Emotion / Information eligible coverage | 0.2522 / 0.0392 / 0.1452 | 0.80 / 0.85 / 0.85 | 未达标 |
| Opportunity detection coverage | 0.9583 | 需完整且可解释 | 通过观测 |
| Over-directing / shot inflation | 0.0069 / 0.0000 | ≤ 0.10 / ≤ 0.50 | 通过 |
| Tail repair trigger / attempted | 0.6250 / 0 | — | 仅触发，尚未执行修复 |
| Cache hit rate | 0.7274 | 观测项 | 已记录 |

### Final As-Built 结论

Phase B 的机会发现、策略覆盖、价值评估、尾部分类、审计与副作用隔离链路已经按计划落地，并完成 B1（12 场景）与 B2（24 场景）真实 MiMo 灰度。结果证明安全边界和指标链路可运行，但价值门未通过：Contract、Director Quality、Creative Value、UCA V2 及三类策略覆盖均低于 Shadow Gate 阈值。因此最终状态保持 **`NOT_READY`**，不得开启 Production Shadow，也不得进入媒体生产灰度。

后续应优先处理通用的契约失败、创意价值接受率、策略覆盖和 Tail Repair 执行链路，再进行新的离线/真实灰度；不得针对特定 book 或场景写特例，也不得用降低阈值替代质量改进。
