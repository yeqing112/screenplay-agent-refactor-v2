# V7.6.18 Director CreativeEnrichment Attempt-10 Real Semantic V2 Revision Canary

DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_SCHEMA_INVALID
NEXT_STATE=DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED
SEMANTIC_REVIEW_V2=NOT_RUN_AFTER_STRUCTURAL_FAILURE

## Scope and authorization

- Target: Book 990453 / Episode 1 / Scene E01_SC001 / Packet 64.
- Packet fingerprint: `e48b8502ab2e14b94798d19a`.
- Authorization: `v7.6.18-attempt10-stage-b-semantic-v2-single-call`.
- Provider profile: `local-llm-2vydoz / openai-compatible / mimo-v2.5 / https://api.xiaomimimo.com`.
- Real Provider POST count: `1`; automatic retry: `0`; Attempt-11: `0`.

## Runtime and transport

- HTTP status: `200` (successful JSON response; no provider request ID was returned, recorded as `null`).
- Finish reason: `stop`; choice index: `0`.
- Latency: `92973.83 ms`.
- Tokens: prompt `5617`, completion `3213`, reasoning `0`, total `8830`.
- Raw length: `5728`; raw SHA256: `5daf096fd07ad58ffe8848b25a8d633797234ce325dba1986f21de4af4ca39f0`.
- Provider request fingerprint: `b9b0592520fd13aac0eb70c671e4fc82be901e1031b4690ae030e146e885169b`.

## Structural gates

- Raw persisted before parse: `True`.
- Strict parse: `PASS` (JSON object was parsed for forensic diagnostics).
- Duplicate key: `PASS`.
- Schema: `FAIL` — missing required field `visual_priority`.
- Text completeness / runtime / compiled V3: `NOT_RUN_AFTER_SCHEMA_FAILURE`.
- Attempt-10 IR fingerprint: not generated.

## Semantic V2

- Parent Attempt-9 V2 status: `BLOCKED`.
- Parent review fingerprint: `e021e4d1380f5d6b91092e892fc9d7a37d71ca3e13a0f17ded88320e74f6c66a`.
- Policy: `director_creative_semantic_review_v2`.
- Policy fingerprint: `9df29513e7bf0433dae06b148b60e93f9afcb5517fd63d75a8b7b98c3994b501`.
- Attempt-10 semantic V2 gate: not run because structural schema validation failed.
- Attempt-9 -> Attempt-10 delta: Attempt-9 had certainty 1, unsupported story action 1, SceneBlocking leakage 2, ShotPlan leakage 0; Attempt-10 semantic counts are not applicable after the structural stop.

## Binding and lineage

- Stage A remains `attempt-7`, IR `b3dbf2624289134c10d19f93c9cbd00614e9caa501dbe40cd002e24e42821086`, materialized `328380be4977fe19f79f574d53facb9df61e229c7098ca28c4919fe25cc5bb01`.
- Parent remains Attempt-9, IR `591bf4ec2f7df8b80a8fdd3a7166c6a76c39a7de0939ba3b1323b6af2320dfaa`, raw SHA `8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589`.
- Source projection fingerprint: `2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f`.
- Source authority content fingerprint: `ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8`.
- Revision parent fingerprint: `e2a53e95c74d72dcae1e7e910574994fddf34a51660c434f861262ac64ad6809`.
- Attempt-9 archive preserved; Attempt-10 failure archive appended. Active Stage B restored to Attempt-9.

## Fresh generation and quality

- Fresh generation contract present; Attempt-9 raw was not included in the prompt.
- V2 feedback was included as four constraints: certainty 1, unsupported story action 1, SceneBlocking 2, ShotPlan 0; V1 false-positive feedback 0.
- Creative quality audit is diagnostic only because schema failed; see `ATTEMPT10_CONTENT_QUALITY_AUDIT.json`.

## Production boundaries

- Proposal unchanged: `True`; `decision=ready_for_review`, `creative_projection.status=PROPOSED`.
- DirectorTreatment approved writes: `0`; Authority writes: `0`; Pointer writes: `0`.
- SceneBlocking / ShotPlan / PromptIR: `0`.
- IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`.
- Confirm endpoint: not called; confirm allowed: `false`.
- No retry, automatic Attempt-11, Authority promotion, or downstream execution occurred.

## Verification

- Provider-free regression suite after the idempotent archive fix: `18 passed` focused tests.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
- Working tree and remote commit are recorded after evidence commit.
