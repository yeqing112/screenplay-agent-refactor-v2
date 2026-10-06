# Real Director Proposal IR Canary V7.5 Report

- Authorization: `v7_5-director-proposal-ir-real-canary-authorization-3`
- Target: Book 990453 / Episode 1 / Scene E01_SC001 / Decision Packet 64
- Provider: `openai-compatible` / `mimo-v2.5` / `api.xiaomimimo.com`
- Result: **FAILED CLOSED** (`DIRECTOR_PROPOSAL_IR_INVALID`)

## Transport

Exactly one corrected request reached MiMo. Provider HTTP status was `200`; transport retry, parse retry, repair and fallback were all `0`. The first app request was rejected locally with `SCENE_ID_REQUIRED` before reaching the Provider. No second Provider request was made.

- Actual request fingerprint: `a151a26c6e5514d6657e24362906ea3638d8cfff20366493fc5ee2a60527f8f9`
- Frozen preflight fingerprint: `26b0a52fd64508d33482be227459a5892039e0924ab96ec9c2eab2375ed77d93`
- Match: **false**. The preflight omitted the endpoint's advisory asset character context; the endpoint rebuilt evidence with that context. This mismatch is recorded and the phase is not review-ready.
- Raw response SHA-256: `bc7af44934f4b3a0f9652fdaddc28b8cc67a24404c0bad6da7aa5170000fe7c5`

## IR gates

- JSON parse: **PASS**, exactly once; raw persisted before parse.
- Formal JSON Schema audit: **FAIL** because each `character_directions` item contains unexpected field `direction`.
- Source coverage: **12/12 units covered**, 6 beats, 0 passthrough.
- Runtime validation: **BLOCKED** with two `DIRECTOR_PROPOSAL_IR_CHARACTER_DIRECTION_FIELD_UNEXPECTED` errors.
- Compiler: **NOT RUN**.
- Compiled ProposalIR / DirectorTreatment: **NOT PERSISTED**.

## Safety boundary

Confirmation was not called. No authority, pointer, SceneBlocking, ShotPlan, storyboard, PromptIR, generation execution, media candidate, official media, IMAGE, VIDEO, SHAPI, Poyo or 75API write/call occurred. Source Script, ScriptIR and FactSnapshot lineage remained unchanged. Only Packet 64 forensic `model_info` and attempt ledger were updated; its proposal remains `{"decision":"awaiting_llm"}`.

## Decision

This is a forensic failure artifact, not a successful Director review. Do not retry in this phase. A later code change must align the provider output contract (or compiler adapter) with the flat v1 schema and make the frozen preflight prompt fingerprint identical to the endpoint request before another authorized canary.
