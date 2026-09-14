# Director Quality V2.4.1 Pilot Postmortem

## 审计结论

V2.4.1 的 fail-closed、rollback 与安全边界均有效，但其 `IR First Pass Valid = 0%` 不能直接解释为 MiMo 无法生成 Repair IR。真实 runner 与 Executor 使用了两个确定性冲突的 output contract：

- runner system prompt 要求 `director_creative_patch_v1`；
- runner `required_keys` 要求 `schema_version`、`patches`、`auxiliary_shot_proposals`；
- provider-bound Executor 同时设置 `require_repair_ir=True`，只接受 `director_tail_repair_ir_v1`。

因此，模型收到的是 canonical patch 输出指令，而接收边界验证的是 Repair IR。该污染根因应记录为 `PROVIDER_EXECUTOR_CONTRACT_MISMATCH`，而不是 `MIMO_IR_INCAPABLE`。

## Retry 与计数审计

Executor 每个 root cause 最多两次业务尝试（`CREATIVE_GENERATION` + `FORMAT_REPAIR` 或 `SEMANTIC_REPAIR`）。V2.4.1 runner 调用 `call_llm_json` 时没有显式关闭 parser retry；`call_llm_json` 默认 `json_parse_retries=1`，required keys 不满足时会再次发起 LLM 请求。因此报告中的 54 次是 27 个 root cause 的 54 次 semantic/业务 attempts，不足以证明 54 次 HTTP requests；当时没有完整 provider HTTP request audit 证据。

## 已验证的安全结果

- 所有不合规输出均被拒绝并回退 baseline；
- canonical `director_creative_patch_v1` contract 未修改或放宽；
- 未产生 Production、Storyboard、Shadow、媒体或对象存储副作用；
- 不应根据旧失败输出增加 alias 或放宽 parser。

## V2.4.2 修复要求

后续实现必须让 Request → Provider → `director_tail_repair_ir_v1` → typed validator → deterministic compiler 的 contract 由单一来源生成；provider adapter 使用 IR required keys 与 IR system prompt；`json_parse_retries=0`，业务级 retry 由 Executor 唯一拥有；transport retry、parser retry 与 semantic attempts 分开计量，并在 preflight 自动阻断任何 contract 漂移。
