# Generation Execution Attempt Lineage Reconcile

## Scope

This reconcile hardens the Foundation before the Canonical Facade. It does
not create a new Provider Execution, add an execute endpoint, invoke a model,
or connect V3 Retry/Regenerate UI.

## Foundation Issues Found

The prior implementation used `variant_index=1` for Retry, allocated
Regenerate variants with `count()+1`, and did not persist database sequence
guards. The prior root report also lagged the actual six Foundation tests.

## Retry Variant Semantics

Retry now always stores `variant_index=0`. Creative version numbering belongs
only to Regenerate. Retry creation rejects any nonzero Retry variant.

## Retry Attempt Number Semantics

`attempt_number` is a monotonic ordinal scoped to `root_execution_id` for
`RETRY` rows. The first explicit retry is 1; sibling retries are 2, 3, and so
on; a retry of a produced retry continues the same root sequence. Different
roots may independently start at 1.

## Regenerate Variant Semantics

Regenerate stores `attempt_number=1` and allocates `variant_index` from
`MAX()+1` in the `(book, episode, storyboard_shot_id, target_media)` lane.
Retry rows never consume this sequence. The durable business shot boundary in
this phase is `GenerationExecutionRecord.storyboard_shot_id`; a future URL
business shot ID must first resolve to that durable row before calling this
service.

## Concurrency Protection

Each Retry ordinal has deterministic `retry_attempt_key`; each Regenerate
ordinal has deterministic `regenerate_variant_key`. Nullable unique indexes
allow the opposite operation kind to remain NULL while the database protects
populated ordinals. Allocation retries at most three times after a recognized
ordinal collision. Same-key idempotency is checked before allocating a new
ordinal.

## Database Guards

Migration `o6j7k8l9m0n1` adds the two nullable keys, corrects existing Retry
rows to variant zero, deterministically backfills keys, fails closed on
duplicate historical ordinals, and adds unique indexes. It does not fabricate
operation IDs, identity fingerprints, or confirmation bindings.

## Migration

The verified single head is `o6j7k8l9m0n1`, with exactly one migration added
after `n5i6j7k8l9m0`. Fresh upgrade, repeated upgrade, downgrade, and schema
drift checks pass.

## Business Shot ID Boundary

The current Foundation service consumes the durable execution shot integer.
The next Canonical Facade must resolve `/books/{book}/episodes/{episode}/shots/{shot_id}`
business IDs through `StoryboardShot` first; this service must not guess
between ID namespaces.

## Confirmation Binding

Confirmation remains fresh and provider-free. Attempt and variant ordinals are
now included in the binding payload, so a changed ordinal invalidates the
token. The raw token remains out of the database.

## Operation Identity

Operation identity now includes operation kind, idempotency key, source/root
execution IDs, source snapshot, target media, reason, and the persisted
attempt/variant ordinals. Ordinary Generate fingerprinting remains untouched.

## Regression

- New Foundation suite: 6 passed.
- Canonical/media/video/legacy retry slice: 83 passed.
- Web: 61 files / 435 tests passed.
- Production build, `compileall`, and `git diff --check`: passed.

## Evidence Correction

The Foundation report now records six tests, matching the final command. The
machine audit records root-scoped Retry ordinals and database guarded
Regenerate lanes.

## Readiness for Canonical Facade

The numbering and concurrency gate is complete. The next phase may implement
`Attempt Intent → new PREVIEWED GenerationExecution`, still backend-first and
provider-gated, before any V3 UI work.

