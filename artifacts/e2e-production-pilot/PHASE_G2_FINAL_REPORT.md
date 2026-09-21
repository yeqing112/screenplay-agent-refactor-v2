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

`pytest -q tests/test_media_validation_promotion_contract.py` → **14 passed**.

Covered cases include validation and promotion idempotency, explicit confirmation rejection, cross-session replay, true concurrent promotion, revision and pointer movement, PromptIR drift to `STALE`, Asset Pointer revision drift, Reference Authority revision drift, candidate checksum/storage tamper, validation payload/snapshot tamper, authority lineage tamper, pointer fingerprint tamper, Official Version tamper, and fail-closed exact resolution.

`python -m scripts.verify_migration_chain --ci` → **exit 0**.

Migration head remains `z0a1b2c3d4e5`; the verifier exercised the complete chain through the Phase G foundation tables.

Golden regression (`python scripts/run-golden-regression.py`) → **5/5 fixtures passed**.

Web regression (`npm --prefix web test -- --run`) → **51 files / 301 tests passed**. Production build (`npm --prefix web run build`) passed.

Full backend regression (`pytest -q`) → **1709 passed, 10 failed**. The 10 failures are pre-existing branch artifact/configuration assertions outside G2 (historical director-quality authority fixtures, active gray registry default, and targeted fact extraction snapshot semantics); the G2 tests, Phase D/E/F tests, migration hardening, production workspace projection, and visual asset authority API all pass. No failure was introduced by the G2 changes.

## Pilot evidence

The local Phase F fake-provider pilot used one Candidate, one validation, and one Official chain:

- Candidate: `candidate-phase-g2-pilot`
- Validation: `mvr-dffd6f637a1c5cdd803dfb128af82fc953726ee4`
- Official version: `omv-f8fca8d5bccaabd086998a9f0f53228063fa1ddc`
- Authority: `oma-8bd6f2008fe80e632c66571e79ace18747775edc`
- Pointer: `1`
- Candidate status, storage identity, checksum, dimensions, and execution lineage were unchanged before and after promotion.
- Resolver returned the exact promoted version. A replay returned `reused=true`.
- A–F authority and execution counts were unchanged; only the four G2 rows were added (`ValidationRecord`, `OfficialMediaVersion`, `OfficialMediaAuthority`, `OfficialMediaPointer`).

Machine-readable evidence:

- [`phase_g2_validation_contract.json`](phase_g2_validation_contract.json)
- [`phase_g2_media_validation_trace.json`](phase_g2_media_validation_trace.json)
- [`phase_g2_official_media_trace.json`](phase_g2_official_media_trace.json)

## Call and scope accounting

Provider calls: **0** additional calls. LLM calls: **0**. Image calls: **0**. Video calls: **0**.

The stored Phase F execution evidence still records its original fake-provider call; G2 performs no provider transport. No AI aesthetic, CLIP, or LLM visual scoring was introduced. Full Real E2E remains `false`. Complete asset binding and full production E2E remain outside this phase because the contract only validates and promotes an existing Phase F Candidate without changing upstream authority schemas.

`FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_TRIGGERED=false`.

## Review status

`PHASE_G2_MEDIA_VALIDATION_AND_PROMOTION_CONTRACT_READY_FOR_REVIEW`
