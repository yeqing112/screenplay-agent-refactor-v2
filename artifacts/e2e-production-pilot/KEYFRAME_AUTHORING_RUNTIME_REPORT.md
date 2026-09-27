# Keyframe Authoring Runtime Report

## KEYFRAME_AUTHORING_RUNTIME_COMPLETE

- **Implementation commit:** `64fc1e3` (`feat: add keyframe authoring runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Migration head:** `e5f6a7b8c9d0`
- **Image generation provider:** [SHAPI](https://www.shapi.vip/)
- **Existing image transport contract:** `shapi-openai-images.image.v1` via `https://shapi.vip/v1`
- **Provider calls in this runtime slice:** `0` (provider-free authoring, lineage, and regression tests)

## Delivered runtime

- `KeyframeSequence` persists a versioned duration and frame plan for one existing `StoryboardShot`.
- `Keyframe` persists ordered `start`, `middle`, and `end` frame states with camera, character, scene, emotion, and motion intent fields.
- Sequence validation fails closed for missing shots, invalid duration, duplicate or out-of-order times, missing start/end frames, and boundary times outside the sequence duration.
- Prompt injection adds `Frame State` and `Motion Preparation` after the existing Shot Direction constraints while preserving the original prompt snapshot.
- Prompt Lineage appends an immutable derived `ProductionPromptVersion` with `KEYFRAME_AUTHORING` and `SHOT_DIRECTION` provenance.
- `KeyframeAssetBinding` links a keyframe to the existing Production Asset Authority registry, version, and current pointer. The first frame can be marked primary and is checked during sequence validation.
- APIs are available at both stable and `/api` paths:
  - `GET /shots/{shot_id}/keyframes`
  - `POST /shots/{shot_id}/keyframes`
  - `PUT /keyframes/{keyframe_id}`
  - `GET /shots/{shot_id}/keyframes/validation`
  - `POST /keyframes/{keyframe_id}/prompt`
  - `POST /keyframes/{keyframe_id}/assets`

The implementation reuses `StoryboardShot`, Shot Direction, Prompt Lineage, Generation Intent-compatible prompt versions, and the existing asset authority/version/pointer graph. It does not add a second shot, prompt, asset, task, video, editing, or animation system.

## Verification

- `pytest -q tests/test_keyframe_authoring_runtime.py` — **4 passed, 0 failed**
- Focused runtime/migration regression — **47 passed, 0 failed**
- `pytest -q` — **1860 passed, 0 failed**
- `npm run test:golden` — **5/5 passed**
- `python -m scripts.verify_migration_chain --ci` — **PASS**; fresh/repeated upgrade, legacy replay, schema drift
- API route import/registration check — **PASS**
- `python -m compileall -q` for new runtime modules — **PASS**
- `git diff --check` — **PASS**

## SHAPI handoff

The keyframe runtime emits provider-neutral frame state and motion preparation constraints. Downstream image generation remains routed through the existing SHAPI adapter contract at `https://shapi.vip/v1`; this phase made no external provider request and does not generate video or animation.
