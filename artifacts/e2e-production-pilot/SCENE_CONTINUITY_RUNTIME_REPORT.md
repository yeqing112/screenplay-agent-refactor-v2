# Scene Continuity Runtime Report

## SCENE_CONTINUITY_RUNTIME_COMPLETE

- **Commit:** `b0fc091` (`feat: add scene continuity runtime`)
- **Branch:** `codex/visual-authoring-provider-canary-reconcile`
- **Migration head:** `e2f3a4b5c6d7`
- **Image generation provider:** [SHAPI](https://www.shapi.vip/)\n- **Image generation provider contract:** `shapi-openai-images / gpt-image-2` via `https://shapi.vip/v1`
- **Provider calls in this runtime slice:** `0` (the runtime and tests are provider-free)

## Delivered runtime

- Existing `VisualLocation` remains the single Scene Identity authority and now carries `attributes` and `environment_profile`.
- `SceneReferenceAsset` stores typed `overview`, `layout`, `lighting`, `detail`, and `prop` references while reusing existing visual/production asset identities.
- `ShotSceneBinding` binds one ACTIVE primary scene to a storyboard shot; rebinding marks the prior binding `STALE`.
- Continuity validation fails closed when a shot lacks a scene, a reference asset, or environment constraints.
- Scene constraints are injected into a derived prompt while preserving the original prompt snapshot.
- Prompt Lineage persists an immutable `ProductionPromptVersion` with `SCENE_CONTINUITY` provenance.
- APIs are available at both stable and `/api` paths:
  - `POST /scenes`
  - `GET /scenes/{scene_id}`
  - `POST /scenes/{scene_id}/references`
  - `GET /scenes/{scene_id}/references`
  - `POST /shots/{shot_id}/scene`
  - `GET /shots/{shot_id}/scene/validation`
  - `POST /shots/{shot_id}/scene/prompt`

The change does not add a second scene registry, asset store, or prompt store. It does not perform provider generation, video generation, 3D reconstruction, or scene rebuilding.

## Verification

- `pytest -q tests/test_scene_continuity_runtime.py tests/test_migration_chain_hardening.py tests/test_h2_asset_authority_schema.py tests/test_j2_3_media_scoped_prompt_pointer_migration.py` — **32 passed, 0 failed**
- `pytest -q` (previous full run) — **1848 passed, 0 failed**
- `npm run test:golden` — **5/5 passed**
- `python scripts/verify_migration_chain.py` — **PASS**; fresh/repeated upgrade, legacy replay, schema drift
- Migration head — **`e2f3a4b5c6d7`**
- `python -m compileall` for new runtime modules — **PASS**
- `git diff --check` — **PASS**

## SHAPI handoff

All image generation remains routed through the existing SHAPI adapter contract. The scene runtime only supplies validated scene identity, reference constraints, and an immutable prompt derivative; the downstream image request should use the configured `shapi-openai-images` profile at `https://shapi.vip/v1`.

