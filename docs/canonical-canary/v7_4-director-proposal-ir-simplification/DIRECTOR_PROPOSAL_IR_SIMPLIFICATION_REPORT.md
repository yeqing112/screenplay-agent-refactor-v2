# Director Proposal IR Simplification V7.4

Status: `DIRECTOR_LLM_PROPOSAL_IR_BOUNDARY_READY`

Next state: `DIRECTOR_LLM_PROPOSAL_IR_AUTHORIZATION_REQUIRED`

This phase was provider-free. No new MiMo, LLM, image, video, Shapi, Poyo, or 75API call was made. The two V7.3 real responses remain immutable forensic evidence.

## Final answers

1. Historical real Director LLM calls: **2 effective external transports**, each under its own authorization.
2. Raw SHA equality: **yes**. Both are `9a4792265b52e9f42c91c925f296d3ef110649c4318edf614ff7f439ef6b3566`.
3. Failure position equality: **yes**, both JSON parses failed at position `1540`.
4. JSON mode improvement: **no observed improvement**. Run 2 used `response_format={"type":"json_object"}` and repeated the same malformed shape.
5. Historical malformed response: **still rejected**, forensic-only; no repair or promotion.
6. New schema: `director_proposal_ir_v1`, a flat object with scene intent, `beats`, character directions, performance/information/rhythm/visual intent, exit intent, prohibited interpretations, explicit passthrough refs, unknowns, confidence, and note. Beat objects contain only `refs`, purpose/objective, information and audience change, performance, transition, hook, and character effects.
7. `creative_projection`: **no longer emitted by the model**.
8. `creative_beat_id`: **no longer emitted by the model**.
9. `authority`: **no longer emitted by the model**.
10. IDs: local deterministic compiler creates `DCB_<scene_id>_<ordinal:03d>`.
11. Authority: local compiler sets `AUTHORIZED_CREATIVE_PROJECTION`.
12. Source constraints: copied from the immutable local V7.1 baseline preview, never accepted from the model.
13. Compiler-added creative semantics: **0** (`local_compiler_new_creative_decision_count=0`). The compiler only maps supplied semantics and adds structural metadata.
14. Five-beat golden: the provider-free compiler test passes; the production-shaped golden fixture is 4 beats covering all 12 units.
15. Twelve-unit coverage: **PASS** — 12 total units, 11 actions, 1 dialogue, 0 source beats; every unit is explicitly referenced.
16. Target dialogue: source speaker, text, and binding remain unchanged; ProposalIR has no dialogue/speaker/binding fields.
17. New request fingerprint: `26b0a52fd64508d33482be227459a5892039e0924ab96ec9c2eab2375ed77d93`.
18. Compared with old `f241d63965020afab0e9e8fc92f0c7ec05f22761e9f75214102f02a0f22c0e8c`: **different**, due to the real prompt and contract change; no nonce or timestamp cache buster.
19. DecisionPacket forensic history: **preserved**. `_persist_v3_raw_forensic` appends `director_llm_attempts` with attempt ID, request fingerprint, raw SHA, and terminal status; it does not overwrite prior attempts.
20. Raw repair heuristic: **none**. No bracket repair, raw-SHA repair, model-specific repair, or manual JSON modification exists.
21. Real Provider calls in V7.4: **0**.
22. Production writes in V7.4: **0**. The target production rows were read-only snapshotted before and after and were byte-equivalent.
23. Tests: **56 passed** across V7.1 source-grounded authoring, V7.2 execution boundary, V7.4 ProposalIR, and treatment authority contract tests. `compileall` and `git diff --check` pass.
24. Commit / remote HEAD / clean tree: verified equal at delivery; the exact final SHA is reported with the pushed branch link.
25. Worth authorizing one new MiMo call: **yes, only as a separately authorized proposal-only canary**. It should be evaluated against the flat IR boundary, with no confirmation or downstream execution implied.

## Required gate statuses

```text
DOUBLE_FAILURE_ROOT_SHAPE_REPRODUCED = PASS
HISTORICAL_OUTPUT_FORENSIC_ONLY = PASS
DIRECTOR_PROPOSAL_IR_V1_READY = PASS
DIRECTOR_PROPOSAL_IR_COMPILER_PASS = PASS
MULTI_BEAT_GOLDEN_PASS = PASS
SOURCE_COVERAGE_GATE_PASS = PASS
COMPILER_SEMANTIC_ADDITION_COUNT = 0
NEW_REQUEST_FINGERPRINT != OLD_REQUEST_FINGERPRINT = PASS
FORENSIC_HISTORY_PRESERVED = PASS
REAL_PROVIDER_CALLS = 0
PRODUCTION_DB_WRITES = 0
```

Evidence files in this directory contain the frozen double-failure comparison, schema induction risk audit, flat schema and compiler contracts, malformed regression, golden fixture, offline end-to-end boundary, determinism audit, forensic history contract, request preflight, and production no-write audit.
