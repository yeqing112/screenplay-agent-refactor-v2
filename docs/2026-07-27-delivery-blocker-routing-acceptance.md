# 2026-07-27 Delivery Blocker Routing Acceptance

## Goal
Turn delivery blockers from static summary cards into actionable repair entry points.

## Implemented
- `DeliveryBlockedItem` now carries optional routing context:
  - `episode`
  - `shotId`
  - `assetId`
- `buildDeliveryEpisodeReadiness()` now attaches first blocking shot context for:
  - missing prompts
  - missing adopted images
  - missing adopted videos
  - missing asset references
- `ProductWorkspaceDeliverySection` now uses `TaskNavigateHandler` instead of plain section switching.
- Delivery blocker CTA text is now more explicit:
  - `定位镜头 X`
  - `去资产中心定位镜头 X`
  - `去剧本工作台`
  - `去 QA 修复`
  - `去改编方向`

## Acceptance criteria
1. Delivery blocker cards must be able to route with episode context.
2. Storyboard-related blockers must route with first blocking `shotId` when available.
3. Assets-related blockers must route with episode and shot context.
4. Record history repair actions must still work after the navigation contract change.
5. Focused tests and frontend build must pass.
6. Real browser must confirm that a blocker CTA lands inside the expected workspace section.

## Test record
- Unit test:
  - `npx vitest run web/src/components/productWorkspaceDelivery.test.ts`
  - passed
- Frontend build:
  - `npm run build`
  - executed in `web/`
  - passed

## Real-browser acceptance
- Entry project: `三个和尚`
- Path:
  - home
  - open project `三个和尚`
  - open `导出中心`
  - wait for real readiness data to finish syncing
  - click first blocker CTA
- Observed result:
  - delivery page first shows a short syncing window, then loads real readiness data
  - new top card appears: `首个阻塞入口`
  - blocker CTA text: `定位镜头 3`
  - page routed into `镜头工作台`
  - selected shot detail displayed shot `3 寺庙后院水房`
  - shot detail correctly showed no adopted frame/video yet, matching the export blocker state

## Outcome
Accepted.

## Remaining follow-up
- Export history repair actions still route by episode, not exact shot.
- `导出中心` still lacks a single top-level “first blocker” summary card.
