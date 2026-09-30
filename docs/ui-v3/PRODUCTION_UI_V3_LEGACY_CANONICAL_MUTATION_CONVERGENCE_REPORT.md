# Production UI V3 Legacy Canonical Mutation Convergence

## Scope

This phase converges the legacy storyboard production surface on the canonical Production Workspace generation contract. The change is limited to generation mutation routing, response handling, recovery bookkeeping, and the evidence needed to retire duplicate request semantics. Source facts, ScriptIR, prompt versions, assets, and backend APIs are unchanged.

## Before Convergence

The legacy storyboard surface assembled IMAGE and VIDEO request bodies independently. VIDEO could send compatibility fields (`compileIfMissing`, `firstFrameAssetId`, and `referenceAssetIds`) while the canonical execution API already owned prompt and source selection. Responses were also interpreted by `task_id` before checking for canonical execution, which made a diagnostic task identifier capable of diverting a canonical execution into legacy polling.

## Shared Canonical Generation Contract

`web/src/services/productionGeneration.ts` is the shared client boundary. Both targets post to the existing storyboard generation route with:

```json
{
  "modelProfileId": "<selected profile>",
  "confirmed": true,
  "allowExternalCall": true,
  "compileIfMissing": false,
  "generationChain": "production_workspace_v2"
}
```

The service forwards an optional `AbortSignal` and preserves the response for explicit classification. Legacy source fields are not part of this contract.

## Legacy Production Mode

When the V2 projection is present, the storyboard surface re-reads the projection at the submission boundary. It verifies the selected shot, lane readiness, and projected model profile identity before posting. IMAGE and VIDEO use the same canonical client. A successful execution stays in the canonical path and refreshes the V2 projection and storyboard data.

The Legacy Production Workspace panel and the legacy canvas generation controls use the same client as well. The canvas keeps its historical task recovery UI, but its production POST no longer carries canvas adopted-media or reference fields.

Production-mode action planning and the advanced generation controls now use V2 lane readiness directly. Legacy adopted-media values remain visible as compatibility evidence and cannot enable or disable a canonical production lane. The canvas also performs a fresh V2 shot and model check immediately before its canonical POST.

## Legacy Compatibility Mode

The non-production branch retains the previous compatibility request for older projects. Its task recovery behavior is unchanged except that the user-visible message is explicitly marked `LEGACY_TASK_RECOVERY_COMPATIBILITY`. This keeps old task-only providers recoverable while making the boundary observable.

The explicit legacy compatibility request is marked `LEGACY_COMPATIBILITY_ONLY` in the phase audit. It is not used by V3 or by a V2 production mutation.

## Response Classification

`legacyProductionGenerationBridge.ts` classifies responses as `canonical_execution`, `canonical_candidate`, `legacy_task`, `mixed_canonical_with_task_diagnostic`, or `invalid_response`.

Canonical execution wins whenever `execution` exists. A `task_id` alongside execution is diagnostic metadata only. A task-only payload is the sole response shape that enters the compatibility polling path. Unknown shapes fail closed.

## Canonical Execution Priority

`ProductWorkspaceTasksSection` and batch actions now avoid creating Pending Tasks for canonical executions. They create recovery state only for task-only responses. This prevents duplicate task-center records and prevents polling a task identifier that is not authoritative.

## Task-ID Fallback

Task-only responses remain supported for legacy providers. The recovery path writes the existing local pending-task record, polls the existing task status endpoint, reconciles when required, and removes the record after completion. Unit coverage verifies that task-only and mixed responses take different paths.

## Mixed Response Handling

A response containing both `execution` and `task_id` is classified as `mixed_canonical_with_task_diagnostic`. It stays on the canonical execution path, does not create a Pending Task, and does not start task polling.

## compileIfMissing Boundary

Production generation always sends `compileIfMissing:false`. Prompt compilation remains an explicit user action. The compatibility branch keeps its historical VIDEO behavior for older projects and is not used for a V2 production mutation.

## Prompt Compile Boundary

Prompt recompile metadata is carried only when the user explicitly ran the recompile flow. Generation does not silently mutate prompt versions or Source Fact records.

The `recompile_then_frame` and `recompile_then_video` chains are evidence of a completed explicit compile step; the shared generation body still sends `compileIfMissing:false`. Contract tests cover both targets.

## Executability Override Boundary

Production submission re-validates the V2 lane after confirmation. A 409 executability confirmation response fails closed and shows the operator guidance; the UI does not automatically issue a second paid POST.

## Model Selection

The selected IMAGE or VIDEO profile is read from the explicit profile selection and compared with the fresh V2 projection before submission. The client does not silently substitute a default profile.

## Freshness Guard

The confirmation dialog is not the final authority. The fresh projection check protects against a changed shot, lane state, or model profile between confirmation and mutation.

## Double Submit

The existing generation state disables repeated user actions during submission, and the Legacy storyboard, Canvas, and V2 panel now also hold a synchronous mutation lock so a second click arriving before React re-renders cannot create a second POST. Canonical completion refreshes the V2 projection and then refreshes the storyboard data. No retry loop or automatic second POST was added.

## LocalStorage Diagnostic Boundary

Canonical executions persist only the existing `NONCANONICAL` execution summary for compatibility UX and diagnostics. Pending storyboard task storage is reserved for task-only recovery. Mixed canonical responses therefore do not leave diagnostic `task_id` values in localStorage. Neither summary is read by `canGenerate`, official-media, or review-eligibility logic; those remain V2 projections.

## Legacy Adoption vs Canonical Promotion

The change does not promote candidates automatically. Canonical candidates remain `MEDIA_CANDIDATE` until the existing explicit validation and human promotion flow is used. Legacy adopted media remains compatibility data and is not rewritten as an official canonical version by this phase.

## Mount-time Reconcile POST Audit

The browser session continues to emit the existing `POST /api/agent/updates/reconcile` during workspace mount. It is background agent-update reconciliation and is unrelated to generation mutation. No new mount-time generation POST was introduced.

## Network Audit

The disposable browser fixture observed:

- IMAGE: `POST /api/books/998755/storyboard/1/1/generate-frame` → `200`.
- VIDEO: `POST /api/books/998755/storyboard/1/1/generate-video` → `200`.
- Both bodies contained `modelProfileId`, `confirmed`, `allowExternalCall`, `compileIfMissing:false`, and `generationChain`.
- Neither body contained `firstFrameAssetId` or `referenceAssetIds`.
- Both mocked responses contained canonical execution plus a diagnostic `task_id`; no task polling request was observed.
- A task-only mocked response entered `LEGACY_TASK_RECOVERY_COMPATIBILITY`, created one pending recovery record, and issued one task status request before removing the record on completion.
- Removing `ui_v3` from an eligible fixture selected `data-storyboard-surface="v3"` with reason `eligible_default`.
- An explicit mocked prompt compile completed before a `recompile_then_video` generation POST; the generation body contained `compileIfMissing:false` and no legacy source fields.

The fixture also exposed unrelated disposable-environment failures for prompt-version loading (`500`) and bridge-state loading (`404` in earlier runs); these did not alter the canonical request assertions.

## Tests

The phase adds response-classification coverage, IMAGE and VIDEO canonical service contract assertions, AbortSignal forwarding, task-id preservation, explicit recompile-chain coverage, V2-only production action gating, canvas freshness coverage, batch/task-center behavior, and a real storyboard alias test proving response-shape telemetry is recorded at the endpoint boundary. The final verification commands are recorded in the truth audit artifact. The final Web suite has 61 files and 417 passing tests; the required backend regression set has 34 passing tests.

## Provider Safety

No real LLM or media provider was called by the browser QA. Provider selection remains profile driven; the configured Shapi (`https://www.shapi.vip/`) adapter can be selected through the existing model registry without changing this UI boundary. The phase does not add provider credentials or bypass human review.

## Remaining Legacy-only Capabilities

The compatibility branch still supports task-only providers, legacy adopted-media recovery, and the older non-production VIDEO request semantics. These are intentionally isolated behind the production-mode gate.

## Next Deprecation Candidates

The next candidates are the remaining non-production compatibility request fields and the legacy task-only provider bridge. They require provider usage telemetry and a separate deprecation decision; no canonical production mutation remains in the canvas surface.

## Completion

`PRODUCTION_UI_V3_LEGACY_CANONICAL_MUTATION_CONVERGENCE_COMPLETE`
