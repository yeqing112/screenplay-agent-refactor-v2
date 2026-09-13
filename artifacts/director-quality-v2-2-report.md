# Director Quality V2.2 — First-Pass Stability & Repair Cost Reduction

## Executive Summary

V2.2 已完成离线的三级 Repair Pipeline：`MiMo Raw Output → Level 0 Normalization → Level 1 Deterministic Repair → Contract Validation → Level 2 Local Repair → fallback`。本地全仓库回归为 `820 passed`，Production Storyboard gate 与 V2.2 定向回归均通过。离线回放 12 个冻结场景未产生 LLM、数据库、Storyboard、媒体或对象存储副作用。

本报告严格区分：

- **V2.1 Baseline**：真实 MiMo Pilot 的已提交基线；
- **V2.2 Offline As-Built**：使用冻结 V2.1 候选文档的本地回放，不等同于真实 MiMo A/B；
- **Stage A Real MiMo**：尚未执行，因此不宣称 V2.2 已达到生产 Shadow 门槛。

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

## Stage A A/B Comparison

Stage A 真实 MiMo 12 场景 benchmark-only 尚未执行。因缺少 V2.2 的真实 repair/token/latency/cache/quality telemetry，以下项目保持未评估：LLM Repair Calls Reduction、Fallback Reduction、Director Quality Delta、Cache Hit、真实 Creative Retention。

## Release Decision

**NOT_READY_FOR_PRODUCTION_SHADOW**

原因是 Stage A 外部 Pilot 证据尚缺；本地安全门、Contract 边界、Production Materializer 反向测试和离线副作用隔离均已通过。下一步只能在明确授权后运行独立的 12 场景真实 MiMo benchmark-only pilot；不得切换 Production default、不得进入媒体生成、不得自动开启 Shadow。

## Remaining Bottlenecks

1. 真实 MiMo 首轮输出尚未用 V2.2 runner 复测，无法验证 repair calls 是否从 33 次下降。
2. 真实 token/latency/cache 需与 V2.1 同口径采集。
3. 需要独立盲审才能报告 Director Quality 与 Creative Retention 的真实变化。
