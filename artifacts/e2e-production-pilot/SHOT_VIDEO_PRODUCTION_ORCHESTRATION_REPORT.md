# Shot Video Production Orchestration Report

## Phase

`PHASE_SHOT_VIDEO_PRODUCTION_ORCHESTRATION` — `SHOT_VIDEO_PRODUCTION_ORCHESTRATION_COMPLETE`

- Implementation commit: `e2903d4`

## Delivered

- Added a thin shot-scoped orchestration boundary in `core/shot_video_production.py`.
- Reconciles current Storyboard materialization, ShotDirection, AutomaticKeyframePlan, official START/END keyframe assets, production GenerationIntent, VIDEO PromptIR, and Model Registry profile into the existing `VideoGenerationIntent`.
- Reuses the existing `GenerationExecutionRecord`/`TaskRun`, `MinimaxH3VideoProvider`, `MediaCandidateRecord`, technical validation, review, and OfficialMedia promotion paths.
- Added `POST /shots/{id}/video-production`, `GET /shots/{id}/video-production`, and `POST /shots/{id}/video-production/reconcile`.
- Added strict source fingerprints, in-flight execution reuse, stale guards before validation and before OfficialMedia promotion, and reject/request-change revisioning.
- API source responses now expose a JSON-safe lineage projection; internal ORM rows never cross the response boundary.

## Guardrails

- Default execution remains provider-free deterministic mock execution; real MiniMax H3 stays behind the existing Model Registry/canary gates.
- No image generation is called in this phase. Existing image assets remain the approved upstream inputs; the configured image provider remains SHAPI (`https://www.shapi.vip/`).
- No source facts, ScriptIR, ShotDirection, AutomaticKeyframePlan, or KeyframeSequence authority is mutated.
- Candidates remain retained history when a source becomes stale; promotion is blocked until a current source is reconciled.
- Human review remains required before OfficialMedia promotion.

## Verification

- `pytest -q` — **1926 passed**.
- Focused orchestration and adjacent runtime suites — **76 passed**.
- `npm run test:golden` — **5/5 passed**.
- `python -m scripts.verify_migration_chain --ci` — **PASS**, fresh/repeat/legacy/drift; head `m4h5i6j7k8l9`.
- `python -m compileall -q core api models scripts tests` — **PASS**.
- `git diff --check` — **PASS**.

## Scope boundary

This phase stops at the existing video candidate and review/promotion authorities. It does not introduce a second video queue, provider manager, asset manager, or review system, and it does not call the real provider by default.
