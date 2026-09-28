# AI Director Runtime Foundation Report

## Phase

`PHASE_AI_DIRECTOR_RUNTIME_FOUNDATION` — `AI_DIRECTOR_RUNTIME_FOUNDATION_COMPLETE`

- Implementation commit: `931b666d04bc1d908abad8d0deff6b3c7edd11a2`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Migration head: `h9c0d1e2f3g4`

## Delivered

- Added provider-free `director_plan(script_ir, episode_context, character_profiles, scene_profiles)` adapter.
- Added versioned `DirectorPlan` and `ScenePlan` persistence. Existing scene-level `ShotPlan` remains the canonical shot-plan table and now records Director lineage.
- Added explicit structured `ShotDirection` candidates and `GenerationIntent` candidates with source hashes and prompt-lineage identifiers.
- Added API routes:
  - `POST /episodes/{id}/director-plan` (also mounted under `/api`)
  - `GET /episodes/{id}/director-plan`
  - `POST /shots/{id}/director-revise`
- Added additive Alembic revisions `g8b9c0d1e2f3` and `h9c0d1e2f3g4`.

## Contract and truth boundary

- No real LLM is imported or called by the runtime adapter.
- No image/video generation is submitted. The existing image provider remains SHAPI (`https://www.shapi.vip/`) in the prior provider registry; this phase only emits reviewable intent.
- Source Fact and ScriptIR inputs are deep-copied, hashed, and carried as immutable lineage references. The adapter marks `source_fact_mutated=false` and `script_ir_mutated=false`.
- POST creates a `DRAFT` version; a newer version supersedes the prior draft. Shot revision is whitelist-limited and creates a new version, preserving the prior version.
- Human review remains required before authority activation or downstream generation.

## Verification

- `pytest -q` — **1911 passed** on the current branch (including downstream runtime migrations).
- `pytest -q tests/test_ai_director_runtime_foundation.py tests/test_migration_chain_hardening.py` — **10 passed** after the final ShotDirection migration.
- `npm run test:golden` — **5/5 passed**.
- `python -m scripts.verify_migration_chain --ci` — **PASS**; fresh upgrade, repeat upgrade, legacy fixtures, schema, and metadata drift all passed (current repository head `m4h5i6j7k8l9`).
- `python -m compileall -q api core models scripts tests` — **PASS**.
- `git diff --check` — **PASS**.

## Migration and lineage

`DirectorPlan` stores episode/version/status/creator/reasoning trace plus source ScriptIR hash, scene plans, shot plans, shot-direction candidates, generation intents, and payload hash. `ScenePlan` rows retain location/time/mood/characters/visual requirements and source lineage. Each shot carries a direction fingerprint, generation-intent ID, and prompt-lineage ID. No automatic authority pointer or media promotion is created.

## Known scope boundary

This foundation stops at a structured, versioned, human-reviewable production plan. It intentionally does not bind an LLM, call SHAPI, create media, mutate scripts, or remove review gates.
