# Director Quality V2.2.2 Rejection Analysis

## Evidence source

- Observability artifact: `artifacts/director-quality-v2-2-2-observability-pilot-20260913T174416Z.json`
- Frozen run: 12 approved scenes, profile `local-llm-2vydoz` (`mimo-v2.5`)
- Side effects: production rows 0, storyboard shots 0, media calls 0, object-storage calls 0

## Observability result

| Metric | Result |
|---|---:|
| Rejected events | 5 |
| Rejection trace coverage | 100% |
| Raw path capture | 100% |
| Raw shot identity capture | 100% |
| Canonical path capture | 100% |
| Rejection stage identified | 100% |
| Fallback classification | 100% |
| UNKNOWN root cause | 0 |
| Fact Override accepted | 0 |

The run produced **no final fallback**. All five rejected patches were accepted by the existing Level-2 repair path. Therefore the five rejection events below are listed for audit completeness, but none is a fallback candidate for recovery.

## Item-by-item evidence

All rows belong to scene `book990402:e3:暗房惊魂（2）` (episode 3), and use the same validated contract.

| trace_id | provider index | shot | raw path | canonical path | allowed | stage | issue | classification | final action | safe recovery? |
|---|---:|---|---|---|---|---|---|---|---|---|
| `rtrace_5c9a2d395a965b45783dc1a4` | 0 | S01 | `camera.shot_size` | `camera.shot_size` | true | `LLM_REPAIR` | `INVALID_PATCH_VALUE` | `INVALID_VALUE` | `REPAIR` | No new deterministic rule |
| `rtrace_897a900c5d9f0016979f5a36` | 1 | S03 | `camera.shot_size` | `camera.shot_size` | true | `LLM_REPAIR` | `INVALID_PATCH_VALUE` | `INVALID_VALUE` | `REPAIR` | No new deterministic rule |
| `rtrace_87d9bc991ed4f6f4dd0497d7` | 2 | S05 | `camera.shot_size` | `camera.shot_size` | true | `LLM_REPAIR` | `INVALID_PATCH_VALUE` | `INVALID_VALUE` | `REPAIR` | No new deterministic rule |
| `rtrace_f8a21cb6b254d3811ee4a078` | 3 | S07 | `camera.shot_size` | `camera.shot_size` | true | `LLM_REPAIR` | `INVALID_PATCH_VALUE` | `INVALID_VALUE` | `REPAIR` | No new deterministic rule |
| `rtrace_211698dd5fad6add21b97e8b` | 4 | S09 | `camera.shot_size` | `camera.shot_size` | true | `LLM_REPAIR` | `INVALID_PATCH_VALUE` | `INVALID_VALUE` | `REPAIR` | No new deterministic rule |

For each row, the raw patch and fingerprint are retained in the JSON artifact. The canonical path is already allowed; the observed failure is a value that cannot be applied to the structural plan, not a resolver or whitelist failure. The repair attempt was accepted, so changing the resolver or contract would be unsafe and unsupported by evidence.

## Recovery decision

No `SAFE_ALIAS`, `SAFE_ENVELOPE_VARIANT`, `CONTRACT_MISMATCH`, or `COMPILER_BUG` evidence was observed in this run. The recovery registry therefore remains empty. This is intentional: adding a generic alias or broadening the allow-list would violate the evidence-driven recovery rule.

| Proposed rule | Evidence count | Decision |
|---|---:|---|
| None | 0 | Do not register |

`TRUE_FORBIDDEN`, `FACT_OVERRIDE`, and ambiguous cases remain fail-closed by contract. `INVALID_VALUE` continues through the existing explicit repair route and is not converted into an automatic deterministic rewrite.

## Comparison to V2.2.1 baseline

The V2.2.1 artifact recorded 13 final fallbacks but lacked raw path, canonical path, provider index, and rejection stage evidence. This run demonstrates that the new trace layer can account for every rejection and classify every observed event without changing quality weights, contracts, or production behavior. Any quality or fallback delta in a later run must therefore be attributed to model output variance or an explicitly evidenced recovery rule, not to hidden resolver behavior.

## Gate status before Recovery Pilot

- Observability completeness: **PASS**
- Recovery rule evidence requirement: **PASS** (no unsupported rule registered)
- Fact Override accepted: **PASS (0)**
- Production/Storyboard/Media/Object Storage side effects: **PASS (0)**
- Production Shadow: **OFF**
