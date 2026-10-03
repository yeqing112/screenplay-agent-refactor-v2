# PRODUCTION UI V3 REAL PROVIDER FINAL VERTICAL SLICE REPORT

## Final status

- phase: `PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE`
- status: `BLOCKED_IMAGE_REVIEW_PRESERVATION_EVIDENCE_GAP`
- marker: `PRODUCTION_UI_V3_REAL_PROVIDER_FINAL_VERTICAL_SLICE_COMPLETE` **未设置**
- historical IMAGE budget: **4/5, CLOSED**
- VIDEO closure budget v3: **CLOSED_BLOCKED_PROVIDER_BALANCE**；真实调用 **2/3**；应急额度 **1 次未使用且永久关闭**
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

历史 JSON 仍有 execution、candidate identity 和 checksum，但 disposable canary 清理后没有可验证的媒体文件或 public asset，因此不能合法 seed historical Official v1。IMAGE preservation evidence closure 的最小未来真实调用数为 **2 次**（initial + regenerate），且需要独立的 IMAGE budget。

证据：[IMAGE closure analysis](./PRODUCTION_UI_V3_REAL_PROVIDER_IMAGE_EVIDENCE_CLOSURE_ANALYSIS.json)。

## VIDEO closure attempt

本轮正式关闭 `REAL_PROVIDER_VIDEO_CLOSURE_BUDGET_V3`。剩余 1 次 reserve 不会带入后续工作；余额恢复后必须创建全新的 v4 budget。

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
- 新增零调用 VIDEO resume preflight：[VIDEO resume preflight](./PRODUCTION_UI_V3_REAL_PROVIDER_VIDEO_RESUME_PREFLIGHT.json)。

## Zero-call evidence instrumentation

E2E runner now writes authoritative JSON snapshots before the human approval click:

- `IMAGE_REGENERATE_PRE_APPROVAL_STATE.json`
- `VIDEO_REGENERATE_PRE_APPROVAL_STATE.json`
- `VIDEO_SUBMIT_BOUNDARY_STATE.json`
- `VIDEO_RELOAD_IDENTITY_STATE.json`

These snapshots carry candidate, execution, attempt, provider-task identity, current Official pointer and review state. They are capture-ready for the next authorized run; historical IMAGE evidence remains `NOT_PROVEN_BY_FINAL_ARTIFACT`.

达到 COMPLETE 还需要：恢复 MiniMax H3 可用余额，完成 VIDEO initial 与 VIDEO regenerate 的成功生命周期，并补齐 IMAGE review 期间旧 Official 保持 current 的最终证据。本轮不设置 COMPLETE marker。

## Verification

- frontend unit suite: **63 files / 447 tests passed**
- targeted backend generation suite: **77 passed**
- full repository pytest: **1990 passed / 24 failed**；失败集中在既有迁移头版本不一致与旧的 episode/keyframe/storyboard/asset 测试，未进入本轮 real Provider evidence。
- frontend production build: **passed**
- Python compileall: **passed**
- `git diff --check`: **passed**
- attempt-facade suite: **16 passed**。测试现在使用显式 test-only media fixtures 与 authority snapshot resolver；生产 URL validation 仍要求公开 `http(s)` URL。

## V4 real 75API VIDEO follow-up

本轮独立 v4 VIDEO 预算已完成两次真实 75API 尝试，均在 canonical media storage validation 失败；没有生成 provider task、candidate 或 Official VIDEO。v4 应急额度未使用，`VIDEO_REAL_PROVIDER_CLOSURE_COMPLETE` 未设置。

- profile/provider/model: `local-video-ex8l4t` / `75api-minimax-h3` / `minimax_h3_no_audios`
- executions: `4937fd6aaf13495388dfa2de41cd8bd0`, `26c085d1106e4157b595c1e02189a71b`
- production DB SHA before/after: `d729360fae56fe082729962db48d26de272cd956e500b1cda6702328d424c026`（相同）
- 代码修复：canonical VIDEO persistence 现在会向 75API 内容 URL 传递解析后的 Bearer credential；该修复尚未用额外真实调用验证。
- 证据：[V4 VIDEO closure evidence](./PRODUCTION_UI_V3_REAL_PROVIDER_VIDEO_CLOSURE_V4_EVIDENCE.json)。

## Provider-free 75API async zero-call closure

本轮新增 provider-free canonical async 验证，不产生任何真实 Provider 调用。75API 的 submit、poll、authenticated content retrieval 均使用同一个 `runtime_credential_value`；canonical submit 在 poll 前持久化 `RUNNING` 与 provider task identity，reconcile 只使用已持久化 task，不重复 POST。

- 0 次 75API POST / poll / content
- 0 次真实 IMAGE
- 本地 HTTP protocol fixture、MP4 持久化、canonical submit/reconcile、task identity、regenerate lineage 测试通过
- 浏览器级 Production UI V3 reload snapshot 尚未执行，因此不创建 V5 预算，状态保持 `BLOCKED_TECHNICAL_VALIDATION`

证据：[zero-call closure report](./PRODUCTION_UI_V3_75API_CANONICAL_ASYNC_ZERO_CALL_CLOSURE_REPORT.md)；[zero-call closure audit](./PRODUCTION_UI_V3_75API_CANONICAL_ASYNC_ZERO_CALL_CLOSURE.json)。
