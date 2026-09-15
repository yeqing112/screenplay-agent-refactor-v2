# Director Quality V3 — Strategy Approval Repair Adjudication

**Status:** `DIRECTOR_V3_STRATEGY_APPROVAL_REPAIR_ADJUDICATION_FAILED`

## Baseline Audit

- Source commit: `31ffb01`; raw responses: 3; prior result Canonical 0/3, Scope 1/3, Authority Unsafe 0/3.
- Historical raw responses and prior artifacts were not modified.

## Final As-Built Verification

- New MiMo/LLM calls: **0**; provider HTTP requests: **0**; transport retries: **0**; semantic retries: **0**.
- Raw fingerprints preserved: **yes**; program-owned metadata echo is deterministically stripped and compiler-owned values are recomputed.
- Canonical/Authority Safe/Registry Identity/Scope: 3/3, 3/3, 3/3, 2/3.
- Semantic Identity FAIL: 0; Future Support/Hint/Reveal: 0/0/0.
- Machine Director Approval: 2/3; Distinctiveness pairs: 3/3; all checked: True; hard template leakage: False.

## Per-scene adjudication

- `book990402:e3:暗房惊魂`: canonical=VALID, authority=SAFE, scope=PASS, direct=1, dependency=0, forbidden=0, semantic=PASS, approval=APPROVED
- `book990402:e3:暗房惊魂（2）`: canonical=VALID, authority=SAFE, scope=FAIL, direct=9, dependency=7, forbidden=3, semantic=PASS, approval=BLOCKED
- `book990402:e2:回声照相馆`: canonical=VALID, authority=SAFE, scope=PASS, direct=5, dependency=1, forbidden=0, semantic=PASS, approval=APPROVED

## Required observations

1. Scene 1 `beat:10` future support is removed by replay and remains at 0; scope is PASS.
2. Scene 2 wildcard matcher accepts every declared `performance[*].character_id` and `power.center_ref`; its remaining forbidden changes are unrelated beat hint/reveal edits and are retained.
3. Scene 2 authoritative identity remains `19=林晚`, `20=顾沉`; semantic audit is PASS.
4. Scene 3 `audience_state.suspects` is a declared dependency closure change; no unrelated frozen field remains.
5. Dependency closure is deterministic, declared per scene, and never dynamically expanded.
6. The replay does not alter raw responses, does not call MiMo, and does not require another call.

## Harness Corrections

- Ingress projection ignores only declared program-owned metadata; unknown creative fields remain protocol errors.
- Scope matching uses tokenized segments and supports `[*]`, named phases and numeric indexes.
- Dependency closure is deterministic and does not dynamically expand.
- Authority Safety is independent from Canonical validity.

## Decision

`READY_FOR_HUMAN_DIRECTOR_REVIEW=false`
`READY_FOR_SHOT_ARCHITECTURE_CANARY=false`
