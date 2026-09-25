# UI V2 Legacy UI Retirement Audit

Date: 2026-09-25
Scope: `web/src` production workspace callsites

## Provider-specific H3 entry point

The canonical Production Workspace has no `submit-machine-prompt-provider`, `真实提交 MiniMax H3`, or `真实提交 H3` callsite. Machine Prompt remains a professional view/export/debug tool. Historical task text may retain provider names, but it is not an executable Production generation action.

Static result:

```text
submit-machine-prompt-provider / 真实提交 MiniMax H3 / 真实提交 H3: 0 reachable frontend callsites
```

## `.adopted` inventory

| Callsite | Classification | Production V2 rule |
|---|---|---|
| `web/src/domain/bookOutputs.ts:22,877` | legacy payload normalization | compatibility input only |
| `web/src/components/productWorkspaceBatchActions.ts:83,86` | compatibility fallback | used only when no V2 snapshot is available; V2 batch eligibility now uses V2 lanes |
| `web/src/components/productWorkspaceCanvasBeta.ts:347-348,876,906` | legacy canvas graph/label | historical compatibility; V2 selected-shot status is rendered separately |
| `web/src/components/ProductWorkspaceCanvasBetaSection.tsx:498,988-993,1270` | recovery compatibility | current video source/readiness uses V2 Official IMAGE when the V2 snapshot is present |
| `web/src/components/productWorkspaceDelivery.ts:748,758,842-843,909,917-918,967` | historical export snapshot | delivery export preserves old evidence and does not create OfficialMedia |
| `web/src/components/ProductWorkspaceDeliverySection.tsx:790,795` | historical delivery metrics | not used by V2 readiness |
| `web/src/components/ProductWorkspaceStoryboardMediaPanel.tsx:68` | `LEGACY_DISPLAY` | explicitly labelled `Legacy / Historical` |
| `web/src/components/ProductWorkspaceStoryboardSection.tsx:1595,1644-1659,2183-2216,2291-2297,4212-4277` | storyboard compatibility and recovery | legacy display/recovery only; V2 panel owns current OfficialMedia semantics |
| `web/src/components/productWorkspaceTaskCenterState.ts:120-122` | recovery compatibility | task-center canonical batch eligibility is V2-gated when the snapshot is present |
| `web/src/components/ProductWorkspaceTasksSection.tsx:718-720` | legacy request fallback | retained only for compatibility endpoint payload construction |

## `shot.assets.images/videos` inventory

| Callsite | Classification | Required boundary |
|---|---|---|
| `productWorkspaceBatchActions.ts:75-79,310` | compatibility fallback | V2 snapshot gates production batch readiness; old arrays are fallback only |
| `productWorkspaceCanvasBeta.ts:293-294` | graph input | historical graph data; V2 status card is authoritative for selected shots |
| `ProductWorkspaceCanvasBetaSection.tsx:988-993,1257` | recovery input | V2 OfficialMedia gates current VIDEO source when available |
| `productWorkspaceDelivery.ts:262-263,516-517,563-564,837-838` | delivery/history | not used to establish OfficialMedia |
| `productWorkspaceOverviewController.ts:234-235` | overview counts | legacy summary only |
| `productWorkspaceStoryboard.ts:121,125` | legacy storyboard summary | not used by V2 readiness |
| `ProductWorkspaceStoryboardUi.tsx:77` | legacy display | not used by V2 readiness |
| `ProductWorkspaceStoryboardSection.tsx:2181-2182,3148,3499,3967-3968` | legacy display/recovery | V2 panel owns current state |
| `productWorkspaceTaskCenterState.ts:120` | recovery compatibility | V2 snapshot gates production batch eligibility |
| `productWorkspaceTasks.ts:464-465,518-519` | task summary | compatibility summary only |
| `ProductWorkspaceTasksSection.tsx:718` | request fallback | canonical eligibility comes from V2 when loaded |

## Current safeguards

- `ProductionWorkspaceV2Panel` reads only the backend V2 projection for current state, blockers, PromptIR, execution, Candidate and OfficialMedia.
- Candidate cards distinguish `候选结果` from `当前正式版本`; validation and promotion use the existing `/api/media-authority` contract.
- V2 batch filters use `asset_readiness`, PromptIR currentness, OfficialMedia currentness and independent IMAGE/VIDEO lanes.
- Canvas selected-shot status displays V2 asset, IMAGE and VIDEO badges and the backend-projected single next action.
- No frontend authority, pointer, candidate selection truth, or database migration was added.

## Audit result

- Reachable provider-specific H3 generation action: `0`
- Frontend OfficialMedia truth outside the backend projection: `0`
- V2 database migration: `0`
- Remaining legacy callsites: classified above as compatibility, historical display, recovery, or summary-only

The implementation remains review-ready as `PHASE_UI_PRODUCTION_WORKSPACE_READY_FOR_REVIEW`; it is not labelled `UI_V2_COMPLETE`.
# Current retirement decision

Legacy `adopted` values are retained for historical display and recovery context only. They are not used for V2 Production execution eligibility, candidate promotion, or current OfficialMedia readiness. Canvas and Task Center now fail closed on an unavailable V2 projection.
