# Director Quality V2.4.2 — Real MiMo Protocol Canary Report

执行时间：2026-09-14 14:56 UTC
模型：`mimo-v2.5`（profile `local-llm-2vydoz`）
样本清单：`artifacts/director-quality-v2-4-2-protocol-canary-manifest.json`
结果：`artifacts/director-quality-v2-4-2-protocol-canary-20260914T145609Z.json`

## 1. 执行边界

- 仅执行 Frozen B2 中确定性选择的 1 个 sample：`V21_FIXTURE_01 / WEAK_EDIT_STRATEGY / edit`；
- semantic attempt 上限为 2，实际调用 2 次；
- provider adapter 使用 `director_tail_repair_ir_v1`、authoritative required keys 与 `json_parse_retries=0`；
- 未重新运行 planner、未修改 Frozen B2、未生成图片/视频、未写入 Production/Storyboard/Shadow、未访问对象存储。

## 2. Protocol Metrics

| 指标 | 结果 |
|---|---:|
| sample_count | 1 |
| semantic_attempt_count | 2 |
| provider_http_request_count | 2 |
| transport_retry_count | 0 |
| json_parser_retry_count | 0 |
| FORMAT_REPAIR count | 1 |
| SEMANTIC_REPAIR count | 0 |
| IR First Pass Valid | 0 / 1（0%） |
| IR Final Valid | 1 / 1（100%） |
| Canonical Compile | 1 / 1（100%） |
| Repair Candidate Contract Pass | 1 / 1（100%） |
| Request Echo | 0 |
| Custom Provider Envelope | 0 |
| Unknown Provider Shape | 0 |
| Fact Override Accepted | 0 |

## 3. Provider 输出观察

第一次响应 HTTP 200，返回的顶层 keys 已与 Repair IR 对齐、`schema_version=director_tail_repair_ir_v1`，但 `shot_decisions` 为空，触发 IR schema 校验失败。系统按业务 retry 规则发送一次 `FORMAT_REPAIR`，没有 parser 内部额外调用；第二次响应合法，通过 IR Validator、deterministic compiler、现有 canonical patch parser/compiler/validator，并被接受。

## 4. Canary Gate

**PROTOCOL_CANARY_FAILED**。

失败仅因 `IR First Pass Valid Rate = 0%`，低于 80% 门槛；其余关键协议指标均通过。该结果证明：

- 正确的 provider contract 下，MiMo 能在一次 FORMAT_REPAIR 后输出可验证的 `director_tail_repair_ir_v1`；
- 不能据此宣称首轮稳定合规，也不能宣称 Director Quality 或生产价值已通过。

按文档必须 STOP：不自动重跑 15-scene Targeted Tail Pilot，不执行 Full 24，不开启 Shadow，不生成媒体。

## 5. 安全与副作用

| 项目 | 数量 |
|---|---:|
| production | 0 |
| storyboard | 0 |
| media | 0 |
| image | 0 |
| video | 0 |
| object_storage | 0 |
| production_shadow | 0 |

响应审计仅保留 fingerprint、长度、顶层结构、schema、bounded sanitized evidence、usage/cache、latency 与 HTTP status；未记录 API key、Authorization 或 secret。

## 6. Final Status

`PROTOCOL_CANARY_FAILED`。本轮不满足 `READY_FOR_TARGETED_TAIL_REEVALUATION`，需要先改进 provider 首次输出的 IR 完整性并重新通过新的 preflight/Canary 授权；不得自动追加调用。
