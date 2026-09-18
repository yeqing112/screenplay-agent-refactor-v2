# Storyboard Materializer Authority Activation Report

Stage: `STORYBOARD_MATERIALIZER_AUTHORITY_CONTRACT`  
Provider policy: **0 external calls**  
Branch: `codex/shot-plan-authority-contract`

## Baseline Audit

Before this stage, production materialization projected a ShotPlan directly
into `StoryboardShot` rows but also called the deterministic Prompt Compiler
and persisted verbalized prompt text in the same transaction. Current rows were
found by scene name and `meta_info` references; there was no versioned
materialization set or scene-level current pointer. Legacy rows could not be
reliably distinguished from production-authoritative rows.

## Final As-Built Verification

- `StoryboardMaterializationSet` is now the versioned projection artifact for a
  single current authoritative ShotPlan.
- `StoryboardMaterializationPointer` is the only production selection source;
  no scene-name/latest-row inference is used by the materializer.
- Each production row has explicit `scene_id`, `plan_shot_id`, materialization
  set id, ShotPlan id/revision/authority fingerprint and projection fingerprint.
- Projection authority is separated into `SHOT_PLAN_PROJECTION`,
  `STRUCTURAL_MATERIALIZATION_METADATA`, `COMPILER_OUTPUT`, `MEDIA_STATE` and
  `UNKNOWN_INVALID` classes.
- Strict production projection rejects missing camera, duration, action
  contract, purpose, entry/exit state, asset bindings, continuity contract or
  plan shot identity. It never applies creative defaults.
- N ShotPlan shots produce exactly N StoryboardShots in the same order. Add,
  delete, merge, split and reorder are not permitted.
- The set fingerprint binds the ShotPlan authority, upstream authority context,
  materializer version/policy and ordered projection payload.
- Repeating the same fresh authority input reuses the complete set and does not
  create duplicate rows. A changed ShotPlan pointer marks the old set and rows
  stale/superseded before a new set is activated.
- Existing rows without explicit production lineage fail closed with
  `LEGACY_STORYBOARD_MIGRATION_REQUIRED`; no association is guessed.
- A downstream resolver validates current ShotPlan lineage, set cardinality,
  row identity and projection hashes, returning `STORYBOARD_MATERIALIZATION_STALE`,
  `STORYBOARD_MATERIALIZATION_SET_INCOMPLETE` or
  `STORYBOARD_PROJECTION_TAMPERED` when required.
- Prompt Compiler output is excluded from projection authority. The only
  handoff stored is a downstream `storyboard_prompt_handoff_v1` containing
  immutable structural fields; prompt strings remain empty at materialization.
- Materialized rows remain `production_status=blocked`; media and visual asset
  readiness are downstream gates. Existing visual asset backlog is preserved.
- Production Materializer does not call `StoryboardAgent.run()` or any LLM,
  image, video, embedding or object-storage provider.

## Verification

- New strict authority suite + legacy materializer + production gate/readiness:
  **24 passed**.
- Storyboard/Prompt Compiler/structure regression subset: **47 passed**.
- Previous authority suites remain green: **25 passed** in SceneBlocking and
  **ShotPlan authority suites**.
- Full backend rerun after this stage: **1502 passed, 5 known historical
  baseline failures**. Those failures are retired Director Quality/provider
  canary expectations and are outside this materializer path:
  `test_director_quality_v24_offline_replay`,
  `test_director_quality_v3_final_spine_topology_preflight_wiring`, two
  `test_director_quality_v3_fresh_integration_pilot` cases, and
  `test_targeted_missing_fact_api`.
- Golden regression remains **5/5** from the previous authority stage.
- Frontend was not touched: `FRONTEND_NOT_TOUCHED`; previous isolated worktree
  lacked `vitest`/`tsc`, so no new frontend contract was introduced.
- Fresh database blocker `f05ab1af29bc` remains intentionally unchanged and is
  tracked for the independent `MIGRATION_CHAIN_HARDENING` stage.

## Scope Boundary

No PromptIR authority migration, Model Adapter work, visual asset generation,
provider canary, image/video generation, object storage call or historical
artifact cleanup was performed.

Completion marker: `STORYBOARD_MATERIALIZER_AUTHORITY_CONTRACT_READY`
