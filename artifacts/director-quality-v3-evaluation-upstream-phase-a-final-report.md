# Director Quality V3 — Fact Evidence Authority V2 — Attempt #2 Final Report

## Baseline Audit

- Attempt #1 is preserved unchanged as historical evidence: execution base `d4e65554a6ab366aa43f877f707849f28110d2f7`, `36` facts, `0` verified, `36` invalid, ScriptIR `0`, exposure `EXPOSED`.
- Attempt #2 authorized execution base: `854be82cd502cc919e58ffb2246683ddcebdc15c`; source `SRC79f12d1b7f5eb828` / `SRC79f12d1b7f5eb828:V01:d001bab5cc82`.
- Attempt #2 used the V2 evidence-ref contract and the currently resolved MiMo profile `openai-compatible / mimo-v2.5`; no model switch.

## Final As-Built Verification

- Real provider calls: `1` of `1` allowed; retries and all repair/fallback/critic/judge calls: `0`.
- FactSnapshot: `PASS`; `7` facts, `7` confirmed, `7` evidence references verified, `0` invalid.
- ScriptIR: `0` calls (`NOT_AUTHORIZED_SCOPE`); Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.
- Production DB and production mutations: `0`.
- Provider exposure: `EXPOSED`; request/response and dispatch ledger are retained under the isolated evaluation namespace.

## Decision

`DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED`

The V2 FactSnapshot is deterministically qualified. This does not authorize ScriptIR or any downstream processing; human review remains required before a separately authorized next stage. No further provider call is authorized by this attempt.
