# Director Quality V2.4.3 Repository Audit

**Audit mode:** read-only repository and artifact audit  
**Audit date:** 2026-09-15  
**Repository:** `yeqing112/screenplay-agent-refactor-v2`  
**Branch:** `codex/unify-formal-workspace`  
**Audited HEAD:** `4fa18b7`  
**Scope:** V2.4.3 Targeted Tail Repair Value Re-evaluation preflight only. No provider, media, storage, CI, or production side effects were executed.

## 1. Inputs and frozen evidence

The audit inspected the following implementation modules:

- `core/director_tail_repair_executor.py`
- `core/director_tail_repair_acceptance.py`
- `core/director_tail_root_cause.py`
- `core/director_creative_value.py`
- `core/director_quality_validator.py`
- `core/director_overdirecting.py`
- `core/director_tail_repair_context.py`
- `core/director_tail_repair_ir.py`
- `core/director_tail_repair_ir_compiler.py`
- `core/director_patch_compiler.py`
- `core/director_patch_validator.py`
- `scripts/run_director_quality_v2_4_targeted_tail_pilot.py`

The frozen evidence inputs are:

- `artifacts/director-quality-v2-4-b2-freeze.json`
- `artifacts/director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json`
- `artifacts/director-quality-v2-4-1-targeted-tail-pilot-20260914T115313Z.json`
- `artifacts/director-quality-v2-4-metrics.json`
- `artifacts/director-quality-v2-4-1-repairability-matrix.json`
- `artifacts/director-quality-v2-3-phase-b2-evidence.json`

The B2 freeze contains 24 scenes. Its `tail_repair.triggered` flag selects exactly 15 scenes for the historical targeted pilot: 5 `approved_record` scenes and 10 fixture-origin scenes. The historical targeted artifacts contain 32 ranked root-cause rows in total; the executor and historical design cap execution at the first two roots per scene, which yields **27 frozen selected root causes**. V2.4.3 must therefore freeze 27, not recompute or expand to 32.

## 2. Audit findings

### A. Quality and value measurements

**Status: PARTIAL / BLOCKED for V2.4.3.**

- `run_targeted_tail_pilot()` computes deterministic DQ before and after with `score_director_quality()`.
- It computes target-dimension deltas from the repair executor's acceptance trace.
- It computes over-directing and shot-inflation before/after with `detect_over_directing()`.
- `evaluate_repair_acceptance()` checks contract, facts, structural blockers, target-dimension improvement, DQ regression, and available CV/over-directing/shot-inflation values.
- It does **not** replay Creative Value against the post-repair candidate. The runner sets `after_cv = before_cv`, `creative_value_delta = 0.0`, and `creative_value_measurement_status = "not_replayed_after_tail_repair"`.
- The executor reads `creative_value_after` / `creative_value_replay` only if the caller has already supplied them in the source record; it does not derive them from the frozen opportunities, eligibility, planner decisions, and candidate.

### B. CV after-value reuse or not-replayed path

**Confirmed.** The current runner explicitly reuses the before score and labels it `not_replayed_after_tail_repair`. This is a measurement placeholder, not a valid after-value measurement.

### C. Missing CV and accepted path

**Confirmed risk.** `evaluate_repair_acceptance()` only rejects CV regression when both values are non-null. If both values are missing, acceptance can still succeed when the other gates pass. The current executor can therefore accept a changed candidate without a measured after CV. V2.4.3 must make missing after-CV a `MEASUREMENT_BLOCKED` rollback for changed candidates.

### D. Deterministic replay feasibility

**Feasible with existing authoritative code.** `core/director_creative_value.py` already exposes:

- `evaluate_useful_creative_acceptance()`
- `evaluate_useful_creative_acceptance_v3()`
- `build_creative_value_score()`

These functions accept frozen opportunities, planner decisions, and intervention outcomes and are deterministic. No second scorer or judge LLM is required. V2.4.3 can replay by keeping the frozen opportunity/eligibility/decision/source evidence and replacing only the intervention outcome with the applied candidate's measured DQ and dimension deltas. The replay fingerprint can be derived from the frozen inputs plus candidate fingerprint.

### E. CV measurement versus no-regression semantics

**Current behavior is unsafe.** A missing CV is not distinguished from a measured unchanged CV by the acceptance function. V2.4.3 must distinguish at least:

- `ready` — valid deterministic replay;
- `unchanged` — replayed score equals before;
- `regressed` — replayed score is lower and must roll back;
- `MEASUREMENT_BLOCKED` — candidate changed but replay evidence is unavailable/invalid and must roll back.

### F. Exact 15-scene cohort and origin

The exact triggered cohort recovered from the B2 freeze and used by both historical targeted artifacts is:

**Approved-record cohort (5):**

1. `book990402:e1:红伞幻影（二）`
2. `book990402:e2:回声照相馆`
3. `book990402:e2:暗房门口的试探`
4. `book990402:e3:暗房惊魂`
5. `book990402:e3:暗房惊魂（2）`

Each is marked `scene.scene_type=approved_record` and `source=approved_treatment_scene_blocking`.

**Fixture cohort (10):**

1. `V21_FIXTURE_01`
2. `V21_FIXTURE_04`
3. `V21_FIXTURE_07`
4. `V21_FIXTURE_08`
5. `V21_FIXTURE_09`
6. `V21_FIXTURE_10`
7. `V21_FIXTURE_11`
8. `fixture:dialogue_power_shift`
9. `fixture:multi_character`
10. `fixture:prop_continuity`

The first seven are `offline_golden_fixture`; the last three are `existing_test_fixture` / `fixture_adapter`. They may be executed through the real MiMo provider when authorized, but must never be described as real production scenes.

### G. Root-cause recovery

**Recovered.** The historical targeted artifacts preserve ranked root causes for all 15 scenes. Applying the historical two-root cap gives 27 roots:

- 1, 3, 3, 3, 3 for the five approved records;
- 2, 2, 2, 1, 2, 1, 2 for `V21_FIXTURE_01/04/07/08/09/10/11`;
- 2, 2, 2 for the three fixture adapters.

The full ranked lists total 32, but the extra five are outside the frozen execution scope and must not be added in this run.

### H. Ranking stability and cohort drift

**Risk confirmed.** `execute_tail_repair()` calls `rank_tail_root_causes_v2()` on the runtime source record. Re-running that ranker can reorder or alter the historical cohort. V2.4.3 must pass an explicit frozen root list/manifest to the executor and must not use a fresh ranking to select experiment subjects. The ranker may be used only as a non-authoritative consistency check, with any mismatch reported as a preflight blocker.

### I. Freeze suitability

**Suitable after manifest creation.** The existing artifacts contain the required source candidate, contract, opportunity, eligibility, planner decision, target dimension and provenance material. A V2.4.3 manifest can freeze:

- scene ID, origin/source type;
- baseline and contract fingerprints;
- the first two historical root causes per scene, original rank, repair type, target dimensions;
- relevant opportunity/beat/shot IDs and allowed character IDs;
- source/evidence fingerprints.

The manifest must be generated from the existing B2 and targeted artifacts without creating a new baseline, opportunity set, or ranking.

## 3. Protocol and safety status

The V2.4.2c protocol safeguards remain present at audited HEAD: Semantic Spec SSOT, typed provider contract, collect-all diagnostics, `allowed_plan_shot_ids`, `allowed_character_ids`, provider request sanitization, `json_parse_retries=0`, and a two-attempt semantic budget. The targeted runner still reports zero production/storyboard/media/object-storage/production-shadow side effects.

The protocol is therefore not the V2.4.3 blocker. The blocker is value measurement and frozen-cohort execution semantics.

## 4. Audit decision

**`CREATIVE_VALUE_REPLAY_REQUIRED_BEFORE_REAL_PILOT`**

Real MiMo execution is not authorized by this audit. Before any real call, implement and test:

1. deterministic post-repair CV replay using `core/director_creative_value.py`;
2. fail-closed acceptance when a changed candidate lacks replay evidence;
3. frozen 15-scene / 27-root manifest and no re-ranking;
4. sequential root-cause attribution and rollback isolation;
5. provider-free tests for accepted, DQ/CV regression, non-target improvement rejection, and measurement blocking.

No historical baseline or B2 artifact should be modified.

## 5. Final As-Built Verification (2026-09-15)

The implementation described above was completed and verified locally. The
provider-free hard gate passed, then the authorized real MiMo targeted run used
the frozen manifest only:

- selected scenes: **15** (5 `approved_record`, 10 fixtures);
- selected / attempted root causes: **27 / 27**;
- semantic attempts / provider HTTP requests: **28 / 28**;
- JSON parser retries: **0**; transport retries: **0**;
- IR first-pass valid: **26/27 (96.30%)**; final IR valid: **27/27**;
- canonical compile: **27/27**; candidate contract pass: **27/27**;
- fact override accepted: **0**; request echo: **0**; unknown provider shape: **0**;
- deterministic Creative Value measurement status: **15/15 ready**;
- production, storyboard, media, object-storage and production-shadow side effects: **0**.

The result is **protocol-reliable but value-gate failing**. All 27 root repairs
were accepted by the local acceptance policy and all 15 scenes had replayable
CV, but the frozen-cohort value thresholds were not met:

- DQ mean delta **+6.75** (gate **≥+15**), median **+6.4** (gate **≥+10**);
- Creative Value mean delta **+11.5802** (gate **≥+15**);
- `<60` tail reduction **14.3%** (gate **≥50%**).

The approved-record cohort is reported separately (5/5 scene success, DQ mean
delta **+5.716**, CV mean delta **+5.435**) and is not substituted by fixture
results. Final status is **`NOT_READY_FOR_FULL_24_REEVALUATION`**; no Full24,
Production Shadow, storyboard, media or storage run was started.

Final artifacts:

- `artifacts/director-quality-v2-4-3-provider-free-preflight.json`
- `artifacts/director-quality-v2-4-3-targeted-tail-manifest.json`
- `artifacts/director-quality-v2-4-3-targeted-tail-pilot-real.json`
- `artifacts/director-quality-v2-4-3-metrics.json`
- `artifacts/director-quality-v2-4-3-report.md`
