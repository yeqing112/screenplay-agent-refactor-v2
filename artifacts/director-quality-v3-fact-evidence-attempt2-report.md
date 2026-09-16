# Director Quality V3 — Fact Evidence Authority V2 — Attempt #2

## Baseline Audit

- Attempt #1 remains immutable: execution base `d4e65554a6ab366aa43f877f707849f28110d2f7`, `36` facts, `0` verified, `36` invalid, ScriptIR `0`, exposure `EXPOSED`.
- V2 execution base: `854be82cd502cc919e58ffb2246683ddcebdc15c`; scope-bound authorization `director-v3-fact-attempt-2-854be82`.
- Source package/version: `SRC79f12d1b7f5eb828` / `SRC79f12d1b7f5eb828:V01:d001bab5cc82`; raw hash and provenance verified.

## Final As-Built Verification

- Provider/model: `openai-compatible` / `mimo-v2.5` (MiMo); no model switch.
- Exactly one real provider call was dispatched; retries, repair, fallback, critic and judge calls: `0`.
- Request task: `extract_source_grounded_facts_v2`; deterministic source blocks: `347`; source evidence index fingerprint: `4697f3069bb34c9650d97b7e2c788d5b9db36034a39fedf77a0756e7a7bf5295`.
- Full source text duplicated in request: `NO`; provider was restricted to `evidence_refs` and could not author offsets, excerpts, authority, status or fact IDs.
- FactSnapshot validation: **PASS**; facts: `7`; confirmed: `7`; evidence verified: `7`; evidence invalid: `0`.
- ScriptIR calls: `0` (not authorized in this scope); Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.
- Production DB and all production mutations: `0`.

## Decision

`DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED`

V2 FactSnapshot passed deterministic evidence resolution. Attempt #1 remains historical failure evidence and is not rewritten. No ScriptIR or downstream processing is authorized by this attempt; any future provider call requires a new explicit authorization.
