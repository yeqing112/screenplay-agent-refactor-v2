# Phase G Media Authority Migration Plan

## Status and gate

- Design status: `PHASE_G_SCHEMA_DESIGN_APPROVED_PENDING_MIGRATION`
- This is a plan only. No `alembic revision` was run and no migration file was created.
- Migration requires separate formal approval before implementation.
- Existing Phase A–F tables and rows must remain unchanged.

## New tables

### 1. `media_validation_records`

Purpose: immutable deterministic validation evidence for one Candidate.

Core columns:

```text
id PK
validation_id UNIQUE
candidate_id FK/equivalent lookup -> media_candidate_records.candidate_id
execution_id FK/equivalent lookup -> generation_execution_records.execution_id
candidate_fingerprint
technical_validation_payload_json
technical_validation_fingerprint
authority_snapshot_json
authority_snapshot_fingerprint
validator_version
status
created_at
```

Allowed status values: `VALIDATION_PENDING`, `TECHNICALLY_VALID`, `REVIEW_REQUIRED`, `REJECTED`, `STALE`. `AUTO_PROMOTED` is not a valid value.

### 2. `official_media_versions`

Purpose: immutable formally adopted revision for one shot/media role.

Core columns:

```text
id PK
official_media_version_id UNIQUE
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
byte_size
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

Allowed status values: `CURRENT`, `SUPERSEDED`, `STALE`.

### 3. `official_media_authorities`

Purpose: independent production-truth envelope for an OfficialMediaVersion.

Core columns:

```text
id PK
authority_id UNIQUE
official_media_version_id UNIQUE
authority_envelope_json
payload_hash
lineage_hash
validation_fingerprint
promotion_fingerprint
status
created_at
```

The envelope must contain explicit confirmation/operator action metadata. `lineage_hash` and `promotion_fingerprint` are required integrity boundaries.

### 4. `official_media_pointers`

Purpose: current-only shot/media-role pointer.

Core columns:

```text
id PK
book_id
episode
storyboard_shot_id
media_role
official_media_version_id
authority_id
fingerprint
updated_at
```

## Keys and indexes

### Primary keys

Each table uses an internal integer `id` primary key. Stable external identities (`validation_id`, `official_media_version_id`, `authority_id`) are unique and indexed.

### Unique keys

```text
media_validation_records.validation_id
official_media_versions.official_media_version_id
official_media_authorities.authority_id
official_media_pointers (book_id, episode, storyboard_shot_id, media_role)
official_media_versions (book_id, episode, storyboard_shot_id, media_role, revision)
```

The existing Candidate uniqueness remains unchanged:

```text
candidate_id
execution_id
storage_identity
```

### Foreign keys / equivalent integrity

Where the current SQLite architecture permits, add foreign keys to the stable Candidate and execution identities. Otherwise enforce the same binding in deterministic resolver/service code and migration tests. Official Version must bind Validation; Authority must bind Version; Pointer must bind both Version and Authority. No new table may point to a “latest” row.

### Lookup indexes

Add indexes for:

```text
candidate_id
execution_id
candidate_fingerprint
validation_fingerprint
storyboard_shot_id
media_role
official_media_version_id
authority_id
status
stale_status if represented separately
```

## Transaction and concurrency requirements

- Version, Authority, and Pointer creation/move are one transaction.
- A failed promotion writes zero rows or pointer changes.
- Same Candidate/current lineage reuses the existing revision.
- Different Candidates require an explicit revision decision and deterministic conflict handling.
- Pointer uniqueness is enforced at the database boundary; no last-writer-wins behavior.
- Resolver uses the exact pointer and never queries by descending id or created time.

## Backward compatibility and migration risk

- No existing `MediaCandidateRecord` is migrated, rewritten, or assigned Official status.
- No `VisualReferenceAsset`, `VisualReferenceAuthority`, `VisualReferenceSet`, or `VisualAssetPointer` row is repurposed.
- No PromptIR, Storyboard, Asset, or Phase A–F authority table is altered.
- Existing Phase A–F replay and candidate behavior remains unchanged.
- The new tables start empty; a later explicitly approved backfill/promotion process must create records through the validation and promotion contracts, never by bulk status update.

## Rollback and verification plan

Before applying a future migration:

1. run migration chain hardening and schema introspection;
2. verify all existing table counts and hashes are unchanged;
3. apply and downgrade in an isolated database;
4. verify new tables are empty and old tables are byte/schema compatible;
5. run candidate, validation, promotion, resolver, and concurrency tests;
6. verify no Provider or LLM calls.

## Not performed in this task

```text
alembic revision
model changes
API changes
Candidate changes
backfill
promotion
Provider calls
LLM calls
```
