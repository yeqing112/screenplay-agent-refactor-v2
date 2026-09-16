# Director Quality V3 — Authorized Evaluation Source Upstream Phase A

**Status:** `DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED`

## Baseline Audit

- Attempt #1 remains immutable historical evidence: `36` facts, `0` verified, `36` invalid, ScriptIR `0`, exposure `EXPOSED`.
- Attempt #2 external runtime authorization froze execution base `854be82cd502cc919e58ffb2246683ddcebdc15c`; observed local and remote HEAD match it.
- Immutable source package: `SRC79f12d1b7f5eb828` / `SRC79f12d1b7f5eb828:V01:d001bab5cc82`; raw hash and provenance: `PASS`.

## Final As-Built Verification

- Provider/model: `openai-compatible` / `mimo-v2.5`; secrets omitted; no model switch.
- Predicted full Phase A calls: `2`; Attempt #2 authorized and executed calls: `1`; retries: `0`.
- FactSnapshot: `PASS` (`7` facts, `7` evidence verified, `0` invalid).
- ScriptIR: `NOT_AUTHORIZED_SCOPE`; Treatment, Blocking, Strategy, Spine, Topology, ShotPlan, Storyboard and media actions: `0`.
- Production DB and all production mutations: `0`; provider exposure: `EXPOSED`.

## Decision

`DIRECTOR_V3_FACT_ATTEMPT_2_CLOSED`

Lineage is `FACT_SNAPSHOT_CONFIRMED`. No ScriptIR or downstream processing is authorized by this Fact-only attempt; human review remains required before a separately authorized next stage.
