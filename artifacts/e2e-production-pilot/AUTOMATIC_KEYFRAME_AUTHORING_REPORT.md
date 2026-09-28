# Automatic Keyframe Authoring Report

## Completion

`AUTOMATIC_KEYFRAME_AUTHORING_COMPLETE`

- Phase: `PHASE_AUTOMATIC_KEYFRAME_AUTHORING`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Remote HEAD before final report refresh: `6668a1a85ece52bcc576b0fd308d8cc0d7af031c`
- Implementation commit: `545242c118104ff9e13f250291af13ad7c4f985b`
- Report commit: `6668a1a85ece52bcc576b0fd308d8cc0d7af031c`
- Migration head: `m4h5i6j7k8l9`

## Delivered

- Added a deterministic, provider-free `AutomaticKeyframePlan` draft layer over the active `StoryboardMaterializationSet` and `StoryboardShot` authorities.
- Added active materialization pointer and source fingerprint guards. A plan is marked `STALE` and compile fails closed after a pointer switch, source revision, ShotDirection revision, GenerationIntent change, or ProductionPromptVersion change.
- Added human review actions `APPROVE`, `REJECT`, and `REVISE`; generated plans begin at `REVIEW_REQUIRED` and never create production keyframes before approval.
- Added deterministic start, optional middle, and end frame planning. Motion fields inherit `camera_motion`, `character_motion`, `environment_motion`, and `emotion_transition` from the active ShotDirection.
- Added atomic compilation through the existing `create_keyframe_sequence` and existing `KeyframeSequence` / `Keyframe` models. Existing keyframe duration, ordering, boundary, and state validation remains authoritative.
- Added immutable `ProductionPromptVersion` rows for each compiled frame with AutomaticKeyframePlan, Keyframe, ShotDirection, GenerationIntent, and source lineage references.
- Added compile idempotency, versioned Plan and Sequence history, and video compatibility checks for duration, first/last frame boundaries, and motion profile.
- Added API routes:
  - `POST /shots/{id}/keyframe-plan/generate`
  - `GET /shots/{id}/keyframe-plan`
  - `POST /shots/{id}/keyframe-plan/{version}/review`
  - `POST /shots/{id}/keyframe-plan/{version}/compile`

## Authority and safety boundary

- Existing `KeyframeSequence`, `Keyframe`, `KeyframeAssetBinding`, `ShotDirection`, `StoryboardMaterializationSet`, `StoryboardMaterializationPointer`, `StoryboardShot`, `ProductionGenerationIntent`, and `ProductionPromptVersion` are reused.
- No second Keyframe, Shot, Prompt, Asset, Review, Task, or Model Registry system was added.
- Source Fact, ScriptIR, StoryboardPlan, and materialized Shot authority rows are read-only inputs to this layer; the new writes are Plan and downstream Keyframe lineage only.
- `PromptIRPointer` is not created or activated in this phase; the existing PromptIR authority remains downstream and unchanged.
- No real LLM, SHAPI image provider, MiniMax H3 video provider, image generation, video generation, rendering, editing, subtitles, audio, or publishing was invoked.
- Human review remains mandatory before compilation and downstream media generation.

## Verification

- Automatic Keyframe tests: `4 passed`.
- Focused regression (`Automatic Keyframe`, existing Keyframe Authoring, Storyboard Production Materialization, Automatic Storyboard, Shot Direction, Prompt Lineage, Video Runtime, Migration Hardening): `46 passed`.
- Full regression: `1911 passed`.
- Golden regression: `5 passed, 0 failed`.
- Migration CI: PASS for fresh upgrade, repeat upgrade, legacy fixtures, schema verification, and drift; current head `m4h5i6j7k8l9`.
- `python -m compileall -q api core models scripts tests`: PASS.
- `git diff --check`: PASS.

## Required behavior evidence

- Review gate: unapproved plans return `REVIEW_REQUIRED`; no `KeyframeSequence` or `Keyframe` rows are created.
- Valid compile: approved Plan v1 creates the existing Sequence v1 with `start`, `middle`, and `end` frames and immutable frame prompt versions.
- Atomic failure: an invalid frame leaves zero new production Sequence or Keyframe rows and preserves the pre-existing prompt row.
- Idempotency: repeating compile for the same Plan version and source fingerprint returns the same Sequence without duplicate production rows.
- Materialization switch: switching the active pointer marks the old Plan `STALE` with `MATERIALIZATION_POINTER_CHANGED`; the old Plan is preserved.
- Rollback: restoring a pointer does not silently reactivate historical production state; the historical Plan requires a fresh human approval after source revalidation.
- Versioning: a ShotDirection revision creates Plan v2 and Sequence v2 while preserving Sequence v1 as historical `STALE` data.
- Video compatibility: the compiled Sequence exposes duration, start/end boundaries, and all four motion fields expected by the existing video runtime.

## Provider boundary

Provider calls in this phase: LLM `0`, SHAPI image `0`, MiniMax H3 video `0`.

The SHAPI endpoint `https://www.shapi.vip/` remains the existing image-provider reference only; this phase stops at reviewed KeyframeSequence and Keyframe rows.


