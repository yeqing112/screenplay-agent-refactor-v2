# Director Quality V2.2.1 — Gap / Failure Audit

> 审计阶段：Step 1（仅审计，未修改代码、未调用 MiMo、生图、视频、对象存储或生产 API）  
> 审计日期：2026-09-13  
> 基于提交：`65a22a2`  以及远程同名分支  
> Stage A artifact：`artifacts/director-quality-v2-2-stage-a-mimo-pilot-20260913T145407Z.json`

## 1. 审计范围与证据边界

本审计逐项核对真实 MiMo Stage A 的 27 个 fallback、V2.2 report/metrics/gap audit，以及当前运行时的 CreativePatch、Normalizer、Patch Compiler、Validator、Repair Router、LLM Repair、Prompt Builder、Telemetry 实现。

重要证据限制：Stage A artifact 只持久化了 `raw_digest`、fallback taxonomy、repair attempt 计数和响应摘要；fallback 条目中的 `scene_id`、`plan_shot_id`、`proposal_id` 均为空，未保存 raw patch、raw path、normalized path 或 repair 原文。因此下表对这些字段明确记为 `NOT_CAPTURED`，不从 digest 或候选 ShotPlan 反推，不把未知信息伪装成确定事实。这一缺口本身是 V2.2.1 必须修复的可观测性问题。

已由 artifact 确认的事实：

- 27 个 fallback：17 个 `FORBIDDEN_PATH / DIRECTOR_PATCH_FIELD_FORBIDDEN`，10 个 `LLM_REPAIR_CONTRACT_FAILURE / INVALID_PATCH_VALUE`。
- 17 个 path fallback 发生在 `book990402:e2:暗房门口的试探`（10 个）与 `book990402:e3:暗房惊魂`（7 个）。
- 10 个 repair fallback 全部发生在 `book990402:e3:暗房惊魂（2）`，每个记录 `repair_level_attempted=2`、`attempt_count=1`、`final_action=FALLBACK_BASELINE_PATCH`。
- 没有观察到 `FACT_OVERRIDE`、`UNKNOWN_PLAN_SHOT_ID`、`AUXILIARY_BINDING_FAILURE` 或任何事实越权被接受的证据。

## 2. 27 个 fallback 逐项清单

由于原始 patch/path 没有被 Stage A artifact 保存，以下每行仍对应唯一的 fallback 条目（按 artifact 顺序编号），但对缺失字段使用明确的 `NOT_CAPTURED`。`normalized path` 在当前实现中没有产生，不能把 canonical path 误写为“已归一化”。

| ID | Scene | plan_shot_id / proposal_id | Raw patch | Issue code | Raw path | Normalized path | Repair attempts / output | Final fallback reason | Deterministic recovery |
|---|---|---|---|---|---|---|---|---|---|
| F01 | `book990402:e2:暗房门口的试探` | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F02 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F03 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F04 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F05 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F06 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F07 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F08 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F09 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F10 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F11 | `book990402:e3:暗房惊魂` | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F12 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F13 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F14 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F15 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F16 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F17 | same | NOT_CAPTURED | NOT_CAPTURED | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | NOT_CAPTURED | NOT_PRODUCED | 0 / no LLM repair | `FORBIDDEN_PATH` → `REJECT_PATCH` | CONDITIONAL: yes if equivalent path |
| F18 | `book990402:e3:暗房惊魂（2）` | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | `LLM_REPAIR_CONTRACT_FAILURE` → `FALLBACK_BASELINE_PATCH` | UNKNOWN until repair output is persisted |
| F19 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F20 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F21 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F22 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F23 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F24 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F25 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F26 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |
| F27 | same | NOT_CAPTURED | NOT_CAPTURED | `INVALID_PATCH_VALUE` | NOT_CAPTURED | NOT_PRODUCED | 1 / repair level 2 failed | same | UNKNOWN until repair output is persisted |

## 3. Root-cause 分类统计

当前能由 artifact 直接证实的分类如下；未记录 raw path/value 的类别不能被臆测拆分为 alias、enum 或 nested patch。

| Root cause | Count | Percentage | Level 0 | Level 1 | Truly needs LLM | Estimated fallback reduction |
|---|---:|---:|---|---|---|---:|
| `PATH_SYNTAX_VARIANT`（由 `FORBIDDEN_PATH` 证实，具体变体未持久化） | 17 | 62.96% | 是，前提是解析无歧义且目标在白名单 | 否/可选稳定排序 | 否 | 最多 17 |
| `REPAIR_INVALID_VALUE`（repair 后 `INVALID_PATCH_VALUE`） | 10 | 37.04% | 否，除非值本身是已知 alias/type coercion | 否，除非 schema 给出唯一修复 | 可能需要；默认受限于 target | 待保存 repair 原文后估算 |
| `PATH_SHOT_ID_ENCODING` | 0（未记录） | 0% | 可 | 否 | 否 | 0（证据不足） |
| `PATH_ALIAS_MISMATCH` | 0（未记录） | 0% | 可 | 否 | 否 | 0（证据不足） |
| `NESTED_VS_FLAT_PATCH` | 0（未记录） | 0% | 可 | 可 | 否 | 0（证据不足） |
| `ENUM_ALIAS` | 0（未记录） | 0% | 可 | 可 | 否 | 0（证据不足） |
| `TYPE_COERCION` | 0（未记录） | 0% | 可 | 可 | 否 | 0（证据不足） |
| `DUPLICATE_IDENTICAL_PATCH` | 0（未记录） | 0% | 否 | 可 | 否 | 0（证据不足） |
| `DUPLICATE_NON_CONFLICTING_PATCH` | 0（未记录） | 0% | 否 | 可 | 否 | 0（证据不足） |
| `CROSS_PATCH_CONFLICT` | 0（未记录） | 0% | 否 | 否 | 可能 | 0（证据不足） |
| `REPAIR_SCHEMA_FAILURE` | 0（未记录；当前 code 是 invalid value） | 0% | 可先规范化 | 否 | 否 | 0（证据不足） |
| `REPAIR_FORBIDDEN_FIELD` | 0（未记录） | 0% | 否 | 否 | 否，必须拒绝 | 0 |
| `REPAIR_INVALID_PATH` | 0（未记录） | 0% | 可先解析 | 否 | 否 | 0（证据不足） |
| `REPAIR_SEMANTIC_FAILURE` | 0（未记录） | 0% | 否 | 否 | 是 | 0（证据不足） |
| `FACT_OVERRIDE` | 0 | 0% | 否 | 否 | 否，安全拒绝 | 0 |
| `UNKNOWN_PLAN_SHOT_ID` | 0 | 0% | 否 | 否 | 否，安全拒绝 | 0 |
| `QUALITY_REPAIR_EXHAUSTED` | 0（未记录） | 0% | 否 | 否 | 是 | 0（证据不足） |
| `OTHER` | 0（未记录） | 0% | — | — | — | 0（证据不足） |

### 安全 vs 可避免

- **已确认的安全必须回退：0 个**。本 artifact 没有事实越权、未知 shot、不可绑定资产或其它必须拒绝的证据。
- **可避免技术回退候选：17 个 path fallback**。结合 V2.1 审计中同类 operation/path envelope 的历史证据，它们很可能是等价路径未先 canonicalize；但由于本次 raw path 未保存，当前结论标记为“条件性可恢复”，不能宣称已恢复。
- **待定技术回退：10 个 repair invalid value**。它们发生在创意 repair 层，不能在没有 repair 原文、target、allowed paths 和值校验结果时判断是安全拒绝还是可恢复。V2.2.1 必须先持久化这些证据，再决定是否归入 avoidable technical fallback。

## 4. 运行时审查结论

1. `core/director_patch_normalizer.py` 已具备 Level 0 的部分规范化，但没有独立的唯一 Canonical Path Resolver；不同入口仍可能在 schema/validator 前各自解析。
2. Stage A 的 `FORBIDDEN_PATH` 在当前流水线中直接 `REJECT_PATCH`，没有先尝试“解析 → 白名单校验 → canonical path”。这解释了为什么 17 个条目没有 LLM repair，也没有 normalized path 记录。
3. Level 2 repair 的输入/输出仍允许落到旧的 patch-shaped contract；artifact 只看到 `INVALID_PATCH_VALUE`，没有可审计的 replacement target/path/value 三元组，无法判断是 schema 漂移、值越界还是语义失败。
4. Fallback taxonomy 已被写入结果，但身份字段为空，导致 fallback 无法与具体 patch、shot、strategy beat 对齐；这会阻碍 Creative Recovery 与 Loss 的可信计算。
5. 当前 Pilot telemetry 能记录 provider、token、cache、latency 和 request fingerprint，但未记录 `path_resolution_*`、stable prefix hash、repair success/failure、creative recovery 等 V2.2.1 指标。

## 5. V2.2.1 实施门槛（审计后的最小闭环）

在进入代码实现前，审计结论只允许形成以下通用改造方向：

1. 建立唯一 `Canonical Path Resolver`，所有 Planner/Repair patch 均先解析，再检查 allowed paths；歧义必须 `AMBIGUOUS_PATCH_PATH` fail-closed。
2. 收窄 repair 输出为 `RepairReplacement`，target 由程序固定；repair 输出同样复用 resolver、normalizer 与 validator。
3. 为每个 fallback 保存 raw patch 摘要、raw/normalized path、target、issue、repair outputs、attempts、最终 reason 和 deterministic recoverability。
4. 新增 safe/avoidable 分类，但在没有证据时保持 `UNKNOWN`，不得用 baseline fallback 数量倒推可恢复率。
5. 在不改变质量权重、不放宽事实契约的前提下，补充 Creative Recovery、Creative Loss、Repair Efficiency 与 stable-prefix telemetry。

**审计结论：** V2.2 的主要回退不是安全边界主动拒绝，而是 path/repair 协议与可观测性不足导致的技术性损失；不过 10 个 repair invalid value 在补齐原文证据前不能擅自判定为可恢复。Step 1 完成，下一步才进入 Canonical Path Resolver 实现；本审计阶段未调用真实 MiMo。
