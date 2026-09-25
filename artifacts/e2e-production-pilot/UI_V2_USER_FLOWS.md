# UI V2 User Flows

## First-time ordinary user

1. Open the project dashboard in **标准视图**.
2. Read the project blocker and the single highlighted next action.
3. Open **资产中心** and choose an entity from the backend manifest.
4. Upload a real media file, preview it, and explicitly confirm the Production Asset binding. The action creates a new version; it does not overwrite history or auto-match by filename.
5. Return to the shot workspace. The shot card changes from `补齐资产` to the next authority-projected action.
6. Select an explicitly configured IMAGE model. Without a model profile, `生成图片` remains blocked.
7. Generate through the canonical IMAGE lane. The result appears as `候选结果`.
8. Review technical validation and use the existing backend promotion contract when it is available. Only the resulting OfficialMedia pointer is shown as `当前正式版本`.
9. Open VIDEO. IMAGE_TO_VIDEO displays the current Official IMAGE as its source; legacy adopted images are not used as the source.
10. Select an explicitly configured VIDEO model, generate a video candidate, review it, and promote through the backend contract when available.

## Asset preparation

The asset hub is entity-first. Each card shows type, current state, media presence, binding count and affected shots from the backend projection. A missing card routes to the existing asset center, where the ordinary flow is `选择实体 → 选择文件 → 预览 → 确认绑定`.

## Generate IMAGE

The IMAGE lane shows PromptIR readiness, model selection, the latest execution, candidate count and OfficialMedia. Missing model, missing real media, stale binding and stale PromptIR are explicit blockers.

## Promote IMAGE / VIDEO

Candidates and official media are separate objects. A candidate is never displayed with the current-official badge. Promotion is offered only by a real backend promotion contract; the V2 read panel does not invent `accepted` or `favorite` state.

## Professional inspection

Switch to **专业视图**. Expand a lane to inspect PromptIR version/hash, ModelProfile, execution ID/state, candidate validation and OfficialMedia authority/pointer lineage. This is a presentation change over the same response, not a second state machine.

## Failure recovery

Failures are shown with the user-facing event and next action first. Professional view adds failure code, adapter, transport and provider task ID. A failed execution requires explicit `重新生成`; the UI does not auto-retry.
