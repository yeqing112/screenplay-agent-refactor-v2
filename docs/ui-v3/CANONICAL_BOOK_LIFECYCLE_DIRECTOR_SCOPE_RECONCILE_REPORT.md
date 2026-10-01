# Canonical Book Lifecycle — Director Scope Reconcile

## Result

`CANONICAL_BOOK_LIFECYCLE_DIRECTOR_SCOPE_RECONCILE_COMPLETE`

Baseline: `26666cd3500d86d5e897e7fee0f146bc25c1cd03`

## Root Cause

DirectorPlan, DirectorReasoning, StoryboardPlan, and DirectorReasoningGeneration
are episode-keyed runtime tables without a direct `book_id` on every row. The
previous lifecycle implementation treated a raw `episode_id` such as `"1"` as
Book ownership evidence. That allowed two Books with Episode 1 to enter the
same delete scope.

## Why Raw Episode Number Is Unsafe

`DirectorPlan` and `DirectorReasoning` use `(episode_id, version)` uniqueness,
and API context loading can interpret a numeric episode key as a
`ScriptIRVersion.id`, `ScriptIRVersion.episode`, or `EpisodeOutline.id`.
Therefore the raw key does not identify a Book. It is now used only to detect a
possible legacy association that requires fail-closed ambiguity handling.

## Director Runtime Identity Semantics

Delete, audit, and preflight now share `_resolve_director_runtime_scope()` and
`_director_row_scope()`. The resolver returns `owned`, `foreign`,
`ambiguous`, or `unrelated` from canonical evidence. ScenePlan inherits
DirectorPlan ownership; StoryBeat and VisualDecision inherit DirectorReasoning
ownership; DirectorReasoningGeneration inherits its DirectorReasoning parent.

## Canonical Ownership Evidence

Evidence is evaluated in this order:

1. Explicit source ScriptIR version and its `ScriptIRVersion.book_id`.
2. Explicit `lineage_json.book_id`.
3. A unique `source_script_ir_hash` whose matching ScriptIR rows all belong to
   the target Book.
4. Canonical parent ownership.

Raw `episode_id` and episode numbers are never sufficient evidence.

## DirectorPlan Ownership

`DirectorPlan.source_script_ir_version_id` is validated against the persisted
ScriptIR row. A foreign source version is preserved. Future DirectorPlan
creation persists backend-derived `book_id`, source version id, and source hash
in lineage; caller supplied conflicting Book values are ignored when a
persisted ScriptIR is available.

## DirectorReasoning Ownership

DirectorReasoning has no source-version column, so its lineage carries the
backend-derived `book_id`, source version id, and source hash. Persistence
validates a supplied source version before writing. Foreign lineage remains
outside the target scope.

## Reasoning Generation Ownership

DirectorReasoningGeneration is deleted only through an owned
`director_reasoning_id`. A generation with no canonical parent and a potential
raw episode association is ambiguous and blocks deletion.

## Ambiguous Legacy Rows

An evidence-free legacy row whose raw episode key could belong to the target
returns HTTP `409` with code `BOOK_DELETE_DIRECTOR_SCOPE_AMBIGUOUS`. The
preflight runs before row deletion, Book deletion, or filesystem cleanup, so
the transaction performs no partial delete. Ambiguous rows are reported
separately from `orphan_rows`.

## Cross-book Same Episode Proof

Two Books were created with Episode 1 and canonical DirectorPlan,
ScenePlan, DirectorReasoning, StoryBeat, VisualDecision, StoryboardPlan, and
DirectorReasoningGeneration rows. Deleting Book A removed only A's graph;
Book B, its Script, ScriptIR, and every Director runtime row remained unchanged.

## Same Hash Proof

Two Books with the same ScriptIR payload hash remain isolated when the runtime
row carries an explicit source ScriptIR version. A hash-only row with matches
in both Books is classified `AMBIGUOUS` and blocks deletion rather than being
assigned to either Book.

## Neighbor Isolation

The cross-book regression asserts zero mutations to the neighbor Book, Script,
ScriptIR, and Director runtime rows. Existing direct Book scope cleanup for
render plans, production batches, and materialization-keyed keyframe plans is
unchanged.

## Bootstrap Regression

- `POST /api/books`: PASS
- `POST /api/books/{id}/scripts`: PASS
- Structured ScriptIR build: provider-free, `legacy_reconstruction=false`,
  `llm_called=false`
- Lifecycle focused tests: **11 passed**
- Full backend: **2006 passed**
- Web: **63 files / 445 tests passed**
- Web build: **PASS**
- Migration chain: **PASS**
- Alembic head: `o6j7k8l9m0n1`
- Python compileall: **PASS**
- `git diff --check`: **PASS**

## Provider Safety

This reconcile made no real Image, Video, SHAPI, MiniMax, or external LLM
calls. Mock adapter tests remain provider-local and review-only. No media was
generated and no source facts or ScriptIR facts were rewritten.

## Protected Data and Migration Boundary

- Book `990400`: preserved; this change issued zero targeted writes.
- Book `998755`: not revived.
- No database migration files added.
- Disposable canary `990403`: remains deleted with zero orphan rows.

## Resume Decision

The canonical bootstrap contract is reconfirmed after the scope reconcile. The
next authorized phase is:

`PHASE_PRODUCTION_UI_V3_REAL_PROVIDER_STAGING_VERTICAL_SLICE`

This phase is a recommendation only; this reconcile does not start real
provider staging.

## Final Status

`CANONICAL_BOOK_LIFECYCLE_DIRECTOR_SCOPE_RECONCILE_COMPLETE`
