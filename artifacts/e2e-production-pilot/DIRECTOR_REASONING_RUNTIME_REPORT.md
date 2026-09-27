# Director Reasoning Runtime Report

## Phase

`PHASE_DIRECTOR_REASONING_RUNTIME` — `DIRECTOR_REASONING_RUNTIME_COMPLETE`

- Implementation commit: `70b67a36afe4353754c3e401e27b231edeee823e`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Migration head: `i0d1e2f3g4h5`

## Delivered

- Added provider-free `DirectorReasoningIR` runtime with deterministic `director_reason(episode_context, script_ir, scene_context)` adapter.
- Added versioned `DirectorReasoning`, `StoryBeat`, and `VisualDecision` authority records.
- Added fail-closed compile path: `DirectorReasoningIR → StoryBeat → VisualDecision → ShotPlan → GenerationIntent → PromptVersion`.
- Added reasoning lineage fields to existing `ShotPlan` and `ProductionGenerationIntent` records.
- Added API routes for create, query, compile, and rollback under root and `/api` mounts.
- Added additive migration `i0d1e2f3g4h5` with legacy-table tolerance.

## Truth and review boundaries

- No real LLM/provider call was made (`llm_called=false`).
- No image or video generation was submitted.
- ScriptIR and Source Fact inputs are copied, hashed, and retained as immutable lineage references; the compiler does not update either source.
- Compile errors return a blocked result before ShotPlan writes.
- Human review is required before downstream authority activation or media generation.
- Rollback marks compiled draft plans superseded while preserving all versions and lineage.

## Verification

- `pytest -q tests/test_director_reasoning_runtime.py`: **5 passed**.
- `pytest -q tests/test_migration_chain_hardening.py`: **7 passed**.
- `python -m scripts.verify_migration_chain --ci`: fresh upgrade, repeat upgrade, legacy fixtures, and drift checks passed; head `i0d1e2f3g4h5`.
- `npm run test:golden`: **5 passed, 0 failed**.
- `git diff --check`: passed.

## Files

- `core/director_reasoning.py`
- `models/director_reasoning.py`
- `api/director_reasoning_api.py`
- `alembic/versions/i0d1e2f3g4h5_add_director_reasoning_ir.py`
- `tests/test_director_reasoning_runtime.py`

