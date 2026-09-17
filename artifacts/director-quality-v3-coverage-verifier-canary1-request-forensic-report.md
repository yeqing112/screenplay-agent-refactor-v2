# Coverage Verifier Canary #1 — Request Forensic Report

## Historical result preservation

The historical runtime classification remains `COVERAGE_VERIFIER_MODEL_SCHEMA_FAILURE`. This report is a separate provider-free forensic record and does not rewrite the historical response, ledger, authorization, or result.

## Actual request path

`run_director_quality_v3_fact_coverage_verifier_canary.py` → `build_request()` → `json.dumps(request)` → `core.llm.call_llm()` → OpenAI-compatible `POST /chat/completions`.

The adapter constructs a system message and a user message, then sends model, messages, temperature and max_tokens. The historical runner did not pass `response_format`; the MiMo profile did not declare one.

## Projection finding

The historical user payload contained only a contract summary: schema fingerprint, enum summaries and forbidden-field names. It did not contain the complete JSON Schema, nested required fields, `additionalProperties=false`, a shape example, or the complete claim/unit field contract. Therefore the model capability cannot be fairly adjudicated.

Primary forensic root cause: `PROVIDER_SCHEMA_PROJECTION_GAP`.

No provider call was made during this forensic run.
