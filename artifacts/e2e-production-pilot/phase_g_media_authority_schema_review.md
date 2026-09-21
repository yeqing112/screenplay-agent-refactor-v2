# Phase G Media Authority Schema Design Review

## Review identity

- Task: `PHASE_G_SCHEMA_APPROVAL_AND_MIGRATION_DESIGN_REVIEW`
- Baseline: `0d168d28afe6a3a485522f6291e1be9410f64a55`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Reviewed inputs:
  - `phase_g_media_authority_schema_proposal.md`
  - `phase_g_media_authority_gap_audit.md`
- Review scope: schema responsibilities, lifecycle, uniqueness, resolver, promotion transaction, migration safety
- Verdict: `PHASE_G_SCHEMA_DESIGN_APPROVED_PENDING_MIGRATION`

## A. Why a new schema is required

`MediaCandidateRecord` is Provider output evidence. It records the result of one generation execution and must remain `MEDIA_CANDIDATE`; it is not a production truth assertion. An Official Media Authority must independently prove why one immutable media version is currently adopted for one shot and role.

| Model | Responsibility |
|---|---|
| `MediaCandidateRecord` | Provider output evidence and immutable candidate lineage |
| `VisualReferenceAuthority` | Character, location, and prop reference authority |
| `StoryboardTransitionContinuityReview` | Video continuity review between shots |
| `OfficialMediaAuthority` | Shot-level production media truth after explicit promotion |

The existing models have different scopes, uniqueness, upstream lineage, and lifecycle states. Reusing them would collapse reference input, generated output, validation fact, and official pointer into one authority domain.

## Review of the existing proposal

### Responsibilities remain separated

The proposed flow keeps five distinct objects:

```text
Candidate = generation result evidence
Validation = deterministic validation fact
Official Version = formally adopted immutable media revision
Authority = proof of production truth and promotion decision
Pointer = current shot/role reference
```

No object is allowed to create or overwrite another object's semantic truth. Candidate status never becomes `OFFICIAL`.

### No fallback and no latest semantics

The proposal correctly requires an exact current pointer. The future resolver must load the pointer's exact Version, Authority, Validation, Candidate, storage bytes, and upstream lineage. It must not use latest Candidate, latest Validation, latest Version, filename, prompt text, or creation time as a substitute.

### No automatic Promotion

Technical validation success is a fact only. Promotion remains a second explicit action with confirmation. Validation cannot create an Official Version or move the Pointer automatically.

### No Provider or LLM calls

Validation and Promotion are local deterministic operations. Both paths must report `provider_calls=0` and `llm_calls=0`; they cannot retry, repair, or regenerate media.

## B. Entity review and normalized contracts

The following field names are the approved canonical names for the future migration. JSON suffixes may be used in SQL column names, but the logical field names must remain stable.

### `MediaValidationRecord`

Required fields:

```text
id
validation_id
candidate_id
execution_id
candidate_fingerprint
technical_validation_payload
technical_validation_fingerprint
authority_snapshot
authority_snapshot_fingerprint
validator_version
status
created_at
```

Allowed `status` values:

```text
VALIDATION_PENDING
TECHNICALLY_VALID
REVIEW_REQUIRED
REJECTED
STALE
```

`AUTO_PROMOTED` is forbidden. The technical payload and fingerprints are immutable facts. A stale transition is an explicit lifecycle update or append-only lifecycle record; it must never rewrite the original validation payload.

### `OfficialMediaVersion`

Required fields:

```text
id
official_media_version_id
book_id
episode
storyboard_shot_id
plan_shot_id
media_role
media_type
candidate_id
candidate_fingerprint
storage_identity
checksum_sha256
mime_type
width
height
duration_ms
prompt_ir_version_id
prompt_ir_payload_hash
generation_payload_fingerprint
provider_request_fingerprint
provider_response_hash
validation_id
validation_fingerprint
revision
status
payload_hash
created_at
```

Allowed `status` values:

```text
CURRENT
SUPERSEDED
STALE
```

The review adds explicit `status` and `provider_response_hash` to remove ambiguity from the earlier proposal's `stale_status` wording. The row is immutable after creation; replacement creates a new revision and marks the old version `SUPERSEDED` or `STALE` through an auditable lifecycle transition.

### `OfficialMediaAuthority`

Required fields:

```text
authority_id
official_media_version_id
authority_envelope
payload_hash
lineage_hash
validation_fingerprint
promotion_fingerprint
status
created_at
```

The `authority_envelope` must include the explicit operator confirmation binding, media role, current upstream lineage snapshot, and the decision that this version is accepted as Production Truth. `lineage_hash` covers PromptIR, GenerationPayload, Asset, Reference, Candidate, Validation, and provider provenance. `promotion_fingerprint` covers the candidate fingerprint, validation fingerprint, current pointer state, role, and explicit promotion decision. The authority is independent of Candidate status.

### `OfficialMediaPointer`

Required fields:

```text
book_id
episode
storyboard_shot_id
media_role
official_media_version_id
authority_id
fingerprint
```

Its only responsibility is:

```text
(book, episode, shot, role) -> current official media version
```

The unique key is `(book_id, episode, storyboard_shot_id, media_role)`. `fingerprint` covers the exact pointer, Version, and Authority binding. Pointer movement is atomic with Version and Authority creation.

## C. Uniqueness and lifecycle review

### Candidate constraints

Existing Candidate constraints remain unchanged:

```text
candidate_id unique
execution_id unique
storage_identity unique
```

No Candidate migration or status mutation is part of this design.

### Official Version constraints

```text
(book_id, episode, storyboard_shot_id, media_role, revision) unique
```

A Candidate fingerprint and validation fingerprint are indexed for integrity and idempotency checks.

### Pointer constraints

```text
(book_id, episode, storyboard_shot_id, media_role) unique
```

There is exactly one current pointer per shot and role. Missing, stale, or mismatched pointers fail closed.

### Lifecycle

```text
Candidate: MEDIA_CANDIDATE (immutable; never OFFICIAL)
Validation: VALIDATION_PENDING -> TECHNICALLY_VALID/REVIEW_REQUIRED/REJECTED -> STALE
Official Version: CURRENT -> SUPERSEDED or STALE
Authority: active -> STALE/SUPERSEDED through an explicit lifecycle record
Pointer: exact current binding; atomic move to a new revision
```

`Validation PASS -> automatic promotion` is forbidden.

## D. Promotion and concurrency review

The approved promotion sequence is:

```text
Candidate
  -> deterministic Validation
  -> explicit confirmation
  -> OfficialMediaVersion
  -> OfficialMediaAuthority
  -> OfficialMediaPointer
```

The Version, Authority, and Pointer are created/moved in one transaction. Any failure produces zero writes to those three objects.

- Same Candidate, same current lineage: reuse the existing official revision; never create a duplicate.
- Different Candidate for the same shot/role: require an explicit revision decision; never use last-writer-wins.
- Promotion revalidates Candidate integrity, storage bytes, Validation integrity, current PromptIR/Asset/Reference lineage, and exact pointer state.
- Promotion accepts only `candidate_id`, `validation_id`, and explicit confirmation. It cannot accept prompt, style, reference, storage, checksum, or media URL overrides.
- Promotion does not call Provider or LLM and cannot modify PromptIR, Storyboard, VisualAssetPointer, ReferenceAuthority, or Candidate bytes.

## E. Current resolver review

The future `resolve_current_official_media(...)` must verify, in order:

1. exact Pointer scope and fingerprint;
2. exact OfficialMediaVersion and status;
3. exact OfficialMediaAuthority and envelope/lineage hashes;
4. exact Validation record and fingerprint;
5. Candidate status and complete lineage;
6. canonical storage bytes, recomputed checksum, MIME, dimensions, and media type;
7. current PromptIR, Asset, Reference, and GenerationPolicy lineage.

No latest fallback is permitted at any layer.

## F. Migration safety review

The design is approved only as a future migration design. The migration must create four new tables and indexes without altering existing Phase A–F tables. It must not migrate or rewrite existing Candidate rows, Reference rows, or Visual Asset rows. The migration plan and test plan are separate artifacts; no Alembic revision is created in this task.

## Review decision

The design is internally consistent after the explicit field/lifecycle clarifications above. It is approved pending formal migration approval and implementation:

`PHASE_G_SCHEMA_DESIGN_APPROVED_PENDING_MIGRATION`
