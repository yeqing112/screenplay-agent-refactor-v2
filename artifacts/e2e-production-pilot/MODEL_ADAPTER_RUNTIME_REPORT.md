# Model Adapter Runtime Report

## Scope

本轮完成 `PHASE_MODEL_ADAPTER_RUNTIME`。链路为：

`GenerationExecutionRecord → GenerationOrchestrator → ModelAdapter Registry → Existing Model Registry profile`。

本阶段只执行 deterministic mock adapter；真实 Provider/API、图片文件和媒体候选仍未接入，为下一阶段 `PHASE_REAL_IMAGE_PROVIDER_CANARY` 保留边界。

## Implementation

- `core/model_adapter_runtime.py`
  - 定义 runtime `ModelAdapter` 协议和 `ModelAdapterResult`。
  - 新增 `ModelAdapterRegistry`，按 `model_profile.provider` 精确选择 adapter。
  - 注册 `MockAdapter`、`FluxAdapter` 占位和其他 Provider 的显式 unavailable adapter。
  - `MockAdapter` 只返回脱敏 metadata，不联网、不写文件、不创建 MediaCandidate。
- `core/generation_orchestrator.py`
  - 读取现有 `GenerationExecutionRecord`。
  - 通过现有 `api.model_registry.get_profile` 解析显式 profile。
  - 读取 PromptIRVersion payload，构造 prompt projection。
  - 使用现有 `build_provider_execution_profile` 生成 secret-free runtime profile。
  - 驱动 `CREATED → QUEUED → RUNNING → SUCCESS`。
  - Adapter failure 持久化为 `FAILED`；非 mock Provider 在进入 `RUNNING` 前 fail-closed。
  - 保存 adapter/model/provider request/response projection、hash、调用计数和错误信息。
- `api/generation_execution_api.py`
  - 新增 `POST /generation/executions/{execution_id}/run`。
  - `/api/generation/executions/{execution_id}/run` 复用同一个 router 和 orchestrator。
- `tests/test_model_adapter_runtime.py`
  - Adapter Registry 选择测试。
  - Orchestrator 成功链路测试。
  - Mock Provider failure → `FAILED` 测试。
  - 非 mock Provider fail-closed 测试。
  - Run API contract 测试。

## Reused boundaries

- Reused existing Model Registry KV profiles/defaults.
- Reused existing `GenerationExecutionRecord`, `GenerationExecutionService`, PromptIRVersion and TaskRun boundary.
- Did not add ModelManager, ProviderManager, AssetManager, GenerationTask, GenerationQueue or GenerationWorker.
- Did not modify Prompt Lineage, Asset Authority or Review Workflow.
- Did not call existing real Provider Transport in this phase.

## Verification

| Gate | Result | Command / evidence |
|---|---|---|
| Runtime tests | PASS: 5 passed | `pytest -q tests/test_model_adapter_runtime.py` |
| Runtime + foundation + Phase F regression | PASS: 42 passed | targeted runtime/regression command |
| Full backend tests | PASS: 1826 passed, 4288 warnings | `pytest -q` |
| Migration chain | PASS | fresh upgrade, second upgrade, legacy preservation, drift; head `b2c3d4e5f6g7` |
| Golden regression | PASS: 5/5 fixtures | `npm run test:golden` |
| Production regression | PASS | `npm run check:production` |
| Frontend build | PASS | included in production regression |
| Syntax / diff check | PASS | `python -m py_compile ...`; `git diff --check` |

Warnings are existing deprecation and test-return warnings; no failures occurred.

## API contract

`POST /generation/executions/{execution_id}/run` accepts an optional `params` object and returns the same serialized execution projection as the GET endpoint. The response includes status, metadata, provider call count, payload projections, errors and timestamps.

## Migration

No migration was required. The orchestrator writes existing columns on `generation_execution_records`; current migration head remains `b2c3d4e5f6g7`.

## Commit and branch

- Commit: `1bbc0686f5c57777f98b60309e96f8509ed91714`
- Branch: `codex/visual-authoring-provider-canary-reconcile`

## Deliberately incomplete

- No real image/video model API call.
- No Provider Transport dispatch from this phase.
- No media file creation, storage ingestion, MediaCandidate creation or OfficialMedia promotion.
- No async submit/poll/reconcile worker; those remain part of the real provider runtime phase.

MODEL_ADAPTER_RUNTIME_COMPLETE
