# Prompt Production Quality Report

## Executive Summary

Full-flow: `PASS` through PromptIR and provider-payload capture; media submission stopped by policy.

- Episode: `红伞倒影` / Book `990401` / Episode `1`.
- Storyboard: `16` materialized shots; `15` current PromptIR pairs; Shot 016 is fail-closed `NOT_APPLICABLE`.
- LLM calls: `0`; IMAGE Provider calls: `0`; VIDEO Provider calls: `0`.
- Prompt quality result: `PROMPT_QUALITY_BLOCKED`.

## Prompt pipeline topology

`Source Script → ScriptIR → Director Treatment → Scene Blocking → ShotPlan → Storyboard → ShotDirection → Asset Bindings → PromptIR → Provider Payload`

Lineage is exported at L0–L12 for each shot package. Provider payload JSON is redacted and includes hashes/fingerprints.

## IMAGE prompt findings

The canonical adapter preserves semantic sections and asset identity references, but serializes them as JSON blocks. The provider prompt has no readable character state, scene layout, lighting direction or VisualStyleProfile. This is a production blocker.

## VIDEO prompt findings

The VIDEO policy is `IMAGE_TO_VIDEO`, 5 seconds, 768p, 16:9. The generated provider prompt repeats the starting-frame semantic surface and does not state an explicit ending state. Camera motion and subject motion are present as structured fields, but not rendered as executable short-form instructions.

## IMAGE/VIDEO pair findings

Pair alignment is `WARNING`: semantic subjects, scene and camera are equal, but reference authority is not locked and the VIDEO prompt does not express a clean start → action → end transition.

## Continuity findings

Character face/hair/costume, time, weather, lighting and screen direction are unknown in the current authoritative layers. These are continuity data gaps, not invented drift.

## TOP_10_PROMPT_PRODUCTION_ISSUES

1. **BLOCKER · PROVIDER_PROJECTION_STRUCTURED_JSON** — Provider-facing IMAGE and VIDEO prompts are renderer JSON sections, not executable natural-language prompts. (owner: `PROVIDER_PROJECTION`).
2. **BLOCKER · VIDEO_PROVIDER_PROMPT_IS_STRUCTURED_JSON** — 75API VIDEO payload receives the same structured semantic surface instead of a short IMAGE_TO_VIDEO action prompt. (owner: `PROVIDER_PROJECTION`).
3. **HIGH · REFERENCE_AUTHORITY_NOT_LOCKED** — Asset bindings exist, but current reference authority/token is not locked for the provider payload. (owner: `REFERENCE_BINDING`).
4. **HIGH · CHARACTER_STATE_NOT_VERBALIZED** — Face, hair, costume, accessories and state are not represented as provider-readable prose. (owner: `CHARACTER_STATE`).
5. **HIGH · SCENE_STATE_NOT_VERBALIZED** — Location layout, time, weather and light direction are absent from the provider-facing prompt. (owner: `SCENE_STATE`).
6. **HIGH · VISUAL_STYLE_NOT_BOUND** — No VisualStyleProfile is bound into the prompt package. (owner: `VISUAL_STYLE`).
7. **HIGH · VIDEO_ENDING_STATE_NOT_EXPLICIT** — Video semantic projection has action and duration but no explicit ending state. (owner: `SHOT_DIRECTION`).
8. **MEDIUM · PROMPT_LANGUAGE_MIXED** — Field labels are English JSON while source values are Chinese; this is not a deliberate provider language strategy. (owner: `PROMPT_COMPILER`).
9. **MEDIUM · NEGATIVE_PROMPT_UNAVAILABLE** — The selected generic adapters do not support negative_prompt; no negative text was sent. (owner: `PROVIDER_PROJECTION`).
10. **MEDIUM · PROMPTIR_SCOPE_GAP_SHOT_016** — Materialized shot 016 has no current PromptIR authority and is fail-closed as NOT_APPLICABLE. (owner: `PROMPT_IR`).

## Representative manual-style review

- **Close-up / insert:** the provider prompt exposes `CAMERA` JSON but does not verbalize lens, subject placement, face state or prop continuity. The camera data comes from `SHOT_PLAN`; the missing prose belongs to `PROVIDER_PROJECTION` and `CHARACTER_STATE`.
- **Two-person interaction:** subject references and spatial zones are preserved, but the provider prompt contains identity tokens rather than a readable interaction beat. The source is `SHOT_PLAN`/`SCENE_STATE`; the projection must render it without leaking internal IDs.
- **Action + camera motion:** movement is carried in structured `ACTION`/`CAMERA` sections. The source exists, but the VIDEO adapter must convert it into one primary action, one camera movement and an explicit ending state.

## Recommended owning-layer fixes

1. Add authoritative CharacterProfile/SceneIdentity/VisualStyleProfile bindings before compilation.
2. Render natural-language provider prompts from semantic PromptIR; do not pass JSON field names or internal IDs.
3. Add an IMAGE_TO_VIDEO projection that emits starting state reference, one main action, camera movement, expression transition and ending state.
4. Lock reference authority/token fingerprints before marking generation ready.
5. Materialize PromptIR for Shot 016 or keep it explicitly blocked until the upstream gap is repaired.

## Go / No-Go

`PROMPT_QUALITY_BLOCKED` — do not enter real IMAGE/VIDEO quality canary until the two BLOCKER items and reference/continuity gaps are fixed.
