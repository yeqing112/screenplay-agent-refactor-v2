# 2026-07-27 Delivery History Shot Routing Acceptance

## Goal
Make blocked export history records route back to the most relevant shot instead of only returning to the episode-level storyboard page.

## Implemented
- `ProductWorkspaceDeliverySection` no longer normalizes export records only once at fetch time.
- Raw export records are now stored first, then re-normalized against the latest readiness data.
- When a history record has no explicit `blockedShotIds`, the UI now infers action-specific shot targets from current readiness blockers.
- History repair buttons now show shot-specific labels when a shot target can be inferred:
  - `返回分镜工作台补参考图（镜头 3）`
  - `返回分镜工作台补视频（镜头 1）`

## Acceptance criteria
1. History records must re-evaluate after readiness data finishes loading.
2. A blocked history record without explicit `blockedShotIds` must still recover a usable shot target when current readiness can explain it.
3. Image-related and video-related repair buttons must be able to point to different shots.
4. Focused frontend tests and production build must pass.
5. Real browser must confirm the actual routed shot matches the button label.

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
- Target record:
  - `2026-07-17T04:05:24.183937`
- Result:
  - image repair button label became `返回分镜工作台补参考图（镜头 3）`
  - clicking it routed to shot `3 寺庙后院水房`
  - video repair button label became `返回分镜工作台补视频（镜头 1）`
  - clicking it routed to shot `1 寺庙后院水房`

## Outcome
Accepted.
