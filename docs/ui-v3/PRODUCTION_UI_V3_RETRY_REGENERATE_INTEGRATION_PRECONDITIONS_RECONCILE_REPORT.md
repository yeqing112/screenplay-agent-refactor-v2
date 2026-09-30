# Production UI V3 Retry / Regenerate Integration Preconditions Reconcile Report

## Phase

`PHASE_PRODUCTION_UI_V3_RETRY_REGENERATE_INTEGRATION_PRECONDITIONS_RECONCILE`

Baseline: `d608c19af0b741967ea34c12fd74100d42f631a6`  
Branch: `codex/visual-authoring-provider-canary-reconcile`  
Date: `2026-10-01`

## Completion marker

`PRODUCTION_UI_V3_RETRY_REGENERATE_INTEGRATION_PRECONDITIONS_RECONCILE_COMPLETE`

## Result

The backend and review-state prerequisites for a future V3 Retry / Regenerate UI are reconciled. A new shot-level intent facade now resolves the business shot from the URL, binds Retry to the current V2 lane execution, resolves Regenerate from the backend Official pointer, and returns an attempt confirmation without starting execution or calling a provider. V3 Retry and Regenerate controls remain disabled until a later integration phase.

## Why integration was not started directly

The existing Foundation route accepts lower-level attempt inputs. A UI integration before the business facade and review controller were reconciled could have allowed a stale Retry source, a client-selected historical Official, or a second Regenerate while a candidate was awaiting review. This phase closes those preconditions first and keeps the existing Legacy UI and execution runtime unchanged.

## Shot-level intent creation contract

Added:

`POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-attempts`

The contract accepts `operationKind` (`RETRY` or `REGENERATE`), `targetMedia`, an idempotency key, and an optional reason. Retry accepts only `sourceExecutionId`; Regenerate accepts neither a source execution nor a client-selected Official version. The response includes the durable Attempt and confirmation token plus explicit `providerCalls=0`, `executionCreated=false`, and `mediaGenerated=false` evidence.

The Foundation `/generation/attempt-intents` route remains available to internal callers. The future UI contract is the shot-level facade and does not require the UI to resolve durable shot ids or Official history.

## Retry source resolution

- The facade reuses `resolve_current_production_lane`, including V2 ordering by `created_at DESC, id DESC`.
- The source must belong to the URL book, episode, durable storyboard shot, and target media lane.
- The source must be the current lane `latest_execution` and have status `FAILED`.
- Older failed executions and successful executions are rejected.
- The operation creates only a GenerationExecutionAttemptLineage row; it does not create an execution or candidate.

## Regenerate source resolution

- The current Official version id is read from the backend V2 Official projection.
- A client-supplied `sourceOfficialMediaVersionId` or `sourceExecutionId` is rejected.
- A broken, missing, historical, or non-current pointer fails closed.
- A pending unpromoted candidate blocks a new Regenerate.
- An active lane execution blocks a new Regenerate.
- IMAGE and VIDEO lanes use the same contract and existing lineage service.

## Idempotency replay

The operation key is scoped to the book and shot. A same-key request with the same operation semantics returns the existing Attempt and confirmation before re-evaluating current lane or pointer state. A scope or semantic mismatch returns a conflict. This preserves replay after a lane execution or Official pointer changes.

## Provider safety

Intent creation does not call a provider, create a GenerationExecution, create a MediaCandidate, create or move an Official pointer, or invoke an LLM. Preview and execute remain explicit downstream actions on the existing canonical executor.

## Official plus Candidate coexistence

The V3 review controller now treats a technically valid newer Candidate as reviewable while an older Official remains current. It still rejects the candidate that already backs the current Official and fails closed for any Official pointer reason code. The fixture and tests cover C1 Official plus C2 Candidate, broken pointer evidence, and post-promotion canonical confirmation.

## Media promotion replacement

The existing media authority promotion runtime already creates a new Official revision, moves the single current pointer only after approval, and marks the old Official version and authority `SUPERSEDED`. Existing promotion contract tests cover two different candidates, one current pointer, idempotent replay, and reject/request-change safety. No promotion runtime or schema change was required in this phase.

Reject and Request Change leave the old Official pointer unchanged and do not create a new Official version.

## Tests and verification

- `pytest -q tests/test_production_attempt_intent_facade.py`: 6 passed.
- `pytest -q tests/test_generation_attempt_canonical_facade.py`: 16 passed.
- `pytest -q tests/test_media_validation_promotion_contract.py tests/test_asset_promotion_runtime.py`: 21 passed.
- `npm --prefix web test -- --run`: 61 files, 438 tests passed.
- `npm --prefix web run build`: passed.
- `python -m compileall -q models core api`: passed.
- `python -c "import api.server"`: passed.
- `git diff --check`: passed.
- `pytest -q`: 1987 passed.

## Remaining UI work

The V3 UI has not been switched to call the new facade. Retry and Regenerate buttons remain disabled, and no real provider integration was attempted. A later phase can add the UI request flow, explicit human confirmation, preview/execute handoff, and browser QA against this contract.

## Constraints preserved

- Source Fact and ScriptIR were not modified.
- No database migration was added.
- No Character, Scene, Prompt, or Asset Manager was added.
- Legacy UI and production execution runtime were not changed.
- Human review remains required for promotion.
- Real provider, SHAPI, MiniMax, and LLM calls: 0.

## Machine-readable evidence

`PRODUCTION_UI_V3_RETRY_REGENERATE_INTEGRATION_PRECONDITIONS_RECONCILE_TRUTH_AUDIT.json`
