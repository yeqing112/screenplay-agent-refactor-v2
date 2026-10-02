# REAL_IMAGE_REVIEW_HARNESS_RAW_V2_RECONCILE

## 状态

`REAL_IMAGE_REVIEW_HARNESS_RAW_V2_RECONCILE_COMPLETE`

本阶段没有调用真实 SHAPI IMAGE、真实 SHAPI VIDEO 或真实 LLM。第 6 次真实 Provider 预算仍冻结。

## 根因与修复

E2E 的 `waitForWorkspaceShot()` 读取 `GET /api/books/{book}/production-workspace-v2` 的 raw Production Workspace V2。此前 Real IMAGE 分支错误读取了只存在于 `productionUiV3.ts` 派生 ViewModel 的 `IMAGE.candidate.reviewEligibility`，导致真实 Candidate 已建立却无法进入审核。

本轮在 E2E runner 增加 `reviewableRawCandidate(lane)`：

- 只从 `latest_execution.candidate_id` 选择 Candidate；
- 在 `candidates.items` / `candidates.latest` 中匹配同一 id；
- 要求 execution 为 `SUCCEEDED`、candidate 为 `MEDIA_CANDIDATE`；
- 仅接受 `TECHNICALLY_VALID`、`REVIEW_REQUIRED`、`PASS`；
- 已成为当前 Official 的 Candidate fail closed；
- 返回 candidate、preview、validation status、execution id 等统一证据。

没有修改 `productionUiV3.ts`、Review service、Promotion API、MediaAuthority 或 Production Workspace V2 schema。

## Provider-free 精确 Real IMAGE 分支

使用：

- `E2E_REAL_IMAGE_STAGING=1`
- `E2E_REAL_IMAGE_SINGLE_CALL=1`
- `E2E_EXTERNAL_RUNTIME=mock`
- `E2E_REAL_IMAGE_PROFILE_ID=builtin-mock-image`

该分支完成了与真实 staging 相同的 UI 链路：

`generate-frame → raw Candidate → 候选媒体审核 → 批准并继续 → Official IMAGE v1`

结果：

| 检查项 | 结果 |
| --- | --- |
| `generate-frame` POST | 1 |
| 真实 SHAPI `/images/generations` | 0 |
| 真实 VIDEO | 0 |
| Candidate raw V2 选择 | PASS |
| latest execution / Candidate id 匹配 | PASS |
| Candidate validation status | `TECHNICALLY_VALID` |
| 候选审核 UI 可见 | PASS |
| “批准并继续” visible + enabled | PASS |
| UI promotion POST | 1 |
| Official v1 | PASS |
| regenerate | 0 |

本次 Candidate 在生成链路中已经建立 `MediaValidationRecord` 与 `validation_id`，因此 Review controller 按正式产品逻辑复用既有 validation id，直接执行 promotion；没有重复发起 validate POST。Promotion 仍由可见 UI 点击触发，未使用 direct API。

## 浏览器与清理证据

- exact Real IMAGE branch：1 次，全部步骤通过；
- 外部 host：0；
- unexpected HTTP 4xx/5xx：0；
- console errors：0；
- duplicate key warnings：0；
- Book 990400 writes：0；
- disposable Book 990453 通过 UI 删除；
- `orphan_rows=0`、`ambiguous_rows=0`、`orphan_media_files=0`；
- mock IMAGE 生成后形成 Official v1，再由清理流程删除；
- 真实 IMAGE 成功证据保留为上一阶段 `aed82ef` 的封板事实，不被本阶段 mock 验证覆盖。

## 测试

- raw V2 candidate helper targeted tests：通过；
- `productionUiV3`：16 tests passed；
- `productWorkspaceShotReview`：15 tests passed；
- `productWorkspaceShotGeneration`：29 tests passed；
- Web related total：60 tests passed；
- Web build：通过；
- `node --check scripts/e2e-production-ui-v3-user-journey.js`：通过；
- Python backend 未修改，无需新增 backend compile pass；
- `git diff --check`：通过；
- Alembic head：`p1q2r3s4t5u6`；
- 新 migration：0。

## 产物

- Truth Audit：`docs/ui-v3/REAL_IMAGE_REVIEW_HARNESS_RAW_V2_RECONCILE_TRUTH_AUDIT.json`
- E2E summary：`output/playwright/real-image-review-harness-raw-v2-reconcile-final/summary.json`
- E2E run：`output/playwright/real-image-review-harness-raw-v2-reconcile-final/run-1.json`
- raw helper test：`scripts/e2e-production-ui-v3-user-journey-raw-helper.test.js`

## 真实 Provider 封板事实

上一阶段的真实 IMAGE Initial 仍为：

- `real_image_initial = GO`；
- response projection、MediaCandidate、MediaValidation、MediaPromotionRecord、媒体完整性均 PASS；
- 真实累计调用保持 `5 / 6`；
- real Official v1 仍未用真实媒体证明，因为真实 Candidate 已随 disposable Book 删除；
- 本阶段没有消耗第 6 次预算。

## 下一步

`STOP — call #6 remains unauthorized`

只有新的明确批准才能决定是否用第 6 次验证真实 IMAGE Initial → Official v1，或扩展预算进行后续工作。
