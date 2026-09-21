# Phase F Minimum Generation Execution Persistence Schema Proposal

## Review status

`PROPOSAL_ONLY_NO_MIGRATION`

This document makes the persistence blocker concrete for human review. It is
not an implementation and does not authorize a database migration. The
proposal preserves the Phase F boundary:

`Current PromptIR → deterministic GenerationPayload → execution attempt → provider provenance → Media Candidate`

The existing `TaskRun.payload`, `VisualReferenceAsset.generation_provenance`,
and `meta_info` remain projections/recovery data only. They are not promoted to
canonical Phase F truth.

## Proposed records

### 1. `generation_execution_records`

One append-only row represents one preview or execute attempt for one explicit
shot. A successful repeat resolves the existing completed row by the unique
request fingerprint and does not create another provider call.

| Field | Type / rule | Purpose |
| --- | --- | --- |
| `id` | integer primary key | Durable row identity |
| `execution_id` | string, unique | Public execution identity |
| `schema_version` | string | `generation_execution_request_v1` |
| `book_id`, `episode`, `storyboard_shot_id` | scoped integers | Explicit shot target; no first/latest lookup |
| `plan_shot_id` | string | Exact ShotPlan lineage |
| `execution_mode` | enum | `PREVIEW` or `CANARY` |
| `status` | enum | `PREVIEWED`, `AUTHORIZED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `STALE`, `REUSED` |
| `target_media` | enum | `IMAGE` for the first canary; `VIDEO` reserved |
| `prompt_ir_version_id` | integer | Exact PromptIR version |
| `prompt_ir_authority_id` | integer | Exact PromptIR authority |
| `prompt_ir_payload_hash` | string | Exact PromptIR integrity binding |
| `generation_payload_fingerprint` | string | Deterministic adapter output |
| `generation_policy_fingerprint` | string | Explicit policy binding |
| `model_profile_id` | string | Explicit registry selection |
| `model_profile_fingerprint` | string | Profile drift detection |
| `provider_adapter_id`, `provider_adapter_version` | strings | Transport contract binding |
| `reference_bindings_fingerprint` | string | Exact current reference authority set |
| `provider_request_fingerprint` | string, unique | Idempotency and concurrent duplicate guard |
| `request_snapshot_json` | secret-free audit JSON | Exact non-secret transport request projection; not semantic source |
| `confirmation_binding_hash` | string | Hash of token binding to PromptIR/payload/profile; raw token is never stored |
| `provider` / `model` | strings | Response provenance |
| `provider_request_id`, `provider_task_id` | strings | Provider identifiers, when supplied |
| `provider_response_hash` | string | Canonical non-secret response snapshot hash |
| `logical_provider_calls` | integer | Must be `0` for preview, at most `1` for canary |
| `transport_retry_count` | integer | Must be `0` for Phase F canary |
| `submitted_at`, `completed_at`, `latency_ms` | timestamps/integer | Replay and audit timing |
| `failure_code` / `failure_message` | strings | Explicit fail-closed result |
| `official_promotion_count` | integer | Must remain `0` in Phase F |
| `candidate_id` | nullable string | Link to the candidate row only after structural media validation |
| `created_at`, `updated_at` | timestamps | Append-only audit timing |

Required constraints:

- unique `provider_request_fingerprint`;
- unique `execution_id`;
- transactionally serialize the create-or-reuse decision before a provider
  call;
- `logical_provider_calls <= 1`, `transport_retry_count = 0` for `CANARY`;
- `official_promotion_count = 0` for every Phase F row;
- no API key, Authorization header, bearer token, signed URL secret, or raw
  confirmation token is persisted.

### 2. `media_candidate_records`

One row represents the canonical stored bytes produced by one successful
execution. It is deliberately below every official pointer and authority.

| Field | Type / rule | Purpose |
| --- | --- | --- |
| `id` | integer primary key | Durable candidate identity |
| `candidate_id` | string, unique | Public candidate identity |
| `execution_id` | string, unique FK | Exact execution lineage |
| `status` | enum | Always `MEDIA_CANDIDATE` in Phase F |
| `media_type` | enum | `IMAGE` or `VIDEO`; must match target |
| `storage_identity` | string, unique | Canonical stored object identity, never provider URL |
| `storage_reference_json` | secret-free projection | Canonical storage locator and serving metadata |
| `checksum_sha256` | string | Hash of actual stored bytes |
| `mime_type` | string | Parsed media type |
| `byte_size` | integer | Non-empty stored bytes |
| `width`, `height` | nullable integers | Parsed image dimensions |
| `duration_ms` | nullable integer | Parsed video duration |
| `prompt_ir_version_id`, `prompt_ir_payload_hash` | exact lineage fields | Candidate-to-PromptIR proof |
| `generation_payload_fingerprint` | string | Candidate-to-payload proof |
| `model_profile_id`, `model_profile_fingerprint` | strings | Candidate-to-profile proof |
| `provider_request_fingerprint` | string | Candidate-to-request proof |
| `provider_response_hash` | string | Candidate-to-response proof |
| `provider_task_id` | string | Provider provenance |
| `created_at` | timestamp | Candidate audit time |

Required constraints:

- `status` cannot be `SELECTED`, `LOCKED`, `OFFICIAL`, or
  `PRODUCTION_READY` in Phase F;
- candidate creation requires existing canonical bytes, valid checksum, valid
  MIME, parseable dimensions/duration, and a complete execution link;
- no write to `PromptIRPointer`, `Storyboard`, `VisualAssetPointer`,
  `VisualReferenceAuthority`, or any official media pointer;
- provider response claims such as `success`, `quality`, `score`, or `safe`
  are not validation truth.

## API boundary implied by the proposal

The production boundary should expose two operations:

1. `POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-canary/preview`
   accepts only `adapter_id` and explicit `model_profile_id`. It resolves the
   current PromptIR, validates historical integrity/currentness/assets/reference
   authority/policy, rebuilds the GenerationPayload, persists a preview record,
   and returns `provider_calls=0` plus a confirmation token.
2. `POST /api/books/{book_id}/episodes/{episode}/shots/{shot_id}/generation-canary/execute`
   accepts only `execute=true`, the preview fingerprint, and the matching
   confirmation token. It re-resolves and rebuilds all authority inputs, rejects
   any drift with `409 GENERATION_CANARY_STALE`, and only then invokes the
   existing provider transport once.

Neither endpoint accepts prompt text, negative prompt, motion prompt, image
URLs, provider URL, API key, model name, or provider configuration overrides.

## Why existing tables cannot be extended implicitly

`TaskRun` has no uniqueness or structured lineage fields. `VisualReferenceAsset`
is a compatibility/reference media container and its provenance is generic
JSON. `VisualReferenceGenerationRequest` is a pre-provider draft. The existing
authority tables intentionally represent current visual assets and references,
which a Phase F candidate must not mutate. Adding the fields above requires an
explicit schema decision; encoding them in existing JSON columns would violate
the stop condition.

## Decision required before implementation

Approve or reject this minimum two-record shape and its uniqueness/transaction
rules. Until approved, the repository remains at:

`GENERATION_EXECUTION_PERSISTENCE_SCHEMA_REQUIRED`

No migration, Phase F endpoint, fake-provider pilot, or real-provider canary is
authorized by this proposal alone.
