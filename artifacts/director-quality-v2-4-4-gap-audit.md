# Director Quality V2.4.4 — Gap Audit

## Baseline Audit

- Repository HEAD: `692dddb1bef3db376388bbcff8fccb3c98db3707`
- Frozen cohort: 15 scenes (5 approved_record, 10 fixture), 27 frozen roots.
- Scorer dimensions and weights are read directly from `core/director_quality_validator.py`; no scorer changes were made.
- Frozen V2.4.3 artifacts were read-only inputs.

## Final As-Built Verification

# Director Quality V2.4.4 — Repair Value Ceiling & Strategy Audit

Generated: `2026-09-14T19:25:13.856828+00:00`

## Status

`VALUE_CEILING_AUDIT_COMPLETE`

Provider-free deterministic audit. Real MiMo/LLM/image/video/storage/CI calls: **0**.

## Baseline and ceiling results

- Actual DQ mean delta: **6.75**; median: **6.4**.
- Current Top-2 ceiling mean delta: **8.466**; median delta: **8.4**; median ceiling score: **56.2**.
- Current Top-2 reaches the +15 mean gate: **no**; reaches the +10 median-delta gate: **no**.
- Current Top-2 tail reduction: **0.2143** (50% gate: **no**).
- All-known-roots uplift over Top-2: **1.9153**; excluded historical roots: **5** (expected 5).
- Value-priority Top-2 uplift over historical Top-2: **0.9753**.
- Coordinated Top-2 uplift over sequential Top-2: **0.0**.
- Scene upper-bound mean delta: **34.6607**.

## Approved-record gap

Approved scenes: **5**; historical V2.4.3 safe acceptance: **5/5**, meaningful uplift: **0/5**, tail: **4 → 4**. Actual DQ delta mean: **5.716**; Top-2 ceiling mean delta: **7.69**.
The approved-record gap is reported as evidence; no acceptance rule or historical artifact is modified.

## Sensitivity

SCORER_SENSITIVITY_GAP: **no**; insensitive field count: **0**.
CV ceiling: `CV_CEILING_NOT_MEASURABLE` (synthetic interventions have no authoritative outcome evidence).
Diagnostic flags: `CV_CEILING_NOT_MEASURABLE, CURRENT_LOCAL_REPAIR_CANNOT_MEET_TAIL_GATE`.
SCORER_INSENSITIVE_FIELD: **no**; ROOT_CAUSE_ALREADY_SATURATED: **no**; TOP2_ROOT_CAP_LIMIT: **no**.
ROOT_CAUSE_PRIORITY_GAP: **no**; COORDINATED_SCENE_REPAIR_OPPORTUNITY: **no**; APPROVED_RECORD_COMPLEXITY_GAP: **yes**.
MiMo actual/Top-2 efficiency **0.7973**; evidence is insufficient to label MODEL_CREATIVE_VALUE_GAP (realization is close to ceiling).

## Route decision

Primary recommendation: **V2.4.5A**; secondary: **REPAIR_SCOPE_LIMITED**.
Evidence: `{"actual_over_top2_efficiency": 0.7973, "all_roots_uplift_over_top2": 1.9153, "coordinated_uplift_over_top2": 0.0, "current_top2_mean_delta": 8.466, "sensitivity_gap_count": 0, "value_priority_uplift_over_top2": 0.9753}`.

## Guardrails

No shot was added, deleted, split, merged or reordered. Immutable facts, participants, events, assets, chronology and continuity fields were preserved and validated for every synthetic candidate.

