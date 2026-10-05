# Historical SC002_002 Keyframe Lineage Report

Status: `KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE`

This phase was read-only. Real IMAGE: `0`; Real VIDEO: `0`; Provider POST: `0`; database writes: `0`.

## Historical evidence

- Run: `20261004T162533Z`; version: `1`.
- Media SHA: `f039112c1a3eb0d7d24785a684b9c104989a549df235a4fdd52c72956e1472c1`; recalculated bytes SHA: `f039112c1a3eb0d7d24785a684b9c104989a549df235a4fdd52c72956e1472c1`; exact: `true`.
- Dimensions: `1672×941`; review: `APPROVE`; judge: `PASS`.
- Provider preview URL is present only as historical evidence. It is not canonical storage truth.

## Existing canonical scan

- GenerationExecutionRecord matches: `0`.
- MediaCandidateRecord matches: `0`.
- MediaValidationRecord matches: `0`.
- MediaPromotionRecord matches: `0`.
- OfficialMediaVersion matches: `0`.
- OfficialMediaAuthority matches: `0`.
- OfficialMediaPointer matches: `0`.
- No record was created and no ID was invented.

## Prompt and Provider lineage

- Historical prompt artifact: `present`; persisted exact PromptIR lineage: `NOT FOUND`.
- Historical provider request fingerprint: `NOT FOUND`.
- Historical provider response hash: `NOT FOUND`.
- Current profile substitution: forbidden.

## Adoption decision

`CANONICAL_ADOPTION_NOT_PROVEN` → `KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE`.

The only valid next action is a new canonical IMAGE generation for SC002_002, followed by Candidate → deterministic validation → explicit review/promotion → OfficialMedia. That action was not executed in this phase.

## Video reference preflight

The FIRST_FRAME preflight remains blocked because there is no current OfficialMedia source binding. No payload was built and no Provider POST was attempted.

## Final closure fields

- Existing canonical scan: Execution `0`; Candidate `0`; Validation `0`; Promotion `0`; OfficialMediaVersion `0`; OfficialMediaAuthority `0`; OfficialMediaPointer `0` matching records.
- Prompt lineage: historical prompt artifact present; persisted PromptIR version/hash exact `NOT FOUND`; status `HISTORICAL_KEYFRAME_PROMPT_LINEAGE_UNRECOVERABLE`.
- Provider lineage: historical provider/model evidence present; request fingerprint and response hash `NOT FOUND`; status `HISTORICAL_PROVIDER_LINEAGE_UNRECOVERABLE`.
- Adoption: eligible `false`; executed `false`; provider calls `0`; no execution/candidate/validation/promotion/official IDs created.
- OfficialMedia: role `KEYFRAME_START_IMAGE` candidate only; checksum exact in artifact; current pointer `false`.
- Video reference bridge: asset id source `OfficialMediaVersion.official_media_version_id`; authority fingerprint source `OfficialMediaAuthority.lineage_hash`; generation execution source `MediaCandidateRecord.execution_id`; FIRST_FRAME `BLOCKED`.
- Runtime reference: URL resolution `false`; hardcoded URL `false`; runtime SHA verification `NOT APPLICABLE` because no canonical source binding exists.
- Final VIDEO preflight: compiled prompt SHA `bfed0de8fe178c819219d0e7f8a59e549cd7d8dcb7727482d65b0c5aff3e8495`; payload SHA `NOT_BUILT_REFERENCE_BLOCKED`; reference lineage `BLOCKED`; POST count `0`.
- Tests: targeted `120 passed`; full baseline `2119 passed / 24 baseline failures`; new failed nodes `0`.
- Safety: Real IMAGE `0`; Real VIDEO `0`; Provider POST `0`; SHAPI `0`; Poyo `0`; production writes `0`; Book 990400 writes `0`; secret leaks `0`; signed URL query persisted `0`; raw base64 persisted `0`; orphans `0`.
- Execution base: `dab5b97c4ae6ee13976c58b9d5af4b3f529c21ca`.
- Final status: `KEYFRAME_CANONICAL_LINEAGE_UNRECOVERABLE`.

The only valid next action is to regenerate one SC002_002 keyframe through the canonical IMAGE path, then use the existing Candidate → deterministic validation → explicit promotion → OfficialMedia chain. That action is intentionally deferred to a later phase.
