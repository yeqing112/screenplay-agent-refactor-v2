# Director Quality V2.4.2 — Provider Contract Wiring Closure

## 结论

**READY_FOR_PROTOCOL_CANARY**

本轮只完成 provider contract wiring、Request SSOT、retry/metrics 分离、审计增强与 provider-free 验证。没有调用真实 MiMo，没有生成媒体，没有写入 Production/Storyboard/Shadow，也没有访问对象存储。下一轮必须取得新的显式确认后，才可执行最多 5 个 repair type 的 Protocol Canary。

## 1. V2.4.1 Postmortem

V2.4.1 的 `IR First Pass Valid = 0%` 被 `PROVIDER_EXECUTOR_CONTRACT_MISMATCH` 直接污染：旧 runner 的 system prompt 要求 `director_creative_patch_v1`，`required_keys` 要求 `patches` 与 `auxiliary_shot_proposals`；provider-bound Executor 却设置 `require_repair_ir=True`，只接受 `director_tail_repair_ir_v1`。因此 0% 不能解释为 `MIMO_IR_INCAPABLE`。

V2.4.1 报告中的 54 次是 27 个 root cause 的业务/semantic attempts，不足以证明 54 次真实 HTTP requests；当时没有完整 HTTP audit 证据。详见 `artifacts/director-quality-v2-4-1-pilot-postmortem.md` 与 `artifacts/director-quality-v2-4-1-metrics-erratum.json`。

## 2. 本轮实现

- 新增 `core/director_tail_repair_provider_contract.py`，从 `director_tail_repair_ir.py` 的 constants 自动生成 provider output contract、required keys、semantic fields 与 system prompt；不再在 runner 手写第二套 schema。
- 真实 provider adapter 现在只要求 `director_tail_repair_ir_v1` 的五个 required keys，明确禁止 canonical patch/path，并调用 `call_llm_json(..., json_parse_retries=0)`。
- Executor 的 base request 统一由 `build_repair_request()` 生成；canonical 字段只有一个 `schema_version=director_tail_repair_request_v1`。retry 信息进入嵌套 `attempt` context；旧 `attempt_kind` 等顶层字段仅保留为兼容投影，不参与 provider contract。
- Executor 继续以业务级最多两次尝试作为唯一 semantic retry owner；HTTP transport retry 独立留在 LLM transport 层。
- LLM audit 对每个 transport attempt 记录 bounded response shape、schema version、sanitized excerpt、HTTP status、latency、usage/cache 与 retry 标记，不记录 secret。
- Preflight 新增 provider/executor/request contract handshake 与阻断码，可自动阻断旧 V2.4.1 配置漂移。

## 3. Gate 结果

| Gate | 结果 |
|---|---|
| Provider system contract alignment | PASS |
| Request SSOT | PASS |
| IR required keys | PASS |
| Executor `require_repair_ir` | PASS |
| Nested parser retry disabled | PASS（adapter 显式 `json_parse_retries=0`） |
| Corrective retry wiring | PASS |
| Deterministic IR compiler | PASS（未修改） |
| Canonical patch boundary | PASS（未修改/未放宽） |
| Fact boundary | PASS |
| Recorded replay / V2.4.1 postmortem | PASS |
| Full provider-free regression | **991 passed, 890 warnings** |
| Real MiMo calls this round | 0 |
| Production / Storyboard / Media / Storage / Shadow | 0 |

## 4. Final Report 问题回答

1. V2.4.1 的 0% IR Valid 是否由 mismatch 污染？**是，直接原因是 `PROVIDER_EXECUTOR_CONTRACT_MISMATCH`。**
2. MiMo 是否被要求输出 `director_creative_patch_v1`？**旧 runner 是；V2.4.2 已改为 Repair IR。**
3. 旧 `required_keys` 是否为 canonical keys？**是；现已改为 IR required keys。**
4. 合法 Repair IR 是否可能被旧 runner 提前拒绝？**是；旧 required keys 会提前拒绝，现已消除。**
5. 54 次是否证明 54 次 HTTP？**否；旧证据不足，已标记 `not_proven`。**
6. Nested retry 是否消除？**provider adapter 的 parser retry 已关闭；transport retry 独立统计。**
7. Executor 是否使用 `build_repair_request()`？**是。**
8. Provider / Executor / Validator 是否共享同一 Repair IR contract？**是，由 IR constants 与 provider contract helper 生成。**
9. Preflight 是否能检测 mismatch？**是，支持 required keys、system prompt、schema、request schema、nested retry、canonical path 阻断码。**
10. 当前状态：**READY_FOR_PROTOCOL_CANARY**。

## 5. 下一轮 Protocol Canary（仅定义，不执行）

取得新的显式确认后，使用同一 Frozen B2 数据，最多选择 5 个不同 `repair_type`（edit、emotion、information、performance、camera），每类最多 1 个 root-cause sample；每个 root cause 最多 2 次 semantic calls，总上限 10 次。由于 adapter 的 `json_parse_retries=0`，不得存在隐藏 parser LLM call。

Canary gate：IR First Pass ≥80%、IR Final=100%、Canonical Compile=100%、Applied Candidate Contract Pass=100%、Fact Override=0、Unknown Provider Shape=0。只有 Canary 通过，才可另行申请 15-scene Targeted Tail Pilot；本报告不授权任何后续真实调用。
