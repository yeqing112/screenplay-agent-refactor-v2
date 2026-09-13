# Director Quality V2.2 — First-Pass Stability & Repair Cost Reduction

## Executive Summary

V2.2 已完成离线的三级 Repair Pipeline：`MiMo Raw Output → Level 0 Normalization → Level 1 Deterministic Repair → Contract Validation → Level 2 Local Repair → fallback`。本地全仓库回归为 `823 passed`，Production Storyboard gate 与 V2.2 定向回归均通过。随后按显式授权完成 12 场景真实 MiMo Stage A benchmark-only Pilot；Pilot 未写生产对象、未生成媒体，且未开启 Production Shadow。

本报告严格区分：

- **V2.1 Baseline**：真实 MiMo Pilot 的已提交基线；
- **V2.2 Offline As-Built**：使用冻结 V2.1 候选文档的本地回放，不等同于真实 MiMo A/B；
- **Stage A Real MiMo**：真实 MiMo 12 场景结果已执行并单独落档；该结果用于 A/B 判断，不等同于已通过 Production Shadow 门槛。

## V2.1 Baseline

| 指标 | V2.1 基线 |
|---|---:|
| 场景 | 12 |
| 总调用 | 45 |
| Repair 调用 | 33 |
| Fallback patch | 15 |
| 首轮 Schema Pass | 10/12 |
| 最终 Contract Pass | 12/12 |
| Cache hit | 79.07% |
| 平均延迟 | 12.25s |

33 次 repair 与 15 个 fallback 的逐类归因保留在 [director-quality-v2-2-gap-audit.md](director-quality-v2-2-gap-audit.md)。主要根因是协议等价格式未先归一化、repair identity 丢失及重复 retry，而非允许放宽事实边界。

## V2.2 As-Built Pipeline

### Level 0 Normalization

`core/director_patch_normalizer.py` 统一 JSON Pointer/dotted/wildcard path、白名单字段 alias、Camera enum、numeric/whitespace 和安全的嵌套 flatten；保留 before/after fingerprint 与 reason，未知字段及 immutable 目标 fail-closed。

### Level 1 Deterministic Repair

`core/director_patch_deterministic_repair.py` 处理 identical/non-conflicting duplicate merge、conflicting duplicate reject 与稳定 patch 顺序，不生成新的创意语义。

### Level 2 LLM Repair

`core/director_quality_v22.py` 只对路由表明确的创意语义问题开放局部 repair；Level 0/1、Fact Override、未知 shot/proposal 不调用 LLM。repair 输入保持 patch 级，重复相同错误由 `stop_on_same_error` 截断。

### Partial Acceptance / Fallback

partial 模式在字段级保留可编译 sibling，默认原子编译行为不变。每个 fallback 记录 `scene_id`、`plan_shot_id/proposal_id`、`root_cause`、`repair_level_attempted`、`attempt_count` 与 `final_action`。

## Offline Replay Results

来源：冻结的 `director-quality-v2-1-golden-scenes.json` 与已提交 V2.1 candidate patch document；运行器为 `scripts/run_director_quality_v2_2_benchmark.py`。

| 指标 | V2.2 Offline Replay |
|---|---:|
| 场景 | 12 |
| Raw Parse Pass | 12/12 |
| Normalized Parse Pass | 12/12 |
| First-Pass Schema Pass | 12/12 |
| First-Pass Contract Pass | 12/12 |
| Post-Normalization Contract Pass | 12/12 |
| Post-Deterministic Repair Pass | 12/12 |
| Post-LLM Repair Pass | 0/12（无 Level 2 输入） |
| Final Contract Pass | 12/12 |
| Normalization events | 24 |
| Deterministic repair events | 0 |
| LLM repair calls | 0 |
| Fallback patches | 0 |
| Fallback patch rate | 0% |
| Creative Retention Rate | 100% |
| Full Creative Scene Success | 100% |
| Provider/media/storage calls | 0 |

以上是离线管线证据，不是对真实 MiMo 首轮输出的性能承诺。对应机器可读回放 artifact 为 `artifacts/director-quality-v2-2-offline-replay.json`（未覆盖 V2.1 历史 artifact）。

## Regression Evidence

- V2.2 targeted + V2.1 + Production + SceneBlocking V2 + Materializer gate：`81 passed`。
- 全仓库 pytest：`820 passed`，仅既有弃用/测试返回值 warnings。
- `python -m compileall -q api core scripts`：通过。
- `git diff --check`：通过。
- Production reverse test：mock `StoryboardAgent.run()` 时调用次数为 `0`。
- Guarded Stage A runner authorization/mock tests：`7 passed`；默认 CLI 为 `preflight_only`，真实 provider 调用 `0`。

## Stage A Real MiMo A/B Comparison

来源：`artifacts/director-quality-v2-2-stage-a-mimo-pilot-20260913T145407Z.json`。运行范围严格为冻结 Golden 的 12 个场景；真实调用仅发生在 guarded runner，未写入生产数据库/Storyboard/媒体/对象存储。

| 指标 | V2.1 基线 | V2.2 Stage A 实测 | 结果 |
|---|---:|---:|---|
| 场景 | 12 | 12 | 同口径 |
| Planner / Repair 调用 | 12 / 33 | 12 / 14 | Repair 下降 57.6% |
| 首轮 Schema Pass | 10/12 | 10/12 | 持平 |
| 最终 Contract Pass | 12/12 | 12/12 | 保持 100% |
| Fallback patch | 15 | 27（20.93%） | 退化 |
| Creative Retention Rate | 未记录 | 78.29% | 未达 ≥90% 门槛 |
| Full Creative Scene Success | 未记录 | 75% | 未达 ≥85% 门槛 |
| Director Quality 平均 | 56.98 | 58.70 | +1.72 |
| 平均延迟 | 12.25s | 17.19s | 退化 |
| Cache hit | 79.07% | 46.05% | 未达 ≥70% 门槛 |

Fallback 根因：17 个 `FORBIDDEN_PATH / DIRECTOR_PATCH_FIELD_FORBIDDEN`，10 个 `LLM_REPAIR_CONTRACT_FAILURE / INVALID_PATCH_VALUE`。9/12 场景为 `valid`，3/12 为 `partial`；所有场景最终 Contract pass，但部分场景依靠 patch-level fallback 保持结构合规。该结果证明“减少无效 repair 调用”已生效，但当前归一化覆盖与创意保留仍不足，不能将 fallback 或低 retention 误报为质量提升。

## Release Decision

**NOT_READY_FOR_PRODUCTION_SHADOW**

Stage A 已有完整外部证据，但未达到 Shadow 门槛：fallback、Creative Retention、Full Creative Scene Success、Cache hit 和延迟均出现退化或不足。Final Contract pass 仍为 12/12，且所有副作用计数为 0。下一阶段应先修复上述根因并重新进行同口径 benchmark；不得切换 Production default、不得进入媒体生成、不得自动开启 Shadow。

## Remaining Bottlenecks

1. `FORBIDDEN_PATH` 仍有 17 个，说明真实 MiMo 的 operation/path envelope 还有未覆盖的等价格式，应扩充 canonical normalization 并增加真实样本回放。
2. 10 个 `INVALID_PATCH_VALUE` 在 Level 2 repair 后仍 fallback，需收紧 repair 输出 schema 与字段级接受策略，提升 creative retention（不得放宽事实边界）。
3. V2.2 cache hit 46.05%、平均延迟 17.19s，需检查 prompt 前缀稳定性与 repair prompt 去重；独立盲审仍需后续执行，当前 Director Quality +1.72 仅为内部指标。
