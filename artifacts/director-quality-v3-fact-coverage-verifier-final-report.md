# Director Quality V3 — Authorized Fact Coverage Verifier Canary

## Execution

- Execution base: `b0cc550cd71083a1be5cf9bf28a2750b1370d696`
- Authorization: `director-v3-fact-coverage-verifier-canary-20260917-01`
- Provider/model: `openai-compatible` / `mimo-v2.5`
- Real provider calls: **1**; retries/repair/fallback/critic/judge: **0**.
- Cumulative provider attempts: `3 → 4`.
- Full-source input: `SRC79f12d1b7f5eb828`, 347 anchors, 5 narrative units, 7 existing facts.

## Contract result

The provider response was received but failed the V2 contract. It began with Markdown fenced JSON, so the strict JSON parse failed. The legacy shape also used `coverage_status`, `unit_relevances`, `claim`, `status`, and `evidence_units`, while omitting required `fact_refs`, canonical `requirement_key`, and complete `unit_assessments`.

Classification: **`COVERAGE_VERIFIER_MODEL_SCHEMA_FAILURE`**.

The program did not repair, reinterpret, or promote the response. No canonical requirement IDs, coverage matrix, missing-fact package, or downstream artifacts were derived from it.

## Authority decision

- Coverage qualified: **NO** (`FACT_COVERAGE_REVIEW_REQUIRED`).
- Targeted missing-fact extraction: **blocked and unauthorized**.
- ScriptIR: **blocked and unauthorized**.
- Production/storyboard/media: **0 calls**.
- This canary is terminal. Do not retry the provider under this authorization. The next permissible work is provider-schema repair and a new explicit authorization.

## Integrity

Historical Fact Attempt #1/#2, Semantic Verifier evidence, full-source completeness, and production data were preserved. This report and its JSON companions are provider-free post-run evidence only.
