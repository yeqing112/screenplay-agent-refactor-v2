# Generation Execution Attempt Lineage Foundation

## Status

`GENERATION_EXECUTION_ATTEMPT_LINEAGE_FOUNDATION_COMPLETE`

This phase adds the durable business operation boundary shared by Retry and
Regenerate. It stops at an intent preview and does not run a provider, create
an execution, write a candidate, move an Official Media pointer, or expose a
V3 UI mutation.

## Delivered

- Added `GenerationExecutionAttemptLineage` and one Alembic migration
  (`n5i6j7k8l9m0`, down revision `m4h5i6j7k8l9`).
- Persisted operation idempotency, operation kind, source/root/produced
  execution relations, attempt and variant numbers, source snapshots,
  confirmation binding, and status.
- Added `GenerationAttemptLineageService` with Retry and Regenerate intent
  creation, current Official Media validation, deterministic confirmation,
  attempt fingerprint derivation, and produced execution binding.
- Added provider-free routes:
  - `POST /generation/attempt-intents`
  - `GET /generation/attempt-intents/{attempt_lineage_id}`
  (and the existing `/api` router mirror).
- Updated the migration-chain authority audit for the new table.

## Guardrails

- Retry accepts only a `FAILED` source execution and leaves its transport retry
  counter unchanged.
- Regenerate resolves the source candidate and execution through the current
  Official Media pointer and enforces media and scope equality.
- Idempotency is durable per book and operation key; semantic reuse returns the
  original lineage and semantic divergence fails closed.
- Confirmation tokens are derived from the complete operation binding; only
  the token hash is persisted.
- `provider_calls=0`, `execution_created=false`, and `media_generated=false`
  are returned for intent previews.

## Verification

- `alembic heads` → `n5i6j7k8l9m0 (head)`
- `python -m scripts.verify_migration_chain` → `MIGRATION_CHAIN_HARDENING_READY`
  with fresh upgrade/downgrade and drift checks passing.
- `python -m pytest -q tests/test_generation_execution_attempt_lineage.py` → 6 passed.
- Existing generation foundation/canary audit suite → 37 passed.
- Canonical/media/video/legacy retry regression slice → 83 passed.
- Web tests → 61 files / 435 tests passed; production build passed.
- `python -m compileall -q models core api scripts` passed.
- `git diff --check` passed.

The canonical report is also available at
`docs/ui-v3/GENERATION_EXECUTION_ATTEMPT_LINEAGE_FOUNDATION_REPORT.md`, with
the machine audit beside it.
