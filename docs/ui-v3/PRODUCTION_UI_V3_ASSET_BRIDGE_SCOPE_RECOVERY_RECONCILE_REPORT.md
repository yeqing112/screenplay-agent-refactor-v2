# Production UI V3 Asset Bridge Scope Recovery and Reconcile Report

## Phase

`PHASE_PRODUCTION_UI_V3_ASSET_BRIDGE_SCOPE_RECOVERY_RECONCILE`

Baseline: `a66902a73f4241c467901ee07c12545de3149510`  
Branch: `codex/visual-authoring-provider-canary-reconcile`  
Date: `2026-09-30`

## Completion marker

`PRODUCTION_UI_V3_ASSET_BRIDGE_SCOPE_RECOVERY_RECONCILE_COMPLETE`

## Result

The V3 Shot Studio asset bridge now recovers its state from the backend canonical graph on mount, reload, and shot change. It no longer relies on browser-held review or version identity. The bridge reads the formal shot requirement contract and exposes one explicit path for upload, human approval, activation, and binding to the current pointer.

The implementation reuses the existing Production Asset Authority, Version, Pointer, Review, ReviewHistory, and ShotAssetBinding records. V3 remains opt-in at `?section=storyboard&ui_v3=shot-studio`; the legacy surface and its default-off behavior are unchanged.

## Backend changes

- Added `ProductionAssetScopeError` and `resolve_production_asset_book_scope()` to verify that review, version, pointer, and binding records belong to the requested book and authority fingerprint.
- Applied book scope checks to review, history, validation, decision, activation, readiness, binding, and media routes.
- Changed HTTP ingestion to require multipart `file` bytes. The HTTP `storageIdentity` field cannot make the server read or write a caller-selected local path.
- Restricted media serving to `UPLOAD_DIR/production-assets/book-{book_id}`.
- Added `GET /api/books/{book_id}/production-assets/shots/{shot_id}/bridge-state`.
- Added `POST /api/books/{book_id}/production-assets/shots/{shot_id}/bind-current`.
- Bridge state reports `MISSING`, `REVIEW_PENDING`, `HUMAN_APPROVED_NOT_ACTIVATED`, `CURRENT_NOT_BOUND`, `BOUND_CURRENT`, `BINDING_STALE`, `REJECTED`, and `REQUEST_CHANGE`, with current pointer/version/media, pending review, active binding, and action capabilities.
- Fixed the V2 projection path to import `resolve_current_production_asset_binding`; without this import a successfully bound shot could make `GET /production-workspace-v2` return HTTP 500.

## Frontend changes

`ProductionAssetBridgePanel` now:

- fetches backend bridge state after mount and whenever the shot changes;
- clears previous shot state before a new fetch;
- fails closed when bridge-state cannot be read;
- uploads only through the multipart canonical ingestion endpoint;
- refreshes bridge state and V2 after upload, approval, activation, and bind;
- keeps approval and activation as human-clicked actions;
- shows `重新绑定当前版本` after a current pointer rolls over;
- removes itself only after the backend reports current bindings and V2 readiness.

## Browser QA

Disposable local project: book `998755`, storyboard shot `216`, character `CHAR_RELOAD_8a0b9338`, scene `SCENE_RELOAD_76c727e3`. No production project was used.

Verified in the V3 route:

1. Reload after a pending upload preserves `REVIEW_PENDING`.
2. Human approval and activation preserve the explicit binding gate.
3. Binding both formal requirements removes the bridge after reload and yields `asset_readiness.current=true`.
4. Uploading, approving, and activating a replacement character version produces `BINDING_STALE` after reload.
5. `重新绑定当前版本` resolves the current backend pointer and restores `asset_readiness.current=true`.
6. IMAGE and VIDEO generation controls remain disabled because PromptIR/model prerequisites are absent.

Screenshots from the disposable bridge pass are retained beside the earlier bridge evidence: `asset-bridge-blocked.png`, `asset-bridge-review-pending.png`, `asset-bridge-approved-binding-needed.png`, and `asset-bridge-ready.png`.

## Safety and authority constraints

- No Source Fact, ScriptIR, storyboard definition, or canonical production asset history was rewritten.
- No migration was added.
- No second asset, review, prompt, character, scene, or manager model was introduced.
- No LLM, SHAPI, MiniMax, image-generation, or video-generation call was made.
- The disposable browser flow used local PNGs only; no real production project was written.
- Provider and LLM call counters remained zero.

## Verification

- `pytest -q tests/test_production_asset_api.py`: 3 passed.
- `pytest -q tests/test_h2_asset_authority_schema.py tests/test_production_asset_graph_canary.py`: passed.
- `npm --prefix web test -- --run src/services/productionAssets.test.ts`: 2 passed.
- `python -m py_compile core/production_asset_authority.py api/production_asset_api.py core/production_workspace_projection_v2.py`: passed.
- Full web test suite and production build are recorded in the final push verification.
- `git diff --check`: passed before commit.

## Machine-readable evidence

- `PRODUCTION_UI_V3_ASSET_BRIDGE_SCOPE_RECOVERY_RECONCILE_TRUTH_AUDIT.json`
- `PRODUCTION_UI_V3_ASSET_BRIDGE_SCOPE_RECOVERY_RECONCILE_BROWSER_QA.json`
- `PRODUCTION_UI_V3_ASSET_BRIDGE_SCOPE_RECOVERY_RECONCILE_RESPONSIVE_QA.json`
- `PRODUCTION_UI_V3_ASSET_BRIDGE_SCOPE_RECOVERY_RECONCILE_NETWORK_AUDIT.json`

## Out of scope

Review Inbox, pagination, retry/regenerate, provider cancellation, automatic LLM/provider calls, and default V3 migration remain out of scope.
