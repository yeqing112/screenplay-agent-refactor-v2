# Phase F Generation Execution Gap Audit

## Audit status

`PHASE_F_REPLAY_PROFILE_CONTRACT_AND_REAL_AUTHORITY_PILOT_CLOSURE_READY_FOR_REVIEW`

The opening section records the historical pre-approval gap audit. It is retained
as evidence of why generic `TaskRun`/`meta_info` fields were rejected. The schema
was implemented in migration `y8h9i0j1k2l3`; formal preimplementation human approval provenance is not verified, and
verified with the fake-provider pilot below. No external Provider was called.

Audit baseline: `434fa124e686ed16aedaafafeb57d2cdb4aac293`  
Branch: `codex/visual-authoring-provider-canary-reconcile`

## Historical revalidation before schema approval

The audit was re-run against the pre-implementation remote-synchronized HEAD
`aaccf3dcf52e4c70d84ce65f4f83813b07afe913`. A full model search found no
`GenerationExecution`, `MediaCandidate`, or equivalent execution model. The
SQLAlchemy column inventory confirms that the closest existing records are
insufficient:

| Existing table | Relevant persisted columns | Missing Phase F proof |
| --- | --- | --- |
| `task_runs` | task identity/status/progress/book/episode/generic `payload`/error/timestamps | PromptIR, GenerationPayload, policy, profile, provider fingerprints, response hash, candidate identity, uniqueness |
| `visual_reference_generation_requests` | request fingerprint, asset key/version, request JSON, status, provider-not-called marker | shot/PromptIR lineage, model profile fingerprint, response/media provenance, candidate state |
| `visual_reference_assets` | asset/version, URL/path, status, checksum, generic provenance/meta JSON | execution identity, exact PromptIR and GenerationPayload bindings, provider request/response hashes, immutable attempt |
| `visual_authoring_proposals` | authoring provider request/response fingerprints and proposal status | media bytes/candidate identity and PromptIR execution lineage |
| `storyboard_video_retry_attempts` | source task, retry root, input fingerprint/snapshot, error/provider response | first execution record and image candidate lifecycle |
| `storyboard_transition_frames` / `storyboard_transition_continuity_reviews` | frame/video storage, checksum, dimensions/review fields | generation request lineage and provider provenance |

This current-state evidence confirms that the stop condition is structural,
not an absence of a convenient helper or an unsearched existing table.

## Existing production path

1. `POST /api/prototyping/generate-image`,
   `POST /api/prototyping/generate-reference-image`, and
   `POST /api/prototyping/generate-video` accept
   `CreativeGenerationRequest` (`api/server.py:4673`). The request accepts
   caller supplied `prompt`, `negative_prompt`, `reference_images`,
   `first_frame_url`, and model fields. This is a legacy creative request,
   not a Phase F authority contract.
2. `_enqueue_creative_task` (`api/server.py:13956`) resolves the requested
   profile, requires `confirmed` plus `allow_external_call` for non-mock
   providers, creates an in-memory `_creative_tasks` entry, then persists a
   serialized copy through the generic `TaskRun` helper and schedules
   `_run_creative_task`.
3. `_run_creative_task` (`api/server.py:13550`) sends the caller request to
   `api/generation_adapters.py`. It may use the mock adapter, image transport,
   or video transport. On success it persists a local media copy and then
   writes either a `VisualReferenceAsset` candidate or storyboard media via
   `_save_asset_to_storyboard` (`api/server.py:12630`). The non-reference path
   therefore mutates storyboard media automatically, which Phase F forbids.
4. Provider transport is already centralized in
   `api/generation_adapters.py` (`generate_image_asset` at line 1530 and
   `generate_video_asset` at line 1632). Phase F must reuse only safe transport
   and storage primitives after a new authority boundary; it must not call
   the legacy creative route.

## Required audit answers

| Question | Current finding | Evidence / Phase F consequence |
| --- | --- | --- |
| 1. Who sends the real provider request? | `api.generation_adapters.generate_image_asset` / `generate_video_asset`, called from `_run_creative_task`. | Reusable transport exists; the legacy task boundary is not reusable as authority. |
| 2. Where is the provider profile resolved? | `_resolve_creative_profile` in `api/server.py`, delegating to `resolve_generation_profile`; registry data comes from `api/model_registry.py`. | A Phase F resolver must require an explicit `model_profile_id`; no default/latest lookup. |
| 3. Where is the API key read? | `get_profile(..., include_sensitive=True)` returns registry profile data; adapters read `profile["api_key"]`. | Phase F audit records only `credential_configured` / source identity and never copies secrets. |
| 4. Where is request payload built? | Provider-specific builders in `api/generation_adapters.py`; the legacy image path also builds a payload directly in `generate_image_asset`. | A deterministic GenerationPayload-to-transport bridge is missing. |
| 5. Where is response saved? | In-memory task state, `TaskRun.payload`, and selected provider metadata under the task/asset projection. | No dedicated execution response record exists. |
| 6. Where is task status saved? | `_creative_tasks` is the live state; `_persist_task_state` mirrors it into `TaskRun`. | DB-backed task visibility exists, but it is a generic snapshot rather than a Phase F execution authority. |
| 7. Is there in-memory-only task state? | Yes. `_creative_tasks` is the primary runtime dictionary; DB load is a recovery/list fallback. | It cannot be the sole execution truth. |
| 8. Is there a DB-backed execution record? | No. `TaskRun` has generic status/progress/book/episode/payload/error fields only. | **Blocking persistence gap.** |
| 9. Is `VisualReferenceAsset` candidate or authority? | It can hold a generated reference candidate; its `status`/`authority_status` are mutable compatibility fields. | It is not a shot-level Media Candidate execution record and cannot become authority automatically. |
| 10. Which path auto-selects? | Existing asset/storyboard flows expose `adopted=True` in `build_task_adapter_asset`; adoption endpoints can write selection state. | Phase F must not reuse this success projection. |
| 11. Which path auto-locks? | Reference authority APIs can bind/lock a `VisualReferenceAuthority`; the creative task path itself currently writes a `VisualReferenceAsset` candidate. | Phase F must not call authority binding or lock on success. |
| 12. Does provider failure auto-retry? | Image safety recovery retries with adjusted prompts in `_generate_image_asset_with_provider_recovery`; async transports poll and retry selected 429s. | This violates the one-call/no-retry Phase F contract. A new wrapper must disable retry or STOP. |
| 13. Is the original request snapshot saved for retry? | Video failures use `StoryboardVideoRetryAttempt.input_snapshot`; ordinary creative attempts use `TaskRun.payload`. | Retry evidence exists for video, but it is not a Phase F execution record and Phase F does not implement retry. |
| 14. Is checksum computed after download? | `_persist_generated_image_locally` and `_persist_generated_video_locally` hash canonical stored bytes with SHA-256. | Reusable storage primitive; candidate dimensions and complete lineage still need a dedicated record. |
| 15. Is storage identity stable? | Local generated-media filenames include book/task label and content digest; media is served through stable local routes. | Reusable for fake/local pilot only after candidate persistence is modeled. |
| 16. Can response be proven to belong to exact GenerationPayload? | No dedicated persisted binding. Provider payload is copied into generic task metadata when available. | Missing canonical execution lineage. |
| 17. Can media be proven to belong to exact PromptIRVersion? | No structured candidate/execution columns bind PromptIR IDs or PromptIR payload hash. | Missing canonical execution lineage. |
| 18. Is there a provider request fingerprint? | `VisualAuthoringProposal` has one for LLM authoring; creative tasks do not have a Phase F provider request fingerprint. | Missing shot-level execution fingerprint. |
| 19. Is there a provider response hash? | `VisualAuthoringProposal` has `provider_response_hash`; creative task state stores a response object without a dedicated hash column. | Missing shot-level response provenance. |
| 20. Is there a media checksum? | `VisualReferenceAsset` and local persistence metadata can carry SHA-256. | Reusable storage evidence, but not bound to an execution row. |
| 21. Is there an official media pointer? | No Phase F pointer is present; existing storyboard/authority writes are exactly the automatic promotion that Phase F forbids. | Candidate must remain below official authority. |

## Existing object roles

### `VisualAuthoringProposal`

`models/visual_authority.py:96` is provider-generated authoring review material.
It is intentionally below the canonical visual authority spine and is scoped by
`request_id` plus provider request fingerprint. It does not represent a media
candidate, exact PromptIR lineage, stored media bytes, or a shot-level execution
attempt. Reusing it would conflate authoring proposals with generation output.

### `VisualReferenceGenerationRequest`

`models/visual_authority.py:175` stores a draft request fingerprint, asset key,
asset version, request JSON, status, and a `provider_not_called` marker. It is a
reference-generation preparation object, not an execution record. It has no
PromptIR version/authority fields, GenerationPayload fingerprint, model profile
fingerprint, provider response hash, media checksum, or candidate identity.

### `VisualReferenceAsset` and reference authority

`models/visual.py:157` stores a reference media container with URL/path,
checksum, status, and provenance. `VisualReferenceAuthority` and
`VisualReferenceSet` are authority objects in the existing visual-asset chain.
They must remain unchanged by a Phase F candidate execution. A generated shot
frame or video cannot be forced into this reference-only container without a
dedicated candidate contract.

### `TaskRun` and `_creative_tasks`

`TaskRun` (`models/task.py:10`) is a generic task snapshot. The live
`_creative_tasks` dictionary is still the primary worker state. The persisted
`payload` is a JSON blob, which is useful for recovery and UI status but is
explicitly disallowed by the Phase F specification as the canonical place for
execution lineage. There is no uniqueness constraint for a Phase F provider
request fingerprint and no atomic single-call/idempotency record.

### `StoryboardVideoRetryAttempt`, transition frame, and continuity review

`StoryboardVideoRetryAttempt` (`models/visual.py:280`) correctly preserves a
manual-retry input snapshot and does not itself retry. It is a future retry
audit object, not a first execution or media candidate record. Transition frames
and continuity reviews are downstream video review objects and must not be used
to bypass the Phase F candidate boundary.

## Provider and storage reuse decision

- Reuse the existing transport functions and canonical byte storage helpers
  only after a Phase F execution contract validates all authority inputs.
- Do not reuse `_enqueue_creative_task`, `_run_creative_task`,
  `_generate_image_asset_with_provider_recovery`, or `_save_asset_to_storyboard`
  as the Phase F boundary: they accept free-form creative input, perform retry
  behavior, or mutate storyboard/reference projections.
- Do not create a second `requests.post`/`httpx.post` provider client.

## Blocking schema gap and minimum future shape

The pre-implementation schema could not durably express the required Phase F record without
using `TaskRun.payload`, `VisualReferenceAsset.generation_provenance`, or
`meta_info` as an undocumented JSON authority. After the architectural review,
the dedicated migration provides structured, queryable fields for:

- execution request identity and `execution_mode=CANARY`;
- exact book/episode/storyboard shot and PromptIR version/authority/hash;
- GenerationPayload and GenerationPolicy fingerprints;
- explicit ModelProfile ID/fingerprint and adapter/version;
- provider request fingerprint and a secret-free request snapshot;
- confirmation-token binding and stale-input snapshot;
- execution status, logical call count, transport retry count, timestamps,
  provider request/task IDs, and canonical response hash;
- Media Candidate identity, storage identity, checksum, MIME, byte size,
  dimensions/duration, and all lineage fingerprints;
- explicit failure state and no-promotion counters;
- a uniqueness/serialization rule preventing concurrent duplicate provider
  calls for one fingerprint.

The pre-implementation finding was `GENERATION_EXECUTION_PERSISTENCE_SCHEMA_REQUIRED`; the schema was then explicitly approved and implemented as migration `y8h9i0j1k2l3`.

## Audit conclusion

The existing provider transport and byte-storage primitives are reused only behind the new Phase F boundary. The legacy creative task boundary remains excluded because it accepts free-form creative input, retries, and performs authority projections. The dedicated records now provide the required execution lineage, candidate provenance, and idempotency uniqueness.

## Implementation addendum — current closure state

The former structural gap is closed by migration `y8h9i0j1k2l3` and the two dedicated SQLAlchemy models `GenerationExecutionRecord` and `MediaCandidateRecord`. The Phase F API boundary is implemented in `api/generation_canary_api.py` and registered by `api/server.py`.

The preview path is provider-free and reconstructs current PromptIR/GenerationPayload. The execute path requires an explicit confirmation token, re-resolves current authority, rejects PromptIR/payload/policy/model/reference/provider fingerprint drift with `409` before any provider call, persists `submitted_at` before the provider boundary, permits one logical call with zero transport retries, and persists only a `MEDIA_CANDIDATE` after canonical byte validation.

The synthetic unit evidence remains in `episode_01_phase_f_fake_provider_trace.json`; the real authority integration evidence is in `episode_01_phase_f_real_authority_fake_provider_trace.json`. The fake provider returned a real PNG and successful replay made zero provider calls. Real external provider execution remains intentionally unclaimed because no provider was configured or authorized.

Current closure status:

```text
PHASE_F_REPLAY_PROFILE_CONTRACT_AND_REAL_AUTHORITY_PILOT_CLOSURE_READY_FOR_REVIEW
```

Extended verification records:

```text
phase_e_targeted=52_passed
phase_f_targeted=13_passed
migration_chain_hardening=7_passed
golden_regression=5_passed
release_gate_self_test=passed
web_tests=301_passed
web_build=passed
full_backend=1663_passed_4_known_baseline_failures
phase_f_induced_failures=0
production_release_gate=blocked_by_environment_and_historical_baseline
```
