# Phase J2.3 Final Report

## Result

`PHASE_J2_3_MEDIA_SCOPED_PROMPT_IR_IMPLEMENTATION_READY_FOR_REVIEW`

This round closes the Media Authority currentness fail open. Media validation and promotion now require one exact `(book, episode, storyboard shot, target_media)` PromptIR pointer, a valid PromptIRVersion payload hash, a valid PromptIRAuthority envelope, an exact generation policy fingerprint, and a fresh live Storyboard lineage comparison. Missing, stale, cross-media, scope-mismatched, policy-incomplete, or upstream-revised lineage fails closed before a validation or official-media row can be created.

## Correction evidence

- Previous reproduction: `before correction = reproduced`; a missing PromptIRPointer was treated as `matches=true` and currentness passed.
- Final behavior: `after correction = fail closed`; missing current pointer returns `MEDIA_CURRENT_PROMPT_IR_INVALID`, creates no `MediaValidationRecord`, and creates no OfficialMedia rows.
- Deleting the pointer after validation returns `MEDIA_PROMOTION_STALE`, marks the validation `STALE`, and creates no OfficialMediaVersion/Authority/Pointer.
- VIDEO execution with only an IMAGE pointer has no cross-media fallback. Pointer payload/scope mismatch and missing generation policy fingerprint also fail closed.
- Deterministic reproduction proved `stored integrity != live lineage`: a historical PromptIR remained byte-identical with `stale_status=FRESH`, while the current Storyboard materialization advanced. The old wrapper returned `current_lineage_valid=true`; the corrected shared read-only validator returns `integrity_valid=true`, `current_lineage_valid=false`, and `obsolete_due_to_upstream_change=true`.
- The same live comparison covers IMAGE and VIDEO independently. Upstream drift before validation fails closed; drift after a valid validation makes promotion return `MEDIA_PROMOTION_STALE`, marks the validation `STALE`, and creates no OfficialMedia rows.
- An unmarked PromptIR with no `source_authority` now fails closed. The only compatibility pass is an explicit `deterministic_media_fixture_v1` contract used by the provider-free Phase I fixture, so missing live lineage cannot be inferred from `FRESH` status.
- The Phase E current-scope validator and resolver now reject persisted lowercase `image`/`video`; only exact `IMAGE`/`VIDEO` are accepted. GenerationPolicy's separate normalization contract is unchanged.
- Provider, LLM, image, and video calls: 0. J3 was not started.

## Changed implementation and evidence

- `core/media_authority.py`: exact persisted media scope checks; shared current-scope PromptIR validation; fail-closed validation and promotion currentness checks.
- `core/prompt_ir_phase_e.py`: added the shared read-only live-lineage validator; `validate_prompt_ir_current_scope(...)` and `resolve_current_authoritative_prompt_ir(...)` both consume it, while historical integrity remains independent. `build_current_prompt_ir_asset_authority(...)` is the shared VisualAssetPointer/Version and VisualReferenceAuthority currentness service consumed by both PromptIR and Media Authority.
- `alembic/versions/b2c3d4e5f6g7_add_media_scoped_prompt_pointer.py`: migration hash helper frozen locally; no application runtime imports.
- `scripts/verify_migration_chain.py`: migration application-runtime import audit.
- `tests/test_media_currentness_fail_closed_regression.py`: missing pointer, stale promotion, cross-media fallback, and policy fingerprint regressions.
- `tests/test_j2_3_dual_media_currentness.py`: deterministic IMAGE/VIDEO upstream drift and historical-integrity-preserved regressions.
- `artifacts/e2e-production-pilot/phase_j2_3_media_currentness_fail_closed_audit.json`: provider-free audit packet.
- `artifacts/e2e-production-pilot/phase_j2_3_live_lineage_currentness_audit.json`: live-lineage correction and drift audit packet.

## Verification

- J2.3 targeted suite: passed, including media validation/promotion, fail-closed regressions, migration, dual-media currentness, concurrency, Phase I pilot, and PromptIR semantic closure tests.
- Migration gate: `MIGRATION_CHAIN_HARDENING_READY`; fresh and repeated upgrade passed; `migration_application_runtime_imports = 0`; fixed hash vector passed.
- Web: `web/npm test` — 51 files / 301 tests passed; `web/npm run build` — passed.
- Full backend final-head rerun on `ba1b7b2`: `1759 passed, 4 failed` (1763 collected). The J2.3 targeted suites and Phase I deterministic pilot are green. The four failures match the recorded baseline family and are outside this change: offline replay branch provenance; real-path historical recanary reason; active gray registry configuration; and targeted missing-fact snapshot mutation.
  - `tests/test_director_quality_v24_offline_replay.py::test_offline_replay_emits_provenance_reports_and_nonempty_gate_reasons` — expected branch `codex/unify-formal-workspace`, actual `codex/visual-authoring-provider-canary-reconcile`; baseline branch-provenance mismatch.
  - `tests/test_director_quality_v3_final_spine_topology_preflight_wiring.py::test_authorized_real_path_requires_entire_worktree_clean` — expected `WORKTREE_NOT_CLEAN_FOR_REAL_PROVIDER_RUN`, received `HISTORICAL_RECANARY_RETIRED`; baseline historical recanary gate mismatch.
  - `tests/test_director_quality_v3_fact_coverage_foundation.py`, `tests/test_director_quality_v3_fact_semantic_grounding.py`, and `tests/test_director_quality_v3_semantic_verifier_canary.py` — expected historical authority artifact fields are absent; baseline artifact shape mismatch.
  - `tests/test_real_llm_gray_selection.py::test_default_scope_uses_active_registry` — expected `[990400]`, actual `[990400, 990401]`; baseline active-registry configuration mismatch.
  - `tests/test_targeted_missing_fact_api.py::test_targeted_missing_fact_api_is_provider_free_and_fail_closed` — expected no FactSnapshot, found one; baseline targeted fact API mutation mismatch.
- Final targeted rerun after correction: J2.3 and related suites `64 passed`; Phase I pilot included; web `301 passed`.
- GitHub Actions: `NO_GITHUB_ACTIONS_RUN_FOR_FINAL_HEAD`.

## Boundary

J3 provider convergence, real media generation, and full production acceptance remain outside this phase. Production database migration was not run; migration verification used disposable SQLite databases only.
