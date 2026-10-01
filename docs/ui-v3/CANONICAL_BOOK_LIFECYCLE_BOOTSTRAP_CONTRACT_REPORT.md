# Canonical Book Lifecycle Bootstrap Contract

## Result

`CANONICAL_BOOK_LIFECYCLE_BOOTSTRAP_CONTRACT_COMPLETE`

This phase establishes a provider-free, API-first lifecycle for creating a
Book and its source Script, and a canonical deletion service that removes the
Book graph without touching another project.

## Decision: disposable canary

The canary selected for disposal is:

```text
V3-CANARY-DISPOSABLE-20261001-R2
```

It was created through `POST /api/books`, received database id `990403`, and
was deleted through `DELETE /api/books/990403`. The delete response reported
`orphan_rows: 0`. The source Script was created through the formal
`POST /api/books/990403/scripts` endpoint before deletion.

The historical `990400` Book was left unchanged. `998755` was not revived.

## API contract

```text
POST /api/books
POST /api/books/{book_id}/scripts
DELETE /api/books/{book_id}
```

Book creation trims and validates the title and owns the generated filename
and database id. Script creation accepts a string or structured JSON object,
serializes JSON canonically, rejects duplicate `(book, episode, genre)` source
scope, and does not create ScriptIR implicitly.

All new write routes remain behind the existing API authentication middleware.

## Provider and source guarantees

- Book and Script bootstrap performs zero Image Provider calls.
- It performs zero Video Provider calls.
- It performs zero LLM calls.
- It does not invoke `/api/pipeline/script` or legacy node ingest.
- ScriptIR build remains an explicit subsequent operation and records a
  provider-free persisted draft.
- Source facts and the original Script content are not rewritten.

## Canonical delete graph

Deletion uses `core.book_lifecycle.delete_book_scope` and an explicit direct
`book_id` inventory. The indirect cleanup covers:

- Agent session plans, messages, and audit logs.
- Fact records below FactSnapshot.
- Generation attempts, candidates, validation, promotion, and Official media
  authority rows.
- Prompt lineage, generation intents, render plans/items, production batches,
  keyframes, and shot bindings.
- Director plans/reasoning/storyboard drafts.
- Typed Character/Scene/Prop asset authorities, pointers, versions, reviews,
  and reference sets.

The inventory fails closed when a new direct `book_id` table is not reviewed.
Filesystem cleanup is scoped by book id; title directories are retained when
another Book shares the same title.

The lifecycle also cleans episode-keyed runtime rows when a bootstrap Script
exists before an `EpisodeOutline` is materialized. This includes DirectorPlan,
ScenePlan, DirectorReasoning, StoryBeat, VisualDecision, and
DirectorReasoningGeneration rows. Render plans keyed by `project_id` and
automatic keyframe plans keyed by materialization set are included in the same
fail-closed scope.

## Verification

```text
8 lifecycle API tests passed
2003 backend tests passed in the full repository run
63 web test files / 445 tests passed
web build passed
compileall passed
```

The integration test creates and removes indirect Agent, Fact, ShotAssetBinding,
and Storyboard rows and requires `orphan_rows == 0`. The disposable canary
vertical slice also passed with `orphan_rows == 0`.

No migration was added. The Alembic head remains `o6j7k8l9m0n1`.

## Files

- `core/book_lifecycle.py`
- `api/book_lifecycle_api.py`
- `api/server.py`
- `tests/test_book_lifecycle_api.py`
- `docs/ui-v3/CANONICAL_BOOK_LIFECYCLE_BOOTSTRAP_CONTRACT_TRUTH_AUDIT.json`
- `docs/ui-v3/CANONICAL_BOOK_LIFECYCLE_BOOTSTRAP_CONTRACT_VERTICAL_SLICE.json`

## Scope boundary

This phase does not call a real provider, generate media, modify ScriptIR
source facts, or authorize production generation. Real Provider work remains
blocked until the V2 IMAGE readiness gate passes.
