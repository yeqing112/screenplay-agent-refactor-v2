# Production UI V3 Canonical State Adapters

- **Phase**: `PHASE_PRODUCTION_UI_V3_CANONICAL_STATE_ADAPTERS`
- **Baseline**: `4fefd0c57f6d9526d9168e073df7efef00b13e5f`
- **Branch**: `codex/visual-authoring-provider-canary-reconcile`
- **Scope**: pure domain adapters and tests for the future V3 Shot Studio surface.
- **Completion marker**: `PRODUCTION_UI_V3_CANONICAL_STATE_ADAPTERS_COMPLETE`

This adapter turns the production workspace V2 projection into a stable, read-only UI view model. It does not call providers, mutate production state, persist browser state, or run React state transitions. The adapter keeps the canonical authority evidence visible for professional inspection while providing one conservative state and one primary action for the standard UI.

## Canonical Inputs

The adapter accepts the existing production projection types from `web/src/domain/productionWorkspace.ts`:

- `ProductionShotV2` and its `asset_readiness`, scene, camera, action, and blocker facts.
- `ProductionMediaLane` for `IMAGE` and `VIDEO`.
- `prompt_ir` currentness, version, state, and reason codes.
- `generation_readiness` as the only generation permission contract.
- `GenerationExecutionProjection` for the latest execution.
- `MediaCandidateProjection` and technical validation for review eligibility.
- `OfficialMediaProjection` authority, current pointer, version, and preview evidence.

The output is `ProductionMediaLaneViewModel` or `ShotStudioViewModel`. The professional section retains raw canonical fields so an operator can inspect the evidence behind the standard state.

## Non-Canonical Inputs

The following values may be displayed as context but cannot establish an official result or enable production:

- legacy adopted flags and legacy output aggregates;
- candidate previews without a technically valid validation result;
- `current=true` without a complete, matching authority/current pointer chain;
- browser `localStorage`, React state, or stale prompt/display caches;
- unknown execution states;
- an implicit readiness inference when `generation_readiness` is absent.

Candidates never become official merely because they exist or are technically valid. Promotion remains an explicit human-reviewed backend operation.

## V3 UI States

| State | Meaning | Typical next action |
| --- | --- | --- |
| `ready` | Explicit readiness contract is true and no higher-priority result exists. | Generate the selected lane |
| `running` | Provider execution is actively processing. | View progress |
| `review` | A candidate is technically reviewable and awaits human decision. | Open review |
| `waiting` | Upstream work or dependency is pending. | Wait for upstream |
| `blocked` | Evidence is missing, contradictory, unsupported, or requires repair. | Resolve blocker |
| `stale` | Prompt, source, candidate, or official context is no longer current. | Inspect upstream change |
| `failed` | The latest execution ended unsuccessfully. | Retry when readiness allows |
| `official` | A canonical current official version is established. | View official |

## Official Rules

`isCanonicalOfficialMedia()` returns true only when all of these facts hold:

1. `current === true`.
2. `currentness === CURRENT` (case-insensitive).
3. A version id exists.
4. An authority id exists and its status is current (or omitted by the source contract).
5. A pointer id and `pointer.authority_id` exist.
6. `pointer.authority_id === authority.id`.

Any failed condition is fail-closed. The adapter emits `V3_CANONICAL_OFFICIAL_POINTER_MISSING` or `V3_CANONICAL_OFFICIAL_POINTER_MISMATCH` and never upgrades the lane to `official`. The promoted candidate id is removed from the review queue when it matches the canonical official version's `candidate_id`.

## Execution Mapping

| `GenerationExecutionProjection.state` | UI execution state | Lane behavior |
| --- | --- | --- |
| `CREATED`, `QUEUED`, `RETRYING` | `waiting` | Disable generation and wait |
| `RUNNING`, `PROVIDER_PENDING`, `PROVIDER_CALLED` | `running` | Show progress; no new generation |
| `SUCCESS` | `succeeded` | Continue to candidate review or official evidence |
| `FAILED`, `CANCELLED`, `ERROR` | `failed` | Retry only when readiness is true |
| `STALE` | `stale` | Refresh the stale source |
| Any other value | `unknown` | Lane is `blocked` with `V3_UNKNOWN_EXECUTION_STATE` |

An execution that ends without a candidate and without canonical official media is treated as failed with `V3_EXECUTION_CANDIDATE_MISSING`.

## Review Mapping

A candidate is reviewable only when its state is `MEDIA_CANDIDATE` and its technical validation status is one of `TECHNICALLY_VALID`, `REVIEW_REQUIRED`, or `PASS`. A reviewable candidate produces `review` and the `review_candidate` action. Pending validation produces `waiting`; unsupported validation produces `blocked` with `V3_CANDIDATE_NOT_REVIEWABLE`. A promoted candidate is excluded from review when its id matches the official version candidate id.

## Stale Mapping

The adapter prioritizes stale evidence over review and readiness. It maps to `stale` when any of these are true:

- `prompt_ir.stale === true`, prompt state is `STALE`, or prompt reason codes contain `STALE`;
- official currentness is `OBSOLETE` or `HISTORICAL`;
- candidate technical validation is `STALE`;
- execution state is `STALE`;
- shot asset binding reports stale data.

The standard action is `refresh_stale_source`; it does not silently regenerate.

## Blocked vs Waiting

Use `blocked` when the UI has a concrete condition that must be repaired or cannot be interpreted safely: missing/inconsistent readiness contract, missing assets, invalid official pointer evidence, unknown execution state, unsupported validation, or an explicit readiness blocker such as `ASSET_MEDIA_NOT_READY`, `PROMPT_IR_NOT_CURRENT`, `MODEL_PROFILE_REQUIRED`, or `VIDEO_GENERATION_MODE_INVALID`.

Use `waiting` when the chain is valid but work is pending: queued execution, pending candidate validation, or `IMAGE_TO_VIDEO` waiting for a canonical current official image. A missing readiness contract is never treated as waiting.

## Primary Action Priority

Each lane and shot receives exactly one `primaryAction`. Resolution precedence is:

1. canonical evidence contradiction or other blocker;
2. stale source;
3. failed execution;
4. active execution;
5. pending upstream dependency;
6. reviewable candidate;
7. explicit readiness and generation;
8. view the official version.

Actions that can invoke a provider are marked with `requiresProviderCall: true`; the adapter itself never invokes that action.

## Reason Codes

Stable adapter-owned codes use the `V3_` prefix:

- `V3_CANONICAL_OFFICIAL_POINTER_MISSING`
- `V3_CANONICAL_OFFICIAL_POINTER_MISMATCH`
- `V3_CANONICAL_SOURCE_OFFICIAL_IMAGE_INVALID`
- `V3_UNKNOWN_EXECUTION_STATE`
- `V3_EXECUTION_CANDIDATE_MISSING`
- `V3_CANDIDATE_NOT_REVIEWABLE`
- `V3_READINESS_CONTRACT_MISSING`
- `V3_READINESS_CONTRACT_INCONSISTENT`
- `V3_STATE_UNRESOLVED`

Upstream reason codes are preserved alongside these codes for professional diagnostics and support traceability.

## Professional Detail Contract

The professional view must keep the raw official projection, candidate list, model profile, generation mode source, readiness contract, execution identifiers, request fingerprint, provider task/request ids, blockers, asset readiness, and legacy context. These fields are diagnostic evidence only; they do not override canonical state rules.

## Known Unsupported Capabilities

- No real LLM, SHAPI, MiniMax, image generation, or video generation call is made.
- No automatic promotion, script change, source fact change, or database/API mutation is performed.
- No cross-review undo window exists. `UNDO_NOT_SUPPORTED` is the explicit product contract; use the relevant domain rollback/recovery operation when one exists.
- React integration, route wiring, and backend contract changes are intentionally out of scope for this phase.

## Test Invariants

The adapter tests assert that:

- incomplete official evidence is never presented as official;
- legacy adopted flags and candidates cannot self-promote;
- active, failed, unknown, stale, and dependency states map conservatively;
- `IMAGE_TO_VIDEO` requires a canonical official image;
- generation is allowed only for an explicit `generation_readiness.ready === true` contract;
- promoted candidates leave the review queue;
- input snapshots are not mutated;
- each shot exposes one primary action;
- no test or adapter path calls a provider or performs a production write.
