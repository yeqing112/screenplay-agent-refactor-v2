# PHASE_F_GENERATION_EXECUTION_PROVIDER_CANARY_CLOSURE

## Current status

`STOPPED_AT_GAP_AUDIT`

Phase F has not been signed off. The formal audit, revalidated against current
HEAD `aaccf3dcf52e4c70d84ce65f4f83813b07afe913`, found that the repository
does not yet have a structured, durable shot-level execution record for the
required PromptIR → GenerationPayload → Provider Request/Response → Media
Candidate chain. The Phase F rules explicitly prohibit using generic
`TaskRun.payload`, `meta_info`, or `generation_provenance` JSON as a new
canonical truth, and explicitly prohibit adding a migration in this stop path.

## Evidence

- Gap audit: `phase_f_generation_execution_gap_audit.md`
- Contract: `phase_f_generation_execution_contract.json`
- Audit baseline: `434fa124e686ed16aedaafafeb57d2cdb4aac293`
- Provider calls in this audit: `0`
- Database migrations added: `0`

The existing provider transport and canonical byte-storage helpers are reusable
after the schema decision. The legacy creative task path is not reusable as the
Phase F authority because it accepts free-form prompt/reference fields, uses an
in-memory `_creative_tasks` worker state, can retry image requests, and writes
storyboard/reference projections on success.

## Required next decision

Human review must define and approve the minimum persistence schema for:

- execution intent and explicit canary confirmation;
- exact PromptIR, GenerationPayload, GenerationPolicy, ModelProfile, and
  provider request lineage;
- provider response hash, call/retry counts, and secret-free provenance;
- Media Candidate storage identity, checksum, MIME, dimensions, and lineage;
- uniqueness/serialization for idempotent single-call execution.

Until that decision is made, no Phase F preview, fake-provider pilot, real
provider canary, migration, or completion token is claimed.
