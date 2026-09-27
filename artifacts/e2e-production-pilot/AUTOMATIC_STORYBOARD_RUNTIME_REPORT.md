# Automatic Storyboard Runtime Foundation Report

## Completion

`AUTOMATIC_STORYBOARD_RUNTIME_COMPLETE`

- Phase: `PHASE_AUTOMATIC_STORYBOARD_RUNTIME`
- Implementation commit: `83995f5f91815a8468dbf2af6491b0e0315635f3`
- Migration head: `k2f3g4h5i6j7`
- Branch: `codex/visual-authoring-provider-canary-reconcile`

## Delivered

- Added versioned, reviewable `StoryboardPlan` and `StoryboardPlanShot` draft tables.
- Added deterministic projection from validated `DirectorReasoningIR` to storyboard drafts.
- Added provider-free endpoints:
  - `POST /episodes/{id}/storyboard/generate`
  - `GET /episodes/{id}/storyboard`
  - `POST /episodes/{id}/storyboard/compile`
  - `POST /episodes/{id}/storyboard/{version}/rollback`
- Generation persists only `REVIEW_REQUIRED` storyboard drafts. It does not create production `StoryboardShot` or `ShotPlan` rows.
- Compile validates scene, character, style, camera, ordering and duration references, then creates blocked draft `ShotPlan` rows and returns GenerationIntent and PromptVersion candidates with lineage.
- Added storyboard lineage columns to `ShotPlan`, `ProductionGenerationIntent` and `ProductionPromptVersion`.
- Added rollback behavior that supersedes compiled draft ShotPlans while preserving source records.

## Safety and authority boundary

- No ScriptIR or Source Fact mutation.
- Human review remains required on every generated storyboard.
- No real LLM/provider transport was called; the runtime accepts the deterministic Mock adapter only.
- No image generation, video generation, publishing or automatic approval was performed.
- Production `StoryboardShot` is not used as the draft layer.

## Verification

- `pytest -q tests/test_automatic_storyboard_runtime.py`: **4 passed**.
- `pytest -q tests/test_director_llm_adapter_runtime.py tests/test_director_reasoning_runtime.py`: **15 passed**.
- `pytest -q`: **1899 passed**.
- `python -m scripts.verify_migration_chain --ci`: **PASS**, fresh/repeat/legacy/drift, head `k2f3g4h5i6j7`.
- `npm run test:golden`: **5 passed, 0 failed**.
- `git diff --check`: **PASS**.

## Known scope

GenerationIntent and PromptVersion are returned as compile candidates and carry complete storyboard lineage. Existing production materialization remains behind its established review and authority gates.
