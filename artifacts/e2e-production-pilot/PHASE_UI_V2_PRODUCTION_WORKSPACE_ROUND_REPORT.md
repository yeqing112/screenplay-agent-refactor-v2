# UI V2 Production Workspace Convergence — Round Report

- Date: 2026-09-25
- Stage: `PHASE_UI_V2_PRODUCTION_WORKSPACE_CONVERGENCE`
- Current outcome: `PHASE_UI_V2_PRODUCTION_WORKSPACE_IN_PROGRESS`
- Review status: `PHASE_UI_PRODUCTION_WORKSPACE_READY_FOR_REVIEW` has **not** been claimed.
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Baseline HEAD: `25f5b5e`

## This round

This round prepared the first read-only Production Workspace V2 projection layer over the existing authority-backed V1 projection.

Added:

- `core/production_workspace_projection_v2.py`

The draft projection:

- keeps the existing backend authority objects as the only source of truth;
- does not write database rows and does not add a migration;
- separates IMAGE and VIDEO lanes;
- exposes candidate, execution, validation, official-media and asset-readiness fields for a future UI read model;
- marks legacy adopted-media data as display-only;
- does not require `provider_calls === 0` in the V2 payload contract.

## Safety and side effects

| Item | Result |
|---|---|
| Real provider calls | `0` |
| Real image calls | `0` |
| Real video calls | `0` |
| Paid LLM calls | `0` |
| Database migrations | `0` |
| Production authority writes | `0` |
| Fake or placeholder Production assets | `0` |

The new module is not imported by the running API or frontend yet, so existing production behavior is unchanged.

## Current production blocker

`book-990401 / Episode 01` remains blocked by the existing real-visual-asset gate:

- 15 required Production Assets;
- 0 explicitly mapped real visual media;
- 4 characters, 2 scenes and 9 props;
- the checkout's canary/storyboard files remain excluded because they have no explicit `entity_id → media_identity` mapping.

This blocker was intentionally not bypassed and no file was promoted to Production Asset or OfficialMedia.

## Verification performed

- `python -m py_compile core/production_workspace_projection_v2.py` — pass
- `git diff --check` — pass
- No external generation or paid service was invoked.

## Remaining work before review-ready

The following items are still open and are not represented as complete in this report:

1. Add the thin read-only `/production-workspace-v2` API route.
2. Add frontend V2 domain types, service/hook, fixtures and validator changes.
3. Integrate the standard/professional toggle and the shot IMAGE/VIDEO lanes into the existing ProductWorkspace shell.
4. Add the entity-first asset hub and the 15-asset blocked-state UX.
5. Retire or label legacy `adopted` and provider-specific H3 entry points.
6. Add the required UI tests and run the full web test/build and relevant backend production regression.
7. Add the four requested UI V2 design/audit documents.

Until these are complete, the correct status remains in progress and the full real E2E asset blocker remains active.

## Git delivery

This report and the V2 projection draft are delivered in the commit that contains this file. The exact commit SHA and remote URL are provided in the task response after push.

Remote repository:

`https://github.com/yeqing112/screenplay-agent-refactor-v2.git`
