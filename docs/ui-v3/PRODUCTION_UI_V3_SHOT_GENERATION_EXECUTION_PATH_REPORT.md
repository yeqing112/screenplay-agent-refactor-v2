# Production UI V3 · Shot Generation Execution Path

## Completion marker

`PRODUCTION_UI_V3_SHOT_GENERATION_EXECUTION_PATH_COMPLETE`

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

`createShotStudioGenerationController()` captures shot, episode, lane, model profile, and the current V2 identity. It owns confirmation, submission lock, abort cancellation, error normalization, 409 refresh, and bounded V2 observation. Review mutation activity is a submission gate, and the existing review controller remains the only promotion path.

## Mutation State Machine

`idle → confirming → submitting → refreshing → running | waiting_candidate → candidate_ready | failed | cancelled`. `running` and `waiting_candidate` are emitted only after V2 refresh observation; the controller does not write optimistic execution or candidate state. A response `task_id` produces `V3_LEGACY_GENERATION_TASK_RESPONSE_UNSUPPORTED` and never enters `productWorkspaceRecovery` or localStorage recovery.

## Freshness and Double Submit Guards

At click time the controller re-reads the latest projected Shot Studio view model and requires the exact lane action. Stale, blocked, review, official, wrong lane, missing model, active review mutation, and active generation mutation all fail before POST. A second click while the controller is active returns `GENERATION_MUTATION_LOCKED`. A 409 causes one V2 refresh and never an automatic second POST.

## Canonical Refetch, Execution Projection, and Candidate Projection

POST success always enters the V2 refresh loop, including a response containing `execution` or `candidate`. The aggregate `production-workspace-v2` projection determines running, waiting, review, failed, and official UI states. If execution success is visible before its candidate, the bounded loop reports candidate synchronization and then fails closed with `V3_EXECUTION_CANDIDATE_NOT_VISIBLE`; it never re-submits.

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
  - exact `generate_image` / `generate_video` action gate;
  - stale, blocked, review, official, missing-model and double-submit guards;
  - explicit fee confirmation: “该操作可能调用外部模型并产生费用。”;
  - abort-safe cancellation and legacy `task_id` fail closed;
  - bounded V2-only refresh loop. No optimistic running or candidate state is written.
- `web/src/components/ProductWorkspaceShotStudioV3.tsx`
  - IMAGE and VIDEO generation controls;
  - canonical status evidence and review controls remain separate;
  - image uses `<img>`, video uses `<video controls>`;
  - next action text now distinguishes executable production work, review, processing and blocked states.
- DEV-only generation fixtures and query selector:
  `workspace_v2_generation_fixture=ready-image|running-image|review-image|official-image-ready-video|running-video|review-video|official-shot`.
- `web/src/services/productWorkspaceShotGeneration.test.ts` covers gates, fee confirmation, double submit, V2 recovery, candidate lag, cancellation, legacy response and request contract.
- The controller suite contains **20 tests**, including the full IMAGE→VIDEO loop, 409 refresh/no-retry, source-official gating, no optimistic state, no-localStorage boundary, and provider-call guards.

## Canonical contract evidence

- POST targets remain `/api/books/{bookId}/storyboard/{episode}/{shotId}/generate-frame` and `generate-video`.
- The backend bridge creates or reuses canonical `GenerationExecutionRecord` and `MediaCandidateRecord`.
- The browser controller reads state only from `production-workspace-v2` after submission.
- IMAGE_TO_VIDEO source authority remains the canonical official IMAGE projection; no legacy localStorage recovery is consulted.

## Verification

- Web tests: **57 files / 377 tests passed**.
- Web build: **PASS** (`tsc && vite build`).
- Backend canonical and authority regression: **32 passed**.
- `git diff --check`: recorded before commit.
- QA policy: no real LLM, SHAPI, MiniMax, provider submission, video/image generation, or production write was performed by this QA run.
- Responsive mocked browser QA: **1280 / 1440 / 1920** widths, no horizontal overflow, Shot Studio mounted, console/page errors **0**. Evidence: `shot-generation-responsive-qa.json`.

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

All browser and unit QA uses disposable fixtures or mocked service responses. Real LLM calls, SHAPI calls, MiniMax calls, image/video generation, provider submissions, validation writes, promotion writes, and generation writes are zero. No backend routes or DB migrations were added. `allowExternalCall: true` and `confirmed: true` are only sent by the post-confirmation generation service call; refresh, navigation, filters, and review reads do not submit generation.

## Deferred Retry / Regenerate

`failed → retry_generation` remains visible as `重试生成尚未接入` and disabled. Official/review states do not expose regenerate. Undo, generic reject/request-changes, and cross-shot Review Inbox remain out of scope. Legacy Storyboard and its recovery implementation remain available.

## Completion Status

`PRODUCTION_UI_V3_SHOT_GENERATION_EXECUTION_PATH_COMPLETE`
