# Phase A Test Fixture Contract Migration Report

## Results

- Baseline at `e6e9b85`: 1516 passed, 35 failed, 926 warnings.
- Contract migration run: all targeted Production authority/downstream fixture failures passed after migration.
- Final full backend: 1549 passed, 4 failed, 928 warnings.
- Golden regression: 5/5 passed.

## Failure classification

### `NEW_CONTRACT_FIXTURE_MIGRATED`

The Production authority, DirectorTreatment, SceneBlocking, ShotPlan, Storyboard materializer, ScriptIR Authority, and compiler integration fixtures were old payloads containing only beats/dialogues or empty scenes. They now use `tests/script_fixtures.py::build_explicit_production_script_payload()`, which constructs raw input with explicit `script_blocks` and `timeline_origin=EXPLICIT`; `build_script_ir()` derives `production_eligible=true`.

32 contract-related fixture candidates were migrated. The migrated fixture set is recorded in `phase-a-test-fixture-contract-migration-audit.json`. No normalized payload is mutated after build, and no gate or authority function is mocked.

### `TRUE_PRE_EXISTING_FAILURE`

The four remaining failures are unrelated to the Phase A timeline contract:

1. `tests/test_director_quality_v24_offline_replay.py::test_offline_replay_emits_provenance_reports_and_nonempty_gate_reasons`
2. `tests/test_director_quality_v3_final_spine_topology_preflight_wiring.py::test_authorized_real_path_requires_entire_worktree_clean`
3. `tests/test_real_llm_gray_selection.py::test_default_scope_uses_active_registry`
4. `tests/test_targeted_missing_fact_api.py::test_targeted_missing_fact_api_is_provider_free_and_fail_closed`

No Phase A business file was changed to mask these failures.

### `REAL_REGRESSION`

None identified.

## Negative contract coverage retained

Missing timeline, inferred timeline, invalid order, missing ref, duplicate order, and invalid type tests remain in `tests/test_script_timeline_fail_closed.py` and continue to assert fail-closed behavior.

## Scope

- Business code changed: no.
- Frontend: `frontend_not_touched`.
- Migration: no database schema change; no Alembic migration.
- Unrelated working-tree changes: the five pre-existing `artifacts/migration-*` audit files remain local and are excluded from this commit.
- Phase B: not started.

