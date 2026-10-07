# V7.6.15 Attempt-9 Real Semantic Revision Canary

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_PREFLIGHT_BLOCKED`

The single authorized Attempt-9 Provider POST was **not sent**. Runtime preflight rebuilt the prompt identity and failed closed because the frozen V7.6.14 user prompt, prompt fingerprint, and Provider request fingerprint do not match the current canonical builder. The source race gate also reports `EXACT_SOURCE_PROJECTION`, while the frozen reconciliation evidence requires `SOURCE_PROJECTION_VERSION_DRIFT`.

- Provider POST: `0`
- Automatic retry: `0`
- Attempt-10: `0`
- IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`
- Confirm endpoint: not called
- DirectorTreatment / Authority / Pointer writes: `0 / 0 / 0`
- Attempt-8: immutable and unchanged
- Production DB before/after: byte-equivalent target snapshot

## Runtime identity

| Field | Frozen | Runtime | Match |
|---|---|---|---|
| system prompt SHA | `6d2c045e97fdc3cfee6797a925010d5e7340fa71d04c41ed3ed59e65ff749baa` | `6d2c045e97fdc3cfee6797a925010d5e7340fa71d04c41ed3ed59e65ff749baa` | `PASS` |
| user prompt SHA | `a60df635b7d70ecd1ba88d28d9ed1dd72cc3fa000987379c4eb42558a8913541` | `6f2bce5bc4aeecf3a535c24016e308c208e02ca1366fb995d4c25fcb0a05f64f` | `FAIL` |
| prompt fingerprint | `a1c5532885d5da943558e041621976886de94299f71d14e5b9489525c1bd6d4d` | `e267cd3061cdeddd65ef5004426322cf8ea5e02aeef1f6af0f4cf45c248f719f` | `FAIL` |
| Provider request fingerprint | `d233292b98a4c50822a99aa6b20b92ab5ff58ccc991878238d5b57811ff928ed` | `092db3c5fbf726ed730b256e5b35a43568d7bfd44590e4f3d8a770647f7c71f5` | `FAIL` |

Profile: `local-llm-2vydoz / openai-compatible / mimo-v2.5 / https://api.xiaomimimo.com`.

Source projection runtime: `2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f`. Source content runtime: `ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8`.

## Validation gates

All post-transport gates are `NOT_RUN` because the preflight did not prove the exact frozen request identity. No raw response was received or persisted. No semantic comparison between Attempt-8 and Attempt-9 exists. Attempt-8 parent review remains `BLOCKED` with its historical fingerprint preserved.

## Verification

- Focused provider-free tests: `42 passed`
- `python -m compileall -q core api`: passed
- `git diff --check`: passed
- Evidence generation performed no external call and no production write.
