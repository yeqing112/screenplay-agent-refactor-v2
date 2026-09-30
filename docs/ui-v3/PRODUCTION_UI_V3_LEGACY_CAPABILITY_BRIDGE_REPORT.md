# Production UI V3 Legacy Capability Bridge Report

## Phase

`PHASE_PRODUCTION_UI_V3_LEGACY_CAPABILITY_BRIDGE`

Baseline: `2d74e13243f3ca35b6ee108c5e4fa87409d63752`  
Branch: `codex/visual-authoring-provider-canary-reconcile`  
Date: `2026-09-30`

## Completion marker

`PRODUCTION_UI_V3_LEGACY_CAPABILITY_BRIDGE_COMPLETE`

## Executive result

BG-03 and BG-05 are closed for the canary path. The implementation reuses the existing Production Asset Authority, Version, Pointer, Review, ReviewHistory, and ShotAssetBinding graph. V3 remains opt-in at `?section=storyboard&ui_v3=shot-studio`; Legacy remains the default fallback. No default switch, deletion, migration, real provider call, LLM call, SHAPI call, MiniMax call, image generation, video generation, or production project write was performed during this phase.

## BG-03: canonical Production Asset ingestion

### HTTP contract

The router in `api/production_asset_api.py` is mounted by `api/server.py`:

- `POST /api/books/{book_id}/production-assets/ingest`
- `GET /api/books/{book_id}/production-assets/reviews/{review_id}`
- `GET /api/books/{book_id}/production-assets/reviews/{review_id}/history`
- `POST /api/books/{book_id}/production-assets/reviews/{review_id}/validate`
- `POST /api/books/{book_id}/production-assets/reviews/{review_id}/decision`
- `POST /api/books/{book_id}/production-assets/reviews/{review_id}/activate`
- `POST /api/books/{book_id}/production-assets/bindings`
- `GET /api/books/{book_id}/production-assets/shots/{storyboard_shot_id}/readiness`
- `GET /api/books/{book_id}/production-assets/versions/{version_id}/media`

Ingestion requires an explicit canonical `assetType` and `entityId` that appear in the persisted shot requirement contract. Multipart bytes are hashed server-side, MIME and image dimensions are checked, and the file is stored beneath `UPLOAD_DIR/production-assets`. Ingestion calls the existing authority service with `activate_pointer=False`, creates an immutable non-current Version, opens a Review, and runs deterministic provider-free validation. The state history is:

`GENERATED → NORMALIZED → AI_VALIDATED → HUMAN_REVIEW_PENDING`

`AI_VALIDATED` is an existing workflow label with an explicit deterministic-validator note; it does not claim an AI call. Pointer movement requires a human decision followed by the existing activation gate. Activation moves only the Pointer and preserves old Versions. Binding requires the exact formal shot requirement set and resolves through current Authority/Pointer/Version rows. V2 exposes `asset_readiness.current=true` only after current binding resolution.

The projection flag `PRODUCTION_ASSET_INGESTION_API_AVAILABLE` is now `True`. Windows local paths are recognized as local durable files, and candidate revisions advance from the latest immutable Version even when no Pointer is active.

## BG-05: shared explicit model selection

`web/src/services/productionModelSelection.ts` owns the shared selection key `production-generation-profile-selection-v1`, capability filtering, read/write helpers, and registry loading. The compatibility exports in `productWorkspaceGeneration.ts` remain available to existing callers.

`ProductionGenerationProfileSelector` is used by Legacy Storyboard and V3 Shot Studio. IMAGE selectors only show enabled `image` profiles; VIDEO selectors only show enabled `video` profiles. A missing or disabled stored profile is not silently replaced. V3 displays the V2 `selected_profile_id` projection, and changing selection persists the preference then refreshes V2. The selector is disabled while review or generation mutations are active and reports unavailable model drift directly.

## Legacy generation compatibility telemetry

`core/generation_compatibility_telemetry.py` records response shape only, in process memory, with no SaaS telemetry dependency. It counts canonical execution responses, canonical candidate responses, task-only fallback responses, and mixed execution-plus-task responses. `GET /api/production/generation-compatibility-telemetry` exposes the snapshot with `provider_calls=0` and `llm_calls=0`.

The Legacy storyboard caller now treats any response containing canonical `execution` as canonical, including mixed diagnostic responses. The V3 controller rejects `task_id` only when no canonical execution is present; it never reads legacy task recovery for a mixed canonical response.

## V3 asset bridge UI

`ProductionAssetBridgePanel` is rendered when V2 asset readiness is blocked. It shows missing/stale canonical entity identities, uploads real image/video files through the canonical ingestion route, displays review pending state, supports explicit human approval and activation, and offers explicit shot binding after all required versions are available. Each mutation refreshes V2; the panel does not infer readiness from Legacy adopted media.

## Safety and source authority

- ScriptIR, Source Fact, ShotPlan, and storyboard definitions are not modified.
- No second Asset Authority, Character Manager, Scene Manager, Prompt Manager, or Asset Manager was introduced.
- All asset Versions and review transitions are durable and versioned.
- Prompt lineage and existing GenerationExecution contracts remain unchanged.
- Legacy manual upload remains non-canonical display/reference behavior.
- V3 default remains off and reversible.

## Verification

- `npm --prefix web test`: 58 files, 386 tests passed.
- `npm --prefix web run build`: passed (`tsc` and Vite production build).
- `pytest -q tests/test_production_asset_api.py`: passed.
- `pytest -q tests/test_generation_compatibility_telemetry.py`: passed.
- Existing canary/runtime suite: 43 tests passed (`test_h2_asset_authority_schema.py`, `test_production_asset_graph_canary.py`, `test_phase_j3_canonical_generation.py`, `test_generation_execution_foundation.py`, `test_asset_promotion_runtime.py`).
- `git diff --check`: passed.
- Provider, LLM, SHAPI, MiniMax, image, and video call count in phase tests: `0`.

Browser screenshots and live production-provider checks were intentionally not run because this phase forbids real generation and production writes. The canary route remains suitable for a later disposable-fixture browser pass.

## Remaining gaps and readiness

Cross-shot Review Inbox, retry/regenerate, pagination, provider cancellation, and default V3 migration remain out of scope. The phase is complete for the Legacy capability bridge and canary validation. V3 is not promoted to default.
