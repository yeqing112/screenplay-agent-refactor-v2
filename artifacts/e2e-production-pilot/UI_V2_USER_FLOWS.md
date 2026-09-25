# UI V2 User Flows

## First-time ordinary user

1. Open the project dashboard in **标准视图**.
2. Read the project blocker and the single highlighted next action.
3. Open **资产中心** and choose an entity from the backend manifest.
4. If the formal Production Asset ingestion API is available, upload a real media file, preview it, and explicitly confirm the binding. In this round the API is not available, so the flow stops at `UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API`.
5. Return to the shot workspace. The shot card changes from `补齐资产` to the next authority-projected action.
6. Select an explicitly configured IMAGE model. Without a model profile, `生成图片` remains blocked.
7. Generate through the canonical IMAGE lane. The result appears as `候选结果`.
8. Review technical validation and use the existing backend promotion contract when it is available. Only the resulting OfficialMedia pointer is shown as `当前正式版本`.
9. Open VIDEO. IMAGE_TO_VIDEO displays the current Official IMAGE as its source; legacy adopted images are not used as the source.
10. Select an explicitly configured VIDEO model, generate a video candidate, review it, and promote through the backend contract when available.

## Asset preparation

The asset hub is entity-first. Each card shows type, current state, media presence, binding count and affected shots from the backend projection. Selecting a V2 card passes its canonical `{ entityId, assetType }` context. A missing card exposes the required entity and blocker; it does not select a guessed legacy ID, fabricate a binding, or enable the old reference upload flow while the formal ingestion API is absent.

## Generate IMAGE

The IMAGE lane shows PromptIR readiness, model selection, the latest execution, candidate count and OfficialMedia. Missing model, missing real media, stale binding and stale PromptIR are explicit blockers.

## Promote IMAGE / VIDEO

Candidates and official media are separate objects. A candidate is never displayed with the current-official badge. Promotion is offered only by a real backend promotion contract; the V2 read panel does not invent `accepted` or `favorite` state.

## Professional inspection

Switch to **专业视图**. Expand a lane to inspect PromptIR version/hash, ModelProfile, execution ID/state, candidate validation and OfficialMedia authority/pointer lineage. This is a presentation change over the same response, not a second state machine.

## Failure recovery

Failures are shown with the user-facing event and next action first. Professional view adds failure code, adapter, transport and provider task ID. A failed execution requires explicit `重新生成`; the UI does not auto-retry.
# Production boundary update

The normal flow is `生成 → Candidate → 验证 → 设为正式版本`; every production action reads the V2 projection and fails closed when it is unavailable. Existing `adopted` media may be shown as historical context but cannot satisfy Production generation or delivery eligibility.

The asset step remains blocked at `UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API` until the formal entity-first ingestion contract is available. No frontend path creates Authority, Pointer, or Version rows.
