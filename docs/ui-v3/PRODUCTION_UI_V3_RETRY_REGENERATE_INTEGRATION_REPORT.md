# Production UI V3 Retry / Regenerate Integration

## Scope

This phase integrates the canonical shot level Retry and Regenerate facade into the default V3 Shot Studio. Ordinary Generate remains on `productionGeneration.ts`; Attempt operations use the dedicated `productionGenerationAttempts.ts` service and `productWorkspaceShotGenerationAttempt.ts` controller.

## Retry UX

`FAILED` IMAGE and VIDEO lanes expose `重试本次生成` only when the current lane execution is the latest failed execution, the lane is executable, and an execution id exists. Retry sends only that execution id and preserves the failed record.

## Regenerate UX

Canonical Official lanes expose the secondary `生成新版本` action. The primary action remains `查看正式版本`. Regenerate sends no source execution or Official version id; the backend resolves the current Official pointer. Existing Official evidence remains visible until the new Candidate is approved.

## Attempt API service

The typed service calls only:

- `POST /api/books/{book}/episodes/{episode}/shots/{shot}/generation-attempts`
- `POST .../generation-attempts/{attempt}/preview`
- `POST .../generation-attempts/{attempt}/execute`

It never calls `/generation/attempt-intents`, ordinary Generate endpoints, or Legacy recovery routes. Backend error payloads are converted to `ProductionGenerationAttemptServiceError` with `status`, `code`, `message`, and `details`.

## Operation identity and confirmation

Each explicit click creates one UUID idempotency key, reused through create, preview, and execute. A controller active lock prevents double click duplication. Cost confirmation occurs before create intent; after confirmation the canonical V2 view is re-read. A changed shot, lane, failed execution, or Official capability fails closed with `ATTEMPT_FRESHNESS_CONFLICT` and performs no Attempt write.

## Preview / execute and observation

Preview returns the durable Attempt confirmation and produced execution id. Execute requires `execute=true`, `confirmed=true`, `allowExternalCall=true`, both confirmation tokens, and the exact preview execution id. Observation is bound to that produced execution id. An old Official alone cannot complete an Attempt. A successful execution with delayed Candidate projection remains `waiting_candidate`; a visible Candidate or an externally promoted Official for the produced Candidate settles the operation. A different latest execution fails closed with `V3_ATTEMPT_EXECUTION_SUPERSEDED`.

## Locks and stop semantics

Ordinary Generate, Attempt mutation, and Review mutation mutually disable one another in Shot Studio. After execute is submitted, stopping the controller only stops foreground observation and reports that the backend task may still be running; it never claims provider cancellation. No localStorage/sessionStorage is used for Attempt truth.

## Review handoff and replacement

Retry and Regenerate Candidates reuse the existing Review Desk. Regenerate keeps the old Official current while the Candidate is under review. Approval uses the existing promotion controller; only canonical V2 refresh establishes the replacement pointer. Reject and Request Change behavior remains unchanged.

## Verification

- Web: `63` test files, `443` tests passed.
- Web build: `npm --prefix web run build` passed.
- Backend Attempt regression: `43 passed` across the canonical Attempt, lineage, and contract suites.
- Backend full suite: `1995 passed`.
- `git diff --check`: passed.
- Database migration: `0`; Alembic head remains `o6j7k8l9m0n1`.
- Provider safety: service/controller tests use mocks; real LLM, SHAPI, MiniMax, image, and video calls are `0`.
- Production writes: `0`.

## Browser / responsive QA

The component render suite covers default V3, Official plus Candidate coexistence, failed state, review state, and 100-shot rendering. Network contract tests assert shot-level routes and the absence of Foundation routes. A real-provider browser run is intentionally outside this phase and remains deferred to the explicitly authorized staging vertical slice.

## Remaining production gaps

Real provider staging, real asynchronous provider timing, and disposable staging production writes remain for `PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_STAGING_VERTICAL_SLICE`. Review Inbox, Reject/Request Change UI, and the 100-shot pagination ceiling remain deferred as specified.

## Recommended next phase

`PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_STAGING_VERTICAL_SLICE`
