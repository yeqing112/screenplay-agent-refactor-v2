# Video Generation Runtime Report

## VIDEO_GENERATION_RUNTIME_COMPLETE

- **Implementation commit:** `5a56257` (`feat: add provider-free video generation runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Migration head:** `e6f7a8b9c0d1`
- **Image generation provider:** [SHAPI](https://www.shapi.vip/)
- **Existing image transport contract:** `shapi-openai-images.image.v1` via `https://shapi.vip/v1`
- **Video provider calls in this runtime slice:** `0` (Mock Video Provider only)

## Delivered runtime

- `VideoGenerationIntent` persists shot-scoped duration, aspect ratio, motion profile, first/last keyframe assets, prompt version, execution reference, and task reference.
- Video intent creation validates the existing `StoryboardShot`, ordered keyframes, current Asset Authority/Version/Pointer bindings, and immutable Production Prompt Version lineage.
- `VideoProviderAdapter` and `MockVideoProvider` expose a provider-neutral video contract and deterministic data URI output without network access.
- Execution reuses `GenerationExecutionRecord`, `TaskRun`, `MediaCandidateRecord`, media validation, and promotion/review linkage; no parallel task, asset, prompt, or model registry is introduced.
- Keyframe asset fingerprints now include `keyframe_id`, allowing the same authoritative scene/character/prop asset to be bound independently to multiple frames.
- APIs are available at both stable and `/api` paths:
  - `GET /shots/{shot_id}/video-intent`
  - `POST /shots/{shot_id}/video-intent`
  - `POST /video-generation/{intent_id}/execute`

## Verification

- `pytest -q tests/test_video_generation_runtime.py` — **5 passed, 0 failed**
- Focused runtime/migration/media regression — **41 passed, 0 failed**
- `pytest -q` — **1865 passed, 0 failed**
- `npm run test:golden` — **5/5 passed**
- `python -m scripts.verify_migration_chain` — **PASS**; fresh/repeated upgrade, legacy replay, schema drift
- `python -m compileall -q api core models scripts` — **PASS**
- `git diff --check` — **PASS**

## SHAPI handoff and provider boundary

The existing image-generation contract remains SHAPI at `https://shapi.vip/v1`. This phase does not invoke SHAPI or any real video provider. Video execution is intentionally provider-free and emits a Mock Video Provider candidate so the production lineage, execution, validation, and review chain can be audited without external side effects.
