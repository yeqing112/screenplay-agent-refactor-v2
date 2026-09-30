# Generation Execution Attempt Lineage Foundation

## Scope

This backend foundation establishes one durable business operation record for
future Retry and Regenerate flows. It intentionally stops before creating a
new `GenerationExecutionRecord`, invoking an adapter, writing a candidate, or
moving Official Media authority. V3 UI remains disabled.

## Migration

Migration `n5i6j7k8l9m0` is the only migration added in this phase and follows
the verified head `m4h5i6j7k8l9`. It creates
`generation_execution_attempt_lineages`, preserves the existing unique
`generation_execution_records.provider_request_fingerprint`, and performs no
historical backfill.

## Attempt Lineage Schema

The table stores operation kind, book/episode/shot/media scope,
source/root/produced execution IDs, attempt and variant numbers, reason,
source candidate and Official IDs, immutable source and operation
fingerprints, confirmation binding hash, status, and timestamps. Execution
references use String business IDs and database foreign keys; candidate and
Official IDs remain indexed String references with service-level validation to
preserve the existing cross-authority migration shape.

## Retry Intent

Retry requires a server-resolved `FAILED` execution. The source snapshot is
constructed from the persisted execution, including request snapshot,
prompt, policy, model, reference, payload, and provider request fingerprints.
The first retry has root equal to source and attempt number 1. A retry of a
produced retry follows the persisted lineage to retain the original root and
increments the business attempt number. Transport retry count is untouched.

## Regenerate Intent

Regenerate accepts only the current Official Media Version. The service checks
the current pointer, resolves Official → Candidate → Execution, enforces
media/scope equality, records the source candidate and Official business IDs,
and allocates a media-scoped Regenerate variant index. Historical Official
versions fail closed.

## Operation Idempotency

`book_id + operation_idempotency_key` is a database unique boundary. Same-key
same-semantic requests return the original lineage; a semantic mismatch
returns `GENERATION_ATTEMPT_IDEMPOTENCY_CONFLICT`. Expected unique races are
reconciled after rollback; unrelated integrity failures are propagated.

## Attempt Fingerprint

`derive_business_attempt_provider_request_fingerprint()` is a pure deterministic
namespace over the base provider request fingerprint and operation identity.
It does not alter `canonical_request_fingerprint()`, and it has no random,
time, or UUID input.

## Confirmation Binding

Each intent has a fresh business binding derived from lineage ID, operation
kind and identity, source/root IDs, source snapshot, and complete scope. Only
the SHA-256 hash is stored. POST returns the raw token; GET never returns it.
Ordinary generation tokens and tokens from another intent fail closed.

## Retry Root Resolution

Root resolution is server-side through `produced_execution_id` lineage rows;
no client storage participates.

## Regenerate Variant Resolution

Variant numbering counts only `REGENERATE` rows in the same book, episode,
shot, and target media scope. Retry attempts do not consume variant numbers.

## Official Media Safety

Intent creation does not update Official Media Version, Official Media
Pointer, or authority records. A non-current Official source is rejected.

## Candidate Safety

Intent creation does not insert or modify `MediaCandidateRecord`. Candidate
and execution lineage is read and validated only.

## Transport Retry Separation

`transport_retry_count` remains the compatibility counter for same-execution
transport/runtime retries. Business attempt numbers live only in this table.

## Foundation API

Provider-free internal routes are available at:

- `POST /generation/attempt-intents`
- `GET /generation/attempt-intents/{attempt_lineage_id}`

The `/api` mirror is registered for existing routing compatibility. The POST
contract accepts exactly one source form per operation kind. The response
states `provider_calls: 0`, `execution_created: false`, and
`media_generated: false`; GET returns no raw token.

## Produced Execution Binding

`bind_produced_execution()` validates scope and rejects source/root reuse. A
NULL-to-B bind succeeds, repeating B is idempotent, and binding C returns
`GENERATION_ATTEMPT_ALREADY_BOUND`. Binding only persists the relation; it
does not run the execution.

## Concurrency

Database uniqueness, rollback, winner lookup, and semantic comparison protect
same-key concurrent intent creation.

## Error Contract

The service uses independent canonical attempt errors including source not
found, Retry source status, non-current Regenerate source, media/scope
mismatch, idempotency conflict, already-bound, and confirmation mismatch.
Legacy task restart and storyboard video retry errors are not reused.

## Provider Safety

The implementation contains no LLM, Shapi, MiniMax, image, or video submit
path. Intent creation and binding are provider-free and produce zero real
provider calls and zero production writes.

## Legacy Compatibility

Legacy restart, `StoryboardVideoRetryAttempt`, recovery behavior, and the V3
production generation services were not modified. Retry and Regenerate UI
actions remain disabled.

## Tests

- Migration chain fresh upgrade, repeated upgrade, downgrade, and drift audit:
  PASS.
- Direct migration schema inspection: 22 columns, 3 unique constraints, 5
  checks, 14 indexes, and 3 execution foreign keys; downgrade removed the
  table: PASS.
- `tests/test_generation_execution_attempt_lineage.py`: 4 passed, including
  Retry idempotency/status, Regenerate trace, confirmation, and fingerprint.
- Existing generation foundation/canary and retry contract suites: 37 passed.
- Web: 61 files / 435 tests passed; production build passed.
- Python compileall and `git diff --check`: PASS.

## Remaining Gap

IMAGE/VIDEO Retry and Regenerate remain `NO_GO` for UI because this phase does
not yet turn an intent into a new previewed canonical execution or provider
execution.

## Recommended Next Phase

`PHASE_GENERATION_EXECUTION_ATTEMPT_CANONICAL_FACADE`: consume an intent into
a new PREVIEWED GenerationExecution, preserve fresh confirmation, then add the
mock/provider boundary and candidate projection before any UI work.
