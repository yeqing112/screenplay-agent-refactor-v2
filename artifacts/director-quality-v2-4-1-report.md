# Director Quality V2.4.1 — Repair Protocol Closure Report

基线：`d99c3c5c3b432aec432c132172f07b952188b043`

## 已完成的 provider-free 闭环

- Repository Audit：完成；四个初始假设 A–D 均被代码与 V2.4 结果支持。
- Request/Output 分离：`director_tail_repair_request_v1` 与 `director_tail_repair_ir_v1`。
- Typed IR Validator：按 `repair_type`、root cause、shot id 与语义字段白名单 fail-closed。
- Deterministic IR Compiler：IR → `director_creative_patch_v1`，不接受模型生成 canonical path。
- Canonical boundary：未修改、未放宽 `director_creative_patch_v1`。
- Corrective retry：两次总预算；格式错误走 `FORMAT_REPAIR`，语义未改善走 `SEMANTIC_REPAIR`，携带前次原文与精确错误。
- Metrics：新增 scene/root-cause attempt coverage、repair acceptance rate、scene repair success rate；保留旧字段供历史兼容。
- Acceptance：Executor 已传入 CV、over-directing、shot-inflation 指标；contract/fact/structural/目标维度/DQ/CV 均参与回退判定。
- Runtime ledger：写入 request/raw/IR/canonical fingerprints、attempt kind、解析/编译/契约状态、目标维度与 DQ/CV 前后值，不记录密钥或原文。
- Replay 与 Matrix：已生成对应 artifact；无未知异常。

## 旧 V2.4 失败本质

53 个 forbidden-field failure 主要是 **prompt contract confusion + provider output-format failure**：模型把输入 Request metadata 与自定义修复元数据回显到输出顶层；不是已接受的事实覆盖，也不是生产链路故障。另有 1 个候选未改善目标维度。

## 当前协议结论

1. Repair Request / Output：已正式分离。
2. `director_tail_repair_ir_v1`：已建立。
3. LLM canonical path：已禁止；路径由 deterministic compiler 生成。
4. IR → canonical patch：相同输入产生相同输出。
5. `director_creative_patch_v1`：未修改、未放宽。
6. 第二次 retry：已成为真正的 FORMAT_REPAIR 或 SEMANTIC_REPAIR。
7. Repairability Matrix：7 个主要 root cause 均有 synthetic 可达改善路径；当前没有 `SCORER_SENSITIVITY_GAP`。
8. CV / over-directing / shot inflation：已接入 acceptance wiring；CV 仅对真正 applied candidate 可由 replay 提供，缺失时保持 fail-closed。

## Provider-free 验证

全量本地回归：**983 passed, 890 warnings**。

新增 V2.4.1 协议、retry、IR/compiler、integration 测试均通过；未调用真实 LLM、生图、视频、对象存储；未写 Production/Storyboard/Shadow。

## Recorded 53 failures replay

V2.4 原始 provider body 没有持久化，只有 bounded error/fingerprint，因此无法安全重建原文。54 条 attempt 均保守分类为 `AMBIGUOUS_REJECTED`，`UNKNOWN_EXCEPTION=0`；没有任何旧输出被加入白名单。

## 第二次 Targeted Pilot

尚未执行。根据计划，必须在本地 hard gate 通过后取得新的显式人工确认，且继续使用同一 Frozen B2 的 15 scenes / 27 root causes。当前可报告：

| 指标 | 结果 |
|---|---:|
| IR First Pass / Final | N/A（未调用 provider）|
| Canonical Compile | N/A |
| Candidate Contract Pass | N/A |
| Target Dimension Improvement | N/A |
| Repair Acceptance / Scene Success | N/A |
| DQ / CV Delta | N/A |
| Fact Override Accepted | 0 |

## 最终状态

**NOT_READY** — provider-free 协议闭环与 hard gate 已通过，但尚未获得 V2.4.1 第二次 Targeted Pilot 的新确认，不能宣称 Creative Gate 通过，也不能进入 Full 24 或 Production Shadow。
