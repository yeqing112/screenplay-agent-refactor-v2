# DIRECTOR_BEAT_PLAN_ATTEMPT6_SCHEMA_INVALID

## Final status

`DIRECTOR_BEAT_PLAN_ATTEMPT6_SCHEMA_INVALID`

Attempt-6 used the authorized dedicated Stage A endpoint and made exactly one
real Provider HTTP POST. The Provider returned HTTP 200 and `finish_reason=stop`.
Strict JSON parsing passed, but the formal `director_beat_plan_ir_v1` schema
gate failed. Execution stopped immediately. No retry, repair, text completion,
runtime validation, materialization, Stage B, confirm, compile, IMAGE, VIDEO,
or authority promotion ran.

## Provider result

- authorization: `v7.6.6-attempt6-stage-a-single-call`
- target: Book 990453 / Episode 1 / `E01_SC001` / Packet 64
- Provider POST: `1`
- HTTP status: `200`
- provider request ID: empty (Provider returned none)
- finish_reason: `stop`
- choice index: `0`
- usage: prompt `2234`, completion `961`, total `3195`, reasoning `0`
- raw length: `1856`
- raw SHA256: `04d407286aa9607e955fe57744d29d4cbf6422decccbf44ab22c13215dbdf86d`
- raw-before-parse: `PASS`
- strict JSON parse: `PASS`

## Schema result

The Attempt-5 `hook` issue was resolved: all returned hook values were JSON
booleans (`1 false`, `7 true`). The new schema failure was unrelated to hook:
the Provider emitted a non-contract field variant for `information_change` in
four beats and omitted the required canonical `information_change` field in
four beats. The read-only schema diagnostic recorded `9` formal errors in
total. No coercion or repair was applied.

Because schema failed, these gates were intentionally `NOT_RUN`:

- text completeness
- source coverage/runtime
- deterministic materialization
- Stage A success persistence

The content quality audit is read-only and does not participate in validation.
It records 8 beats, 12 source references, non-empty purpose/objective text,
hook distribution `true=7 / false=1`, no Stage B top-level fields, and no
production interpretation or repair.

## Identity and lineage

- system prompt SHA256: `0d33e6805d856ec167ba6c6c9327f2942c6db159fd5edbacb3df0c16c25d12a7`
- user prompt SHA256: `250d67053dd3ca95c8a698bc69f756986fb100eb3f83dbef857d4a9bc16744a4`
- prompt fingerprint: `ddf1662a8583a48d2347ac4e231c3ff27769679224ed1946069018effdbbc488`
- Provider Request Fingerprint V2: `3a73fc2e762e0572b810dfe2149c959356e8786148e040897839cba418f9cee4`
- identity internal consistency: `PASS`
- preflight/runtime parity: `PASS`
- attempt lineage: `PASS`

## Persistence boundary

- ledger: `5 → 6`
- latest ledger attempt: `attempt-6`
- latest status: `DIRECTOR_BEAT_PLAN_ATTEMPT6_SCHEMA_INVALID`
- Attempts 1–5: immutable
- Stage A persisted attempt ID: none; schema failed before Stage A persistence
- Packet proposal before/after: `{"decision":"awaiting_llm"}` / unchanged
- DirectorTreatment rows: `0`
- Authority rows: `0`
- Pointer rows: `0`
- Stage B calls: `0`
- IMAGE calls: `0`
- VIDEO calls: `0`
- downstream production rows: `0`
- allowed production write: Packet `model_info` forensic/ledger/validation metadata only

## Verification

- pre-canary focused suites: `100 passed`
- post-canary local evidence validation: PASS
- compileall: PASS before canary
- `git diff --check`: PASS before canary
- Attempt-7: not executed
- Stage B: not entered

The next action requires a new schema contract decision for the Provider's
field-name drift. No automatic continuation is authorized.
