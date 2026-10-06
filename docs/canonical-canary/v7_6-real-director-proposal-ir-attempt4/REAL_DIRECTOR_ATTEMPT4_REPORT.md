# V7.6 Real Director ProposalIR Attempt-4 Report

## Result

`DIRECTOR_PROPOSAL_IR_SCHEMA_INVALID`

The single authorized Director MiMo call completed with HTTP 200 and a parseable JSON response. The formal `director_proposal_ir_v1` schema gate failed, so execution stopped before runtime validation, compilation, proposal persistence, confirmation, and downstream work.

## Required answers

1. Base HEAD: `06d0a5596be3afa517682cc655b9938ded87925e`.
2. Authorization ID: `v7_6-director-proposal-ir-attempt4-authorization-4`.
3. Attempt ID: `attempt-4`.
4. Historical attempts before: `3` (`v7_3_attempt_1`, `v7_3_attempt_2`, `attempt-3`).
5. Scope fingerprint: `83fa9de56efb24c19e296be933cc5a394ddb7887e1356315642fd5c4be4ae80f`.
6. Scene ID: `E01_SC001`.
7. Source unit fingerprint: `2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f`.
8. Packet fingerprint: `e48b8502ab2e14b94798d19a`.
9. Profile/model: `local-llm-2vydoz / mimo-v2.5`; provider `openai-compatible`, host `https://api.xiaomimimo.com`.
10. Frozen request fingerprint: `331223e1a5d7ee567a3b73091e35d00055212df6f5b57205043873819c951402`.
11. Actual request fingerprint: `331223e1a5d7ee567a3b73091e35d00055212df6f5b57205043873819c951402`.
12. Match: `YES`.
13. Provider POST count: `1`.
14. Transport attempts: `1`.
15. Retry: `0`.
16. HTTP status: `200`.
17. Provider request ID: `not returned`.
18. Raw response SHA: `98ea44dd68877b14c733b4bf49fd01252cd76c8aeacbf3c3d561a481b1a3679b`.
19. Same as historical raw SHA: `NO`.
20. Raw forensic persisted before parse: `YES`.
21. Attempt ledger final count: `4`.
22. Attempt-4 terminal status: `SCHEMA_INVALID`.
23. JSON parse: `PASS`, exactly once.
24. Formal schema: `FAIL`; missing required top-level fields and invalid beat fields were reported.
25. Runtime validation: `NOT RUN`.
26. Creative beat count: `NOT EVALUATED`.
27. Beat refs: `NOT EVALUATED`.
28. Coverage 12/12: `NOT EVALUATED` because schema gate stopped execution.
29. Passthrough count: `NOT EVALUATED`.
30. Hook count: `NOT EVALUATED`.
31. Transition intent count: `NOT EVALUATED`.
32. Character direction fields: `NOT EVALUATED`; no attempt-4 character_directions passed the gate.
33. Local direction semantic expansion: `0` (compiler not run).
34. Compiler: `NOT RUN`.
35. Compiler new creative semantics: `0`.
36. Candidate status PROPOSED: `NO CANDIDATE`; proposal remains `awaiting_llm`.
37. Scene objective: `NOT EVALUATED`.
38. Dramatic question: `NOT EVALUATED`.
39. “也许是你自己” beat: `NOT EVALUATED`.
40. Performance interpretation: `NOT EVALUATED`.
41. Unknown facts: source unknowns remained unchanged; overinterpretation review not run.
42. New characters: `0` persisted; creative review not run.
43. Source mutation count: `0`.
44. Creative authority invalid count: `0`.
45. Target DB before/after scope: `PASS`, same fingerprint.
46. Target counts: Packet `1 -> 1`; Treatment/Authority/Pointer/SceneBlocking/ShotPlan/Storyboard/PromptIR/Execution/Media all `0 -> 0`.
47. DecisionPacket proposal saved: `NO`; proposal unchanged; forensic and attempt ledger saved in `model_info`.
48. Confirm called: `NO`.
49. IMAGE / VIDEO: `0 / 0`.
50. Explicit confirm next: `NO`; first resolve schema contract and obtain a new authorization.
51. Director quality improvement vs attempt-3: `NOT EVALUATED`; attempt-4 stopped at schema gate.
52. Tests / compileall / diff: `46 passed`; compileall PASS; diff check PASS before execution.
53. Working tree: evidence files pending commit; no core/api/models changes.
54. Evidence commit SHA: `c7cd60f542a8b7ea2ca2078ece8504dcd4e9a967`.
55. Remote HEAD at evidence push: `c7cd60f542a8b7ea2ca2078ece8504dcd4e9a967`; the final report-metadata commit is reported by the task delivery.

## Failure boundary

The authorization was consumed by the one real POST. No retry, repair LLM, fallback, confirm, SceneBlocking, ShotPlan, Storyboard, PromptIR, IMAGE, VIDEO, SHAPI, Poyo, or 75API call was made. Attempt-3 and V7.5 historical evidence remain unchanged.

