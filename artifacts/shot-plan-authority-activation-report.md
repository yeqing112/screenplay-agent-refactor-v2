# ShotPlan Authority Activation Report

Stage: `SHOT_PLAN_AUTHORITY_CONTRACT`  
Provider policy: **0 external calls**  
Branch: `codex/shot-plan-authority-contract`

## Baseline Audit

Before this stage, production materialization selected an approved ShotPlan by
scene name and descending revision. That made an old approved row eligible even
when no explicit current authority existed, and it did not bind the plan to a
durable authority envelope.

## Final As-Built Verification

- Production ShotPlan activation now requires the current ScriptIR, current
  DirectorTreatment pointer, current SceneBlocking pointer and exact
  FactSnapshot lineage.
- Candidate validation preserves the approved `plan_shot_id` sequence exactly;
  it rejects add/delete/reorder and does not invent missing facts.
- Camera and duration defaults carry explicit provenance. Action beats are
  bounded by the duration preflight.
- Character and prop entry/exit state, screen direction and declared
  transitions are checked before activation.
- Prop continuity records now carry `prop_id`, `scene_id`, `shot_id`, entry /
  exit state, location, holder/owner, visibility, state variant, source,
  provenance and unresolved fields; asset bindings separately distinguish
  canonical identity, locked visual references and pending media.
- Activation creates `ShotPlanAuthority` and atomically swaps the per-scene
  `ShotPlanPointer`; the previous pointer target is retained as a rollback
  anchor and marked superseded.
- A legacy approved ShotPlan without a pointer fails closed with
  `SHOT_PLAN_POINTER_MISSING`; no automatic migration or latest-row fallback is
  performed.
- Storyboard materialization resolves only the current pointer, validates the
  authority envelope again, preserves the N-to-N shot mapping, and stores the
  complete authority envelope in the production upstream metadata.
- Production materialization does not call `StoryboardAgent.run()` and does
  not call any LLM, image, video or object-storage provider.

## Verification scope

The authority contract unit suite covers cardinality, unknown closure,
camera provenance, continuity, prop transitions and payload stability. The
SceneBlocking authority integration suite covers first activation, pointer
replacement, old-plan rejection and the reverse `StoryboardAgent.run()` call
count gate. Existing legacy materializer fixtures were updated to assert the
new fail-closed pointer requirement instead of the removed latest-approved
behavior.

Final local run evidence: ShotPlan/SceneBlocking authority and production gate
suite **30 passed**; deterministic Golden regression **5/5 passed**; full
backend run **1480 passed, 11 known baseline failures**. The remaining failures
are historical Director Quality artifact/database expectations and retired
provider-canary assertions; none enter this ShotPlan authority path. Frontend
Vitest/build could not start in this isolated worktree because `vitest` and
`tsc` are not installed in `web/node_modules`.

Known environment blocker: fresh-database migration `f05ab1af29bc` remains an
upstream repository blocker and was not modified in this stage.

## Scope boundary

No Prompt Compiler optimization, provider canary, asset generation, media
generation, GitHub Actions or historical artifact cleanup was performed.
