# Production UI V3 · Shot Generation Execution Path

## Previous phase completion marker

`PRODUCTION_UI_V3_SHOT_GENERATION_EXECUTION_PATH_COMPLETE`

## Current phase

`PHASE_PRODUCTION_UI_V3_GENERATION_RUNTIME_RECONCILE`

Baseline: `87d35d610d25b57b21ac7014fbddcb1e5bc64413`

Current completion marker: `PRODUCTION_UI_V3_GENERATION_RUNTIME_RECONCILE_COMPLETE`

## Scope

This phase connects the Shot Studio V3 canary to the existing canonical production generation contract:

`ProductionWorkspaceV2Snapshot → productionUiV3 adapter → Shot Studio generation controller → canonical storyboard generation POST → Production Workspace V2 refresh`

The implementation keeps Legacy Storyboard available and does not add a second generation architecture, route, database table, or provider adapter.

## Existing Generation Architecture

V3 reuses `productionGeneration.ts` and the existing storyboard compatibility routes. Those routes delegate to `preview_canonical_generation` and `execute_canonical_generation`; the backend owns `GenerationExecutionRecord`, `MediaCandidateRecord`, request fingerprints, current PromptIR resolution, readiness, source binding, and provider boundary auditing.

## Canonical Endpoint Contract

The two POST endpoints are `/api/books/{bookId}/storyboard/{episode}/{shotId}/generate-frame` and `generate-video`. The canonical response can contain `execution`, `candidate`, `provider_calls`, `reused`, and diagnostic fingerprints. Execution serialization includes `execution_id`, `status`, `target_media`, PromptIR/policy/model/reference fingerprints, provider/model, provider request/task IDs, failure fields, timestamps, and `candidate_id`. Candidate serialization includes `candidate_id`, execution binding, validation status, media/storage metadata, PromptIR and request fingerprints, and provider task ID.

The canonical resolver creates or reuses an execution by `provider_request_fingerprint`, so repeated submissions are idempotent. It re-resolves current PromptIR, generation policy, asset/reference authority, model profile, and IMAGE_TO_VIDEO source before provider submission. Drift and readiness failures return 409 before provider work. `task_id` is not the V3 response contract; V3 fails closed if one appears without the durable execution/candidate shape.

## compileIfMissing Audit

V3 sends `compileIfMissing: false`. The canonical resolver requires a current media-scoped PromptIR pointer and a ready generation payload, so the generation click cannot silently create a prompt version or call an LLM. The request contract test asserts the field is false and that legacy media fields are absent.

## Model Selection Contract

The selected profile comes from `ProductionWorkspaceV2Snapshot` and `lane.professional.model.selected_profile_id`. No first profile, builtin fallback, legacy model string, or V3-local model state is created. Missing selection keeps `generation_readiness.ready` false and the CTA disabled; the backend independently returns `PRODUCTION_MODEL_SELECTION_REQUIRED` when applicable.

## IMAGE Generation Contract

IMAGE is submittable only when `primaryAction.kind === generate_image`, its lane is IMAGE, the lane is ready and generation-allowed, the snapshot is fresh, and a selected model profile exists. After POST, the response is retained for diagnostics only. The controller performs bounded V2 refreshes and waits for the canonical execution/candidate projection before showing review.

## VIDEO Generation Contract

VIDEO follows the same gates with `generate_video`. The V3 caller sends no `firstFrameAssetId` or `referenceAssetIds`; canonical PromptIR, asset bindings, and generation policy resolve those inputs server-side. A VIDEO lane with an existing candidate, official media, stale state, or unsupported mode cannot submit.

## IMAGE_TO_VIDEO Source Contract

The backend resolver calls the current IMAGE_TO_VIDEO source binding path and validates the `OfficialMediaPointer`. The V2 adapter exposes this as `VIDEO.source_official_image`; readiness is false until `isCanonicalOfficial === true`. No adopted image, legacy selected image, localStorage value, or first-frame asset is used.

## Generation Controller Architecture

`createShotStudioGenerationController()` captures shot, episode, lane, model profile, and the current V2 identity. It owns confirmation, submission lock, lifecycle-safe observation abort, error normalization, 409 refresh, and bounded V2 observation. Review mutation activity is a submission gate, and the existing review controller remains the only promotion path. The controller re-reads the V2 projection after the fee confirmation resolves and fails closed if the executable state, model, prompt identity, generation mode, or canonical source identity changed while the dialog was open. Observation abort is not backend/provider cancellation.

## Mutation State Machine

`idle → confirming → submitting → refreshing → running | waiting_candidate → candidate_ready | failed | cancelled`. `running` and `waiting_candidate` are emitted only after V2 refresh observation; the controller does not write optimistic execution or candidate state. A response `task_id` produces `V3_LEGACY_GENERATION_TASK_RESPONSE_UNSUPPORTED` and never enters `productWorkspaceRecovery` or localStorage recovery.

## Freshness and Double Submit Guards

At click time and again immediately before POST (after fee confirmation), the controller re-reads the latest projected Shot Studio view model and requires the exact lane action and captured generation identity. Stale, blocked, review, official, wrong lane, missing model, active review mutation, changed prompt/model/source, and active generation mutation all fail before POST; a change during confirmation returns `GENERATION_FRESHNESS_CONFLICT` with no provider call. A second click while the controller is active returns `GENERATION_MUTATION_LOCKED`. A 409 causes one V2 refresh and never an automatic second POST.

## Canonical Refetch, Execution Projection, and Candidate Projection

POST success always enters the V2 refresh loop, including a response containing `execution` or `candidate`. The aggregate `production-workspace-v2` projection determines running, waiting, review, failed, and official UI states. If execution success is visible before its candidate, the bounded loop reports candidate synchronization and returns `in_progress` / `waiting_candidate` when the observation window ends; it never re-submits. If no execution, candidate, or official projection becomes visible, the controller fails closed with the separate `V3_GENERATION_PROJECTION_NOT_VISIBLE` anomaly.

## Legacy task_id and No-Legacy-Recovery Boundary

V3 does not import or call `productWorkspaceRecovery`, `PendingStoryboardTask`, `ShotExecutionSummary`, `waitForCreativeTask`, or prototyping task endpoints. Legacy Storyboard may continue using those modules independently. V3 does not use legacy adopted state, asset links, or component state as canonical truth.

## Full IMAGE→VIDEO Flow

The integration test drives `IMAGE ready → running → review → explicit APPROVE → IMAGE official / VIDEO ready → VIDEO running → review → explicit APPROVE → IMAGE + VIDEO official`. It asserts exactly one IMAGE POST, one VIDEO POST, one promotion per lane, and no automatic chained VIDEO generation after IMAGE approval.

## Network Audit

The mocked flow records only canonical workspace traffic:

```text
POST /api/books/{bookId}/storyboard/{episode}/{shotId}/generate-frame
GET  /api/books/{bookId}/production-workspace-v2
POST /api/assets/candidates/{candidateId}/promote
GET  /api/books/{bookId}/production-workspace-v2
POST /api/books/{bookId}/storyboard/{episode}/{shotId}/generate-video
GET  /api/books/{bookId}/production-workspace-v2
POST /api/assets/candidates/{candidateId}/promote
GET  /api/books/{bookId}/production-workspace-v2
```

No prompt compile, LLM, unexpected storyboard generation, prototyping task polling, or provider endpoint is used by the V3 mocked flow.

## Delivered

- `web/src/services/productionGeneration.ts`
  - typed execution/candidate response and backend error objects;
  - explicit model profile is required by the caller;
  - `compileIfMissing: false` so generation consumes the current PromptIR;
  - legacy `firstFrameAssetId` and `referenceAssetIds` are not forwarded;
  - HTTP status and backend error code are preserved.
- `web/src/services/productWorkspaceShotGeneration.ts`
  - controller states: `idle`, `confirming`, `submitting`, `refreshing`, `running`, `waiting_candidate`, `candidate_ready`, `failed`, `cancelled`;
  - result outcomes: `candidate_ready`, `in_progress`, `failed`, `cancelled`; `ok=true` means the submission/observation contract stayed safe, not that media is complete;
  - exact `generate_image` / `generate_video` action gate;
  - stale, blocked, review, official, missing-model and double-submit guards;
  - explicit fee confirmation: “该操作可能调用外部模型并产生费用。”;
  - lifecycle-safe `AbortController` observation cleanup and legacy `task_id` fail closed;
  - bounded V2-only refresh loop that preserves long-running/candidate-pending states. No optimistic running or candidate state is written;
  - no post-submit cancel CTA; internal `stopObserving()` never claims backend/provider cancellation.
- `web/src/components/ProductWorkspaceShotStudioV3.tsx`
  - IMAGE and VIDEO generation controls;
  - canonical status evidence and review controls remain separate;
  - image uses `<img>`, video uses `<video controls>`;
  - next action text now distinguishes executable production work, review, processing and blocked states.
- DEV-only generation fixtures and query selector:
  `workspace_v2_generation_fixture=ready-image|running-image|review-image|official-image-ready-video|running-video|review-video|official-shot`.
- Running DEV fixtures now use the canonical V2 `latest_execution.id/state` projection shape, so the browser running surface proves `生成中` instead of an unknown execution state.
- `web/src/services/productWorkspaceShotGeneration.test.ts` covers gates, fee confirmation, double submit, V2 recovery, candidate lag, cancellation, legacy response and request contract.
- The controller suite contains **26 tests**, including the full IMAGE→VIDEO loop, persistent running, candidate projection lag, projection anomaly, immediate canonical failure, stale/blocked observation, post-confirmation freshness recheck, 409 refresh/no-retry, source-official gating, no optimistic state, no-localStorage boundary, and provider-call guards.

## Canonical contract evidence

- POST targets remain `/api/books/{bookId}/storyboard/{episode}/{shotId}/generate-frame` and `generate-video`.
- The backend bridge creates or reuses canonical `GenerationExecutionRecord` and `MediaCandidateRecord`.
- The browser controller reads state only from `production-workspace-v2` after submission.
- IMAGE_TO_VIDEO source authority remains the canonical official IMAGE projection; no legacy localStorage recovery is consulted.

## Long-running Execution Semantics

`maxRefreshAttempts` bounds only foreground observation. If the latest canonical V2 projection still reports an active/running execution when the window ends, the controller returns `ok=true`, outcome `in_progress`, mutation state `running`, and a message that the backend task continues in the background. Foreground timeout is not generation failure, and the local mutation lock is released; the next page load reads the same state from `ProductionWorkspaceV2Snapshot`.

## Foreground Observation Boundary

The controller makes one bounded V2 refresh loop for the active mutation. It does not create a timer per shot or persist runtime state in React/localStorage. After the loop returns `in_progress`, the canonical lane remains responsible for preventing a duplicate generation action.

## Candidate Projection Pending Semantics

When V2 proves `SUCCESS` and exposes an execution `candidate_id` but the candidate projection is still absent, the mutation state is `waiting_candidate` and the result is `ok=true`, outcome `in_progress` after the observation window. The UI says `生成已完成，正在同步候选结果` and does not reopen Generate. A POST with no execution, candidate, or official projection produces the independent `V3_GENERATION_PROJECTION_NOT_VISIBLE` sync anomaly.

## True Failure Contract

Canonical `failed` / `ERROR` execution evidence fails immediately with the adapter/backend reason code. `stale` and `blocked` V2 states also stop observation and fail closed with their canonical reason. They are not converted into a generic candidate visibility timeout.

## Generation Cancellation Semantics

Before POST, the fee confirmation dialog can decline and the generation request count remains zero. After POST, Shot Studio renders no `取消生成` button. Internal `stopObserving()` and lifecycle `dispose()` only abort the foreground fetch/sleep/observation; they may return `in_progress` with `已停止前台等待；后台生成任务可能仍在运行。` and never mark the canonical lane cancelled.

## Backend Cancel Capability

`GenerationExecution`, canonical generation routes, and provider runtime expose no verified cancel contract in this phase. Backend/provider cancellation is **NOT_SUPPORTED**. No cancel endpoint, DELETE execution call, or provider cancel request was added. `AbortController != backend generation cancellation`.

## Tests

- Directed controller tests: **26 passed**, covering ready IMAGE/VIDEO, explicit model gate, stale/review/official/blocked gates, fee cancellation, post-confirmation freshness conflict, double-submit lock, persistent running, candidate projection pending, projection anomaly, immediate canonical failure, stale/blocked observation, stop-observing semantics, abort cleanup, no optimistic state, V2 recovery, 409 no-retry, legacy `task_id` fail-closed, IMAGE_TO_VIDEO source authority, and the full IMAGE→VIDEO approval loop.
- Directed Shot Studio, review, and `productionUiV3` tests are included in the full Web suite below.
- Backend canonical tests: `tests/test_phase_j3_canonical_generation.py`, `tests/test_generation_execution_foundation.py`, and `tests/test_asset_promotion_runtime.py`.

## Browser QA

- DEV-only mocked fixtures mounted successfully for `ready-image`, `running-image`, `review-image`, `official-image-ready-video`, `running-video`, `review-video`, and `official-shot`.
- Long-running mocked observation sequence `ready-image → submit → running-image → running-image → running-image` remains `running` after the foreground window and renders the background-progress message; no cancel request is emitted. Evidence: `shot-generation-browser-qa.json` and the persistent-running controller test.
- Browser console/page errors: **0**. Evidence: `shot-generation-browser-qa.json`.

## Responsive QA

- Mocked Shot Studio checked at **1280×900**, **1440×900**, and **1920×1080**; `scrollWidth === innerWidth` at every width and console/page errors are **0**. Evidence: `shot-generation-responsive-qa.json`.

## Verification

- Web tests: **57 files / 385 tests passed**.
- Web build: **PASS** (`tsc && vite build`).
- Backend canonical and authority regression: **32 passed**.
- `git diff --check`: recorded before commit.
- QA policy: no real LLM, SHAPI, MiniMax, provider submission, video/image generation, provider cancellation, or production write was performed by this QA run.
- Responsive mocked browser QA: **1280 / 1440 / 1920** widths, no horizontal overflow, Shot Studio mounted, running state visible, cancel CTA absent, console/page errors **0**. Evidence: `shot-generation-responsive-qa.json`.
- Refresh recovery test restores a `running` lane from the V2 projection with no React runtime state or localStorage payload.
- The controller performs one bounded V2 observation loop for the active mutation; it does not create a timer per shot, so the existing 100-shot stress surface remains a single aggregate projection.

## Visual evidence

The following evidence files are saved with this report when browser capture is available:

- `shot-generation-image-ready.png`
- `shot-generation-image-running.png`
- `shot-generation-image-review.png`
- `shot-generation-video-ready.png`
- `shot-generation-video-running.png`
- `shot-generation-video-review.png`
- `shot-generation-shot-official.png`

- `shot-generation-responsive-qa.json`
- `shot-generation-browser-qa.json`

All captures use the DEV fixture selector and therefore do not invoke a provider.

## Known boundary

The canonical POST still represents the backend’s preview-plus-execute compatibility bridge. Shot Studio treats its response as an execution acknowledgement and waits for the V2 projection to expose `running`, candidate review, or official state before presenting the next action.

## Review Path Regression

The existing explicit APPROVE path remains unchanged: validation and promotion are separate, canonical pointer/currentness evidence is required, stale candidates and 409 conflicts fail closed, and undo/request-changes/review inbox are not introduced. Confirmed evidence prefers the canonical official preview and falls back to an evidence placeholder when no preview URL exists. VIDEO review evidence uses `<video controls>`.

## Production Safety

All browser and unit QA uses disposable fixtures or mocked service responses. Real LLM calls, SHAPI calls, MiniMax calls, image/video generation, provider submissions, provider cancellation, validation writes, promotion writes, and generation writes are zero. No backend routes or DB migrations were added. `allowExternalCall: true` and `confirmed: true` are only sent by the post-confirmation generation service call; refresh, navigation, filters, review reads, and stop-observing cleanup do not submit generation or cancellation requests.

## Deferred Retry / Regenerate

`failed → retry_generation` remains visible as `重试生成尚未接入` and disabled. Official/review states do not expose regenerate. Undo, generic reject/request-changes, and cross-shot Review Inbox remain out of scope. Legacy Storyboard and its recovery implementation remain available.

## Completion Status

`PRODUCTION_UI_V3_GENERATION_RUNTIME_RECONCILE_COMPLETE`
