# 2026-07-27 Delivery Readiness Syncing Acceptance

## Goal
Prevent the delivery center from briefly showing a misleading empty state while real project readiness data is still loading.

## Implemented
- Added `isProjectDataLoading` to the delivery-section bundle contract.
- Routed workspace loading state down into `ProductWorkspaceDeliverySection`.
- Split the delivery UI into three distinct states:
  - syncing delivery readiness
  - true empty readiness
  - loaded readiness
- Added a regression test to prevent the old false-empty behavior from returning.

## Acceptance criteria
1. While project data is still loading and readiness is empty, the delivery page must show a syncing message.
2. It must not show:
   - `当前还没有可评估交付的分集`
   - `当前没有可查看的交付分集`
   during that transient loading window.
3. Once readiness data is loaded, the delivery page must show the real episode panel and blocker content.
4. Focused tests and frontend build must pass.
5. Real browser must confirm the early syncing state and the final loaded state.

## Test record
- Unit tests:
  - `npx vitest run web/src/components/ProductWorkspaceDeliverySection.test.tsx web/src/components/productWorkspaceDelivery.test.ts`
  - passed
- Frontend build:
  - `npm run build`
  - executed in `web/`
  - passed

## Real-browser acceptance
- Project: `三个和尚`
- Entry path:
  - home
  - open project `三个和尚`
  - open `导出中心`
- Early state:
  - syncing copy visible
  - false empty-state copy not visible
- Final state after wait:
  - `第 1 集交付面板` visible
  - `首个阻塞入口` visible
  - false empty-state copy not visible

## Outcome
Accepted.
