# PHASE_G2_MEDIA_VALIDATION_AND_PROMOTION_CONTRACT_READY_FOR_REVIEW

## Scope

Phase G2 adds the deterministic media validation and explicit promotion contract on top of the Phase F `MEDIA_CANDIDATE` record. The implementation is additive and does not rewrite Candidate, GenerationExecution, PromptIR, Storyboard, Reference Authority, or VisualAssetPointer rows.

## Delivered

- Candidate integrity checks bind Candidate fields to its GenerationExecution lineage and keep Candidate status at `MEDIA_CANDIDATE`.
- Technical validation reads canonical storage bytes and verifies supported image signature, SHA-256, byte size, MIME, media type, and dimensions.
- `MediaValidationRecord` creation is idempotent by candidate fingerprint, authority snapshot fingerprint, and validator version.
- Promotion requires an explicit positive confirmation and a valid validation record. It creates one Official Media Version, Authority, and exact-scope Pointer in one commit.
- Repeated promotion reuses the existing chain. A different Candidate creates an explicit revision and supersedes the previous current version for that exact shot and role.
- Resolver follows the exact Pointer only. It has no `latest` fallback and fails closed on pointer, authority envelope, lineage, validation, upstream currentness, or storage tamper.
- API routes are registered under `/api/media-authority`; promotion request fields are `extra="forbid"`.

## Verification

`pytest -q tests/test_media_validation_promotion_contract.py` → **8 passed**.

Covered cases include validation and promotion idempotency, explicit confirmation rejection, cross-session replay, revision and pointer movement, PromptIR drift to `STALE`, storage tamper, validation fingerprint tamper, authority lineage tamper, pointer fingerprint tamper, and fail-closed exact resolution.

`python -m scripts.verify_migration_chain --ci` → **exit 0**.

Migration head remains `z0a1b2c3d4e5`; the verifier exercised the complete chain through the Phase G foundation tables.

## Pilot evidence

The local Phase F fake-provider pilot used one Candidate, one validation, and one Official chain:

- Candidate: `candidate-phase-g2-pilot`
- Validation: `mvr-dffd6f637a1c5cdd803dfb128af82fc953726ee4`
- Official version: `omv-f8fca8d5bccaabd086998a9f0f53228063fa1ddc`
- Authority: `oma-8bd6f2008fe80e632c66571e79ace18747775edc`
- Pointer: `1`
- Candidate status, storage identity, checksum, dimensions, and execution lineage were unchanged before and after promotion.
- Resolver returned the exact promoted version. A replay returned `reused=true`.

Machine-readable evidence:

- [`phase_g2_validation_contract.json`](phase_g2_validation_contract.json)
- [`phase_g2_media_validation_trace.json`](phase_g2_media_validation_trace.json)
- [`phase_g2_official_media_trace.json`](phase_g2_official_media_trace.json)

## Call and scope accounting

Provider calls: **0** additional calls. LLM calls: **0**. Image calls: **0**. Video calls: **0**.

The stored Phase F execution evidence still records its original fake-provider call; G2 performs no provider transport. No AI aesthetic, CLIP, or LLM visual scoring was introduced. Full Real E2E remains `false`. Complete asset binding and full production E2E remain outside this phase because the contract only validates and promotes an existing Phase F Candidate without changing upstream authority schemas.

## Review status

`PHASE_G2_MEDIA_VALIDATION_AND_PROMOTION_CONTRACT_READY_FOR_REVIEW`
