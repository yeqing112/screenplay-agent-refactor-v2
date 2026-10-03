# PRODUCTION UI V3 REAL PROVIDER FINAL VERTICAL SLICE REPORT

## Final status

- phase: `PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE`
- status: `BLOCKED_INSUFFICIENT_REAL_PROVIDER_BUDGET`
- marker: `PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_COMPLETE` **未设置**
- historical budget: **2/5, CLOSED**
- current budget: **4/5, ACTIVE**
- emergency reserve: **未使用，剩余 1 次**
- blocking rule: 剩余 1 次不能覆盖尚未证明的 VIDEO initial + VIDEO regenerate 两次正常调用；第 5 次也不能用于 application/configuration 问题。

## Zero-call preflight

新的 mock 预检已通过：

- IMAGE：submit → execution → candidate → approve → Official v1 → regenerate → candidate v2 → Official v2
- VIDEO：异步 option 存在、selected value 稳定、submit → RUNNING → reload 后 execution identity 保持 → candidate → approve → regenerate → Official v2
- 外部 host：0
- 失败：0

证据：[zero-call preflight](../../output/playwright/real-provider-final-slice-v2-zero-call-preflight-authoritative/summary.json)。

## Real Provider calls

四次真实调用均为 SHAPI IMAGE，且均成功：

1. IMAGE initial — execution `cc1bfad62e104750bf5b6565193dda4b`
2. IMAGE regenerate — execution `8fbcfa4e9c8b4284affcfbd97ca12edc`
3. IMAGE initial — execution `8fb1e56f6270412ebf658891c26a0534`
4. IMAGE regenerate — execution `f166c8d2af6145339e5baa546a4237d2`

Provider：`shapi-openai-images`；model：`grok-imagine-image-quality`。每次 logical provider calls=1，transport retry=0。两次 canary 均在 VIDEO 阶段前后清理完成，orphan rows/files=0。

IMAGE v2 晋级已证明；由于最终快照的 projection 没有保留 review 中旧 Official 的 current 字段，本轮将“旧 Official 在 review 期间保持 current”记为 **NOT_PROVEN_BY_FINAL_ARTIFACT**，没有把它伪记为通过。

## VIDEO blocking facts

VIDEO selection gate 已经在 mock preflight 中通过，且 real attempt 的浏览器层也确认：

- expected profile: `local-video-7deneh`
- option exists: true
- selected value: `local-video-7deneh`

随后真实 VIDEO 未产生 Provider call。连续修复/验证得到：

- `RUNTIME_CREDENTIAL_NOT_RESOLVED`：已修复 staging 环境变量绑定。
- `MODEL_CAPABILITY_MISMATCH`：已修复 staging profile 的 VIDEO capability/adapter 元数据。
- 当前剩余阻塞：`GENERATION_PROVIDER_PARAM_INVALID`，MiniMax profile 的旧 default_params 含 canonical allowlist 不接受的字段；Provider calls=0。

因此 VIDEO 的 RUNNING、reload identity、candidate v1/v2、Official v1/v2、VIDEO regenerate 均没有真实证据。按照本轮规则，不使用剩余的第 5 次调用。

## Isolation and audit

- production DB SHA256 before/after：`3f04988bfca00ed20233a3a355e381c403409482df176246de32c8451167218d`（相同）
- production DB writes：0
- protected Book 990400 writes：0
- writes outside canary：0
- browser direct Provider calls：0
- browser external Provider hosts：0
- secret leaks：0
- orphan rows：0
- orphan media files：0
- Alembic head：`p1q2r3s4t5u6`
- new migrations：0

## Code and evidence updates

本轮已更新：

- E2E VIDEO submit 前重新选择并断言 model profile，避免 PromptIR rehydrate 清空 selector。
- Model registry 对旧 image/video profile 自动补齐 canonical capability/adapter metadata。
- 增加 MiniMax environment-backed runtime credential binding。
- 更新 Truth Audit、Provider Evidence、Network Audit、Data Audit、Browser QA。

最终权威文件：

- [Truth Audit](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_TRUTH_AUDIT.json)
- [Provider Evidence](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_PROVIDER_EVIDENCE.json)
- [Network Audit](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_NETWORK_AUDIT.json)
- [Data Audit](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_DATA_AUDIT.json)
- [Browser QA](./PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_BROWSER_QA.json)

要达到 COMPLETE，需要新的独立真实 Provider 预算，再完成 VIDEO initial 与 VIDEO regenerate 两次调用；本轮不设置 COMPLETE marker。
