# PRODUCTION UI V3 REAL PROVIDER FINAL VERTICAL SLICE REPORT

## 状态

- phase: `PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE`
- baseline: `ce9c4c93ccd632fe21dd94e0b7c94ff484933205`
- status: `BLOCKED_REAL_VIDEO_NOT_CONFIGURED_AFTER_CANARY_BUDGET_GUARD`
- target marker `PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_COMPLETE` 未设置。
- 本阶段真实 Provider 预算：`2/5`，剩余 `3`；没有为绕过当前阻塞而重复调用。

## 已完成的真实链路

### IMAGE

独立 staging SQLite 中完成了真实 IMAGE 初次生成和重生成，共 2 次真实调用：

- profile: `local-image-mw4y52`
- provider: `shapi-openai-images`
- model: `grok-imagine-image-quality`
- transport: `shapi-openai-images.image.v1`
- initial execution: `ea054b0e7b834f989792e6ffa577adc3`
- initial candidate: `candidate-3c1ea83d3ca2457aa9eb93bb9e741990`
- initial official: `omv-a44eb0a35c4ca8b6c105e008b89e9dfa51626232`
- regenerate execution: `93ea2c354cfd4a1cbe6b61dbc43ba038`
- regenerate candidate: `candidate-2564a864cf3344919f2451efdc02d88d`
- final official v2: `omv-9cae40c7d65c97022299161fa5f1b0721efca2a6`
- v1 superseded: `true`
- transport retries: `0`

IMAGE 的 Provider 证据、执行身份和候选校验已写入 [Provider Evidence](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_PROVIDER_EVIDENCE.json)。

### VIDEO

VIDEO 尚未完成真实调用。浏览器在 VIDEO 模型选项异步刷新完成前读取到空选择，点击生成被 canonical API 以 `409` 拒绝；没有写入 VIDEO execution，也没有产生真实 VIDEO Provider 账单调用。该问题已在 E2E 编排中增加“等待 option 并确认 selected value”的修复，且失败的 real canary 后续已由 UI 清理，清理审计为 `orphan_rows=0`。

因此以下目标仍未证明：VIDEO running → reload identity → candidate v1 → official v1 → regenerate → candidate v2 → official v2。

## 安全与隔离

- staging DB: `work/db/phase-production-ui-v3-final-slice-20261003.sqlite`
- production DB SHA256 before/after: `3f04988bfca00ed20233a3a355e381c403409482df176246de32c8451167218d`
- production DB writes: `0`
- protected Book `990400` writes: `0`
- browser direct Provider calls: `0`
- browser external hosts: `0`
- secrets leaked in committed artifacts: `0`
- canary cleanup orphan rows/files: `0`

## 验证

- mock full journey preflight: 1 run, all steps passed
- real final attempt: setup steps passed; media step blocked at VIDEO 409
- Web targeted tests: 72 passed
- backend relevant suite: 111 passed
- frontend build: passed
- Python compileall: passed
- Alembic head: `p1q2r3s4t5u6`
- `git diff --check`: passed

证据目录：

- [mock preflight](../../output/playwright/real-provider-final-slice-mock-final/summary.json)
- [real attempt](../../output/playwright/real-provider-final-slice-real-final2/summary.json)
- [Truth Audit](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_TRUTH_AUDIT.json)
- [Provider Evidence](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_PROVIDER_EVIDENCE.json)
- [Network Audit](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_NETWORK_AUDIT.json)
- [Data Audit](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_DATA_AUDIT.json)
- [Browser QA](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_BROWSER_QA.json)

## 后续恢复条件

在新的用户批准预算下，复用已修复的模型选择等待逻辑，创建新的 disposable staging canary，仅执行完整的 4-call IMAGE/VIDEO 纵向切片；不复用已清理 canary，不修改 production DB。
