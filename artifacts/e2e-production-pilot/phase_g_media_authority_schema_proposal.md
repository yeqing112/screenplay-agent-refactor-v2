# Phase G Media Authority Schema Proposal

## Status

Proposal only. This document does not create tables or migration files. It is required because the current schema cannot represent a shot-level Official Media lifecycle.

## Design boundary

```text
MediaCandidate (immutable execution evidence)
  -> MediaValidationRecord (deterministic technical validation)
  -> explicit promotion decision
  -> OfficialMediaVersion (immutable official revision)
  -> OfficialMediaAuthority (authority envelope)
  -> OfficialMediaPointer (current shot/role pointer)
```

`VisualReferenceAuthority` remains reference-only. `MediaCandidateRecord.status` remains `MEDIA_CANDIDATE`.

## Proposed entities

### `media_validation_records`

Purpose: persist one deterministic validation result without changing the Candidate.

Required fields:

- `id`, `validation_id` (unique)
- `candidate_id`, `execution_id`
- `candidate_fingerprint`
- `technical_validation_payload_json`
- `technical_validation_fingerprint`
- `authority_snapshot_json`
- `authority_snapshot_fingerprint`
- `validator_schema_version`
- `status`: `VALIDATION_PENDING`, `TECHNICALLY_VALID`, `REVIEW_REQUIRED`, `REJECTED`, or `STALE`
- `created_at`

The immutable validation payload and fingerprints must be integrity-checked. Revalidation must compare the current Candidate and current authority snapshot; a status change must be an explicit lifecycle event, never an in-place payload rewrite.

### `official_media_versions`

Purpose: immutable official revision for one shot and media role.

Required fields:

- `id`, `official_media_version_id`, `revision`
- `book_id`, `episode`, `storyboard_shot_id`, `plan_shot_id`
- `media_role` (initial role: `SHOT_PRIMARY_IMAGE`)
- `media_type` (`IMAGE`, `VIDEO`, or `TRANSITION_FRAME`)
- `candidate_id`, `candidate_fingerprint`
- `candidate_checksum_sha256`, `storage_identity`, `mime_type`, `byte_size`, `width`, `height`, `duration_ms`
- `validation_id`, `validation_fingerprint`
- `prompt_ir_version_id`, `prompt_ir_payload_hash`
- `generation_payload_fingerprint`
- `provider_request_fingerprint`, `provider_response_hash`
- `payload_hash`, `stale_status`, `superseded_by_version_id`, `created_at`

Promotion must bind the exact Candidate bytes and checksum. Promotion cannot copy, transcode, crop, recolor, or otherwise mutate media bytes.

### `official_media_authorities`

Purpose: independent authority envelope proving the explicit promotion decision.

Required fields:

- `id`, `authority_id`, `official_media_version_id` (unique)
- `authority_envelope_json`, `authority_envelope_fingerprint`
- `payload_hash`
- `validation_id`, `validation_fingerprint`
- upstream PromptIR, GenerationPayload, Asset, Reference, and provider lineage fingerprints
- `promotion_decision_json`, `promotion_decision_fingerprint`
- explicit confirmation binding/operator action metadata
- `stale_status`, `stale_reasons`, `created_at`

This object must never be inferred from Candidate status or from a latest row.

### `official_media_pointers`

Purpose: current-only pointer from a shot and role to one official version.

Required fields and constraints:

- `id`, `book_id`, `episode`, `storyboard_shot_id`, `media_role`
- `current_version_id`
- `pointer_payload_hash`, `authority_envelope_fingerprint`
- `stale_status`, `stale_reasons`, `updated_at`
- unique `(book_id, episode, storyboard_shot_id, media_role)`
- foreign-key/equivalent integrity to the selected OfficialMediaVersion

The resolver must follow this exact pointer only; no latest-version, latest-validation, or latest-candidate fallback is permitted.

## Deterministic contracts

### Candidate fingerprint

Canonical hash of candidate id, execution id, storage identity, checksum, dimensions, PromptIR hash, GenerationPayload fingerprint, provider request fingerprint, and provider response hash. Timestamps are excluded.

### Technical validation

The pure validator must reread canonical storage bytes and deterministically report:

- file exists and is readable
- bytes are non-empty
- recomputed SHA-256 equals Candidate checksum
- MIME is parseable and matches Candidate
- media type matches the requested role
- dimensions are parseable and match Candidate
- duration is parseable for future video media
- storage identity is stable
- Candidate and execution lineage is complete

Validation must not use CLIP, face similarity, LLM judgement, prompt similarity, keyword heuristics, or other subjective visual scoring as a Production hard gate.

### Promotion

Promotion requires a separate explicit confirmation bound to candidate fingerprint, validation fingerprint, current PromptIR hash, current asset/reference lineage, and current pointer state. It must:

1. validate the validation record integrity;
2. reread and validate Candidate bytes and lineage;
3. re-resolve current PromptIR, Asset, Reference, and GenerationPolicy authority;
4. compare technical and authority fingerprints;
5. create/reuse the immutable OfficialMediaVersion, Authority, and Pointer atomically.

Promotion must call zero Provider and zero LLM calls, cannot accept prompt/style/reference/storage/checksum overrides, and cannot modify PromptIR, Storyboard, VisualAssetPointer, ReferenceAuthority, or Candidate bytes.

## Lifecycle and concurrency

- Candidate remains immutable `MEDIA_CANDIDATE`.
- Failed or rejected Candidates remain queryable; retry/repair creates a new execution and Candidate in a later phase.
- A stale upstream revision makes the old validation/promotion ineligible; it cannot be silently repaired by a new Candidate.
- Same Candidate + same current lineage reuses the existing official version and does not create a duplicate.
- Different Candidates for the same shot/role require a deterministic conflict/revision decision; no last-writer-wins behavior.
- Pointer, Version, and Authority creation/move occur in one transaction. Failed promotion writes none of the three.
- A tampered current pointer, version, authority, validation, Candidate, or storage file fails closed; a new promotion cannot wash away a tampered old official record.

## Proposed uniqueness and indexes

- `media_validation_records`: unique validation id; idempotency key over candidate fingerprint + authority snapshot fingerprint + validator schema version.
- `official_media_versions`: unique `(book_id, episode, storyboard_shot_id, media_role, revision)`; indexed Candidate and validation fingerprints.
- `official_media_authorities`: unique official version id and authority fingerprint.
- `official_media_pointers`: unique `(book_id, episode, storyboard_shot_id, media_role)`; indexed current version id and pointer fingerprint.

## Migration and approval

A new migration is required to implement this proposal. Phase G has no formal migration approval, so this proposal is intentionally unimplemented. No JSON field, Candidate status, StoryboardShot metadata, or VisualReferenceAuthority is used as a substitute.
