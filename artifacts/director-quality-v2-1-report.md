# Director Quality V2.1 Report

## Executive Summary

- 离线 Golden 场景：18 个。
- Contract Parse/Pass：100.0% / 100.0%。
- Director Quality 平均：43.99，相对 baseline 提升：0.0。
- 本报告未调用真实 LLM、MiMo、生图、视频或对象存储。
- 真实 MiMo 12-scene Pilot 按当前约束未执行，不能据此宣称 Production Shadow Candidate。

## V2 → V2.1 架构变化

Immutable Contract → Scene Strategy → CreativePatch/AuxiliaryProposal → Patch Compiler → Validator → Partial Acceptance → Patch-level Repair → Metrics。

## Contract Reliability

- Fact Override Attempt/Accepted：0 / 0。
- Auxiliary Unbound Accepted：0。
- Patch First/Final Success：100.0% / 100.0%。
- Partial Acceptance：0.0%；Local Repair Yield：0.0%。

## Director Quality 10维

| 维度 | 平均分 |
|---|---:|
| DRAMATIC_CLARITY | 9.11 |
| SHOT_MOTIVATION | 1.11 |
| EMOTIONAL_PROGRESSION | 4.0 |
| VISUAL_STORYTELLING | 7.78 |
| SPATIAL_CLARITY | 7.0 |
| PERFORMANCE_DIRECTION | 0.0 |
| EDIT_RHYTHM | 1.85 |
| INFORMATION_STRATEGY | 0.0 |
| POWER_DYNAMICS | 8.0 |
| SHOT_DIVERSITY | 4.07 |

- 当前较强维度：DRAMATIC_CLARITY, POWER_DYNAMICS, VISUAL_STORYTELLING。
- 当前较弱维度：PERFORMANCE_DIRECTION, INFORMATION_STRATEGY, SHOT_MOTIVATION。

## Baseline / First Candidate / Final Candidate

每个场景均保存三组候选及其十维分数；本离线样本 first/final 使用确定性 patch，未调用模型。

## MiMo Telemetry / Cache

- calls=0、cached_tokens=0、latency=0；这是离线约束下的真实记录，不代表线上缓存表现。

## Production Shadow Candidate

未达到/未评估：真实 MiMo Pilot 尚未执行，因此不能证明 V2.1 的真实 Contract Stability、Director Quality 或 Media Production Pilot V1 条件。

## Remaining Work

1. 在所有本地回归通过后，另行执行不少于 12 场景的真实 MiMo benchmark-only pilot。
2. 记录真实 parse/contract/repair/token/cache/latency 指标。
3. 满足双重门槛后再评估 Production Shadow；本阶段不切换 Production 默认。

## Auxiliary Shot Failures

离线样本未提交辅助镜头；source beat 未绑定提案不会被接受。

## Required Decision Answers

1. Creative Contract Success：离线 100%；真实 MiMo V2.1 尚未复测。
2. Fact Override：离线 attempt=0、accepted=0。
3. Auxiliary Unbound：accepted=0。
4. Partial Acceptance：已由集成测试证明单 patch 失败不会丢弃其他合法 patch。
5. Local Repair：只发送失败 patch，最多 2 次。
6. Director Quality：离线平均 43.99，未达到 70。
7. 真实提升最大维度：尚无真实 MiMo 证据。
8. 当前较弱维度：PERFORMANCE_DIRECTION, INFORMATION_STRATEGY, SHOT_MOTIVATION。
9. 过度运镜/切镜/shot inflation：合同和质量规则已覆盖，离线未新增镜头。
10. Token/latency/cache：本阶段调用为 0，不能比较线上变化。
11. Production Shadow Candidate：未达到/未评估。
12. Media Production Pilot V1：暂不进入，真实 12 场景证据缺失。

## Failure Cases / Bottlenecks

当前最大瓶颈是缺少真实 V2.1 多场景 LLM 输出、repair yield、token/latency/cache telemetry。

## Prompt Prefix Verification

- Prompt prefix fingerprints：1 个；request fingerprints：18 个。
- 固定前缀包含 Role、Director Contract、Output Schema、Allowed/Forbidden Paths、Auxiliary Policy、Quality Rules；场景证据采用规范化动态上下文。
- 每次候选请求输出 system/user/prefix fingerprint 与非敏感 model snapshot；未添加 provider-specific cache 参数。
- Patch schema 被拒绝时记录 schema_pass=false、schema_error_code 与 forbidden_field_attempt。
- 非致命 schema 错误按 patch/proposal 粒度部分接受；版本或 fingerprint 错误仍 fail-closed。

## Evidence Replay Readiness

每个 Golden 场景保存冻结、脱敏的 Treatment、SceneBlocking、Director Contract 与 Scene Strategy；Pilot preflight 会校验 evidence 完整性及 contract/strategy fingerprint 一致性。

## Authorized Pilot Runner

`scripts/run_director_quality_v2_1_mimo_pilot_authorized.py` 默认只运行 preflight；真实路径必须同时提供 `--execute-real`、精确 confirmation token 与显式 MiMo profile，且只写 benchmark artifact，不写生产数据。

## Offline Pilot Replay

mock LLM 回放测试覆盖 12 个冻结场景；逐场景执行与零生产副作用均通过。该结果不计入真实 MiMo 指标。

## Artifact Safety

V2.1 Golden、metrics 和 report 不保存 API key、Bearer token 或 provider credential；运行器仅输出非敏感模型快照与 fingerprint。

## Blind Review Readiness

受控 Pilot 为每个场景生成匿名化 Version A/B 盲审包，默认不填写偏好、不调用 Judge；真实偏好必须由独立评审记录。
盲审 payload 不包含预计算的 `director_quality` 分数，避免候选强弱泄漏；分数仅保留在非盲 benchmark artifact。

## Contract-First Planner Design

Approved Structural ShotPlan → Immutable Director Contract → Scene Directing Strategy → CreativePatch/AuxiliaryShotProposal → Deterministic Patch Compiler → Authority/Quality Validator → Partial Acceptance → Patch-level Local Repair。LLM 只能提出创意 patch，不能写入事实或生产对象。

## CreativePatch and Auxiliary Schemas

CreativePatch 使用 `director_creative_patch_v1`，每个 patch 以 plan_shot_id + path-to-value changes 定位；辅助镜头使用独立 proposal，必须绑定 source_beat_id、insert_after_plan_shot_id、批准参与者和动机。

## Immutable Fields

`scene_id, scene_name, plan_shot_id, beat_id, beat_order, event, dialogue, participants, action_beats, entry_state, exit_state, asset_bindings, prop_ownership, continuity_contract, continuity, spatial_source, source_facts, plot_result, chronology`

## Allowed Patch Paths

- `/shots/*/camera/shot_size`
- `/shots/*/camera/angle`
- `/shots/*/camera/movement`
- `/shots/*/camera/speed`
- `/shots/*/camera/camera_side`
- `/shots/*/composition/*`
- `/shots/*/composition`
- `/shots/*/why_this_shot`
- `/shots/*/dramatic_function`
- `/shots/*/emotion/*`
- `/shots/*/emotion`
- `/shots/*/performance_direction/*`
- `/shots/*/performance_direction/*/*`
- `/shots/*/performance_direction`
- `/shots/*/edit/*`
- `/shots/*/edit`
- `/shots/*/information_strategy/*`
- `/shots/*/information_strategy`
- `/shots/*/visual_emphasis`

## Contract Reliability Metrics

- Contract Parse/Pass：100.0% / 100.0%
- Fact Override Attempt/Accepted：0 / 0；Forbidden Field Attempt：离线 0（schema failure telemetry 已接线）
- Auxiliary Unbound Accepted：0
- Patch First/Final Success：100.0% / 100.0%
- Partial Acceptance：0.0%；Local Repair Yield：0.0%
- Deterministic Fallback：0.0%；Scene Planner Success：100.0%

## Blind Judge

未执行独立 Blind Judge；不得将离线结果称为 Human Preferred Rate。

## Pilot and Release Decision

真实 MiMo 12 场景 Pilot、token/latency/cache 实测尚未执行；当前不满足 Production Shadow Candidate，也不进入 Media Production Pilot V1。Production Pipeline V2 默认路径保持不变。

## Final As-Built Verification — Authorized MiMo Pilot（2026-09-13）

本节覆盖本轮最终实现；上文的离线 Baseline Audit 与历史“尚未执行”描述保留为历史记录，不作为本轮结果。

- Artifact：`artifacts/director-quality-v2-1-mimo-pilot-20260913T093747Z.json`
- 范围：12 个冻结 Golden 场景；仅 benchmark artifact；production rows、StoryboardShot、媒体和对象存储调用均为 `0`。
- Contract Parse/Pass：首轮 schema pass `10/12`、parse success `10/12`；最终 validator contract pass `12/12`。
- Patch/Repair：33 次 repair LLM 调用，18 条 repair 记录；15 个 patch 在两次尝试后回退 baseline；辅助 proposal rejected `0`。失败项按 patch/proposal 隔离处理，不重跑整个场景。
- Director Quality：Baseline `44.71` → Before Repair `56.98` → After Repair `56.98`，平均 delta `+12.27`；质量分数不绕过 Contract blocker。
- Token/Cache/Latency：45 次真实调用；prompt `151,037`、cached `119,424`、completion `21,018`、total `172,055`、cache hit rate `79.07%`、平均延迟 `12,247.68ms`。
- 规范化审计：记录 `normalization_metadata` 与每个 patch 的 `_source_format`；非冲突重复 target 合并，冲突、不可变字段、未知绑定和非法辅助字段仍 fail-closed。

### Release Decision

本轮证明了真实 MiMo 在 Contract-First 边界内可以安全完成候选解析、部分接受和逐项修复，且最终 12/12 contract pass；但首轮 schema 稳定性为 `83.3%`，仍有明显 repair/fallback 成本，未达到 Production Shadow Candidate。继续保持 Production Pipeline V2 默认路径不变，不进入媒体生产放量。
