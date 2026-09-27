# Visual Style Consistency Runtime Report

## VISUAL_STYLE_CONSISTENCY_RUNTIME_COMPLETE

- **Commit:** `a439584` (`feat: add visual style consistency runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Migration head:** `e3f4a5b6c7d8`
- **Image generation provider:** [SHAPI](https://www.shapi.vip/)
- **Existing image transport contract:** `shapi-openai-images.image.v1` via `https://shapi.vip/v1`
- **Provider calls in this runtime slice:** `0` (provider-free runtime and regression tests)

## Delivered runtime

- `VisualStyleProfile` persists the canonical style identity with `camera_profile`, `lighting_profile`, `color_profile`, and `composition_profile`.
- `StyleReferenceAsset` stores typed `color`, `camera`, `lighting`, `composition`, and `mood` references while reusing existing visual/production asset identities.
- `ShotStyleBinding` supports `EPISODE_DEFAULT` and `SHOT_OVERRIDE`; a shot override takes precedence over the episode default and prior active bindings become `STALE`.
- Style validation fails closed when a shot has no effective style, no active reference asset, an invalid selected reference, or incomplete camera/lighting/color/composition constraints.
- Prompt injection adds Camera Rules, Lighting Rules, Color Rules, Composition Rules, shot style rules, and reference constraints while preserving the original prompt snapshot.
- Prompt Lineage persists an immutable derived `ProductionPromptVersion` with `VISUAL_STYLE_CONSISTENCY` provenance.
- APIs are available at both stable and `/api` paths:
  - `POST /styles`
  - `GET /styles/{style_id}`
  - `POST /styles/{style_id}/references`
  - `GET /styles/{style_id}/references`
  - `POST /episodes/{book_id}/{episode}/style`
  - `POST /shots/{shot_id}/style`
  - `GET /shots/{shot_id}/style/validation`
  - `POST /shots/{shot_id}/style/prompt`

The implementation reuses existing asset authority, asset versions, pointers, bindings, storyboard shots, and Prompt Lineage. It does not add a second asset, prompt, or scene system, and does not perform video generation, automatic color grading, model training, or 3D reconstruction.

## Verification

- `pytest -q tests/test_visual_style_consistency_runtime.py` — **4 passed, 0 failed**
- Focused continuity/migration regression — **39 passed, 0 failed**
- `pytest -q` — **1852 passed, 0 failed**
- `npm run test:golden` — **5/5 passed**
- `python scripts/verify_migration_chain.py` — **PASS**; fresh/repeated upgrade, legacy replay, schema drift
- API route import/registration check — **PASS**
- `python -m compileall` for new runtime modules — **PASS**
- `git diff --check` — **PASS**

## SHAPI handoff

The style runtime produces provider-neutral prompt constraints and reference identities. Downstream image generation remains routed through the existing SHAPI adapter contract at `https://shapi.vip/v1`; no external provider request was made by this phase.
