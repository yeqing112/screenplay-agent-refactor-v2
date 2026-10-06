# V7.6.3 Attempt-5 Stage A Canary Report

## Final status

`DIRECTOR_BEAT_PLAN_ATTEMPT5_SCHEMA_INVALID`

Exactly one real Stage A Provider HTTP POST was made. The response was HTTP
200 with `finish_reason=stop` and strict JSON parsing passed. Formal Stage A
schema validation failed because all six `beats[].hook` values were strings
instead of booleans. The canary stopped immediately. No retry, repair,
fallback, Stage B, confirm, compile, IMAGE, VIDEO, or authority promotion ran.

## Fingerprint reconciliation

The runtime canonical builder is `build_director_beat_plan_provider_request()`.
It is shared by preflight, endpoint execution, and forensic identity. The
actual runtime user prompt SHA256 is:

`bad2bcde00e01f2f65e72ca90c9d536f04a6de6e2ee4d306c584f4fedac460d6`

The old V7.6.2 top-level artifact had that value, while its nested payload
still contained the stale value
`0bc0b7eb5f1d64bfef8956fc88d655a5c825716cb63b1262ec9fdd4740c5e74f`.
The cause was evidence generator drift: a partial artifact update changed the
top-level field without rebuilding the nested payload. Runtime prompt
construction was not duplicated, mutated, normalized, or serialized through a
second path. The old parity test compared only two equally stale final
fingerprints, so it produced a false PASS.

V7.6.3 adds an internal consistency gate that checks actual prompt SHA256,
identity fields, payload fields, prompt fingerprint, and Provider Request
Fingerprint V2 before any Provider call.

Current reconciled values:

- system prompt SHA256: `63d78804b933754c2534577134adc0d7181cbc4cfaaa73bc3a0d4a98d4abed53`
- user prompt SHA256: `bad2bcde00e01f2f65e72ca90c9d536f04a6de6e2ee4d306c584f4fedac460d6`
- prompt fingerprint: `90b3c6109c422096ac944c05cbc186f0d471c8ec53bdbf990c3075108225ff5b`
- Provider Request Fingerprint V2: `d56b76506818878f29a2677c3652e566fe905e489a6eb6a263b578df3e1cef4e`
- preflight/runtime parity: `PASS`
- internal consistency: `PASS`

## Canary result

- authorization: `v7.6.3-attempt5-stage-a-single-call`
- target: Book 990453 / Episode 1 / `E01_SC001` / Packet 64
- profile: `local-llm-2vydoz`
- provider/model: `openai-compatible / mimo-v2.5`
- host: `https://api.xiaomimimo.com`
- schema: `director_beat_plan_ir_v1`
- authoring stage: `BEAT_PLAN`
- execution boundary: `director_beat_plan_provider_request_v1`
- max_tokens: `8192`
- temperature: `0.0`
- response format: `{"type":"json_object"}`
- thinking: `{"type":"disabled"}`
- actual Provider HTTP POST: `1`
- provider request ID: empty (Provider did not return one)
- finish_reason: `stop`
- choice_index: `0`
- token usage: prompt `1900`, completion `1076`, total `2976`, reasoning `0`
- raw response length: `2079`
- raw response SHA256: `34bdae748ee533b123e1c436a864623797b13cbc6d4868791323b118e2208421`
- raw persisted before parse: `PASS`
- parse: `PASS`
- schema: `FAIL`
- text completeness: `NOT_RUN` after schema gate
- source coverage: `NOT_RUN` after schema gate
- beat count in response: `6`
- local creative completion: `0`

## Persistence and downstream boundary

- ledger before: `4`
- ledger after: `5`
- attempts 1–4: unchanged
- attempt-5: appended with Stage A, both fingerprints, raw SHA, finish reason and schema-invalid status
- packet proposal before/after: `{"decision":"awaiting_llm"}` / unchanged
- allowed write: Packet 64 `model_info` forensic, ledger and validation metadata
- DirectorTreatment / Authority / Pointer promotion: `0`
- Stage B calls: `0`
- confirm calls: `0`
- compile calls: `0`
- IMAGE calls: `0`
- VIDEO calls: `0`
- downstream production rows: `0`

## Verification

- focused suites: `79 passed`
- compileall: PASS
- `git diff --check`: PASS before canary
- final status and evidence were recorded without another Provider request

Evidence files in this directory contain the root-cause audit, internal
consistency checks, reconciled preflight, authorization, request identity,
transport audit, raw forensic response, validation, ledger, write boundary and
downstream zero-call audits.

The next action is not automatic. Stage B requires a separate authorization.
