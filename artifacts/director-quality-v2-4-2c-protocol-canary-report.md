# Director Quality V2.4.2c — Typed Repair IR Protocol Canary

## Baseline Audit

V2.4.2b 的 emotion/performance 失败来自 Provider 未看到 intensity range、minItems、minLength 与 required child fields；Validator fail-fast，FORMAT_REPAIR 仅接收纯文本，且一个 sample 被拆成多条 trace。详见 `director-quality-v2-4-2c-gap-audit.md` 的 Baseline 部分。

## Final As-Built Verification

- Semantic Spec SSOT：`director_tail_repair_semantic_spec_v1`
- Frozen samples：4（edit / emotion / information / performance），与 V2.4.2b 完全相同
- Semantic attempts：4（最多预算 8）
- Provider HTTP requests：4
- IR First Pass：4/4（100%）
- IR Final：4/4（100%）
- Canonical Compile：4/4
- Candidate Contract Pass：4/4
- FORMAT_REPAIR attempts：0（四个样本首轮均通过）
- Attempt rejected：0；root-cause rollback：0；scene rollback：0；accepted root-cause：4
- Fact Override Accepted：0
- Request Echo：0
- Unknown Provider Shape：0
- 请求 fingerprint：4/4 非空
- Side effects：production/storyboard/media/image/video/object_storage/production_shadow 全部 0

## Gate

`PROTOCOL_CANARY_PASSED`，并满足 `READY_FOR_TARGETED_TAIL_REEVALUATION`。按 V2.4.2c 规则立即停止，不自动扩大 Pilot。

真实结果 JSON：`artifacts/director-quality-v2-4-2c-protocol-canary-20260914T164228Z.json`
