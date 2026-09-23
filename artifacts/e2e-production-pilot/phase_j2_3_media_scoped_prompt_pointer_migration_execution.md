# Phase J2.3 Media Scoped PromptIR Pointer Migration Execution

Status: `PHASE_J2_3_MEDIA_SCOPED_PROMPT_IR_IMPLEMENTATION_READY_FOR_REVIEW`

## Migration

- Revision: `b2c3d4e5f6g7`
- Down revision: `a1b2c3d4e5f6`
- Scope: add `prompt_ir_pointers.target_media`, remove the legacy single-column shot uniqueness, and enforce uniqueness on `(book_id, episode, storyboard_shot_id, target_media)`.
- Semantic source: `PromptIRVersion.payload_json.generation_policy.target_media`.
- No `target_media` column was added to `PromptIRVersion` or `PromptIRAuthority`.
- No provider, LLM, image, or video call was made.

## Deterministic backfill

The migration validates pointer/version book, episode, shot, payload hash, and canonical payload fingerprint before DDL. It derives `target_media` only from the stored generation policy and blocks missing, malformed, lowercase, `AUTO`, or otherwise invalid values. No IMAGE default and no media-role inference are used.

Disposable SQLite verification completed:

- fresh base to head: PASS
- legacy IMAGE pointer backfill: PASS (`target_media=IMAGE`)
- row count preserved through upgrade: PASS
- single-scope downgrade: PASS
- multi-scope downgrade: fails closed with `PROMPT_IR_POINTER_DOWNGRADE_CARDINALITY_CONFLICT` before schema mutation

The migration was exercised only against disposable test databases; no production database was opened or migrated.

## Remaining review boundary

This is implementation-ready for review. J3 provider convergence and real media generation remain outside this phase.
