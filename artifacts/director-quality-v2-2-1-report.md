# Director Quality V2.2.1 Final Local Closure Report

**Pilot artifact:** `artifacts/director-quality-v2-2-1-mimo-pilot-20260913T161906Z.json`  
**Metrics:** `artifacts/director-quality-v2-2-1-metrics.json`  
**Scope:** the same 12 frozen Stage-A scenes, real MiMo `mimo-v2.5`, benchmark-only.  
**Production Shadow:** OFF.

## 1. Executive Summary

V2.2.1 的安全闭环已经落地并完成 12 场真实 MiMo Pilot：最终 Contract Pass 为 12/12，Fact Override Accepted 为 0，未写入生产/Storyboard，也没有图片、视频或对象存储调用。Canonical Path Resolution 为 477/477，Repair Contract Pass 为 8/8。

但本轮没有达到 Production Shadow 门槛：fallback 13 个（14.29%）、创意保留 46.15%、Full Creative Scene Success 66.67%、Director Quality 58.77、缓存命中 12.32%、平均延迟 19.77 秒。因此结论为 **NOT_READY_FOR_PRODUCTION_SHADOW**，不扩容 Stage B，不进入媒体生产。

## 2. 为什么 V2.2 出现 Repair ↓ 但 Fallback ↑

同一组 12 场景的证据显示：V2.1 为 33 次 repair / 15 个 fallback，V2.2 降至 14 次 repair 但 fallback 升至 27 个，创意保留为 78.29%。这说明“减少 repair 调用”并没有减少创意损失。V2.2.1 进一步将 repair 降至 8 次、fallback 降至 13 个，但创意保留仍降至 46.15%。因此 repair 数不是单独的优化目标，必须和合法创意保留、fallback 原因一起看。

## 3. V2.2 的 27 个 fallback root cause

Step-1 审计已逐条覆盖 F01–F27。原 V2.2 artifact 没有保存 raw patch、raw path、normalized path、shot identity 或 repair 原文，因此这些字段在审计中明确标为 `NOT_CAPTURED`，没有从 digest 反推：

| Root cause | 数量 | 占比 | Level 0/1 | 是否真正需要 LLM | 安全结论 |
|---|---:|---:|---|---|---|
| `FORBIDDEN_PATH / DIRECTOR_PATCH_FIELD_FORBIDDEN` | 17 | 62.96% | 可在无歧义且命中白名单时恢复 | 否 | 条件性可恢复技术问题 |
| `LLM_REPAIR_CONTRACT_FAILURE / INVALID_PATCH_VALUE` | 10 | 37.04% | 需先补齐 repair 原文后判断 | 可能 | 不能臆判为安全或可恢复 |

未发现事实越权、未知 shot、未绑定 auxiliary 被接受。审计原文见 `director-quality-v2-2-1-gap-audit.md`。

## 4. Path Resolver 改造

新增唯一 `core/director_patch_path_resolver.py`，统一处理 slash、dotted、shot-id prefix、numeric selector、wildcard 和字段 alias。流程固定为 Parse → Canonical Candidate → Allowed Path Check → Accept；歧义和越权 fail-closed。Planner、Normalizer、Deterministic Repair 和 RepairReplacement 均复用该模块。

V2.2.1 Pilot：477 次解析、477 次成功、0 次失败、110 次 alias 命中，成功率 100%。这证明 resolver 本身达到门槛，但 provider 仍产生 13 个最终 `FORBIDDEN_PATH` fallback，说明这些输出尚未都能被当前证据安全映射，不能把它们自动算作已恢复。

## 5. Repair Contract 改造

Repair 输出收窄为 `director_patch_repair_v1` 的 target + replacement_value。程序锁定 `plan_shot_id` 和 path；禁止返回 `patches[]`、完整 scene/ShotPlan 或修改目标。多字段 repair 必须显式提供 `allowed_repair_paths`，且最多两次 LLM 尝试。旧 V2.1 runner 使用显式兼容开关，不改变 V2.2+ 的严格契约。

Pilot 中 8 次 repair 全部通过，`repair_success_rate=100%`，失败 0；没有因 repair contract 失败而产生新的 fallback。

## 6. Creative Recovery 模型

流水线为 Raw → Normalization → Deterministic Recovery → Contract Validation → Minimal Repair → Validated Patch → Fallback。V2.2.1 的 `creative_recovery_rate=100%` 表示进入“可恢复创意”分母的项目均被安全恢复；这不等同于整体创意保留，因为 13 个 path fallback 在进入该分母前已被判定为不可安全接受。整体 `creative_retention_rate=46.15%`，所以不能据此宣称质量已恢复。

## 7. Safe vs Avoidable Fallback

本次 V2.2.1 artifact：`SAFE_REQUIRED_FALLBACK=0`，`AVOIDABLE_TECHNICAL_FALLBACK=13`。13 个均为 `FORBIDDEN_PATH`，分布在 4 个场景（2、2、6、3）。由于 fallback 记录仍缺少 raw path/shot identity，报告将其保留为“可避免候选”，不把未知事实强行归类为可恢复。

## 8. Cache regression root cause

代码侧已将 Planner Prompt 固定为 SECTION 1–7，并记录 `stable_prefix_hash`、`stable_prefix_length`、`variable_tail_hash`；Repair Prompt 也拆为稳定前缀与变量尾部。Pilot 结构化 telemetry 完整，但供应商返回的 cache hit 只有 12.3246%，低于 V2.1 的 79.0694% 和 V2.2 的 46.0539%。当前证据只能证明“布局已稳定、运行时命中仍低”，不能把原因归结为单一 prompt 字段或未经官方支持的 cache 参数。

## 9. Prompt prefix restoration

已恢复稳定前缀：角色、不可变契约、allowed paths、CreativePatch schema、Auxiliary schema、质量规则、输出规则均不插入 scene/book/shot 动态字段。变量数据统一放在 user tail；repair 的失败 patch、issue、target、allowed paths 和最小 strategy 位于变量尾部。所有 Pilot 记录都含稳定前缀与变量尾部 hash。

## 10. V2.1 / V2.2 / V2.2.1 A/B

| 指标 | V2.1 | V2.2 | V2.2.1 | 相对 V2.2 |
|---|---:|---:|---:|---:|
| Planner Calls | 12 | 12 | 12 | 0 |
| Repair Calls | 33 | 14 | 8 | -6 |
| Final Contract Pass | 12/12 | 12/12 | 12/12 | 0 |
| Fallback Count | 15 | 27 | 13 | -14 |
| Fallback Patch Rate | — | 20.93% | 14.29% | -6.64pp |
| Avoidable Fallback | — | — | 13 | — |
| Creative Retention | — | 78.29% | 46.15% | -32.14pp |
| Creative Recovery | — | — | 100% | — |
| Full Creative Scene Success | — | 75% | 66.67% | -8.33pp |
| Director Quality | 56.98 | 58.70 | 58.77 | +0.07 |
| Cache Hit | 79.07% | 46.05% | 12.32% | -33.73pp |
| Avg Latency | 12.25s | 17.19s | 19.77s | +2.58s |
| Prompt Tokens | 151,037 | 98,945 | 87,240 | -11,705 |
| Repair Tokens | 83,688 | 34,125 | 17,982 | -16,143 |

## 11. Director 10 维质量变化

以下为 12 场景平均维度（分数口径沿用现有 scorer）：

| Dimension | V2.1 | V2.2 | V2.2.1 | Δ vs V2.2 |
|---|---:|---:|---:|---:|
| DRAMATIC_CLARITY | 8.67 | 8.67 | 8.67 | 0.00 |
| SHOT_MOTIVATION | 1.67 | 7.77 | 6.67 | -1.10 |
| EMOTIONAL_PROGRESSION | 4.00 | 4.33 | 4.08 | -0.25 |
| VISUAL_STORYTELLING | 6.67 | 7.77 | 8.33 | +0.56 |
| SPATIAL_CLARITY | 10.00 | 10.00 | 10.00 | 0.00 |
| PERFORMANCE_DIRECTION | 0.00 | 0.00 | 0.00 | 0.00 |
| EDIT_RHYTHM | 1.53 | 1.53 | 1.53 | 0.00 |
| INFORMATION_STRATEGY | 0.00 | 1.08 | 2.75 | +1.67 |
| POWER_DYNAMICS | 6.75 | 8.00 | 8.00 | 0.00 |
| SHOT_DIVERSITY | 3.61 | 6.84 | 6.89 | +0.05 |

证据表明 V2.2.1 在 Visual Storytelling 和 Information Strategy 上有小幅改善，但 Shot Motivation 与 Emotional Progression 回落；整体质量几乎没有恢复到目标线。

## 12. Creative Retention

V2.2.1 为 46.15%，低于 V2.2 的 78.29% 和目标 92%。这不是因为非法 patch 被接受：Fact Override 和 unknown shot 仍 fail-closed。主要可确认事实是 13 个技术 fallback 仍从候选结果中丢失，且旧 V2.2 的 27 个 fallback 中有 10 个 repair 原文不可观测。

## 13. Creative Recovery

可恢复分母内的 recovery 为 100%，但 `creative_patches_saved_by_llm_repair=0`、`fallbacks_prevented_by_repair=0`。也就是说当前成功恢复主要来自 path normalization/deterministic stages；LLM repair 没有在本样本中额外挽回创意 patch。

## 14. Repair Success Rate

8/8 repair 成功，成功率 100%，失败 0，平均每次成功 repair 2,368.5 tokens、6,217ms。该结果满足 Repair Contract 门槛，但调用次数减少并未转化为整体质量提升。

## 15. Repair Cost

V2.2.1 共 20 次 provider call（12 planner + 8 repair），总 prompt tokens 87,240；repair prompt tokens 17,982。相对 V2.2 少 6 次 repair、少 11,705 prompt tokens，但平均延迟增加 2,584.85ms。

## 16. Cache

稳定前缀 hash/length、变量尾部 hash 均已写入每次调用 telemetry；实际 cache hit 12.3246%。在没有官方 cache 参数和供应商端命中明细的情况下，不做进一步猜测，也不把低命中率通过权重或指标口径掩盖。

## 17. Latency

平均延迟 19,774.69ms，超过 13,000ms 门槛。Pilot 期间没有重试（retry_count=0），因此延迟不是重试膨胀造成的可见结果；是否由供应商排队、输入长度或缓存未命中导致，当前 artifact 不足以单独证明。

## 18. 失败案例 Top 10

以下按 V2.2.1 artifact 顺序列出前 10 个失败记录。它们的 `plan_shot_id`、raw path 和 raw patch 在 provider 输出层仍未持久化，故明确标注 `NOT_CAPTURED`：

| 记录 | Scene | Issue | 最终动作 | 身份/路径 |
|---|---|---|---|---|
| F01 | book990402:e1:红伞幻影（一） | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F02 | book990402:e1:红伞幻影（一） | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F03 | book990402:e2:暗房门口的试探 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F04 | book990402:e2:暗房门口的试探 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F05 | book990402:e3:暗房惊魂 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F06 | book990402:e3:暗房惊魂 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F07 | book990402:e3:暗房惊魂 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F08 | book990402:e3:暗房惊魂 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F09 | book990402:e3:暗房惊魂 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |
| F10 | book990402:e3:暗房惊魂 | DIRECTOR_PATCH_FIELD_FORBIDDEN | REJECT_PATCH | NOT_CAPTURED |

## 19. 当前 Top 3 remaining blockers

仅列可由本轮证据支持的三项，未扩展成大重构：

1. **Provider path envelope 仍触发 fallback**：evidence_count=13，affected_patch_count=13，affected_scene_count=4，estimated_recoverable_patches=最多 13（需 raw path 验证），estimated_quality_gain=未估计，estimated_call_reduction=0。
2. **首轮候选/质量覆盖不足**：evidence_count=12 个 scene 评分，affected_patch_count=未由 artifact 稳定映射，affected_scene_count=12，estimated_recoverable_patches=未估计，estimated_quality_gain=至少需要把 58.77 提升至 70，estimated_call_reduction=不可从当前样本证明。
3. **供应商缓存命中仍低**：evidence_count=20 次调用，affected_patch_count=未适用，affected_scene_count=12，estimated_recoverable_patches=0，estimated_quality_gain=未估计，estimated_call_reduction=未估计；需要 provider-side cache 证据后再做小范围修复。

## 20. 是否建议 Production Shadow

**不建议，结论为 `NOT_READY_FOR_PRODUCTION_SHADOW`。**

通过：Final Contract Pass 100%、Fact Override 0、Auxiliary Unbound 0、Path Resolution 100%、Repair Contract 100%、Creative Recovery 100%。

未通过：Fallback ≤8%、Avoidable Fallback ≤2%、Creative Retention ≥92%、Full Creative Scene Success ≥85%、Director Quality ≥70、Quality Delta ≥+15、Cache Hit ≥70%、Average Latency ≤13s。

本轮不执行 Stage B 24 场、不进入 Production Shadow、不调用生图/视频/对象存储。下一轮应优先补齐 fallback 的 raw patch/path/shot identity 观测，再针对 13 个可避免候选做证据驱动的恢复验证。
