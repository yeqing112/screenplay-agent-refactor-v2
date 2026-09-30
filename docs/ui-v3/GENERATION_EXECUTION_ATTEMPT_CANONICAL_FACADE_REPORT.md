# Generation Execution Attempt Canonical Facade

## Result

`GENERATION_EXECUTION_ATTEMPT_CANONICAL_FACADE_COMPLETE`

This phase adds the shot-level Retry/Regenerate production facade while
keeping the existing canonical `GenerationExecutionRecord` runtime as the
only executor. The facade does not add a provider runtime, UI path, legacy
retry path, or migration.

## API

```text
POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-attempts/{attempt_lineage_id}/preview
POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-attempts/{attempt_lineage_id}/execute
```

`shot_id` is resolved as `StoryboardShot.shot_id`; the durable
`StoryboardShot.id` is then compared with the Attempt scope before any
canonical resolution or execution.

Preview accepts only the Attempt confirmation token. It resolves current
PromptIR, asset, reference, model, and IMAGE/VIDEO policy authority, compares
the current base request fingerprint with the Attempt source, derives a
business attempt fingerprint, creates a `PREVIEWED` GenerationExecutionRecord,
and immediately binds it through `GenerationAttemptLineageService`.

Execute requires all three explicit gates:

```json
{
  "execute": true,
  "confirmed": true,
  "allowExternalCall": true
}
```

It verifies the Attempt token and execution token independently, rechecks
source freshness and canonical drift, then delegates to
`_execute_generation_canary_impl(..., _canonical=True)`.

## Lineage and safety guarantees

- Attempt-produced executions use `derive_business_attempt_provider_request_fingerprint(base, operation_identity)`.
- `_generation_attempt` metadata records the Attempt id, operation identity, source/root lineage, ordinal, variant, source snapshot fingerprint, and base request fingerprint.
- Retry sources must remain `FAILED`.
- Regenerate sources must remain the current OfficialMedia pointer target.
- Missing or tampered produced-execution lineage fails closed with
  `GENERATION_ATTEMPT_SOURCE_LINEAGE_INVALID`.
- Preview performs zero provider calls, candidate writes, or Official writes.
- Execute writes at most one canonical Candidate and never promotes Official media.
- Ordinary canonical generation fingerprints and routes remain unchanged.
- Real LLM, Shapi, MiniMax, image, and video providers were not called.

## Changed files

- `api/generation_attempt_canonical_api.py`
- `api/generation_canary_api.py`
- `api/server.py`
- `core/generation_attempt_lineage.py`
- `scripts/run_real_episode_production_pilot.py`
- `tests/test_generation_attempt_canonical_facade.py`
- `tests/test_h2_asset_authority_schema.py`
- `tests/test_j2_3_media_scoped_prompt_pointer_migration.py`
- `tests/test_migration_chain_hardening.py`
- `docs/ui-v3/GENERATION_EXECUTION_ATTEMPT_CANONICAL_FACADE_REPORT.md`
- `docs/ui-v3/GENERATION_EXECUTION_ATTEMPT_CANONICAL_FACADE_TRUTH_AUDIT.json`
- `docs/ui-v3/GENERATION_EXECUTION_ATTEMPT_CANONICAL_FACADE_VERTICAL_SLICE.json`

## Verification

```text
44 targeted tests passed
  - Attempt lineage foundation: 6 tests
  - Canonical IMAGE/VIDEO regression: 22 tests
  - Canonical Attempt facade: 16 tests
41 migration and production-pilot gate tests passed
Web regression: 61 files / 435 tests passed
Web build: passed
compileall: passed
server route import: passed
Alembic heads: o6j7k8l9m0n1
```

The facade remains provider-free by default. A mock transport is available to
exercise the existing executor; no automatic promotion or human-review bypass
was introduced.

The full repository run completed with `1981 passed` and no failures. The
migration-head expectations were reconciled to the branch's existing
`o6j7k8l9m0n1` head; no migration or facade test was skipped.

## Scope

This phase does not connect V3 UI or Legacy UI, does not promote media, does
not move Official pointers, and does not call a real provider.

## Shot-level Facade

```text
POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-attempts/{attempt_lineage_id}/preview
POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-attempts/{attempt_lineage_id}/execute
```

The Foundation API remains internal; future UI callers use this Shot-level
contract.

## Business Shot Resolution

The URL `shot_id` is resolved as `StoryboardShot.shot_id` within book and
episode. Its durable `StoryboardShot.id` is compared with
`attempt.storyboard_shot_id` before canonical resolution or execution.

## Attempt Confirmation

Preview and Execute both call `GenerationAttemptLineageService.verify_confirmation`.
Cancelled and non-consumable Attempts fail closed. The Attempt token authorizes
the business operation and is never used as an execution token.

## Retry Freshness

Retry requires the source execution to exist, remain `FAILED`, retain its
immutable generation mode, and match the current canonical base fingerprint.
The old source row is not modified.

## Regenerate Freshness

Regenerate requires its source `OfficialMediaVersion` to remain the current
target of the scoped `OfficialMediaPointer`; a moved pointer returns
`GENERATION_ATTEMPT_SOURCE_STALE` without creating an execution.

## Base Fingerprint Resolution

`resolve_execution_base_provider_request_fingerprint()` uses the ordinary
execution fingerprint for ordinary history. For `_generation_attempt` history
it requires valid produced Attempt metadata and returns the persisted base
fingerprint. Missing or malformed metadata returns
`GENERATION_ATTEMPT_SOURCE_LINEAGE_INVALID` without fallback.

## Attempt Provider Fingerprint

New executions use
`derive_business_attempt_provider_request_fingerprint(base, operation_identity)`.
Ordinary Generate identity is unchanged; different Retry intents and
Regenerate variants occupy distinct namespaces.

## Preview Execution Creation

Current PromptIR, GenerationPayload, GenerationPolicy, model, adapter, assets,
references, and I2V source are re-resolved through
`_resolve_canonical_execution_inputs()`. The shared
`_build_canonical_preview_execution()` creates a new `PREVIEWED`
`GenerationExecutionRecord` with zero provider calls and zero transport retry
count. The response includes the Attempt, execution, payload, redacted request
snapshot, execution confirmation, `execution_created`, and `media_generated`.

## Lineage Binding

Execution creation and `bind_produced_execution()` share one transaction.
Deterministic fingerprint plus existing uniqueness constraints recover a
concurrent winner and prevent an orphan execution. BOUND preview replay reads
the same execution.

## Execution Confirmation

Execute requires `execute=true`, `confirmed=true`, and `allowExternalCall=true`,
then verifies both the Attempt token and `_confirmation_token()` for the exact
preview execution.

## Provider Execution Reuse

Execute delegates to `_execute_generation_canary_impl(..., _canonical=True,
_attempt_lineage_id=...)`; it does not dispatch a provider directly or create
a second Retry/Regenerate runner.

## Retry Runtime

IMAGE and VIDEO Retry mock flows each create one new Candidate. A failed
produced execution remains bound and requires a new business Retry intent.

## Regenerate Runtime

IMAGE and VIDEO Regenerate mock flows create a new Candidate while the source
Official version and pointer remain unchanged, including on failure.

## Retry-of-Retry

The original `root_execution_id` is preserved and root-scoped attempt ordinals
increment. The second source recovers the original base fingerprint from
`_generation_attempt` metadata.

## Regenerate-from-Regenerate

After a later current Official version explicitly represents a produced
candidate, a subsequent Regenerate resolves the produced source metadata and
creates a new variant fingerprint.

## VIDEO I2V Source Safety

The source immutable mode must be `IMAGE_TO_VIDEO`. Current canonical
resolution revalidates its Official image dependency and includes that source
binding in the base fingerprint, so an image pointer change is stale.

## Official Pointer Safety

The facade never calls promotion APIs. Official pointer writes and promotion
count remain zero.

## Candidate Projection

Existing `MediaCandidateRecord.execution_id` uniqueness keeps one candidate per
produced execution and preserves append-only provenance.

## V2 Projection

The read-only V2 lane sees the new latest execution and candidate. When an old
Official and a newer unpromoted Candidate coexist, the lane exposes both and
selects the appropriate review action.

## Concurrency

Preview idempotency uses the deterministic attempt fingerprint and existing
unique constraints. Execute reuses the canonical claim/state machine, so a
successful replay returns the same Candidate without another provider call.
Independent-session concurrency tests verify that two Preview requests create
one Execution and two Execute requests dispatch one mock provider call and
persist one Candidate; the losing Execute observes the existing in-progress
claim.

## Error Contract

```text
GENERATION_ATTEMPT_SCOPE_MISMATCH
GENERATION_ATTEMPT_CONFIRMATION_MISMATCH
GENERATION_ATTEMPT_SOURCE_STALE
GENERATION_ATTEMPT_SOURCE_LINEAGE_INVALID
GENERATION_ATTEMPT_EXECUTION_MISMATCH
GENERATION_ATTEMPT_ALREADY_BOUND
GENERATION_ATTEMPT_CANCELLED
```

Canonical execution errors remain unchanged.

## Ordinary Generate Regression

Ordinary same-request preview continues to reuse its ordinary provider request
fingerprint and returns `provider_calls=0`; ordinary snapshots do not receive
Attempt metadata.

## Provider Safety

All tests use disposable SQLite state and deterministic mock transports. Real
LLM, Shapi, MiniMax, image, and video calls are zero; real production writes
are zero.

## Remaining UI Gap

V3 Retry and Regenerate remain disabled or absent. `productionGeneration.ts`,
Legacy `restartCreativeTask`, and `StoryboardVideoRetryAttempt` are unchanged.

## Recommended Next Phase

`PHASE_PRODUCTION_UI_V3_RETRY_REGENERATE_INTEGRATION`
