# Phase J2.2 Media-Scoped PromptIR Pointer Schema

## Review result

```text
PHASE_J2_2_MEDIA_SCOPED_PROMPT_IR_SCHEMA_APPROVED_PENDING_MIGRATION
```

This document is a design contract only. No ORM model, migration, API, compiler, resolver, or production database was changed.

## Target model

`PromptIRVersion.payload_json.generation_policy.target_media` remains the only semantic source. The pointer column is a scope discriminator copied from a compiled version and checked against it; it is not an independent policy.

Conceptual ORM target:

```python
class PromptIRPointer(Base):
    __tablename__ = "prompt_ir_pointers"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    episode = Column(Integer, nullable=False, index=True)
    storyboard_shot_id = Column(Integer, nullable=False, index=True)
    target_media = Column(String, nullable=False, index=True)
    prompt_ir_version_id = Column(Integer, nullable=False)
    payload_hash = Column(String, nullable=False)
    qualification_state = Column(String, nullable=False, default="PROMPT_IR_QUALIFIED")

    __table_args__ = (
        CheckConstraint(
            "target_media IN ('IMAGE','VIDEO')",
            name="ck_prompt_ir_pointer_target_media",
        ),
        UniqueConstraint(
            "book_id", "episode", "storyboard_shot_id", "target_media",
            name="uq_prompt_ir_pointer_media_scope",
        ),
    )
```

The final `String` length follows existing project conventions. The check constraint and application contract both reject empty, null, lower-case, `UNKNOWN`, `AUTO`, and `DEFAULT` values. Compilation normalizes an explicit request through `build_generation_policy()` and derives the pointer value from the compiled payload; a caller cannot independently set pointer scope.

## Invariants

Every current pointer must satisfy all of the following, or resolution fails closed:

```text
pointer.target_media ∈ {IMAGE, VIDEO}
pointer.target_media == pointed_version.payload_json.generation_policy.target_media
pointer.book_id == version.book_id
pointer.episode == version.episode
pointer.storyboard_shot_id == version.storyboard_shot_id
pointer.payload_hash == version.payload_hash
pointed_version.schema_version == prompt_ir_v2
```

`PromptIRAuthority` does not gain a second `target_media` column. Its existing envelope continues to bind the immutable payload and policy. `PromptIRVersion` does not gain a column either: adding one would create a payload/column dual truth without solving a requirement that the pointer contract cannot solve.

## Cardinality and indexes

The database guarantees one current pointer per `(book_id, episode, storyboard_shot_id, target_media)`. IMAGE and VIDEO pointers for the same shot may coexist. The existing `ix_prompt_ir_pointers_book_episode` and `ix_prompt_ir_pointers_shot` indexes remain. The named composite unique constraint supplies the exact scope lookup index; no redundant four-column non-unique index is proposed. A separate target-media index is unnecessary until a measured query requires it.

Concurrent updates to the same media scope must use the database constraint as the arbiter: an atomic update/upsert or a transaction with the scope row locked may replace the pointer, and a competing insert/update must resolve as one committed winner or a deterministic conflict/409. A concurrent IMAGE update and VIDEO update have different scopes and must not conflict merely because their shot is the same. Application `SELECT then INSERT` uniqueness is insufficient.

`media_role` remains independent. `SHOT_PRIMARY_IMAGE`, `SHOT_ALTERNATE_IMAGE`, and `TRANSITION_IMAGE` can all have `media_type=IMAGE`; current PromptIR selection must never parse role strings to infer a target media.

## Scope and byte preservation

The migration changes only pointer scope metadata and its constraints. It must preserve byte/semantic values of `PromptIRVersion.payload_json`, `payload_hash`, `PromptIRAuthority.envelope_json`, `envelope_fingerprint`, pointer version/hash/qualification fields, and every GenerationExecution, MediaCandidate, and OfficialMedia row. The migration does not create a VIDEO pointer that does not already exist.

The audit found no formal foreign key on the existing `PromptIRPointer` ORM/migration definition. This review intentionally does not add one or expand the migration into unrelated historical-schema cleanup; missing-FK risk remains a separately tracked concern.

## Explicit failure codes

The implementation should use stable 409 contracts for:

- `PROMPT_IR_MEDIA_SCOPE_REQUIRED` when a current resolver or production API has no target media.
- `PROMPT_IR_MEDIA_SCOPE_INVALID` for values outside exact `IMAGE`/`VIDEO`.
- `PROMPT_IR_POINTER_MEDIA_SCOPE_MISMATCH` when pointer scope and payload policy disagree.
- `PROMPT_IR_POINTER_TAMPERED` for version/shot/book/episode/hash mismatch.
- `PROMPT_IR_POINTER_MISSING` when the requested media scope has no current pointer.
