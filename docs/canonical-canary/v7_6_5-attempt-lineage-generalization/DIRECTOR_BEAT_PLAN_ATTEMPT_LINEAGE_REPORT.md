# V7.6.5 Director BeatPlan Attempt Lineage Generalization Report

## Final status

`DIRECTOR_BEAT_PLAN_ATTEMPT6_AUTHORIZATION_REQUIRED`

No real Provider request was made in V7.6.5. Attempt-6 remains preflight-only.

## Runtime hardcode audit

The runtime hardcodes found before this phase were eight Attempt-5 status
codes, one hardcoded `attempt_id="attempt-5"` in Stage A persistence, and one
success response status. Historical evidence and tests remain allowed to name
Attempt-5. Runtime production code now contains no `attempt-5`, `ATTEMPT5`,
`attempt-6`, or `ATTEMPT6` literals.

## Canonical AttemptContext

`DirectorAttemptContext` is derived once from
`DecisionPacketRecord.model_info.director_llm_attempts` by
`resolve_next_director_attempt_context()`. It contains history count, ordinal,
attempt ID, and dynamic status prefix. The same context is used by raw
forensic append, status generation, Stage A persistence, and API response.

The raw append validates the frozen ledger count and expected ID. Before Stage
A persistence, the latest ledger ID must still equal the frozen context ID.
Any race fails with `DIRECTOR_BEAT_PLAN_ATTEMPT_LINEAGE_CONFLICT` without
renumbering or retrying.

## Provider-free simulations

- history 5 → `attempt-6`, `DIRECTOR_BEAT_PLAN_ATTEMPT6_VALIDATED`
- history 5 schema failure → `DIRECTOR_BEAT_PLAN_ATTEMPT6_SCHEMA_INVALID`
- history 5 parse failure → `DIRECTOR_BEAT_PLAN_ATTEMPT6_PARSE_FAILED`
- history 5 text failure → `DIRECTOR_BEAT_PLAN_ATTEMPT6_TEXT_INCOMPLETE`
- history 5 coverage failure → `DIRECTOR_BEAT_PLAN_ATTEMPT6_SOURCE_COVERAGE_INCOMPLETE`
- history 6 → `attempt-7`, with dynamic Attempt-7 statuses
- race from frozen count 5 to current count 6 → lineage conflict; no attempt-7 append and no Provider retry
- authorization ID is independent of attempt number

## Transport semantics

`call_llm(retries=1)` uses `attempt_budget=max(1, int(retries or 0))`, so the
Stage A canary budget is one actual HTTP attempt. It does not mean one initial
POST plus a retry.

## Attempt-6 preflight

- target: Book 990453 / Episode 1 / `E01_SC001` / Packet 64
- ledger before/after: `5 / 5`
- expected attempt: `attempt-6`
- source units: `12`
- schema: `director_beat_plan_ir_v1`
- execution boundary: `director_beat_plan_provider_request_v1`
- profile: `local-llm-2vydoz / openai-compatible / mimo-v2.5`
- identity consistency: `PASS`
- preflight/runtime parity: `PASS`
- Provider calls: `0`
- Stage B / IMAGE / VIDEO: `0`
- production authority writes: `0`
- Packet proposal: unchanged `{"decision":"awaiting_llm"}`

Prompt identity remains the V7.6.4 frozen identity because this phase changes
lineage handling only:

- system SHA256: `0d33e6805d856ec167ba6c6c9327f2942c6db159fd5edbacb3df0c16c25d12a7`
- user SHA256: `250d67053dd3ca95c8a698bc69f756986fb100eb3f83dbef857d4a9bc16744a4`
- prompt fingerprint: `ddf1662a8583a48d2347ac4e231c3ff27769679224ed1946069018effdbbc488`
- Provider Request Fingerprint V2: `3a73fc2e762e0572b810dfe2149c959356e8786148e040897839cba418f9cee4`

## Verification

- V7.6.5 + V7.6.4 + V7.6.2 + V7.6.1 + V7.2 + V7.1 + V7.4.1 focused tests: `100 passed`
- compileall: PASS
- `git diff --check`: PASS
- working tree: clean after push

Attempt-6 was not executed and Stage B was not entered.
