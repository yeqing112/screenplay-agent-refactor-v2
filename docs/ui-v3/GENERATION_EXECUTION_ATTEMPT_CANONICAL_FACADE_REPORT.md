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
- `tests/test_generation_attempt_canonical_facade.py`
- `docs/ui-v3/GENERATION_EXECUTION_ATTEMPT_CANONICAL_FACADE_TRUTH_AUDIT.json`
- `docs/ui-v3/GENERATION_EXECUTION_ATTEMPT_CANONICAL_FACADE_VERTICAL_SLICE.json`

## Verification

```text
31 passed
  - Attempt lineage foundation: 6 tests
  - Canonical IMAGE/VIDEO regression: 22 tests
  - Canonical Attempt facade: 3 tests
compileall: passed
server route import: passed
Alembic heads: o6j7k8l9m0n1
```

The facade remains provider-free by default. A mock transport is available to
exercise the existing executor; no automatic promotion or human-review bypass
was introduced.

The full repository run completed with `1962 passed` and six pre-existing
migration-head expectation failures. Those failures assert the historical
`m4h5i6j7k8l9` head while this branch already contains the reconciled
`o6j7k8l9m0n1` head; no facade test failed.
