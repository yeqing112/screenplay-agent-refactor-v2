# Director Quality V3 — Final Re-Canary Adjudication

**Status:** `DIRECTOR_V3_FINAL_RECANARY_ADJUDICATION_FAILED`

## Contract Wiring Finding

The original run used `build_strategy_contract()` for runtime normalization/validation while the provider saw the V2 SourceRef contract. The corrected runtime contract now shares `allowed_ids`, `allowed_source_refs`, `beat_alias_table`, and `source_ref_contract` with the provider projection.

## Replay Evidence

- Original commit: `9db8f9f`; raw outputs reused unchanged: `yes`; raw fingerprints preserved: `yes`.
- New MiMo/LLM calls: `0`; provider HTTP requests: `0`; transport retries: `0`; parser retries: `0`.
- Contract equivalence: `3/3`.
- SourceRef errors removed by wiring: `146`; remaining semantic errors are retained per policy.
- Protocol valid: `0/3`; Canonical V3: `0/3`.
- Distinctiveness: `0/3`, all checked `False`.

## Adjudication Answers

1. Original 0/3 was caused by the runtime harness using the wrong SourceRef contract.
2. MiMo did not use disallowed beat IDs; `beat:1…` was explicitly allowed by the Provider contract.
3. Provider allowed the scene beat IDs and character IDs listed in the equivalence artifact.
4. Runtime called the old contract without `allowed_ids` and `beat_alias_table`, so legal refs were classified unknown.
5. `build_strategy_contract()` lacked `allowed_ids`, `allowed_source_refs`, `beat_alias_table`, and `source_ref_contract`.
6. Runtime V1 adds those fields plus deterministic fingerprints.
7. Provider and Runtime are now built from the same Runtime Contract SSOT.
8. Contract fingerprints/equality: `3/3`.
9. New MiMo calls: `0`.
10. Raw evidence reused from `9db8f9f`: `yes`.
11. Raw fingerprints unchanged: `yes`.
12. Unknown beat refs: `32` original → `0` adjudicated.
13. Unknown source refs: `114` original → `0` adjudicated.
14. Remaining genuinely unknown refs: `0`.
15. Fact authority violations: `0`.
16. Inference→fact promotion: `0`.
17. Future reveal/hint/support: `0/1/5`.
18. Protocol valid: `0/3`.
19. Canonical V3: `0/3`.
20. Distinctiveness pairs: `0/3`, all checked `False`.
21. The old STRONG + phase_count=0 mismatch is corrected: non-canonical inputs are labeled `CANDIDATE_…`; canonical inputs alone may use `AUTOMATED_…`.
22. Formal signal input type is `CANONICAL_V3` only for compiled canonical output, otherwise `NORMALIZED_NONCANONICAL_CANDIDATE`.
23. Custom IR stop-loss: `false`.
24. It is false because the primary failure was a harness implementation bug; remaining semantic errors are reported separately.
25. Original experiment validity: `INVALID_DUE_TO_HARNESS_CONTRACT_WIRING`.
26. Adjudicated status: `DIRECTOR_V3_FINAL_RECANARY_ADJUDICATION_FAILED`.
27. MiMo re-call required: `no`.
28. Automatic Shot Architecture entry: `no`.
29. Human Director Review required: `yes`.

## Decision

`ORIGINAL_FINAL_RECANARY_STATUS=SCENE_DIRECTOR_FINAL_RECANARY_FAILED`
`ORIGINAL_EXPERIMENT_VALIDITY=INVALID_DUE_TO_HARNESS_CONTRACT_WIRING`
`ADJUDICATED_FINAL_RECANARY_STATUS=DIRECTOR_V3_FINAL_RECANARY_ADJUDICATION_FAILED`
`AWAITING_HUMAN_DIRECTOR_REVIEW=true`
`READY_FOR_SHOT_ARCHITECTURE_CANARY=false`
