# Phase J2 Legacy Storyboard Provider Retirement Plan

## Chosen strategy

Choose **A: delegate the existing endpoints to the canonical generation service**.

The public routes remain stable temporarily for UI compatibility, but they stop being Provider entry points. They become thin request adapters that create an explicit selection and call the shared preview/execute service. Strategy B (disable the routes) is the fail-closed emergency state before delegation is available, not the long-term architecture.

```text
/api/books/{book_id}/storyboard/{episode}/{shot_id}/generate-frame
/api/books/{book_id}/storyboard/{episode}/{shot_id}/generate-video
  → typed ProductionGenerationSelection
  → shared canonical preview/execute service
  → GenerationExecutionRecord
  → MediaCandidateRecord
```

## Current path to retire

```text
visual_prompt_static / visual_prompt_motion
  → _queue_storyboard_generation_task()
  → _resolve_creative_profile() / resolve_generation_profile()
  → _run_creative_task()
  → generate_image_asset() / generate_video_asset()
  → _save_asset_to_storyboard()
```

This path has independent task state, profile fallback, URL/reference handling, and direct storyboard persistence. It cannot remain a second Production Generation Truth.

## Retirement phases

### Phase 0 — Freeze the boundary

- Keep the routes available only as a compatibility façade.
- Reject production requests without explicit `model_profile_id`; never call `get_default_profile()` for execution.
- Keep connectivity-test routes separate and non-production.
- Add no new provider branch or legacy task persistence.

### Phase 1 — Delegate preview and selection

- Normalize `generate-frame`/`generate-video` into the typed selection and media request contract.
- Resolve current PromptIR and H2/H2.2 bindings; do not read `visual_prompt_*` as Provider truth.
- Resolve the profile-bound adapter and credential readiness.
- Call shared `preview_generation()` and return execution ID/confirmation token.

### Phase 2 — Delegate execution and async polling

- Route confirmation to `execute_generation(preview_execution_id, confirmation_token)`.
- Keep IMAGE and VIDEO in the same lifecycle and idempotency boundary.
- Store async task IDs on the existing execution/candidate records; polling remains transport work.
- Do not invoke `_run_creative_task()` or Provider adapters directly from the public storyboard route.

### Phase 3 — Candidate projection only

- Show `MediaCandidateRecord` through a read-only storyboard projection if the UI needs a preview.
- Remove direct `_save_asset_to_storyboard()` authority writes from canonical generation.
- Resolve adopted/official storyboard media through OfficialMedia pointers after validation and explicit promotion.

### Phase 4 — Deprecate and remove the direct branch

- Mark direct task fields and Provider call sites deprecated after all production callers delegate.
- Remove direct Provider call sites and fallback default behavior after a caller audit.
- Keep connectivity tests and draft/mock workflows under separate contracts.

## Required safeguards

| Risk | Required guard |
|---|---|
| Registry default becomes hidden selection | Explicit profile ID required; absence fails closed. |
| Caller pairs ModelProfile A with Adapter B | Adapter binding is resolved from the profile; caller cannot send free `adapter_id`. |
| Stored storyboard prompt becomes Provider truth | Current PromptIR is re-resolved; storyboard prompt columns are projection only. |
| Raw URL becomes reference truth | Only current authority bindings are accepted. |
| Provider success writes official media | Candidate-only write; validation and explicit promotion remain separate. |
| Profile changes after preview | Compare profile and adapter fingerprints; mark execution `STALE`. |
| Async polling duplicates generation | One execution ID and one logical Provider call. |

## Exit criteria

Retire the legacy branch only when:

1. both routes delegate to the shared service;
2. no production caller reaches `_run_creative_task()` or `_save_asset_to_storyboard()` for Provider generation;
3. execution records contain target media, selection/profile/adapter fingerprints, and authority fingerprints;
4. IMAGE and VIDEO candidate validation use the same downstream authority chain;
5. a route audit proves no implicit default or raw storyboard URL remains;
6. the deprecation window completes with no legacy production callers.

Until these criteria are met, canonical design remains pending implementation and full real E2E stays disabled.
