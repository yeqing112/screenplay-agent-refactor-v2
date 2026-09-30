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

## Validation

- Web Vitest: **61 files, 431 tests passed**.
- Web TypeScript and Vite production build: passed.
- Backend targeted regression: **21 tests passed** across production workspace projection, storyboard generation flow, generation compatibility telemetry, and video generation runtime.
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
