# Director Quality V2.4.2b — Real MiMo Multi-Type Protocol Canary

执行时间：2026-09-14 15:56 UTC
模型：`mimo-v2.5`（profile `local-llm-2vydoz`）
样本清单：`artifacts/director-quality-v2-4-2b-protocol-canary-manifest.json`
结果：`artifacts/director-quality-v2-4-2b-protocol-canary-20260914T155655Z.json`

## 执行边界

- Frozen B2 确定性选取 4 个不同 repair types：`edit`、`emotion`、`information`、`performance`；`camera` 因真实 evidence 不足列为 missing，未伪造样本。
- 每个样本最多 2 次 semantic attempt，总预算 8；实际 6 次 semantic/provider HTTP 请求。
- Provider 只要求 `director_tail_repair_ir_v1`；`json_parse_retries=0`，canonical patch 仍由确定性编译器生成。
- 未运行 15-scene/Full 24、未写入 Production/Storyboard/Shadow，未生成图片/视频，未访问对象存储。

## Protocol Metrics

| 指标 | 结果 |
|---|---:|
| sample_count | 4 |
| repair types | edit / emotion / information / performance |
| semantic attempts | 6 |
| provider HTTP requests | 6 |
| transport retries | 0 |
| JSON parser retries | 0 |
| IR First Pass | 2 / 4（50%）|
| IR Final | 2 / 4（50%）|
| FORMAT_REPAIR attempted | 2 |
| FORMAT_REPAIR success | 0 |
| Canonical Compile | 2 / 2（100% of final-valid）|
| Candidate Contract Pass | 2 / 2（100% of compiled）|
| Request fingerprint non-empty | 6 / 6（100%）|
| Request Echo | 0 |
| Unknown Provider Shape | 0 |
| Fact Override Accepted | 0 |

## First-pass by repair type

| repair_type | First Pass | Final Pass |
|---|---:|---:|
| edit | 1/1 | 1/1 |
| emotion | 0/1 | 0/1 |
| information | 1/1 | 1/1 |
| performance | 0/1 | 0/1 |

两类失败均为严格 IR 字段校验失败：`emotion` 样本出现越界的 `emotion.intensity` 或无效 `performance_emphasis`，`performance` 样本的 `performance_direction` 为空；FORMAT_REPAIR 未能在第二次 attempt 内修复。由于这是 Provider 输出合规问题，系统按 fail-closed 保留回滚，不放宽 Validator 或 canonical contract。

## Gate 结论

**`PROTOCOL_CANARY_FAILED`**。

虽然覆盖达到 4 类且 provenance/fingerprint、canonical boundary 和副作用安全均通过，但 IR First Pass 仅 50%、Final IR 仅 50%，不满足 80%/100% 门槛；因此不满足 `READY_FOR_TARGETED_TAIL_REEVALUATION`，不得自动扩大 Pilot 或进入生产媒体链路。

## 安全结果

production、storyboard、media、image、video、object_storage、production_shadow 均为 **0**。真实结果文件完整保留 provider HTTP 审计、请求三层 fingerprint、schema/shape、usage 与延迟，不保存密钥或原始敏感凭据。
