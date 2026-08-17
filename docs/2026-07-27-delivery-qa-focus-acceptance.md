# 2026-07-27 Delivery QA Focus Acceptance

## Goal
Make `导出中心 -> QA 修复` land on the most repairable QA issue for delivery recovery instead of always defaulting to the highest-priority generic script issue.

## Problem
- The delivery page already passed episode context into QA.
- But when the user clicked `去 QA 修复`, the QA workspace still tended to select a generic script workbench issue first.
- In the real `三个和尚` project, that meant the user landed on a script truncation issue instead of a shot-bound storyboard / asset / video issue that was closer to restoring delivery readiness.

## Implemented
- Added `qaFocus: 'delivery_recovery'` to cross-workspace task navigation options.
- Delivery blocker actions and delivery history repair actions now pass this focus hint when routing into QA.
- QA navigation selection now supports a delivery-recovery preference:
  - prefer actionable issues first
  - when focus is `delivery_recovery`, prefer downstream layers in this order:
    - `video`
    - `asset`
    - `storyboard`
    - `general`
    - then generic `script`
  - prefer shot-bound issues within that delivery-recovery path
  - fall back to previous workbench / severity / freshness ordering when no better downstream issue exists

## Acceptance criteria
1. `导出中心 -> 去 QA 修复` must still enter the QA workspace for the same episode.
2. The selected QA issue should prioritize delivery-recovery usefulness over generic script-first ordering.
3. When a shot-bound downstream issue exists, QA should prefer that issue over a generic script workbench issue.
4. Focused frontend tests and `npm run build` must pass.
5. Real browser must confirm the selected QA detail panel matches the intended delivery-recovery context.

## Verification
- Tests:
  - `npx vitest run web/src/components/productWorkspaceQa.test.ts web/src/components/ProductWorkspaceDeliverySection.test.tsx web/src/components/productWorkspaceDelivery.test.ts`
  - passed
- Build:
  - `npm run build`
  - executed in `web/`
  - passed

## Real-browser acceptance
- Date validated: July 27, 2026
- Project: `三个和尚`
- Flow:
  - enter `导出中心`
  - click `去 QA 修复`
- Result:
  - QA no longer defaulted to the generic script truncation issue
  - selected issue became a storyboard-derived issue:
    - `分镜问题 · 镜头 1-2 · 建议为方丈令牌在前文增加 1-2 个伏笔镜头`
  - QA detail panel exposed a direct repair action:
    - `定位镜头 1-2`

## Outcome
Accepted.
