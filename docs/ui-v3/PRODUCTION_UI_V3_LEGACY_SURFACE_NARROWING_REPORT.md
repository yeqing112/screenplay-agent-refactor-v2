# Production UI V3 Legacy Surface Narrowing Report

## Phase

`PHASE_PRODUCTION_UI_V3_LEGACY_SURFACE_NARROWING`

Completion marker: `PRODUCTION_UI_V3_LEGACY_SURFACE_NARROWING_COMPLETE`

Baseline: `faf88a53d1d6ecea1d6612c7ed77cb69bfc34edf`

Branch: `codex/visual-authoring-provider-canary-reconcile`

## Scope delivered

- Added pure `resolveLegacyStoryboardMode()` policy with four modes:
  `advanced_compatibility`, `creation`, `recovery`, and `full_fallback`.
- Added `buildStoryboardReturnToV3Url()`; it preserves storyboard context and unrelated query parameters, removes Legacy-only `step`, and sets `ui_v3=shot-studio`.
- Narrowed the eligible explicit Legacy surface so the main entry points to Shot Studio, while Prompt Compiler, Prompt Draft, Prompt History, Prompt Authority, diagnostics, repair, continuity, acceptance, decision, recovery, and advanced executability tools remain available.
- Folded compatibility model selectors and generation actions into explicit “使用兼容生产入口” disclosure in advanced compatibility mode.
- Kept the complete Legacy surface for hard disable, ordinary rollback, V2 unavailable or invalid, rollout shot limit, and storyboard generation in progress.
- Added creation and recovery banners. Recovery keeps task and shot context visible and does not redirect automatically.
- Clarified Legacy media as “兼容采纳” and task-center empty execution copy as “本地执行记录”.
- Preserved the canonical generation mutation boundary, recovery code, V2 freshness guard, and double-submit lock. No provider, LLM, video, image, route, database, or source-fact mutation was introduced.

## Policy matrix

| Mode | Main behavior | Canonical generation | V3 return |
| --- | --- | --- | --- |
| `advanced_compatibility` | Prompt and recovery tools lead; compatibility generation is folded | hidden by default | visible |
| `creation` | One-click storyboard creation leads | not applicable | hidden |
| `recovery` | Current task/shot recovery leads | reduced duplicate overview | visible on explicit click |
| `full_fallback` | Full Legacy production surface remains available | visible | not offered when V3 is unavailable |

## Canonical UI ownership

Eligible projects remain owned by Shot Studio V3. Advanced compatibility keeps one compact canonical status strip and sends the primary production action to V3. The full `ProductionWorkspaceV2Panel` remains visible in `full_fallback` only.

## Advanced compatibility

Prompt Compiler, Prompt Draft, Prompt History, Prompt Authority, Compile Diagnostics, Repair, Continuity, Acceptance/Decision, recovery, and advanced executability tools remain available. Canonical generation, model selectors, and duplicate V2 status are collapsed under `使用兼容生产入口`.

## Creation and recovery

Zero-shot projects keep `一键生成分镜` as the primary action and do not promote a V3 return link. Recovery focus and `step=frame|video|review` lead with task and shot context; recovery never redirects automatically.

## Full fallback protection

Hard disable, default disabled, V2 unavailable or invalid, storyboard generation in progress, and 101+ shot rollout limits retain the complete Legacy production surface, including IMAGE/VIDEO generation, selectors, production status, recovery, and advanced tools.

## Compatibility generation and recovery ownership

Legacy generation continues to use the shared canonical generation client with `compileIfMissing=false`, V2 freshness checks, synchronous double-submit locking, canonical execution precedence, and task-id-only compatibility recovery. `productWorkspaceRecovery` and task recovery remain intact. Compatibility task and local runtime evidence are labelled as compatibility/local records.

## Manual media and adoption boundary

Manual media remains a Legacy compatibility tool. UI copy distinguishes `兼容采纳` from canonical Official Media; uploads and adopted media do not imply Official promotion.

## URL transition

`buildStoryboardSurfaceUrl()` remains unchanged for compatibility. Explicit return-to-V3 links use `buildStoryboardReturnToV3Url()`, preserve `section`, `episode`, `shot`, and unrelated query values, and remove only Legacy-only `step` after the user clicks the return link.

## Visible / hidden / fallback matrix

| Capability | Advanced compatibility | Creation | Recovery | Full fallback |
| --- | --- | --- | --- | --- |
| V3 return CTA | visible | hidden | visible | unavailable when V3 is unavailable |
| Canonical status | compact strip | hidden | compact strip | full V2 panel |
| Canonical generation CTA | hidden from primary path | not applicable | not promoted | visible |
| Compatibility generation | collapsed | creation flow leads | available for recovery | visible |
| Prompt/repair/recovery tools | visible | creation first | visible | visible |

## Network, browser, and responsive QA

The provider-free QA artifacts cover eligible default V3, explicit Legacy narrowing, compatibility disclosure, 101-shot fallback, zero-shot creation, recovery context, and step removal. Rendering tests exercise the same state matrix. No generation POST, provider request, asset write, or media authority write is introduced by surface resolution. Responsive review targets 1280×900, 1440×900, and 1920×1080 banner/control wrapping; no new fixed-width surface was added.

Browser evidence screenshots: `output/playwright/legacy-surface-advanced-1920.png` and `output/playwright/legacy-surface-recovery-1920.png`.

## Provider safety and production writes

Real LLM, Shapi (`https://www.shapi.vip/`), MiniMax, image, and video calls remain at zero. This phase adds only a provider-free mode event containing `mode` and `reason`; it does not record business正文 or trigger production writes. Backend routes changed: 0. Database migrations: 0.

## Deprecation candidates / do not remove yet

`ProductionWorkspaceV2Panel` duplication in advanced compatibility is a deprecation candidate after V3 has equivalent recovery and prompt tooling. Do not remove Legacy generation, `productWorkspaceRecovery`, manual media compatibility, continuity, acceptance/decision panels, task-id recovery, >100-shot fallback, hard-disable fallback, or Canvas integration in this phase. Review Inbox and Retry/Regenerate remain unimplemented.

## Recommended next phase

Choose the next phase only after observing actual mode evidence: Legacy deprecation evidence, Retry/Regenerate contract audit, or Review Inbox backend foundation. No next phase is started here.

## Validation

- Web Vitest: **61 files, 435 tests passed**.
- Web TypeScript and Vite production build: passed.
- Backend targeted regression: **34 tests passed** with `pytest -q tests/test_generation_compatibility_telemetry.py tests/test_production_asset_api.py tests/test_production_workspace_projection.py tests/test_video_generation_runtime.py tests/test_storyboard_generation_flow.py tests/test_production_batch_runtime.py tests/test_production_readiness.py tests/test_storyboard_media_preflight.py`.
- `python -m compileall -q .`: passed.
- `git diff --check`: passed.
- New policy coverage includes mode matrix, recovery focus/deeplink, compatibility disclosure, and step-free V3 return URL.
- QA is provider-free; no request was sent to Shapi, MiniMax, or any image/video provider.

## Files

- `web/src/domain/productionUiV3SurfacePolicy.ts`
- `web/src/domain/productionUiV3SurfacePolicy.test.ts`
- `web/src/components/ProductWorkspaceSectionContent.tsx`
- `web/src/components/ProductWorkspaceStoryboardSection.tsx`
- `web/src/components/ProductWorkspaceStoryboardAdvancedToolsPanel.tsx`
- `web/src/components/ProductWorkspaceStoryboardSection.test.tsx`
- `web/src/components/productWorkspaceTaskCenterSelectedTaskPanel.tsx`
