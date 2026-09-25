# UI V2 Legacy UI Retirement Audit

Date: 2026-09-25

## Provider-specific H3 entry point

The canonical Production Workspace no longer renders a `真实提交 H3` button and no frontend callsite remains for `submit-machine-prompt-provider`. Machine prompt export is retained as a professional read/export tool. Historical task records may still mention old provider activity, but the task center labels them as historical recovery and does not expose a new provider submission action.

## `adopted` callsites

The remaining `.adopted` references are legacy compatibility consumers in storyboard media, task recovery, delivery export and canvas summaries. They are not used by the V2 read model to establish OfficialMedia. The storyboard media panel labels those records `Legacy / Historical`; current official status comes only from the V2 `official` lane.

| Area | Classification | Action |
|---|---|---|
| `ProductWorkspaceStoryboardMediaPanel` | `LEGACY_DISPLAY` | historical card only; no current-official label |
| task recovery / delivery export | `NON_PRODUCTION` or historical compatibility | preserve export/recovery evidence; do not write OfficialMedia |
| canvas legacy summaries | `NON_PRODUCTION` | progressively replace badges with V2 snapshot |
| canonical V2 panel | `MUST_NOT_USE` | reads only `official.current`, candidate and backend readiness |

## `shot.assets.images/videos` audit

The following old consumers still read legacy shot media arrays for compatibility or secondary summaries: `productWorkspaceBatchActions.ts`, `productWorkspaceTaskCenterState.ts`, `ProductWorkspaceTasksSection.tsx`, `ProductWorkspaceCanvasBeta.tsx`, `ProductWorkspaceCanvasBetaSection.tsx`, `productWorkspaceDelivery.ts`, `productWorkspaceOverviewController.ts`, `productWorkspacePrompt.ts`, `productWorkspaceStoryboard.ts`, `ProductWorkspaceStoryboardUi.tsx`, and `ProductWorkspaceStoryboardSection.tsx`.

They are not allowed to define V2 Production readiness. The V2 dashboard, asset hub, and shot lanes use `production_workspace_projection_v2`; the old panels are retained only during migration and are labeled historical where they show media records. Any remaining batch eligibility or canonical execution migration must consume the V2 snapshot before the workspace is declared complete.

## Audit result

- Legacy provider action reachable from canonical UI: `0`
- New UI authority or frontend official truth: `0`
- Database migration added for V2: `0`
- Legacy callsites remaining for compatibility: documented above
