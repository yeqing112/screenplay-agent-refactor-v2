# Phase J2.2 Final Report — Media-Scoped PromptIR Schema Design Review

## Final status

```text
PHASE_J2_2_MEDIA_SCOPED_PROMPT_IR_SCHEMA_APPROVED_PENDING_MIGRATION
```

This phase completed schema, migration, resolver, stale-semantics, and callsite design review only. Migration and J3 implementation were not started.

## Baseline and evidence

- Baseline HEAD: `144e2a61f9355051127539a6cec4da7c9b3bb936`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- J2.1 reproduction: IMAGE OfficialMedia resolved before the one-shot PromptIR pointer moved to VIDEO, then failed currentness while historical integrity remained valid.
- Current ORM and Alembic both define `PromptIRPointer.storyboard_shot_id` as the sole unique scope.
- SQLite inspection confirms the old physical unique object is the unnamed `sqlite_autoindex_prompt_ir_pointers_1`; the existing named indexes are `ix_prompt_ir_pointers_book_episode` and `ix_prompt_ir_pointers_shot`.

## Design decision

Add only `PromptIRPointer.target_media` as a scope discriminator, with exact values `IMAGE` or `VIDEO`, a check constraint, and the named composite uniqueness:

```text
UNIQUE(book_id, episode, storyboard_shot_id, target_media)
```

Do not add `target_media` to `PromptIRVersion` or `PromptIRAuthority`. The semantic source remains `PromptIRVersion.payload_json.generation_policy.target_media`; pointer scope must equal that value and must be derived from compiled PromptIR output.

The migration must deterministically backfill existing pointers from their pointed version payload. Missing policy, invalid policy, pointer/version identity mismatch, or invalid payload hash blocks the migration. It must never default to IMAGE or infer from media/adapter history. SQLite requires a transactional batch table rebuild to remove the unnamed old autoindex and add the named composite constraint.

Downgrade is lossless only when every shot has at most one pointer. If any shot has both IMAGE and VIDEO pointers, downgrade must refuse with `PROMPT_IR_POINTER_DOWNGRADE_CARDINALITY_CONFLICT` before schema mutation.

The composite database constraint is also the concurrency boundary: same-scope races must produce one committed winner or deterministic conflict, while independent IMAGE and VIDEO scopes may commit concurrently. The existing missing PromptIRPointer foreign key is recorded but intentionally left outside this scoped migration.

## Resolver contract

All current PromptIR, adapter preview, generation, and OfficialMedia paths require explicit `target_media`. No `.first()`, latest, IMAGE default, media-role parsing, stale-media fallback, or cross-media fallback is permitted. OfficialMedia selects the PromptIR scope from validated `GenerationExecutionRecord.target_media`, then checks execution/candidate/official media type equality and exact PromptIR lineage.

IMAGE_TO_VIDEO binds the current `SHOT_PRIMARY_IMAGE` OfficialMedia authority with authority ID, version ID, checksum, and source PromptIR lineage. It is not copied into `VisualReferenceAuthority`, and transport URLs remain Provider-boundary data.

## Stale semantics

Policy revisions are scope-local. IMAGE revision affects IMAGE; VIDEO revision affects VIDEO. Shared storyboard/asset revisions re-evaluate each scope using its own stored policy. If a VIDEO explicitly requires the current official IMAGE and IMAGE I1 is replaced by I2, the old VIDEO remains historically valid but becomes current-lineage obsolete; no automatic regeneration occurs.

## Callsite impact

The inventory found old one-pointer assumptions in:

- Phase E compile/update and current integrity APIs;
- adapter preview and Phase F canary execution;
- media currentness and strict OfficialMedia resolution;
- production workspace projection/API snapshots;
- migration verification, pilots, and test fixtures;
- frontend consumers of the one-PromptIR-per-shot snapshot.

The resolver test plan includes dual-scope PASS, no cross-media fallback, pointer/payload mismatch, IMAGE_TO_VIDEO authority binding, and image-revision current-lineage invalidation without historical tamper.

See [the complete callsite inventory](./phase_j2_2_prompt_pointer_callsite_inventory.md).

## Side-effect accounting

```text
Provider calls: 0
LLM calls: 0
Image calls: 0
Video calls: 0
Alembic migration performed: false
ORM/production API/resolver/compiler changes: false
Production Authority writes: 0
FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_COMPLETE=false
```

## Required next gate

Implement nothing from this review yet. The next authorized step is a separately reviewed Alembic/SQLite migration plus the inventoried resolver/callsite changes and rollback/currentness tests. Do not start J3 until the migration and dual-media acceptance matrix pass.
