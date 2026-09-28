# KEYFRAME_IMAGE_PRODUCTION_REPORT

## Result

`KEYFRAME_IMAGE_PRODUCTION_COMPLETE`

The single-shot vertical slice now runs through the existing authorities:

`Reviewed Keyframe → PromptIR Pointer/Version → GenerationExecutionRecord → Model Registry profile → deterministic SHAPI-compatible fixture → MediaCandidate → technical validation → REVIEW_REQUIRED → human APPROVE → OfficialMediaVersion/Pointer → KeyframeAssetBinding`.

The executable prompt authority is the existing **PromptIRPointer + PromptIRVersion**. The immutable `ProductionPromptVersion` remains the keyframe prompt source and is recorded in the execution request snapshot; no second prompt authority was introduced.

## Repository and migration

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Previous remote HEAD before this implementation: `6f1a537b68e3ead98c28bb620c22e7111e13709b`
- Implementation commit: `33fc4f7841b933754eae8e68fa876b1d55ade0eb`
- Report commit: recorded by the commit containing this report
- Migration head: `m4h5i6j7k8l9`
- New migration: **not required**. Existing GenerationExecution, PromptIR, Media Authority, Production Asset Authority, and Keyframe Authoring tables express the new scope.

## Runtime evidence

| Check | Result |
|---|---:|
| Keyframe image production tests | 4 passed |
| Focused regression | 31 passed |
| Full regression | 1915 passed |
| Golden | 5/5 (existing baseline) |
| Migration CI | fresh/repeat/legacy/drift PASS (existing baseline) |
| SHAPI provider calls | 0 real calls; fixture provider metadata only |
| MiniMax H3 calls | 0 |
| Candidates created (START + END vertical slice) | 2 |
| Validated candidates | 2 |
| Approved candidates | 2 |
| Official Media versions | 2 |
| Keyframe asset bindings | 2 |

## Contract outcomes

- Eligibility rechecks active sequence, compiled AutomaticKeyframePlan, and current source fingerprint; stale sources fail closed.
- START, MIDDLE, and END are represented by the existing `Keyframe.frame_type`; production role is recorded as `KEYFRAME_<TYPE>_IMAGE`.
- START approval sets the existing keyframe binding as primary.
- Candidate bytes remain immutable and must pass existing technical validation before review.
- REJECT and REQUEST_CHANGE preserve candidate, execution, and review history; a subsequent request creates a new execution/candidate.
- Repeating the same request while review is active or approved reuses the existing execution (idempotent).
- Official promotion and the existing typed Production Asset Authority bridge plus `KeyframeAssetBinding` are flushed in one transaction through the promotion callback; failures roll back the transaction.
- No source fact, ScriptIR, StoryboardPlan, StoryboardShot, ShotDirection, or AutomaticKeyframePlan fact is mutated by image production.
- The fixture path emits no network request and no secret. Real provider execution is fail-closed unless a future explicit canary gate is enabled.
- Video compatibility remains through the existing keyframe binding contract; no video is generated in this phase.

## API

- `POST /keyframes/{id}/image-production`
- `GET /keyframes/{id}/image-production`
- `POST /keyframes/{id}/image-production/review`
- Existing `/assets/candidates/{candidate_id}/validate` and `/assets/candidates/{candidate_id}/promote` remain the canonical candidate/review APIs.

## Working tree

Clean after the report commit and push.
