# UI V2 Production Read Model

## Contract

`production_workspace_projection_v2` is a read-only projection assembled from the existing authority and pointer records. It does not create a UI authority, a frontend official state, a candidate-selection truth, a migration, or a browser-cache fallback.

The HTTP read route is:

```text
GET /api/books/{book_id}/production-workspace-v2
```

The source remains `current_authority_pointers_only`. The projection exposes:

- project and episode state, blockers, and the current next action;
- shot identity, scene, duration, camera and action;
- asset readiness and current/stale/missing bindings;
- independent IMAGE and VIDEO lanes;
- media-scoped PromptIR currentness;
- explicitly selected model profile when an execution exists;
- latest GenerationExecution, MediaCandidate and technical validation;
- OfficialMedia pointer, version and authority lineage;
- VIDEO generation mode and the current Official IMAGE source when the backend projection has one.

## Presentation contract

Standard and professional views consume the same snapshot. The toggle only changes disclosure density:

| View | Shows | Hides by default |
|---|---|---|
| Standard | state, missing prerequisites, one next action, candidate vs current official, video source | authority IDs, hashes, fingerprints, provider task IDs |
| Professional | all standard fields plus PromptIR, ModelProfile, Adapter/transport, execution, candidate validation, OfficialMedia and history lineage | nothing from the read model |

`provider_calls` is telemetry only. V2 validation does not require it to be zero before rendering. UI tests and fixtures remain provider-free.

## Current blocker semantics

For `book-990401 / Episode 01`, the projection must keep the asset gate visible as `15 Production Assets / 15 real visual media missing`. Existing canary and storyboard files are excluded unless an explicit `entity_id → media_identity` mapping exists. A legacy `StoryboardShot.assets.*.adopted` value never becomes OfficialMedia.

## Refresh and persistence

The frontend does not persist production truth in localStorage. Refreshing the page, clearing localStorage, or opening another browser causes the V2 route to rebuild the snapshot from backend authority records.

## Upload boundary

The V2 card is entity-first, but this round does not invent a browser upload contract. A formal Production Asset ingestion API must provide the durable media identity, checksum, typed Authority/Version/Pointer rows, and explicit shot binding before the card can move from `缺少真实视觉资产` to `已就绪`. Until then the state is recorded as `UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API`.
