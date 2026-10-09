# V7.6.17 Director Semantic Review V2 Production Wiring

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED`

## Production wiring

- Revision endpoint: persisted V1 parent review -> server-side V2 recomputation for Attempt-9+ revisions.
- Executor: fixed V1 validator -> policy resolver dispatch; Attempt-10+ uses `validate_director_creative_semantic_review_v2`.
- V2 policy fingerprint: `9df29513e7bf0433dae06b148b60e93f9afcb5517fd63d75a8b7b98c3994b501`.
- Attempt-9 runtime V2 review fingerprint: `e021e4d1380f5d6b91092e892fc9d7a37d71ca3e13a0f17ded88320e74f6c66a`.
- V2 feedback: `4` constraints; certainty collapse 1, unsupported story action 1, SceneBlocking leakage 2; ShotPlan false positives 0.
- V1 false-positive feedback count: 0.

## Attempt-10 preflight

- Status: `DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT10_AUTHORIZATION_REQUIRED`; history `9` -> `attempt-10`.
- Parent identity: `e2a53e95c74d72dcae1e7e910574994fddf34a51660c434f861262ac64ad6809`.
- System SHA256: `6d2c045e97fdc3cfee6797a925010d5e7340fa71d04c41ed3ed59e65ff749baa`.
- User SHA256: `1c894944d41b6b369f27e453062a515f40a2b8e9e4a179749616c5ee245f3462`.
- Prompt fingerprint: `b7a023dc4a3eeadefb135d7954f6cf08464fef4f822bf0414fd5284a7bb46da2`.
- Provider Request fingerprint: `b9b0592520fd13aac0eb70c671e4fc82be901e1031b4690ae030e146e885169b`.
- Authorization: `REQUIRED_NOT_GRANTED`; Provider calls: `0`.

## Persistence and gates

- Mock PASS, Mock BLOCKED, and structural failure all use the production executor in the provider-free test suite.
- Attempt-10 V2 assessment is append-only; historical Attempt-9 V1 remains unchanged.
- Confirm gate requires a bound V2 PASS assessment; no confirm call was made.
- Future Attempt-11 preflight reads the persisted Attempt-10 V2 assessment; no automatic Attempt-11 call.

## Invariants and verification

- Production Packet 64 before/after is byte-fingerprint unchanged: `True`.
- Real LLM / Attempt-10 POST / Attempt-11 / IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`.
- `python -m pytest -q tests/test_director_semantic_v2_production_wiring_v7_6_17.py`: `7 passed`.
- V7.6.16, V7.6.14, V7.6.13, Stage A/Stage B execution and provider contract regression suite: `77 passed`.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
