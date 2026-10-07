# V7.6.15 Attempt-9 Real Semantic Revision Canary

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT9_VALIDATED`

`NEXT_STATE=DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED`

`SEMANTIC_REVIEW=BLOCKED`

The single authorized production revision transport completed once. HTTP was `200`, finish reason `stop`, raw SHA256 `8cbb4343c4c762e74eba92a6cf6a2e5a02d74c6e789c636f1bd5f405e7521589`, and raw length `6733`. No retry, Attempt-10, confirm, approved Treatment, Authority, Pointer, SceneBlocking, ShotPlan, PromptIR, IMAGE, or VIDEO was run.

## Semantic result

- Attempt-9 structural validation: PASS; beat coverage 4/4; compiled V3 validation: PASS.
- Semantic review: BLOCKED. Counts: `{"DOWNSTREAM_SHOTPLAN_LEAKAGE": 1, "SAFE_CREATIVE_DIRECTION": 90, "SOURCE_EXPLICIT": 11, "UNSUPPORTED_BACKSTORY": 1, "UNSUPPORTED_EMOTIONAL_FACT": 1}`.
- ShotPlan leakage: `1`; SceneBlocking leakage: 0.
- Attempt-8 → Attempt-9 semantic comparison is recorded in `ATTEMPT8_TO_ATTEMPT9_SEMANTIC_REGRESSION_AUDIT.json`.
- Attempt-8 remains immutable in the archive with IR SHA `5bb234bb5439d0d762f4fc41d63ed5d409f855d9047dff1d26645a7ef90483f4` and raw SHA `7d456c16384b09a7f00d9c41f032185a6646d40727108bc60b23f5fe0cb574c2`.

## Runtime identity and scope

Runtime profile: `local-llm-2vydoz / openai-compatible / mimo-v2.5 / https://api.xiaomimimo.com`. Runtime prompt identity is recorded by hash only. The V7.6.14 frozen prompt identity is marked stale because it came from a synthetic test fixture; it was not hardcoded into production.

Canonical target scope fingerprint: `83fa9de56efb24c19e296be933cc5a394ddb7887e1356315642fd5c4be4ae80f`. The persisted packet retains its historical legacy scope descriptor and fingerprint `866fc1aa010d89d1bd5ac7c0f3029d913c8908a0829592dbc5bbe42d3f15b0f1`; the reconciliation is explicit in `ATTEMPT9_RUNTIME_SCOPE.json`.

## Boundaries

- Active Stage B: `attempt-9`; proposal decision: `ready_for_review`; creative projection: `PROPOSED`.
- `confirm_allowed=false`; confirm endpoint not called.
- DirectorTreatment / Authority / Pointer writes: `0 / 0 / 0`.
- Downstream SceneBlocking / ShotPlan / PromptIR: `0 / 0 / 0`.
- IMAGE / VIDEO / SHAPI / Poyo / 75API: `0 / 0 / 0 / 0 / 0`.
- Attempt-10: `0`.

## Verification

- Provider-free focused revision tests: 36 passed before the transport; post-transport validation was provider-free.
- `python -m compileall -q core api scripts`: passed.
- `git diff --check`: passed.
