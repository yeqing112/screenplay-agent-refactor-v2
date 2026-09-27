# Shot Direction Runtime Report

## SHOT_DIRECTION_RUNTIME_COMPLETE

- **Implementation commit:** `ef54a0a` (`feat: add shot direction runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Migration head:** `e4f5a6b7c8d9`
- **Image generation provider:** [SHAPI](https://www.shapi.vip/)
- **Existing image transport contract:** `shapi-openai-images.image.v1` via `https://shapi.vip/v1`
- **Provider calls in this runtime slice:** `0` (provider-free runtime and regression tests)

## Delivered runtime

- `ShotDirection` persists one canonical direction record for each existing `StoryboardShot`, covering shot type, camera, movement, composition, performance, and emotion profiles.
- Create and update operations validate required camera parameters, increment immutable revisions, and refresh a deterministic direction fingerprint.
- Validation fails closed for missing direction, incomplete profiles, invalid lens/angle/distance/speed, and missing required composition or performance constraints.
- Prompt injection appends a provider-neutral shot direction constraint block while preserving the original prompt snapshot.
- Prompt Lineage creates an immutable derived `ProductionPromptVersion` with `SHOT_DIRECTION` provenance and the direction constraint structure.
- APIs are available at both stable and `/api` paths:
  - `POST /shots/{shot_id}/direction`
  - `GET /shots/{shot_id}/direction`
  - `PUT /shots/{shot_id}/direction`
  - `GET /shots/{shot_id}/direction/validation`
  - `POST /shots/{shot_id}/direction/prompt`

The implementation reuses the existing `StoryboardShot`, Prompt Lineage, and asset authority identities. It does not add a second shot, prompt, asset, or task system, and it does not perform video generation, automatic editing, or real provider execution.

## Verification

- `pytest -q tests/test_shot_direction_runtime.py` — **4 passed, 0 failed**
- Focused runtime/migration regression — **43 passed, 0 failed**
- `pytest -q` — **1856 passed, 0 failed**
- `npm run test:golden` — **5/5 passed**
- `python -m scripts.verify_migration_chain --ci` — **PASS**; fresh/repeated upgrade, legacy replay, schema drift
- API route import/registration check — **PASS**
- `python -m compileall -q` for new runtime modules — **PASS**
- `git diff --check` — **PASS**

## SHAPI handoff

The shot direction runtime produces provider-neutral camera and performance constraints. Downstream image generation remains routed through the existing SHAPI adapter contract at `https://shapi.vip/v1`; no external provider request was made by this phase.
