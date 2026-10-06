# Director Proposal IR Integrity Closure V7.4.1

Status: `DIRECTOR_PROPOSAL_IR_INTEGRITY_READY`

Next state: `DIRECTOR_LLM_PROPOSAL_IR_AUTHORIZATION_REQUIRED`

This closure made no external Provider call and generated no DirectorTreatment. The only production mutation was the explicitly allowed metadata-only hydration of `DecisionPacketRecord` 64's forensic attempt ledger.

## Final answers

1. V7.4 remains valid. The flat ProposalIR boundary, deterministic compiler, 12/12 source coverage, and zero creative compiler additions remain intact.
2. The compiler previously wrote `CONFIRMED` because it reused a confirmed-looking creative projection fixture even though the packet still required human confirmation. That violated the state model.
3. The current compiler output is `creative_projection.status = PROPOSED` with `human_confirmation_required = true` and `decision = ready_for_review`.
4. `production_confirm_service` owns `PROPOSED → CONFIRMED`.
5. Confirmation semantic mutation count: **0**. Only confirmation metadata is added.
6. DecisionPacket 64 prestate did **not** contain either attempt history row. It had only the latest raw forensic record.
7. Hydration completed once from the immutable V7.3 evidence, producing exactly two canonical rows.
8. Hydration is idempotent: second run writes `0`, duplicates `2`, history remains length `2`.
9. Attempt 1 authorization: `v7_3-real-director-creative-proposal-authorization-1`; attempt 2 authorization: `v7_3-real-director-creative-proposal-retry-json-mode-authorization-2`.
10. Next attempt number: `3`, generated as `attempt-3`.
11. Every new source-grounded external call must include `authorization_id`; otherwise it fails with `DIRECTOR_LLM_AUTHORIZATION_ID_REQUIRED` before Provider POST.
12. The formal beat JSON Schema now declares `properties`, `required`, `minItems`, item types, and `additionalProperties=false`; character directions and effects are explicit too.
13. The schema-driven runtime check and custom ProposalIR validator agree on the valid fixture and all six invalid fixtures.
14. Five-beat golden: **PASS**.
15. Source coverage: **12/12** — 11 actions, 1 dialogue, 0 source beats.
16. Provider-facing prompt remains flat/minimal: field list, textual beat contract, and empty shape only; no nested schema example was restored.
17. Next request fingerprint remains `26b0a52fd64508d33482be227459a5892039e0924ab96ec9c2eab2375ed77d93` because the Provider prompt did not change.
18. New real Provider calls: **0**.
19. Production mutation: only `DecisionPacketRecord id=64.model_info.director_llm_attempts` metadata hydration; packet fingerprint, proposal, status, and latest raw forensic were preserved.
20. DirectorTreatment / Authority / Pointer writes: `0 / 0 / 0`.
21. Tests: **70 passed** for V7.1, V7.2, V7.4, V7.4.1, and authority contracts. `compileall` and `git diff --check` pass.
22. Commit / remote HEAD / clean tree: verified equal at delivery; exact final SHA is reported with the pushed branch link.
23. A third real MiMo ProposalIR call may now be authorized once, explicitly and separately. The call remains proposal-only and must carry its authorization ID; confirmation and downstream production remain separate.

## Gate status

```text
PROPOSAL_STATUS = PROPOSED
CONFIRMATION_OWNS_CONFIRMED_TRANSITION = PASS
CONFIRM_SEMANTIC_MUTATION_COUNT = 0
HISTORICAL_ATTEMPT_COUNT = 2
HISTORY_HYDRATION_IDEMPOTENT = PASS
NEXT_ATTEMPT_NUMBER = 3
AUTHORIZATION_ID_BOUND = PASS
FORMAL_SCHEMA_RUNTIME_CONFORMANCE = PASS
FIVE_BEAT_GOLDEN = PASS
SOURCE_COVERAGE = 12/12
REAL_PROVIDER_CALLS = 0
DOWNSTREAM_WRITES = 0
```
