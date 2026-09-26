# Generation Execution Foundation Report

## Scope

本轮完成 `PHASE_GENERATION_EXECUTION_FOUNDATION`：建立 `PromptIRPointer/PromptIRVersion → GenerationExecutionRecord` 的生产事实链。实现停在 provider-free foundation，不调用真实模型、不接 Provider、不生成图片。

## Implementation

- Reused the existing `GenerationExecutionRecord` / `generation_execution_records` table and existing `TaskRun` runtime boundary.
- Added compatibility properties for the foundation vocabulary (`shot_id`, `prompt_pointer_id`, `prompt_version_id`, `execution_status`, payloads, error, retry count, timestamps) without introducing a second execution table.
- Added `GenerationExecutionService` with creation, legal state transitions, single lookup, shot history lookup, and serialization.
- Added API routes:
  - `POST /generation/executions`
  - `GET /generation/executions/{execution_id}`
  - The same router is mounted under `/api/generation/executions` for the project API namespace.
- Creation validates the shot, pointer ownership, pointer/version match, and required model profile. It records `provider_calls = 0` and does not invoke a provider.
- State machine: `CREATED → QUEUED → RUNNING → SUCCESS`; failure path `RUNNING → FAILED → RETRYING → QUEUED`.

## Files

- `models/generation_execution.py`
- `core/generation_execution_service.py`
- `api/generation_execution_api.py`
- `api/server.py`
- `tests/test_generation_execution_foundation.py`
- `artifacts/e2e-production-pilot/GENERATION_EXECUTION_FOUNDATION_REPORT.md`
- `artifacts/e2e-production-pilot/GENERATION_EXECUTION_TRUTH_AUDIT.json`
- `artifacts/e2e-production-pilot/GENERATION_EXECUTION_VERTICAL_SLICE.json`

## Verification

| Gate | Result | Evidence |
|---|---|---|
| Foundation tests | PASS: 4 passed | `pytest -q tests/test_generation_execution_foundation.py` |
| Related Generation/Prompt/Asset regression | PASS: 98 passed | Phase F, PromptIR authority, media validation, visual asset suites |
| Full backend tests | PASS: 1821 passed, 4203 warnings | `pytest -q` |
| Migration chain | PASS | fresh upgrade, second upgrade, legacy preservation, drift; head `b2c3d4e5f6g7` |
| Golden regression | PASS: 5/5 fixtures | `npm run test:golden` |
| Production regression | PASS | `npm run check:production`; backend, Golden, config, release-gate invariants, frontend build |
| Syntax check | PASS | `python -m py_compile ...` |

Warnings are existing deprecation/test-return warnings; no test failures occurred.

## Migration decision

No new migration was added. The canonical Phase F table already exists and the current migration head is fixed at `b2c3d4e5f6g7`. Foundation-only fields are exposed through compatibility properties and a namespaced JSON snapshot, preserving the existing schema and old data.

## Commit and branch

- Implementation commit: `3cb22be59b5d089dc8c13acbd73a52934eb07f0d`
- Branch: `codex/visual-authoring-provider-canary-reconcile`

## Not implemented in this phase

- ModelAdapter runtime
- Provider transport or real model calls
- Image/media generation
- MediaCandidate or OfficialMediaAuthority changes
- New ModelManager, ProviderManager, AssetManager, GenerationTask, GenerationQueue, or GenerationWorker

## Next phase

`PHASE_MODEL_ADAPTER_RUNTIME` can consume the durable execution record and connect it to the existing Model Registry and Provider Transport under an explicit provider boundary.

GENERATION_EXECUTION_FOUNDATION_COMPLETE
