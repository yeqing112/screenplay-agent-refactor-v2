# Director LLM Creative Proposal Execution Boundary V7.2

Status: `DIRECTOR_LLM_CREATIVE_PROPOSAL_EXECUTION_BOUNDARY_READY`

Next state: `DIRECTOR_LLM_CREATIVE_PROPOSAL_AUTHORIZATION_REQUIRED`

## Final answers

1. V7/V7.1 remain unchanged: `PASS`; this run read them only.
2. The historical endpoint used the old V1 prompt; the source-grounded branch now uses a separate V3 prompt.
3. Historical V1 required keys: `dramatic_objective`, `audience_question`, `character_intents`, `beat_map`, `visual_strategy`.
4. V3 now requires only top-level `creative_projection`; deterministic V3 validation checks its internals.
5. V3 does not require source `beat_id`; it uses generic SourceAuthoringUnit refs.
6. V3 transport total attempt budget: `1`.
7. Parser retry budget: `0`; local parse executes once.
8. Repair budget: `0`.
9. Fallback budget: `0`.
10. Raw forensic is wired into the real V3 endpoint through `DecisionPacketRecord.model_info.raw_response_forensic`.
11. Raw response is committed before parse begins.
12. Invalid JSON makes no second Provider call.
13. Timeout maps to `DIRECTOR_LLM_SUBMISSION_AMBIGUOUS`, retry `0`.
14. 429 makes one POST and no retry.
15. Canonical response hash is full SHA-256, 64 hex characters.
16. Successful proposals write only `DecisionPacketRecord` proposal/provenance/forensic state.
17. DirectorTreatment writes: `0`.
18. Authority/pointer writes: `0`.
19. SceneBlocking writes: `0`.
20. Frozen profile: `local-llm-2vydoz` / `mimo-v2.5`; key status is recorded without exposing the key.
21. Exactly-one-call authorization is safe only after the separate user authorization boundary and profile binding.
22. Production writes: `0`.
23. Real Provider calls: `0`.
24. V7.2 execution-boundary tests: `17 passed`; V7.1 regression tests also pass. compileall and diff check are run before commit.
25. This report is committed and pushed with local/remote HEAD equality.

## Required states

```text
V3_LLM_PROMPT_CONTRACT_PASS
V3_REQUIRED_KEYS_PASS
DIRECTOR_LLM_MAX_CALLS = 1
TRANSPORT_RETRY = 0
PARSE_RETRY = 0
REPAIR_LLM = 0
FALLBACK = 0
RAW_FORENSIC_BEFORE_PARSE = PASS
INVALID_JSON_FAIL_CLOSED = PASS
INVALID_CANDIDATE_FAIL_CLOSED = PASS
PROPOSAL_ONLY_BOUNDARY = PASS
PROFILE_PREFLIGHT_FROZEN = PASS
PRODUCTION_DB_WRITES = 0
REAL_PROVIDER_CALLS = 0
```
