# Episode Rendering Runtime Report

## EPISODE_RENDERING_RUNTIME_COMPLETE

- **Implementation commit:** `f879e44` (`feat: add episode rendering runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Migration head:** `f7a8b9c0d1e2`
- **Image generation provider:** [SHAPI](https://www.shapi.vip/)
- **Existing image transport contract:** `shapi-openai-images.image.v1` via `https://shapi.vip/v1`
- **Provider calls in this runtime slice:** `0` (tests use an injected provider-free runner)

## Delivered runtime

- `EpisodeRenderPlan` persists the episode scope, render strategy, state, and linked `ProductionBatch`.
- `EpisodeRenderItem` persists every storyboard shot, contiguous order, dependency edges, queue status, and linked `ProductionBatchItem`.
- Dependency validation rejects missing shots, duplicate or non-contiguous order, self-dependencies, dependency cycles, and dependencies that occur after their dependent shot.
- The state machine is durable and fail-closed: `DRAFT → PREPARING → GENERATING → REVIEWING → COMPLETED`, with `FAILED` recovery gated by `retry_failed=true`.
- Episode rendering creates and runs the existing `ProductionBatch`, `ProductionBatchItem`, `TaskRun`, and `GenerationExecutionRecord` chain. It does not create a second task, asset, execution, or model registry.
- Generation completion stops at `REVIEWING`; an explicit review confirmation is required before `COMPLETED`. No automatic editing, audio, subtitles, or publishing is performed.
- APIs are available at both stable and `/api` paths:
  - `GET /episodes/{id}/render-plan`
  - `POST /episodes/{id}/render-plan`
  - `POST /episodes/{id}/render`
  - `GET /episodes/{id}/render-status`
  - `POST /episodes/{id}/render/complete` (explicit review completion gate)

## Verification

- `pytest -q tests/test_episode_rendering_runtime.py` — **5 passed, 0 failed**
- Focused episode/batch/migration regression — **38 passed, 0 failed**
- `pytest -q` — **1870 passed, 0 failed**
- `npm run test:golden` — **5/5 passed**
- `python -m scripts.verify_migration_chain` — **PASS**; fresh/repeated upgrade, legacy replay, schema drift
- `python -m compileall -q api core models scripts` — **PASS**
- `git diff --check` — **PASS**

## Boundary and reuse audit

Episode rendering is an orchestration layer over existing production authority and execution records. It queues shots through `ProductionBatch`, preserves per-shot `GenerationExecution` and `TaskRun` lineage, and leaves media validation/review/promotion as the existing explicit boundary. The existing SHAPI image contract remains unchanged; this phase performs no external provider or storage call.
