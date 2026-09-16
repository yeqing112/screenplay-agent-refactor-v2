# Director Quality V3 — Authorized Evaluation Source Upstream Phase A

## Baseline Audit

- Authorized scope: `DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A`.
- Source: `SRC79f12d1b7f5eb828` / `SRC79f12d1b7f5eb828:V01:d001bab5cc82` (`《门外那把伞》`).
- Authorized execution base: `d4e65554a6ab366aa43f877f707849f28110d2f7`.
- Runtime authorization was external, scope-bound, and validated before dispatch; no tracked authorization file was used.
- Historical Spine → Topology re-canary remains retired and is not executable.

## Final As-Built Verification

- Provider/model: `openai-compatible` / `mimo-v2.5` (MiMo); no model switch.
- Fact Extraction dispatch attempts: `1` of `1` allowed; ScriptIR dispatch attempts: `0` of `1` allowed.
- Total real provider attempts: `1`; transport retries, repair calls, fallback calls, critic calls and judge calls: `0`.
- Provider exposure: `EXPOSED` because a real dispatch attempt was made, regardless of validation outcome.
- Fact response was received and retained locally; canonical validation failed with `36` invalid source-evidence records. No FactSnapshot was promoted.
- Fail-closed boundary held: ScriptIR was not dispatched after Fact validation failure.
- Production DB, Book/Scene/FactSnapshot/ScriptIR mutations, Human Fresh Pool, Treatment, Blocking, Strategy, Spine, Skeleton, Topology, ShotPlan, Storyboard and media actions: `0`.

## Decision

`DIRECTOR_V3_AUTHORIZED_EVALUATION_UPSTREAM_PHASE_A_FAILED`

Lineage remains `SOURCE_ACCEPTED`; no Treatment processing is authorized. Human review remains `NOT_RECORDED`. No further provider call is authorized by this run; a new explicit authorization is required for any future attempt.
