# Director Quality V2.3 — Quality Signal Audit

审计时间：2026-09-14（本地工作区）  
分支：`codex/unify-formal-workspace`  
基线提交：`af8675b`（本地与 `origin/codex/unify-formal-workspace` 当前一致）

## 0. 审计边界与基线

本审计遵循 V2.3 执行方案，只读检查以下链路：

`Scene Strategy → Planner raw output → normalized/accepted patch → compiled candidate → scorer input → dimension score`

没有调用真实 LLM、图片/视频供应商或对象存储，也没有修改 Production Pipeline、质量权重、阈值或 Production Shadow。`git fetch`/远程网络检查在当前环境被连接重置/超时；本地记录的 HEAD 与远程跟踪分支均为 `af8675b`。

V2.2.2 可复核基线（`artifacts/director-quality-v2-2-2-metrics.json`）：

- 12 scenes；Final Contract Pass 100%；Fact Override Accepted 0；所有副作用 0。
- Creative Retention 54.76%；Full Creative Scene Success 91.67%；Director Quality 58.41。
- Rejection trace、raw/canonical path、stage、classification 均 100%；Unknown root cause 0；Avoidable technical fallback 0。
- 四个重点维度在多个真实样本中长期为 0 或接近 0：`PERFORMANCE_DIRECTION`、`EDIT_RHYTHM`、`EMOTIONAL_PROGRESSION`、`INFORMATION_STRATEGY`。

## 1. 十维评分器现状

实现位置：`core/director_quality_validator.py` 的 `_dimension_scores()` / `score_director_quality()`。权重保持现状（本轮不调整）。

| 维度 | 当前计算 | 直接依赖字段 | 当前风险 |
|---|---|---|---|
| `DRAMATIC_CLARITY` | 非空且非 `coverage` 的 `purpose` 比例；额外用 `coverage` 惩罚 | `shot.purpose` | 只看 purpose 是否覆盖，不判断 beat 目的是否与结构一致 |
| `SHOT_MOTIVATION` | `why_this_shot` 非空，或同时有非 coverage 的 `purpose` 与 `dramatic_function` | `why_this_shot`, `purpose`, `dramatic_function` | 语义很宽，抽象文本也可得分 |
| `EMOTIONAL_PROGRESSION` | 读取每 shot `emotion.intensity`；无数值时 4，有一个时 6；多值按 spread 与变化次数加分；全相同且至少两 shot 时降至 3 | `emotion.intensity` | 不读取 start/end/state；场景策略的曲线没有进入 scorer |
| `VISUAL_STORYTELLING` | `purpose` 非空/非 coverage，或存在 `composition` / `information_strategy` 对象 | `purpose`, `composition`, `information_strategy` | 存在空对象即可计入 visual coverage |
| `SPATIAL_CLARITY` | `continuity_contract` 且 `camera.camera_side` 或 `composition.frame_relationship`；无 blocking 时固定 7 | `continuity_contract`, `camera.camera_side`, `composition.frame_relationship`, `blocking` | 对 blocking 缺失的计划无法分辨真实质量 |
| `PERFORMANCE_DIRECTION` | 对每 shot，要求 `performance_direction` 可迭代，且每项同时有 `objective` 与 `visible_behavior`；有效 shot 占比 ×10 | `performance_direction[]` | scorer 只接受 list[object]，不接受 character-id keyed object 或字符串 |
| `EDIT_RHYTHM` | `edit.cut_reason` 覆盖率与正时长的 distinct ratio 平均；时长来自 `edit.duration_seconds` 或 `duration_hint_seconds` | `edit.cut_reason`, `edit.duration_seconds`, `duration_hint_seconds` | 不读取 `pacing`/`transition`/`hold_after_action_seconds`；结构计划时长相同会天然拉低 |
| `INFORMATION_STRATEGY` | `information_strategy` 中 `reveals`、`withholds`、`audience_focus` 任一非空/真值即有效 | `information_strategy.reveals/withholds/audience_focus` | 不接受 provider 常用的单数 `reveal/withhold` 作为 scorer 信号，且不读取 scene 级计划 |
| `POWER_DYNAMICS` | treatment beat_map 出现 `decision`/`power_shift` 时，若镜头签名与 frame relationship 均未变则 3，否则 8；无 power beat 固定 8 | `treatment.beat_map[].type`, shot camera signature, `composition.frame_relationship` | 仅判断是否变镜头，不读取 strategy 的 power curve 语义 |
| `SHOT_DIVERSITY` | 不同 camera signature 数量/镜头数，减 `CAMERA_REPETITION` 惩罚 | `camera.shot_size/angle/movement/speed/camera_side` | 只按签名统计，不识别有意保持连续性的合法重复 |

## 2. Planner 输出核对

### 2.1 Deterministic planner

`core/director_creative_planner.py::_creative_for_beat()` 会输出：

- `performance_direction`：**list[object]**，包含 `character_id`、`objective`、`visible_behavior`；
- `emotion`：`start`、`end`、`intensity`；
- `edit`：`duration_seconds`、`cut_reason`、`hold_after_action_seconds`；
- `information_strategy`：`reveals`、`withholds`、`audience_focus`。

因此 deterministic surrogate 的形状与 scorer 约定基本一致，但它把所有 beat 的 intensity 以 `4 + index` 推导（受 reveal/decision 加成），不是从结构化场景策略读取，且 `duration_seconds` 默认取 baseline 时长，可能形成机械相同。

### 2.2 Real MiMo provider samples

V2.2.2 artifacts 的候选样本证实 provider 输出并非稳定 canonical 形状：

- `performance_direction` 常见为 `{角色ID: "可见行为文本"}`，不是 scorer 需要的 `[{character_id, objective, visible_behavior}]`；
- `emotion` 常见为 `{primary, subtext}`，缺少 numeric `intensity`；
- `edit` 常见为 `{pacing, transition}`，缺少 `cut_reason` 与 `duration_seconds`；
- `information_strategy` 常见为 `{reveal, withhold}`，字段为单数；
- 部分 shots 直接缺少以上对象。

在 `recovery` 与 `observability` artifact 中对候选 shot 类型计数可复核：多个场景的 `performance_direction`、`information_strategy`、`edit` 为 `dict` 或 `None`，`emotion` 也有字符串/对象混用。这解释了四维的长期低分至少部分来自 provider shape mismatch，而不能归因于模型创意能力。

## 3. Normalizer / Schema / Compiler 链路

### 3.1 Normalizer

`core/director_patch_normalizer.py` 与 `core/director_patch_schema.py` 只做协议等价的结构展开：

- `camera`、`emotion`、`composition`、`edit`、`information_strategy` 会展开一层 dotted paths；
- `performance_direction` 被列入 nested fields，但不会把 character-id keyed map 转成 list，也不会把单数 `reveal/withhold` 变成 canonical `reveals/withholds`；
- unknown spelling 不做猜测，unsafe/不等价表示保持拒绝或进入 repair，符合 fail-closed 原则。

### 3.2 Patch compiler

`core/director_patch_compiler.py` 原子应用允许路径并保留操作 provenance。它不会主动删除字段，但在 `performance_direction` / `information_strategy` 的 object 值通过 `replace` 写入后，candidate 形状仍等于 provider 形状；compiler 没有 schema-level semantic adapter。

### 3.3 Final candidate / scorer path

Final candidate 中字段可能存在，但 scorer 通过：

```python
for item in (shot.get("performance_direction") or []):
    item.get("objective"), item.get("visible_behavior")
```

读取，因此 keyed object 会迭代 key 字符串并永远得不到有效项；`reveal/withhold` 不会命中复数 key；`pacing/transition` 不会命中 `cut_reason`。这属于**字段形状/读取路径不一致**，不是字段在 compiler 中丢失。

## 4. 端到端缺口分类

| 缺口 | 证据 | 分类 |
|---|---|---|
| Scene Strategy 只有全场 `emotional_curve`，且 builder 默认全 5 | `core/scene_directing_strategy.py` v1 schema/builder | `STRATEGY_MISSING` |
| Deterministic planner 能输出四维，但未引用 strategy refs | `_creative_for_beat()`、`build_creative_patch_candidate()` | `PLANNER_NOT_OUTPUT`（strategy provenance 缺失；字段本身不一定缺失） |
| Provider keyed `performance_direction` 被当作合法 object 值 | normalizer/schema/compiler 允许 creative root object | `SCORER_PATH_MISMATCH` |
| Provider `reveal/withhold` 与 scorer 复数约定不一致 | normalizer 没有协议等价别名；scorer 只看复数 | `SCORER_PATH_MISMATCH` / `FIELD_DROPPED`（未被识别为信号，不是物理丢失） |
| Provider `pacing/transition` 与 scorer 的 `cut_reason` 不一致 | schema 未定义 edit semantic mapping；scorer只看 cut_reason | `SCORER_PATH_MISMATCH` |
| emotion 缺 intensity 或所有值相同 | artifacts 候选与 scorer 规则 | 缺失时 `MODEL_QUALITY_LOW` 或 `SCORER_RULE_FAILURE`；目前无法细分，需新增 trace |
| 真正 patch/contract 拒绝 | V2.2.2 rejection artifacts：invalid value/true forbidden 已可追踪 | `PATCH_REJECTED` / `PATCH_FALLBACK`，不属于上述四维 shape 问题 |

当前 `UNKNOWN` 根因在 V2.2.2 rejection telemetry 中为 0；V2.3 需要把上述质量信号链也按同一 shot/dimension 粒度落 trace。

## 5. 本轮需要补全的字段/结构（不改事实边界）

1. Scene Directing Strategy V2：按 `beat_id` 提供 `performance_arc`、`rhythm_curve`、`emotion_curve`、`information_plan`；保留旧字段兼容读取，不写入剧情事实。
2. Patch provenance：每个 creative patch 记录 `strategy_refs`，只引用已批准 beat/character，不重新定义事件。
3. Canonical semantic normalization：仅对已声明协议等价形状做 deterministic conversion；无法证明等价时拒绝，不做自由推断。
4. Quality Trace：记录 strategy evidence、planner presence、accepted/rejected/fallback、final field presence、scorer input/raw value、dimension score、`missing_stage`。
5. Coverage metrics：Performance、Edit、Emotion Arc、Information Strategy、Useful Creative Acceptance。

不需要 migration：这些字段属于 `ready_for_review` creative candidate/strategy artifacts，不修改结构性 ShotPlan、FactSnapshot 或历史数据库行；旧候选按缺失处理并保持可回放。

## 6. 测试计划

### 6.1 Signal-chain fixtures

- list 形 `performance_direction`（objective + visible_behavior）得分 >0；抽象 emotion-only 不得得分；
- `edit.cut_reason` + hold timing 得分高于无策略 baseline，并检测机械等时长；
- emotion `start/development/turn/peak/release` 与 flatline 检测；
- information reveal/withhold/reaction priority 命中 scorer；
- keyed-map / 单数 provider shape 要么 deterministic canonicalize（有协议依据）要么留下明确 mismatch trace。

### 6.2 Integration

`Treatment → Blocking → Structural ShotPlan → Strategy V2 → CreativePatch → Compiler → Contract Validator → Final Candidate → Quality Trace → Scorer → Coverage`，验证 immutable projection/fact fingerprint 不变。

### 6.3 Regression / gates

运行现有 V2.2.2/V2.2.1/V2.2/V2.1、Director Quality V2、Production Pipeline V2、SceneBlocking、Golden、Production Gate、`compileall`、`diff-check`。只有 deterministic 全绿后才允许 Phase A 真实 MiMo（12 scenes × 1 run，artifact-only）；本轮不运行真实调用。

## 7. 重复 Pilot 设计

- 冻结同一 12 scenes、ScriptIR、Treatment、Blocking、Structural ShotPlan、Contract、Validator、Scorer；
- A = 当前 V2.2.2 Strategy/Planner，B = V2.3 Strategy/Planner，仅 creative decision/strategy 改变；
- deterministic smoke 通过后，Phase A 只跑 B 12×1；通过后 A/B 各 3 runs（36 samples），不写生产/媒体/存储；
- 每个 sample 记录 10 维、5 coverage metrics、contract/fallback/repair、tokens/cache/latency；汇总 mean/median/stddev/P25/P75、per-scene paired delta、improved_run_count；
- 成功标准遵循方案原值：Final Contract 100%、Fact Override 0、四维 coverage 达标、Director Quality mean/median ≥70、相对 structural baseline ≥+15，且 B 在 3 runs 中至少 2 次优于 A。不得为通过而改权重/阈值。

## 8. 结论

V2.2.2 的安全与可观测性已达标，但创意质量信号尚未闭环。当前首要修复顺序是：**先建立 trace 与四维 fixtures，修复可证明的 scorer/协议形状错配，再引入 Strategy V2 与 planner strategy refs，最后进行 coverage/variance benchmark**。在这些步骤完成前，不应把低分简单解释为 MiMo 能力不足，也不应开启 Production Shadow。
