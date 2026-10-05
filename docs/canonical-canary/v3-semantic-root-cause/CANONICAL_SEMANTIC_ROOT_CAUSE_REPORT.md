# Canonical Semantic Root Cause Report V3

Run: `20261005T095639Z`

## Final state

`CODE_BUG_FIXED_RECANARY_REQUIRED`

## Answers

### 1. Why are canonical subjects empty?

All `20` current rows retain source participant evidence, and SceneBlocking participants are populated, but the production preview compiled an empty `initial_state.characters`. The state snapshots were therefore empty; Phase C then read empty beat characters/participants and emitted no ShotPlan subjects. The Storyboard visual semantic handoff and canonical projection correctly propagated those empty ShotPlan values.

### 2. Why is canonical dialogue empty?

The current source and ScriptIR contain no structured dialogue (`SOURCE_DIALOGUE_EMPTY` on `20` rows). No dialogue was lost at Storyboard projection; there was no authoritative dialogue to propagate. Historical prompt text was not used.

### 3. Cause type

The character path has a deterministic upstream hydration defect at `api/scene_blocking_api.py:292`; this is fixed by `initial_state_from_participants`. The dialogue path is source absence. Current rows are current materializations, not legacy stale rows.

### 4. Exact boundary

`SceneBlocking.participants` → production preview `initial_state` → `compile_blocking_states()` → Phase C `subjects`.

### 5. canonical_asset_identity

The nested identity object is structurally present in all 20 rows but has empty `characters` and `props` arrays, with the scene identity present. It is readiness metadata, not semantic truth, and was not used to manufacture subjects.

### 6. Are the 20 rows legacy/stale?

No. They point to current materialization sets using `storyboard_materializer_v2` and `storyboard_visual_semantic_handoff_v1`; they are semantically incomplete current rows, not legacy rows requiring a blind cleanup.

### 7. Legitimate production source?

`NO_PRODUCTION_SOURCE_WITH_USEFUL_SEMANTICS`. Book 990402 has useful ScriptIR participant/dialogue data, but it has no explicit production provenance and remains ineligible. No other current source meets the people-plus-dialogue minimum.

### 8. Can an existing production row become a valid person + dialogue IMAGE→VIDEO canary?

No. A safe rematerialization can recover the declared single subject from the patched path, but it cannot create dialogue absent from source. No current production-provenanced row has the required two-person dialogue semantics.

### 9. Code repair, rematerialization, or new source?

Code repair is required for participant hydration. A separately authorized dry-run rematerialization is required for affected current rows. New explicitly production-provenanced source material with actual dialogue is required before canary selection.

### 10. Safest next action

Keep production database unchanged; use the patched provider-free hydration path for a new explicitly production-provenanced source with actual dialogue, then run a separately authorized dry-run rematerialization before any write.

## Row root-cause counts

- `SHOT_SEMANTIC_HYDRATION_NOT_RUN`: `20`

## External-call and production-write counters

- Real IMAGE: `0`
- Real VIDEO: `0`
- External LLM: `0`
- SHAPI: `0`
- Poyo: `0`
- 75API IMAGE POST: `0`
- 75API VIDEO POST: `0`
- PromptIR writes: `0`
- Media writes: `0`
- OfficialMedia writes: `0`
- GenerationExecution production writes: `0`

## Evidence

- `CANONICAL_SEMANTIC_LINEAGE_MAP.md` / `.json`
- `CANONICAL_ROW_SEMANTIC_ROOT_CAUSE_AUDIT.json`
- `PRODUCTION_SEMANTIC_SOURCE_CANDIDATE_AUDIT.json`
- `CANONICAL_SEMANTIC_REMATERIALIZATION_DRY_RUN_PLAN.md`
