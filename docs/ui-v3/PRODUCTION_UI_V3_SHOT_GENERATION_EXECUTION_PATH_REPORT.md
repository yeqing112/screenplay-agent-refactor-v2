# Production UI V3 · Shot Generation Execution Path

## Completion marker

`PRODUCTION_UI_V3_SHOT_GENERATION_EXECUTION_PATH_COMPLETE`

## Scope

This phase connects the Shot Studio V3 canary to the existing canonical production generation contract:

`ProductionWorkspaceV2Snapshot → productionUiV3 adapter → Shot Studio generation controller → canonical storyboard generation POST → Production Workspace V2 refresh`

The implementation keeps Legacy Storyboard available and does not add a second generation architecture, route, database table, or provider adapter.

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

## Canonical contract evidence

- POST targets remain `/api/books/{bookId}/storyboard/{episode}/{shotId}/generate-frame` and `generate-video`.
- The backend bridge creates or reuses canonical `GenerationExecutionRecord` and `MediaCandidateRecord`.
- The browser controller reads state only from `production-workspace-v2` after submission.
- IMAGE_TO_VIDEO source authority remains the canonical official IMAGE projection; no legacy localStorage recovery is consulted.

## Verification

- Web tests: **57 files / 365 tests passed**.
- Web build: **PASS** (`tsc && vite build`).
- Backend canonical and authority regression: **32 passed**.
- `git diff --check`: recorded before commit.
- QA policy: no real LLM, SHAPI, MiniMax, provider submission, video/image generation, or production write was performed by this QA run.

## Visual evidence

The following evidence files are saved with this report when browser capture is available:

- `shot-generation-image-ready.png`
- `shot-generation-image-running.png`
- `shot-generation-image-review.png`
- `shot-generation-video-ready.png`
- `shot-generation-video-running.png`
- `shot-generation-video-review.png`
- `shot-generation-shot-official.png`

All captures use the DEV fixture selector and therefore do not invoke a provider.

## Known boundary

The canonical POST still represents the backend’s preview-plus-execute compatibility bridge. Shot Studio treats its response as an execution acknowledgement and waits for the V2 projection to expose `running`, candidate review, or official state before presenting the next action.

