# V7.6.4 Stage A Schema Contract Hardening Report

## Final status

`DIRECTOR_BEAT_PLAN_ATTEMPT6_AUTHORIZATION_REQUIRED`

This phase made zero Provider calls and did not modify Packet 64. Attempt-5
remains immutable with its original raw response and schema-invalid outcome.

## Attempt-5 root cause

Attempt-5 returned six `beats[].hook` values as natural-language strings. The
formal schema requires boolean values. The failure was caused by prompt
contract ambiguity: `REQUIRED_BEAT_FIELDS` named `hook` but did not declare its
type, while the general complete-sentence instruction made a text
interpretation plausible.

The schema was not weakened. `hook` remains boolean because the runtime
validator and final compiler copy it to `hook_intent` as a boolean. No string
coercion, parser repair, fallback, local completion, or production repair was
added.

Read-only diagnosis found exactly six schema errors, one for each returned
hook. `confidence="high"` is allowed by the existing `number|string` contract
and was not reported as an error.

## Contract hardening

The Stage A prompt now contains an explicit field-type table, a boolean-only
hook contract, true/false business semantics, prohibited string examples, and
a type-only JSON shape example. Text completeness applies only to string
creative fields. Stage B and compiler semantics were not changed.

## Attempt-6 provider-free preflight

- target: Book 990453 / Episode 1 / `E01_SC001` / Packet 64
- attempt history before/after: `5 / 5`
- expected attempt: `attempt-6`
- source units: `12`
- profile: `local-llm-2vydoz / openai-compatible / mimo-v2.5`
- host: `https://api.xiaomimimo.com`
- schema: `director_beat_plan_ir_v1`
- execution boundary: `director_beat_plan_provider_request_v1`
- max_tokens: `8192`
- temperature: `0.0`
- response format: `{"type":"json_object"}`
- thinking: `{"type":"disabled"}`
- internal consistency: `PASS`
- preflight/runtime identity parity: `PASS`
- Provider calls: `0`

New identity values:

- system prompt SHA256: `0d33e6805d856ec167ba6c6c9327f2942c6db159fd5edbacb3df0c16c25d12a7`
- user prompt SHA256: `250d67053dd3ca95c8a698bc69f756986fb100eb3f83dbef857d4a9bc16744a4`
- prompt fingerprint: `ddf1662a8583a48d2347ac4e231c3ff27769679224ed1946069018effdbbc488`
- Provider Request Fingerprint V2: `3a73fc2e762e0572b810dfe2149c959356e8786148e040897839cba418f9cee4`

The fingerprint changed from Attempt-5 because the typed hook contract,
semantic definition, and JSON shape example changed the canonical prompt.

## Provider-free regression

- `hook=true`: PASS
- `hook=false`: PASS
- string/number/null hook variants: schema FAIL
- no coercion or repair: PASS
- 12/12 coverage: PASS
- local creative completion: `0`
- deterministic materialization: PASS
- Attempt-5 raw diagnostic: read-only, unchanged
- unknowns audit: `UNKNOWN_SOURCE_FACTS_PROVIDER_OPTIONAL`; current schema permits the Provider to return an empty `unknowns` array and no existing contract requires preservation, so this did not block schema hardening.

## Verification

- V7.6.4 + V7.6.2 + V7.6.1 + V7.2 + V7.1 + V7.4.1 focused suites: `89 passed`
- compileall: PASS
- `git diff --check`: PASS
- production writes: `0`
- Stage B / IMAGE / VIDEO: `0`

Attempt-6 may be authorized separately. It was not executed in this phase.
