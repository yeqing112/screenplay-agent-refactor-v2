# Director LLM Adapter Runtime Report

## Phase

`PHASE_DIRECTOR_LLM_ADAPTER_RUNTIME` — `DIRECTOR_LLM_ADAPTER_RUNTIME_COMPLETE`

- Implementation commit: `422bc742aae9a549a1a54f3d3ffb1ac798a2a881`
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Migration head: `j1e2f3g4h5i6`

## Delivered

- Added `DirectorContextBuilder` to snapshot Episode, ScriptIR, Characters, Scenes, VisualStyle and ExistingShots with source hashes and safety constraints.
- Added provider-neutral `DirectorLLMAdapter` contract plus OpenAI-compatible, Anthropic-compatible, Custom and Mock implementations.
- Added strict provider-envelope extraction, JSON schema validation, DirectorReasoningIR cross-reference validation and adapter lineage creation.
- Added `POST /episodes/{id}/director-reasoning/generate` and `GET /episodes/{id}/director-reasoning/generation-status`.
- Added durable `director_reasoning_generations` audit records for running, review-required and failed attempts.
- Generated output is persisted only as a `REVIEW_REQUIRED` DirectorReasoning draft. Compile remains a separate operation.
- Added additive migration `j1e2f3g4h5i6` and adapter runtime tests.

## Safety boundary

- Adapters receive a context snapshot and never receive a SQLAlchemy session.
- Default provider mode is Mock; OpenAI-compatible and Anthropic-compatible transports are disabled unless an explicit transport is injected for tests.
- No real LLM/provider call was made in this phase.
- No image or video generation was submitted.
- Source Fact mutation: `0`; ScriptIR mutation: `0`.
- No Shot, Asset or production authority is modified by generation.
- Every successful generation remains `REVIEW_REQUIRED`; no review is bypassed and no compile is triggered automatically.

## Verification

- `pytest -q tests/test_director_llm_adapter_runtime.py`: **7 passed**.
- `pytest -q tests/test_director_reasoning_runtime.py`: **5 passed**.
- Full suite: **1895 passed**.
- `python -m scripts.verify_migration_chain --ci`: fresh/repeat/legacy/drift checks **PASS**, head `j1e2f3g4h5i6`.
- `npm run test:golden`: **5 passed, 0 failed**.
- `git diff --check`: **PASS**.

