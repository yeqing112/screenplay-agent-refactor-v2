# Phase G Media Authority Gap Audit

## Audit identity

- Task: `PHASE_G_MEDIA_VALIDATION_AND_OFFICIAL_AUTHORITY_BOUNDARY`
- Formal baseline: `73e9d1d58cd667cc3228c4eaad63d63d0103c2d8`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Audit mode: read-only schema gate
- Decision: `MEDIA_OFFICIAL_AUTHORITY_SCHEMA_REQUIRED`
- No database, Candidate, Pointer, Reference Authority, PromptIR, Storyboard, or storage mutation was performed.

## Evidence inspected

- `models/generation_execution.py`
- `models/visual_authority.py`
- `models/visual.py`
- `api/generation_canary_api.py`
- `core/public_asset_storage.py`
- Alembic revisions through `y8h9i0j1k2l3`
- Current SQLAlchemy metadata and existing Phase A–F pilot artifacts

## Findings

### 1. Shot-level Official Media Version

**Absent.** `MediaCandidateRecord` is the only generated-media persistence model. `VisualAssetVersion` is an authoring/spec asset version and is not bound to a generated storyboard shot, execution, PromptIR, GenerationPayload, or provider response.

### 2. Shot-level Official Media Authority

**Absent.** `VisualReferenceAuthority` exists, but its contract is for character/scene/prop reference assets (`asset_key`, `asset_version_id`, `reference_scope`, `image_identity`, and reference storage). It is not an authority envelope for a generated shot output.

### 3. Shot-level Official Media Pointer

**Absent.** `VisualAssetPointer` points to the current version of a visual authoring asset. No pointer is scoped by `(book_id, episode, storyboard_shot_id, media_role)` for official generated media.

### 4. Current-only resolver

**Absent for official shot media.** Existing visual asset and reference resolvers resolve their own domains. There is no `resolve_current_official_media(...)` that verifies pointer, version, authority, validation, candidate, storage bytes, and upstream currentness together. No latest-candidate/latest-validation fallback is available because those objects do not exist yet.

### 5. Immutable media version

**Absent.** `MediaCandidateRecord` stores provenance and technical fields but has no immutable official-version identity, revision, stale/superseded lifecycle, validation binding, or authority envelope. SQL row mutability cannot be treated as official-media immutability.

### 6. Historical stale/superseded lifecycle

**Absent for shot media.** `VisualAssetVersion` and transition records have unrelated stale/superseded fields. No generated-media official version can be marked stale while preserving a replacement lineage.

### 7. Candidate validation record

**Absent.** Phase F has `_validate_candidate_lineage(...)`, which checks DB lineage fields during replay. It does not persist a technical validation result, validation payload, validation fingerprint, authority snapshot, or validation lifecycle status.

### 8. Promotion event / decision

**Absent.** `GenerationExecutionRecord.official_promotion_count` is only a counter initialized to zero; it is not a promotion decision, event, authority envelope, confirmation binding, or pointer transition record.

### 9. Media-domain separation

The repository separates reference assets (`VisualReferenceAsset` / `VisualReferenceAuthority`), transition frames (`StoryboardTransitionFrame`), continuity reviews (`StoryboardTransitionContinuityReview`), and video retry attempts (`StoryboardVideoRetryAttempt`). Generated shot media exists only as `MediaCandidateRecord`; there is no official generated-media domain object. This separation must be preserved.

### 10. Reuse of `VisualReferenceAuthority`

**Not legal.** Reference Authority has asset/version scope and reference status semantics. A generated shot Candidate requires execution, PromptIR, GenerationPayload, model/profile, provider request/response, storage bytes, media role, and current shot lineage. Reusing the reference table would conflate reference input with generated output, provide the wrong uniqueness scope, and permit the wrong lifecycle transitions.

### 11. Candidate direct upgrade

**Not legal.** `MediaCandidateRecord` is execution-output evidence and must remain `MEDIA_CANDIDATE` and immutable. Official status cannot be represented by changing `candidate.status` or by inserting `official=true` into JSON fields.

### 12. Storage capability

`core.public_asset_storage._load_source_bytes(...)` can read data URIs, local manual media, local paths, and HTTP(S) sources; Phase F records a storage identity, checksum, MIME type, byte size, and dimensions. There is no Candidate-specific resolver that rereads canonical bytes, recomputes SHA-256, validates MIME/media type/dimensions, and persists a validation fingerprint.

### 13. Migration requirement

The existing schema cannot express the required validation/version/authority/pointer lifecycle. A dedicated migration is required. No Phase G migration has formal approval, so implementation must stop at this gate.

## Schema gate decision

`MEDIA_OFFICIAL_AUTHORITY_SCHEMA_REQUIRED`

The minimum dedicated schema is documented in `phase_g_media_authority_schema_proposal.md`. No migration was added and no Candidate or existing authority model was repurposed.
