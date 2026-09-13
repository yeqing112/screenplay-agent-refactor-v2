# Director Quality V2.2.2 Final Report

## 1. Executive Summary

V2.2.2 completed the rejection-observability and evidence-driven-recovery loop on 12 frozen scenes. The final local state is safe to shadow from a contract/side-effect perspective, but not valuable enough to shadow for production quality. Rejection traces are complete and no unsupported recovery rule was registered.

## 2. Why V2.2.1 could not identify the 13 fallbacks

V2.2.1 only retained a `raw_digest` and a coarse `FORBIDDEN_PATH` fallback. It did not preserve the provider patch, raw path/selector, provider index, canonical path, allow-list result, or rejection stage. Consequently, a fallback could not be distinguished as a true forbidden field, safe envelope/alias, contract mismatch, compiler defect, or ambiguous case.

## 3. Rejection Trace Design

`core/director_rejection_trace.py` captures provider items immediately after JSON parsing and before normalization. Each completed trace contains a stable trace id, bounded raw evidence/fingerprint, provider index, shot identity or auxiliary anchor, raw/canonical path, resolution rule, allow-list result, stage, issue code, repair attempts, final action, and classification. Long text is bounded; prompt bodies, provider responses, API keys, and authorization headers are not persisted.

## 4. Raw Evidence Capture

The Observability artifact `artifacts/director-quality-v2-2-2-observability-pilot-20260913T174416Z.json` records 5 rejected events. Raw path, raw shot identity, and canonical path capture are each 100%. Auxiliary proposals are traced as their own JSON items and use the insertion anchor as shot identity evidence.

## 5. Rejection Stage Taxonomy

All observed events have an allowed stage (`LLM_REPAIR` or `CONTRACT_VALIDATION`); no `UNKNOWN` stage occurred. The implementation recognizes the complete V2.2.2 taxonomy: `RAW_PARSE`, `PATH_PARSE`, `PATH_RESOLUTION`, `ALLOWED_PATH_CHECK`, `VALUE_SCHEMA`, `CONTRACT_VALIDATION`, `PATCH_MERGE`, `DETERMINISTIC_REPAIR`, `LLM_REPAIR`, `QUALITY_VALIDATION`, and `FINAL_FALLBACK`.

## 6. Fallback Classification

Observability classification was 100% with `UNKNOWN root cause = 0`. The observed event set contained only `INVALID_VALUE` repairs in the Observability run. The later Recovery run observed two auxiliary schema violations and classified both as `TRUE_FORBIDDEN`; they remain fail-closed. `Fact Override Accepted = 0`.

## 7. Observability Pilot Result

- 12 scenes, `mimo-v2.5`, profile `local-llm-2vydoz`
- Rejection events/traces: 5/5
- Final fallback count: 0
- Final contract pass: 12/12
- Production, Storyboard, Media, Object Storage side effects: 0
- Production Shadow: OFF

## 8. Raw/canonical fallback analysis

The Observability-only run had no final fallbacks. Its five rejected items were S01, S03, S05, S07, and S09 in `book990402:e3:暗房惊魂（2）`; every raw and canonical path was `camera.shot_size`, allowed by contract, and classified `INVALID_VALUE`. Each was repaired successfully by the existing explicit LLM repair route.

The Recovery run produced two final fallbacks, both true auxiliary schema violations:

| trace_id | scene | provider index | raw path | canonical path | allowed | stage | issue | classification | action |
|---|---|---:|---|---|---|---|---|---|---|
| `rtrace_7ede22cb6b8fcb62cc6233a1` | `book990402:e3:暗房惊魂` | 6 | `auxiliary_shot_proposals[0].composition` | same | false | `CONTRACT_VALIDATION` | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | `TRUE_FORBIDDEN` | `FALLBACK` |
| `rtrace_96f58d1462af1b81c788336d` | `book990402:e3:暗房惊魂` | 7 | `auxiliary_shot_proposals[1].composition` | same | false | `CONTRACT_VALIDATION` | `DIRECTOR_PATCH_FIELD_FORBIDDEN` | `TRUE_FORBIDDEN` | `FALLBACK` |

No alias, envelope, contract-mismatch, or compiler-bug evidence was found. Therefore no recovery rule is safe to add.

## 9. Recovery Rule List and Evidence

The registry is intentionally empty. A rule requires a positive evidence count, an example raw path, canonical output, safety rationale, and a regression case. Registering an alias or expanding the auxiliary allow-list without evidence would violate the fail-closed contract.

## 10. Recovery Pilot Result

`artifacts/director-quality-v2-2-2-recovery-pilot-20260913T180409Z.json` ran the same 12-scene benchmark with the same model and no recovery rules. It produced 2 safe-required fallbacks, 0 avoidable technical fallbacks, 100% final contract pass, and 0 side effects.

## 11. V2.2.1 vs Observability vs Recovery

| Run | Fallbacks | Avoidable fallback rate | Creative retention | Full creative scene success | Director quality | Repair calls | Final contract pass |
|---|---:|---:|---:|---:|---:|---:|---:|
| V2.2.1 baseline | 13 | 100% (legacy classification) | 46.15% | 66.67% | 58.77 | 8 | 100% |
| V2.2.2 Observability-only | 0 | 0% | 52.56% | 100% | 59.65 | 6 | 100% |
| V2.2.2 Recovery | 2 | 0% | 54.76% | 91.67% | 58.41 | 9 | 100% |

The runs are real-model samples and therefore show expected output variance. The quality change is not attributed to a prompt strategy or weight change; this stage only adds evidence and preserves the existing repair contract.

## 12. Avoidable Technical Fallback

Only `SAFE_ALIAS`, `SAFE_ENVELOPE_VARIANT`, `CONTRACT_MISMATCH`, and `COMPILER_BUG` count as avoidable. The Recovery run has zero of these. `INVALID_VALUE` and `TRUE_FORBIDDEN` remain required fail-closed outcomes and are not counted as avoidable.

## 13. Creative Retention

Recovery retention is 54.76%, below the V2.2.2 reference target of 90%. No unsupported normalization was introduced to improve this number.

## 14. Full Creative Scene Success

Recovery full-scene success is 91.67%, above the 85% reference target. This does not override the lower creative-retention result.

## 15. Director 10-Dimension Quality

Recovery Director Quality is 58.41. The scorer and weights were not changed. Differences from V2.2.1/Observability reflect the sampled model output and repaired candidates only.

## 16. Repair Calls

Recovery used 9 LLM repair calls, all successful (`repair_success_rate = 100%`), with no production or media side effects. Repair remains explicit and bounded.

## 17. Cache / Latency (observation only)

Recovery cache hit rate was 87.25% and average latency 14,965.98 ms. These are telemetry only and were not used as correctness or safety gates.

## 18. SAFE_TO_SHADOW

**YES.** Final contract pass is 100%, Fact Override Accepted is 0, and Production/Storyboard/Media/Object Storage side effects are all 0. Production Shadow remains disabled.

## 19. VALUABLE_ENOUGH_TO_SHADOW

**NO.** Although avoidable fallback rate is 0% and full-scene success is 91.67%, creative retention is 54.76%, below the 90% reference threshold. Shadow must not be enabled on this evidence.

## 20. Current Top 3 Remaining Blockers

1. Creative retention is below the shadow-value threshold; additional improvements require new evidence and a separate quality phase.
2. True-forbidden auxiliary proposals still need human/model upstream compliance; they must remain fail-closed.
3. Real-model repair latency/cost remains material (9 repair calls, ~15 s average latency); this is an observation for a later phase, not a reason to weaken contracts or introduce unsupported cache parameters.

## 21. Scope and Safety Confirmation

No Production Pipeline V3, SceneBlocking, FactSnapshot, Materializer, Prompt Compiler, quality weights, Production Shadow, Stage B expansion, media generation, object storage, or CI workflow was changed or enabled. The final artifacts and code are local-only pilot evidence.
