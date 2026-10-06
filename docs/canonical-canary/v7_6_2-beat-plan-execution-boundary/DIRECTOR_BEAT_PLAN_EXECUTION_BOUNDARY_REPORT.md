# V7.6.2 Director BeatPlan Execution Boundary Report

## Status

`DIRECTOR_BEAT_PLAN_EXECUTION_BOUNDARY_READY`

Next state: `DIRECTOR_BEAT_PLAN_ATTEMPT5_AUTHORIZATION_REQUIRED`. No real Provider,
IMAGE, VIDEO, SHAPI, Poyo, or 75API call was made. Packet 64 and its four
historical attempts remain unchanged.

## Required answers

1. V7.6.1 progressive Stage A/Stage B architecture remains unchanged.
2. The old production source-grounded endpoint still used the single-shot ProposalIR path; this gap is recorded in `CURRENT_STAGE_A_EXECUTION_GAP.json`.
3. New endpoint: `POST /api/books/{book_id}/episodes/{episode}/director-treatment/beat-plan/llm-draft`.
4. The old source-grounded production endpoint now fails closed with `DIRECTOR_PROGRESSIVE_AUTHORING_REQUIRED` and performs zero Provider calls.
5. Legacy authored screenplay behavior remains compatible.
6. Stage A system prompt length is recorded in `STAGE_A_PROMPT_COMPLEXITY.json`.
7. Stage A user prompt length is recorded in `STAGE_A_PROMPT_COMPLEXITY.json`.
8. Stage A has fewer fields and lower estimated prompt burden than the old single-shot contract.
9. Schema: `director_beat_plan_ir_v1`.
10. Per-beat fields: `refs`, `purpose`, `objective`, `information_change`, `hook`.
11. Stage A does not contain `performance`.
12. Stage A does not contain `visual_priority`.
13. Stage A does not contain `character_directions`.
14. Provider Request Fingerprint V2 binds profile, provider, model, host, prompt hashes, policy, schema, and execution boundary.
15. Prompt fingerprint is the deterministic SHA256 over the Stage A system and user prompt.
16. Resolved `max_tokens` is `8192` for the frozen profile.
17. Temperature is explicitly `0.0`.
18. Response format is `{"type":"json_object"}`.
19. Thinking is `{"type":"disabled"}`.
20. Finish reason and resolved policy fields are retained in Stage A forensic evidence.
21. `finish_reason=length` retains raw evidence and blocks parse, retry, and persistence with `DIRECTOR_BEAT_PLAN_OUTPUT_TRUNCATED_BY_LENGTH`.
22. Incomplete or placeholder creative text fails with `DIRECTOR_BEAT_PLAN_TEXT_INCOMPLETE`; local sentence completion is zero.
23. 11/12 source coverage fails closed with `DIRECTOR_BEAT_PLAN_SOURCE_COVERAGE_INCOMPLETE`.
24. A valid 12/12 provider-free mock passes schema, text, runtime, and materialization gates.
25. Local beat IDs are deterministic `DBP_E01_SC001_001` through the beat ordinal; the raw and materialized fingerprints remain separate.
26. Stage A success is stored only at `DecisionPacketRecord.model_info.progressive_director_authoring.stage_a`.
27. Packet proposal remains `{"decision":"awaiting_llm"}`.
28. Stage A alone cannot confirm; confirmation returns `DIRECTOR_CREATIVE_ENRICHMENT_REQUIRED`.
29. Stage B is not called automatically.
30. Stage A success returns `DIRECTOR_CREATIVE_ENRICHMENT_AUTHORIZATION_REQUIRED`.
31. Current attempt ledger count is `4`; attempts 1–4 remain immutable.
32. Next attempt is `attempt-5`.
33. Attempt-5 preflight prompt fingerprint is recorded in `ATTEMPT5_BEAT_PLAN_PREFLIGHT.json`.
34. Attempt-5 Provider Request Fingerprint V2 is recorded in the same preflight artifact.
35. Frozen profile is `local-llm-2vydoz / openai-compatible / mimo-v2.5 / https://api.xiaomimimo.com`.
36. Real Provider calls: `0`.
37. Production writes: `0` for this phase; the target audit remains Packet 64 only with no downstream rows.
38. Tests: `76 passed` in the V7.6.2, V7.6.1, V7.2, V7.1, and V7.4.1 focused suite; compileall and diff check pass.
39. Commit SHA is reported after the final commit.
40. Remote HEAD is verified equal to local HEAD after push; working tree is clean.
41. An attempt-5 Stage A authorization may be requested next, but no authorization was created or consumed in V7.6.2.

## Evidence

The JSON contracts in this directory cover endpoint gates, minimized prompt,
provider identity parity, forensic order, ledger metadata, text completeness,
persistence, old-path guard, provider-free mock outcomes, preflight, and the
zero-call/zero-write audit.
