# Director Quality V3 — Fresh Integration Pilot

**Final status:** `DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED`

## Baseline Audit

- Authorization document baseline: `eea7a86`; the clean execution base was its descendant `a31bdd1` (ancestry verified).
- Authority & Contract SSOT: `CLOSED`; Provider/Validator parity and Provider Readiness: `PASS`.
- Historical three-scene cohort remained retired and enforced. No historical raw, Spine, Topology, fixture, synthetic or Golden-only scene was used as a selected candidate.
- Fresh selection was provider-free and deterministic (`fresh_scene_complexity_v1`); no exposure-unknown candidate was selected.

## Frozen Fresh Cohort

| Cohort role | Scene | Complexity |
|---|---|---:|
| Low | `book990402:e1:红伞幻影（一）` | 43 |
| Medium | `book990402:e1:红伞幻影（二）` | 57 |
| High | `book990402:e2:暗房门口的试探` | 60 |

Candidate count was `3`; excluded retired count was `3`; excluded exposed/unknown/incomplete counts were `0/0/0`. Cohort fingerprint: `dafee06b86a26ef3290177e1f4d9654c1db49c38a89758c289a53bed8f330d8e`. The cohort was frozen before provider execution and was never replaced.

## Upstream and Contract Gates

- Real approved-record inputs: `3/3`.
- FactSnapshot valid: `3/3`; Qualified ScriptIR: `3/3`; Approved DirectorTreatment: `3/3`; Approved SceneBlocking: `3/3`.
- Strategy / Preserve / Spine / Skeleton contracts were assembled from the SSOT; schema, enum, forbidden-field and provider/validator parity preflight passed.
- Identity projections were authoritative and bound to the runtime validator; no legacy identity fallback was used.

## Provider Accounting

| Layer | Calls | Result |
|---|---:|---|
| Strategy | 3 | all returned provider responses; all failed authority completeness |
| Spine | 0 | fail-closed downstream skip |
| Skeleton | 0 | fail-closed downstream skip |
| Total | 3 | within maximum 9 |

All retry counters were zero: transport, format, semantic, creative and repair. Raw request/response evidence is stored per scene with fingerprints and was not overwritten.

## Scene Results and Failure Adjudication

All three selected scenes are `MODEL_FAILURE` at the same layer: `STRATEGY_AUTHORITY_INCOMPLETE`. The model produced protocol-shaped Strategy output, but its `must_preserve` intents were natural-language-only and lacked resolvable beat/event/source bindings. The deterministic resolver therefore produced unresolved Preserve constraints and the Authority Completeness Gate stopped each scene before Spine.

Structured Preserve counts were Low `5` (5 unresolved), Medium `10` (10 unresolved), High `4` (4 unresolved). This is a model-output/authority-data failure, not a Harness Failure. No automatic retry, repair, best-of-N, provider critic call or cohort replacement occurred.

## Machine Gate and Side Effects

- Strategy protocol 3/3: `FAIL` (authority gate blocked all three).
- Spine protocol, Skeleton protocol, Binder: `0` calls / not reached.
- Distinctiveness check: `PASS`; retries-zero: `PASS`; harness-errors-zero: `PASS`; budget: `PASS`.
- Atomic Expansion calls: `0`; Production ShotPlan: `HOLD`; Storyboard/Image/Video/Media/Storage/CI: `0`.
- Human Preference: `NOT_RECORDED`; External Director Critic review: pending.

## Decision

`DIRECTOR_V3_FRESH_INTEGRATION_PILOT_FAILED`

The failure is recorded without retry. The next action is external review of the frozen raw evidence and the missing structured Preserve bindings; this Pilot must not automatically advance to Strategy Repair, a second Fresh batch, Spine/Skeleton repair, Atomic Expansion, ShotPlan or media production.
