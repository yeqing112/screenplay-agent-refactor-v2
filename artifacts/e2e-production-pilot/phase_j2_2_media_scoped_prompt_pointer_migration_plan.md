# Phase J2.2 Media-Scoped PromptIR Pointer Migration Plan

## Existing physical constraint evidence

`alembic/versions/u4d5e6f7g8h9_add_prompt_ir_authority.py` creates `storyboard_shot_id` with `unique=True`; `models/prompt.py` repeats that declaration. There is no explicit old constraint name. On SQLite the physical object is the unnamed autoindex `sqlite_autoindex_prompt_ir_pointers_1` over `storyboard_shot_id`. The named non-unique indexes are:

```text
ix_prompt_ir_pointers_book_episode (book_id, episode)
ix_prompt_ir_pointers_shot         (storyboard_shot_id)
```

The replacement names are:

```text
ck_prompt_ir_pointer_target_media
uq_prompt_ir_pointer_media_scope
```

## Upgrade contract

The migration must run in one transaction and abort before changing the schema if any blocker is found.

1. Add nullable `target_media` to `prompt_ir_pointers` as a temporary column.
2. Read every pointer joined by `prompt_ir_version_id` to its version. Validate pointer existence, matching book/episode/shot identity, valid pointer payload hash, valid version payload hash, valid JSON, explicit `generation_policy`, and exact `target_media` in `{IMAGE, VIDEO}`.
3. Derive `target_media` only from the version payload. Never infer it from prompts, model names, adapters, media rows, historical usage, or a missing value. A missing/invalid policy or a mismatch produces a migration blocker and rolls back.
4. Write the derived value for every existing pointer. Assert the pointer row count is unchanged and no duplicate `(book, episode, shot, target_media)` scope exists.
5. Rebuild `prompt_ir_pointers` with SQLite `batch_alter_table(..., recreate="always")` (or the dialect-equivalent table rebuild). This is required because the old inline unique creates an unnamed SQLite autoindex that cannot be dropped by name. The rebuilt table removes the shot-only inline unique, makes `target_media` `NOT NULL`, adds `ck_prompt_ir_pointer_target_media`, and adds `uq_prompt_ir_pointer_media_scope`.
6. Recreate the existing `ix_prompt_ir_pointers_book_episode` and `ix_prompt_ir_pointers_shot` indexes. The composite unique index is the exact-scope lookup index.
7. Re-read all rows and verify row count, IDs, version IDs, payload hashes, qualification states, timestamps, and derived scope values. Verify every pointer/payload invariant before committing.

For non-SQLite engines, use an explicitly named old constraint if introspection finds one; never assume a guessed name. The SQLite path is mandatory for the repository's local and test databases.

## Backfill blockers

The migration must stop with a clear diagnostic if any row has:

- missing pointed version or authority lineage;
- pointer book/episode/shot different from the version;
- invalid or mismatched `payload_hash`;
- invalid JSON or missing `generation_policy`;
- missing, null, empty, lower-case, `UNKNOWN`, `AUTO`, or otherwise invalid `target_media`;
- a duplicate target-media scope after derivation.

There is no default-to-IMAGE path and no partial backfill. A failed backfill leaves the pre-migration schema and rows unchanged.

## Downgrade contract

Downgrade first groups pointers by `(book_id, episode, storyboard_shot_id)`.

```text
count > 1 → refuse with PROMPT_IR_POINTER_DOWNGRADE_CARDINALITY_CONFLICT
count ≤ 1 → safe to rebuild the old one-pointer-per-shot table
```

The conflict check occurs before any table rebuild, so a dual-media database cannot be randomly reduced to IMAGE, VIDEO, newest, or latest. The safe path drops the composite constraint/check and `target_media`, restores the old shot-only unique, recreates the two existing indexes, and verifies row count and all preserved pointer payload fields. It is lossless only when every shot has at most one pointer.

## Rollback and verification fixtures

The implementation test plan must run upgrade → downgrade → upgrade on:

1. a fresh database;
2. a pre-migration database with one IMAGE pointer per shot;
3. a pilot copy with IMAGE and VIDEO pointers for one shot;
4. a tampered/malformed backfill fixture.

The dual-media downgrade must fail before mutation. Missing/invalid policy, pointer/version mismatch, duplicate scope, and invalid enum fixtures must fail before mutation. No migration test may call a Provider, LLM, image, or video service.

The pointer implementation test plan must also exercise two concurrent writes to the same `(shot, target_media)` scope (one committed winner or deterministic conflict) and concurrent IMAGE/VIDEO writes for one shot (both scopes retained). These are database-constraint tests, not application-only uniqueness tests.
