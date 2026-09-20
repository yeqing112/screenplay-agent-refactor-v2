# PHASE D FINAL REPORT

## 1. Scope and delivery

- Phase: `PHASE_D_STORYBOARD_MATERIALIZATION_AND_VISUAL_SEMANTIC_CLOSURE`
- Starting HEAD: `22553f24fe245ceec1a8b59fa8c1d9a9dd0282a2`
- Implementation commit: `bdebe75` (`Run Phase D through real storyboard production materialization`)
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Production pilot: temporary SQLite database migrated through Alembic; no
  provider, PromptIR compiler, image generation or video generation.
- Implementation changes: `core/storyboard_materializer.py`,
  `scripts/run_phase_b_director_blocking_pilot.py`, and
  `scripts/phase_d_real_materialization.py`.

## 2. Gap audit and authority classes

The gap audit is in `phase_d_storyboard_materialization_gap_audit.md`.
Storyboard uses these classes only:

- `SHOT_PLAN_PROJECTION`
- `PRODUCTION_CONTINUITY_STATE`
- `ASSET_IDENTITY_BINDING`
- `STRUCTURAL_MATERIALIZATION_METADATA`
- `DOWNSTREAM_HANDOFF_METADATA`
- `MEDIA_STATE`
- `UNKNOWN_INVALID`

`STORYBOARD_CREATIVE_DECISION` was not introduced. Storyboard remains a
deterministic projection of the current ShotPlan and Blocking authorities.

## 3. MaterializationSet and Pointer contract

`StoryboardMaterializationSet` is an immutable materialization version. Its
fingerprint binds the current ShotPlan, Treatment, Blocking, handoff schema and
fingerprints, exact count, exact ordered `plan_shot_id` values and every
projection payload. Upstream changes create a new explicit materialization;
the previous Set and rows become `STALE`.

`StoryboardMaterializationPointer` is the only Production current selector.
The resolver does not use `latest()`, timestamps, `max(id)` or a fallback Set.

## 4. Resolver revalidation

`resolve_current_authoritative_materialization()` revalidates:

- current ShotPlan Authority and `phase_c_semantic_ready`;
- current Blocking Authority and Treatment lineage;
- authority envelope and `storyboard_handoff_v1` fingerprints;
- Set fingerprint, count and exact order;
- mutable StoryboardShot columns against the protected projection payload;
- per-row projection fingerprints and source authority fingerprints;
- structured visual semantic handoff and asset identity bindings;
- empty Phase D prompt fields.

Tamper is detected, persisted as stale and returned as HTTP `409`. It is not
repaired in place.

## 5. Real Production materialization identity evidence

The trace is `episode_01_phase_d_trace.json`. It records persisted database
identity from the real materialization API:

| Scene | Canonical | Handoff | Materialized | Set ID | Pointer ID | StoryboardShot IDs |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `E01_SC001` | 8 | 8 | 8 | 1 | 1 | 1–8 |
| `E01_SC002` | 7 | 7 | 7 | 2 | 2 | 9–15 |
| **Total** | **15** | **15** | **15** |  |  | **15 rows** |

Both scenes resolved successfully with `readiness=true`; exact
`plan_shot_id` order is preserved. The trace contains the ShotPlan Authority,
ShotPlan Pointer, Blocking Authority, Blocking Pointer, Set, Storyboard Pointer,
StoryboardShot IDs, handoff fingerprint, projection fingerprints and semantic
fingerprints.

## 6. Visual semantic projection

`storyboard_visual_semantic_handoff_v1` is structured and prompt-free. Each
shot preserves:

- beat, DirectorDecision, requirement, information, reaction and coverage refs;
- subject, prop and canonical scene/character/prop asset identities;
- camera framing, orientation, support, movement and movement conditions;
- duration mode, cut trigger, duration hint, continuous-take and cut events;
- information visibility;
- axis ref(s), policy, applicability, screen sides and look direction;
- Blocking state refs, entry/exit refs and subject zones;
- projection provenance and semantic fingerprint.

`compare_shotplan_storyboard_semantics()` compares only structured IDs, refs and
enum-like values. Missing and extra semantics, camera mismatch, continuity
mismatch and asset-binding mismatch are hard-gated before writes.

## 7. Asset and media boundary

Asset gates cover only identities explicitly required by ShotPlan. No reference
image or visual variant is selected. `visual_prompt_static`,
`visual_prompt_motion` and `visual_prompt_final` are empty for all 15 rows;
direct mutation returns `STORYBOARD_PROMPT_PREMATURE_MUTATION`.
Media state remains `NOT_GENERATED`.

## 8. Atomicity, idempotency and negative evidence

The real temporary-DB trace records these cases, each restored from a valid
baseline before mutation:

- repeated materialization: same Set, same Pointer, no duplicate rows;
- failed materialization with `confirmed=false`: zero Storyboard writes and
  Pointer unchanged;
- ShotPlan Pointer change and Blocking Pointer change: current Set stale, 409;
- projection column tamper: `STORYBOARD_PROJECTION_TAMPERED`, stale Set;
- handoff and Set fingerprint tamper: 409, stale Set;
- missing, extra and reordered shot: `STORYBOARD_MATERIALIZATION_SET_INCOMPLETE`;
- information, reaction, camera, axis and asset semantic mismatch: structured
  semantic mismatch, stale Set;
- premature prompt mutation: `STORYBOARD_PROMPT_PREMATURE_MUTATION`.

The pilot proves failed candidates do not move the current Pointer and that no
partial materialization is accepted.

## 9. Artifacts

- `phase_d_storyboard_materialization_gap_audit.md`
- `episode_01_storyboard_phase_d.json`
- `episode_01_storyboard_phase_d.md`
- `episode_01_storyboard_visual_semantic_handoff.json`
- `episode_01_phase_d_trace.json`
- `PHASE_D_FINAL_REPORT.md`

## 10. Verification

- Real Phase D pilot: PASS, 2 scenes, 15 persisted StoryboardShot rows.
- Phase D / authority / resolver targeted tests: `41 passed`.
- Storyboard, PromptIR and visual authority regression set: `213 passed`.
- Deterministic Golden regression: `5/5 passed`.
- Full backend: `1604 passed, 4 failed, 930 warnings`.
- The four failures are unchanged historical baseline failures:
  `test_director_quality_v24_offline_replay`,
  `test_director_quality_v3_final_spine_topology_preflight_wiring`,
  `test_real_llm_gray_selection`, and
  `test_targeted_missing_fact_api`.
- Phase-D-induced failures: `0` relative to the recorded baseline.
- `REAL_REGRESSION=0`.

## 11. Migration and heuristic audit

- Database migrations added: `0`.
- Provider calls: `0`.
- Raw Authority fabrication in the pilot: `0`.
- No latest/max/fallback resolver path.
- No prompt prose, keyword, regex, text-similarity or quality-score gate.
- PromptIR compiler, Flux adapter, image generation and video generation were
  not started.

## Completion token

`PHASE_D_STORYBOARD_MATERIALIZATION_AND_VISUAL_SEMANTIC_CLOSURE_READY_FOR_REVIEW`

## 12. Materialization Reuse & Stale Immutability

- `validate_current_materialization_authority()` is the pure canonical validator shared by the resolver and Production reuse path; callers decide whether an invalid result should mark the Set stale.
- Untouched FRESH Sets reuse the same Set and Pointer IDs with no duplicate StoryboardShot rows; the real pilot records `reused=true` for both scenes.
- Semantic, prompt, projection-column, authority-envelope/handoff and Set-fingerprint tampering all fail closed with HTTP `409` and persist the Set as `STALE`.
- A resolver-staled Set cannot transition back to `FRESH` and cannot trigger an automatic replacement Set with the same fingerprint; the real pilot records `STORYBOARD_MATERIALIZATION_STALE` and unchanged Set count.
- Pointer recovery is permitted only for a complete, fully revalidated, never-stale FRESH Set; no Set fields or rows are rewritten. A tampered Set with its Pointer deleted fails closed and is not reattached.
- Evidence: `phase_d_materialization_reuse_audit.json`, `episode_01_phase_d_trace.json`, and `tests/test_storyboard_phase_d_reuse_stale_closure.py`.
- Provider calls: `0`; PromptIR/image/video generation: not started; migrations added: `0`.

## 13. Verification update

- Reuse/stale closure regression: `5 passed`; combined Phase D targeted regression: `18 passed`.
- Existing Phase D semantic/materializer regression: `13 passed`.
- Real Production pilot: PASS; Scene 1 `8` shots, Scene 2 `7` shots; direct materialization tamper cases all HTTP `409`.

## Completion token

`PHASE_D_MATERIALIZATION_REUSE_AND_STALE_REACTIVATION_CLOSURE_READY_FOR_REVIEW`

- Full backend rerun: `1609 passed, 4 failed, 930 warnings`; the same four historical failures remain unchanged: `test_director_quality_v24_offline_replay`, `test_director_quality_v3_final_spine_topology_preflight_wiring`, `test_real_llm_gray_selection`, and `test_targeted_missing_fact_api`.

## 14. Delivery metadata

- Continuation starting HEAD: `d385eb5`.
- Implementation commit: `9b6ca1eb90aec5b177e96eb6cdb235ce92068903`.
- Branch: `codex/visual-authoring-provider-canary-reconcile`.
- GitHub Actions run: none observed; verification source: local clean full-suite rerun.
- Final remote HEAD is recorded after the report commit is pushed.
