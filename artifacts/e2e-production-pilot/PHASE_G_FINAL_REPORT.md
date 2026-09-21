# PHASE_G_SCHEMA_DESIGN_APPROVED_PENDING_MIGRATION

## Phase G decision

The Schema Gate remains closed for implementation: the current repository cannot represent an independent shot-level Official Media Version, Official Media Authority, Official Media Pointer, or persisted deterministic Media Validation Record. The formal design review of the proposed future schema passes with explicit field and lifecycle clarifications. Implementation still requires separate migration approval.

No migration was approved for this task. No migration was added.

## Gap audit

See [`phase_g_media_authority_gap_audit.md`](phase_g_media_authority_gap_audit.md) for the read-only audit of:

- `MediaCandidateRecord` and `GenerationExecutionRecord`
- `VisualReferenceAsset`, `VisualReferenceAuthority`, `VisualReferenceSet`, and `VisualAssetPointer`
- transition contracts, frames, continuity reviews, and video retry attempts
- public asset storage readers
- all discovered media/official/validation/pointer model names and tables

The audit proves that existing Reference Authority and Visual Asset Pointer semantics cannot safely represent generated shot media. Candidate status remains `MEDIA_CANDIDATE`; no JSON field was used as an authority substitute.

## Design review and implementation plan

- [Schema Design Review](phase_g_media_authority_schema_review.md)
- [Migration Plan](phase_g_media_authority_migration_plan.md)
- [Migration Test Plan](phase_g_media_authority_test_plan.md)

Review verdict: `PHASE_G_SCHEMA_DESIGN_APPROVED_PENDING_MIGRATION`.

## Minimal schema proposal

See [`phase_g_media_authority_schema_proposal.md`](phase_g_media_authority_schema_proposal.md). It defines the minimum independent objects:

1. `MediaValidationRecord` — deterministic technical validation and authority snapshot.
2. `OfficialMediaVersion` — immutable shot/media-role revision bound to Candidate bytes and lineage.
3. `OfficialMediaAuthority` — explicit promotion envelope and decision fingerprint.
4. `OfficialMediaPointer` — unique current pointer by book, episode, shot, and media role.

It also defines exact fingerprints, uniqueness, stale/superseded lifecycle, atomic promotion, concurrency behavior, and fail-closed resolver rules.

## Full real production trigger

`FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_TRIGGERED = false`.

The current Phase A–F evidence is a persisted authority chain with a fake Provider Candidate, not a complete real production acceptance. Before the trigger can become true, the project still needs the dedicated Official Media Authority schema, deterministic media validation/promotion, and a full real-E2E acceptance of complete episode script, shot plan/storyboard, complete character/scene/key-prop assets with formal authority, and shot bindings.

## Verification performed

- Starting baseline confirmed as `73e9d1d58cd667cc3228c4eaad63d63d0103c2d8`.
- Working tree was clean before audit.
- Existing Phase A–F source and model audit completed read-only.
- No `alembic/versions` changes.
- Existing Phase A–F targeted regression plus migration hardening: `58 passed`.
- No external Provider, LLM, Candidate, Storyboard, PromptIR, Reference Authority, or storage writes.

## Stop token

Implementation stop: `MEDIA_OFFICIAL_AUTHORITY_SCHEMA_REQUIRED`

Design review completion token: `PHASE_G_SCHEMA_DESIGN_APPROVED_PENDING_MIGRATION`
