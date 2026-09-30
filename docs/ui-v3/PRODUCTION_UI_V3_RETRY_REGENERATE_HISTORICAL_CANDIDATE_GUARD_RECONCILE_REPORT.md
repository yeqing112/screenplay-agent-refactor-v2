# Production UI V3 Retry / Regenerate Historical Candidate Guard Reconcile Report

## Phase

`PHASE_PRODUCTION_UI_V3_RETRY_REGENERATE_HISTORICAL_CANDIDATE_GUARD_RECONCILE`

Baseline: `2ea3e4c984690a77a87bb621db03fcf77d7651d8`  
Branch: `codex/visual-authoring-provider-canary-reconcile`  
Date: `2026-10-01`

## Completion marker

`PRODUCTION_UI_V3_RETRY_REGENERATE_HISTORICAL_CANDIDATE_GUARD_RECONCILE_COMPLETE`

## Problem

The Regenerate guard scanned all durable candidates in a Shot/lane. It excluded only the current Official candidate and candidates with `REJECTED` or `REQUEST_CHANGE` review decisions. A candidate that had already produced Official v1 and was later superseded by Official v2 therefore looked like a new pending candidate and incorrectly returned `GENERATION_REGENERATE_PENDING_CANDIDATE_EXISTS`.

## Canonical pending Candidate definition

A Candidate is pending only when it has no `OfficialMediaVersion` evidence and has not been explicitly marked `REJECTED` or `REQUEST_CHANGE`. The guard now evaluates the complete database candidate set, independent of the V2 projection's display limit.

For each Candidate:

1. Skip the current Official candidate.
2. Skip any candidate with an `OfficialMediaVersion` row, whether that version is `CURRENT` or `SUPERSEDED`.
3. Skip `MediaPromotionRecord.REJECTED` and `REQUEST_CHANGE`.
4. Treat every other candidate as pending.

`OfficialMediaVersion` is the promotion evidence. An `APPROVED` review record without an Official version remains pending and blocks conservatively.

## Historical Official Candidate handling

The guard now recognizes a candidate's historical promotion by querying `OfficialMediaVersion(candidate_id=...)`. This handles C1 → Official v1 → SUPERSEDED, C2 → Official v2 → SUPERSEDED, and C3 → Official v3 CURRENT without allowing C1 or C2 to block another Regenerate. The current Official candidate is still explicitly safe, and the backend current Official pointer remains the only Regenerate source.

## Review status handling

- `REVIEW_REQUIRED`: blocks with `GENERATION_REGENERATE_PENDING_CANDIDATE_EXISTS`.
- No `MediaPromotionRecord`: blocks as an unresolved generated candidate.
- `APPROVED` without an Official version: blocks fail-closed.
- `REJECTED`: does not block.
- `REQUEST_CHANGE`: does not block.

## IMAGE / VIDEO coverage

The same canonical guard is applied to IMAGE and VIDEO lanes. Tests cover a second Regenerate after two Official revisions for both media types, with no provider or execution writes during intent creation.

## Sequential Regenerate proof

The provider-free disposable DB tests create two durable Official revisions in one lane, mark the first `SUPERSEDED`, move the pointer to the second, retain both historical Candidate rows, and submit a new Shot-level Regenerate intent. The intent is created successfully and uses the current Official v2 source. A separate pending Candidate still blocks, while explicitly rejected or request-change candidates allow the request.

The existing promotion runtime and `core/media_authority.py` were not changed. Its established tests continue to cover validation, approval, pointer movement, superseding the old Official, and reject/request-change safety.

## Contract preservation

- Shot-level create-intent endpoint remains the UI-facing boundary.
- Regenerate source remains backend-resolved from the current Official pointer; clients cannot select historical Official versions.
- Retry remains bound to the current lane latest `FAILED` execution.
- Attempt lineage, idempotency, confirmation binding, Preview, and Execute are unchanged.
- Review Controller coexistence and broken Official fail-closed behavior are unchanged.
- V3 Retry and Regenerate UI remain disabled; no frontend service was added.

## Regression and verification

- `pytest -q tests/test_production_attempt_intent_facade.py`: 14 passed.
- `pytest -q tests/test_generation_attempt_canonical_facade.py`: 16 passed.
- `pytest -q tests/test_generation_execution_attempt_lineage.py tests/test_phase_j3_canonical_generation.py tests/test_media_validation_promotion_contract.py tests/test_asset_promotion_runtime.py`: 49 passed.
- `pytest -q --disable-warnings`: 1995 passed.
- `npm --prefix web test -- --run`: 61 files, 438 tests passed.
- `npm --prefix web run build`: passed.
- `python -m compileall -q models core api`: passed.
- `alembic heads`: `o6j7k8l9m0n1`.
- `git diff --check`: passed.

## Provider and production safety

All tests use disposable DB fixtures or existing provider-free mocks. Real LLM, SHAPI, MiniMax, IMAGE provider, and VIDEO provider calls remain zero. No production database writes were made. No migration, Source Fact, ScriptIR, execution runtime, promotion runtime, Legacy UI, or V3 UI enablement changed.

## Readiness for V3 integration

The historical Candidate guard is reconciled and the existing foundation contracts remain green. The next phase can directly implement `PHASE_PRODUCTION_UI_V3_RETRY_REGENERATE_INTEGRATION` without another foundation phase.
