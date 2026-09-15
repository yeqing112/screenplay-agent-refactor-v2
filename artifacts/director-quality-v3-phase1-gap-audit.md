# Director Quality V3 Phase 1 — Gap Audit

## Baseline Audit

The V3 Foundation manifest used an untyped approved-record projection for Treatment and Blocking.

## Phase 1 resolution

- Provenance diagnosis: `historical_manifest_projection_collision_only`.
- Actual wiring error: `False`.
- Treatment and Blocking are independently projected and typed-hashed; historical artifacts are unchanged.
- The three fixed scenes remain exactly the approved_record cohort in the Foundation manifest.

## Canary boundary

Only SceneDirectingStrategy is sent to MiMo. No ShotPlan, baseline shot decisions, repair answer, media or storage input is sent.

## Final As-Built Verification

Provider-free checks: `PASS`; real calls before authorization: `0`.
