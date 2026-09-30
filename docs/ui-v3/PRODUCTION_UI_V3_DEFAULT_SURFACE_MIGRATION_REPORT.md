# Production UI V3 Default Surface Migration Report

- Phase: `PHASE_PRODUCTION_UI_V3_DEFAULT_SURFACE_MIGRATION`
- Completion marker: `PRODUCTION_UI_V3_DEFAULT_SURFACE_MIGRATION_COMPLETE`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Baseline: `3c8d91d7d71e7bcda708d5b8da6e3787cf373cd7`
- Verification date: 2026-09-30

## Outcome

Eligible storyboard projects now enter **Shot Studio · V3** by default. Legacy remains available through the compatibility link and `?ui_v3=legacy`. Explicit `?ui_v3=shot-studio` remains an override for QA and support. The rollout is guarded by the V2 read contract, canonical shot availability, a 100-shot ceiling, recovery context, active whole-storyboard generation, and legacy `step=` deep links.

The migration changes surface selection only. V2 remains the canonical read projection; Source Fact and ScriptIR are not changed. Generation, provider, LLM, SHAPI, MiniMax, image, and video calls are not initiated by the default-surface decision.

## Implementation

- Added `web/src/domain/productionUiV3SurfacePolicy.ts` with explicit decision reasons, feature flag parsing, V2 contract validation, shot-count ceiling, and context-preserving URL switching.
- Added policy tests covering default/override/rollback/hard-disable, loading, unavailable and invalid contracts, empty/oversized projections, generation/recovery/deep-link fallback, state variants, URL preservation, and flag parsing.
- Integrated policy selection into `ProductWorkspaceSectionContent`.
- Added V3 and Legacy surface notices and reversible links.
- Renamed the V3 header from Canary to `Shot Studio · V3`.

## Verification

- Web test suite: **60 files / 403 tests passed**.
- Web production build: **passed** (`tsc && vite build`).
- `tests/test_production_asset_api.py`: **3 passed**.
- Runtime regression set: **33 passed**.
- Python compile: **passed**.
- `git diff --check`: **passed**.

Detailed browser and network evidence is stored beside this report:

- `PRODUCTION_UI_V3_DEFAULT_SURFACE_MIGRATION_TRUTH_AUDIT.json`
- `PRODUCTION_UI_V3_DEFAULT_SURFACE_MIGRATION_BROWSER_QA.json`
- `PRODUCTION_UI_V3_DEFAULT_SURFACE_MIGRATION_RESPONSIVE_QA.json`
- `PRODUCTION_UI_V3_DEFAULT_SURFACE_MIGRATION_NETWORK_AUDIT.json`

## Browser QA summary

The disposable `998755` project was used with development fixtures only. Default eligible/review and blocked states rendered V3. Explicit Legacy rendered the existing storyboard list and production recovery controls. The reverse link returned to V3 while preserving section, episode, shot, step, and fixture context. A `step=frame` deep link remained on Legacy. The 100/101 shot boundary and V2 loading pending state are covered by the policy test suite.

At 1280×900, 1440×900, and 1920×1080, V3 rendered without horizontal overflow. No generation CTA was submitted.

## Known fixture-only observations

The disposable fixture can request bridge-state and prompt-version endpoints that return 404/500 because it has no matching persisted production asset or prompt-version rows. These responses predate this surface policy and did not trigger a provider or generation request. They are recorded in the network evidence rather than treated as migration failures.

PRODUCTION_UI_V3_DEFAULT_SURFACE_MIGRATION_COMPLETE
