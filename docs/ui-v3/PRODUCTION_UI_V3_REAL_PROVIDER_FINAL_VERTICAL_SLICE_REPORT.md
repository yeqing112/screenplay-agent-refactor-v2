# PRODUCTION UI V3 REAL PROVIDER FINAL VERTICAL SLICE REPORT

## Final status

- phase: `PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE`
- status: `BLOCKED_IMAGE_REVIEW_PRESERVATION_EVIDENCE_GAP`
- marker: `PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_COMPLETE` **未设置**
- historical IMAGE budget: **4/5, CLOSED**
- VIDEO closure budget v3: **2/3 used**；正常调用链仍未完成；应急额度 **1 次未使用**
- IMAGE review preservation evidence: **NOT_PROVEN_BY_FINAL_ARTIFACT**

## Zero-call preflight

此前 mock vertical slice 通过了 IMAGE 与 VIDEO 的 UI、selector、PromptIR、RUNNING/reload、审核和清理路径，外部 host 为 0，失败为 0。证据：[zero-call preflight](../../output/playwright/real-provider-final-slice-v2-zero-call-preflight-authoritative3/summary.json)。

## Historical real IMAGE calls

四次真实调用均为 SHAPI IMAGE，且均成功：

1. IMAGE initial — `cc1bfad62e104750bf5b6565193dda4b`
2. IMAGE regenerate — `8fbcfa4e9c8b4284affcfbd97ca12edc`
3. IMAGE initial — `8fb1e56f6270412ebf658891c26a0534`
4. IMAGE regenerate — `f166c8d2af6145339e5baa546a4237d2`

IMAGE v2 晋级已证明；最终快照没有保留 review 中旧 Official 的 current 字段，因此该项继续记为 **NOT_PROVEN_BY_FINAL_ARTIFACT**，没有补写为通过。

## VIDEO closure attempt

本轮 VIDEO 专用 staging canary 使用了保留权威身份的 mock IMAGE。真实传输边界把源图映射到已推送的公开 fixture URL；源 OfficialMedia authority、checksum、PromptIR 和 lineage 没有被改写。

Selector、canonical payload、runtime credential、VIDEO capability、adapter、transport binding 和 provider-neutral validation 均通过：

- profile: `local-video-7deneh`
- provider: `minimax-h3-async`
- adapter: `video_generic`
- transport: `minimax-h3-async.video.v1`
- public source URL gate: PASS

实际 Provider 结果：

1. VIDEO initial — execution `c744b569c3474b19a548eef314cbb9d3`：HTTP 400，错误 `2013 image_url.url must be a public http(s) URL`。该应用问题已修复。
2. VIDEO initial retry — execution `848741711c0842d08c419bbe64c4c347`：HTTP 402，错误 `1008 H3 account balance insufficient`。

两次调用都没有返回 Provider task/request ID，因此没有声称 RUNNING、reload identity、candidate、Official v1/v2 或 regenerate 成功。余额不足属于账户/Provider 配置问题，未消耗应急额度。

证据：[VIDEO closure evidence](./PRODUCTION_UI_V3_REAL_PROVIDER_VIDEO_CLOSURE_EVIDENCE.json)。

## Isolation and cleanup

- production DB SHA256 before/after：`3f04988BFCA00ED20233A3A355E381C403409482DF176246DE32C8451167218D`（相同）
- production DB writes：0
- protected Book 990400 writes：0
- browser direct Provider calls：0
- browser external hosts：0
- secret leaks：0
- disposable VIDEO canary：已通过 UI 删除
- orphan rows/files：0
- ambiguous rows：0
- Alembic head：`p1q2r3s4t5u6`

## Code and evidence updates

- canonical VIDEO source handoff 支持 staging 公开 fixture URL，避免把本地 `/api/...` 路径提交给真实 Provider。
- VIDEO E2E 在 PromptIR/selector refresh 后重新选择 profile，并支持失败 execution 的可见重试入口。
- 新增公开 fixture：`fixtures/video-canary-source.png`。
- 更新 Truth Audit、Provider Evidence、Network Audit、Data Audit、Browser QA。

达到 COMPLETE 还需要：恢复 MiniMax H3 可用余额，完成 VIDEO initial 与 VIDEO regenerate 的成功生命周期，并补齐 IMAGE review 期间旧 Official 保持 current 的最终证据。本轮不设置 COMPLETE marker。

## Verification

- targeted backend generation suite: **51 passed**
- frontend production build: **passed**
- Python compileall: **passed**
- `git diff --check`: **passed**
- the existing attempt-facade suite still has local fixture validation failures (`local://...`); those failures are recorded as pre-existing and were not counted as closure evidence.
