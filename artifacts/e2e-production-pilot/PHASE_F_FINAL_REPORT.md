# PHASE_F_GENERATION_EXECUTION_PROVIDER_CANARY_CLOSURE_READY_FOR_REVIEW

## 本轮结论

Phase F 已完成最小可审查实现：current PromptIR v2 每次重新解析并重建 GenerationPayload，经过显式 `model_profile_id` 和确认 token 后，最多执行一次无重试 Provider 调用。成功结果只落为 `MEDIA_CANDIDATE`，不会自动写回 Storyboard、PromptIR、VisualAssetPointer 或 VisualReferenceAuthority。

真实外部 Provider 未执行：

```text
real_provider_canary_executed=false
reason=PROVIDER_NOT_CONFIGURED_OR_NOT_AUTHORIZED
```

## 已交付

- `generation_execution_records`：执行意图、PromptIR/GenerationPayload/Policy、模型与 Provider 指纹、请求快照、响应 hash、调用/重试计数、状态与失败证据。
- `media_candidate_records`：规范化媒体存储身份、SHA-256、MIME、字节数、尺寸及完整 lineage。
- Preview 路由：provider 调用数为 0；同一 request fingerprint 幂等复用。
- Execute 路由：确认 token、current authority 重解析、漂移检查、单次 Provider 边界、成功 replay 为 0 次调用。
- Provider 失败或媒体校验失败：不创建 Candidate，不做 retry，不产生 authority promotion。
- Provider transport semantic loss、PromptIR integrity、asset/reference/model drift 均在 provider 边界前 fail-closed；并发 claim 使用数据库条件更新避免同一 fingerprint 双调用。
- request snapshot、fingerprint 和持久化审计不包含 API key、Authorization、Bearer 或 reference token secret。
- 外部 Provider profile 必须声明 `default_params.timeout_seconds`；允许的同步 transport 使用该 profile timeout，未声明时 fail-closed。
- 业务 `shot_id` 与数据库 `StoryboardShot.id` 已在执行边界明确校验。

## Episode 1 单镜头 Provider-free pilot

- Preview：`provider_calls=0`，生成 deterministic request fingerprint。
- Fake Provider：1 次逻辑调用，返回真实 PNG（68 bytes，1×1，`image/png`），写入 1 条 `MEDIA_CANDIDATE`。
- Successful replay：`provider_calls=0`，`reused=true`。
- Prompt/authority drift：在 Provider 边界前返回 409，`provider_calls=0`。
- Provider failure：`candidate_count=0`，`logical_provider_calls=1`，`transport_retry_count=0`。

证据文件：

- `episode_01_phase_f_canary_preview.json`
- `episode_01_phase_f_fake_provider_trace.json`
- `phase_f_provider_request_audit.json`
- `tests/test_generation_canary_phase_f.py`

## 验证结果

- `python -m py_compile api/generation_canary_api.py api/server.py`：通过
- `git diff --check`：通过
- `pytest -q tests/test_generation_canary_phase_f.py`：13 passed
- Alembic migration `y8h9i0j1k2l3`：已升级至 head

Phase A–E 历史回归中的既有失败保持原状，本轮未修改其失败断言；Phase F 新增测试未发现新增失败。

## Extended regression evidence

- Phase C–E targeted regression: `52 passed`; Phase F final targeted suite: `13 passed`; combined rerun: `65 passed`.
- Migration chain hardening after updating canonical head to `y8h9i0j1k2l3`: `7 passed`.
- Golden regression: `5/5 passed`.
- Release-gate self-test: passed.
- Web unit tests: `51 files / 301 tests passed`.
- Web production build: passed.
- Full backend regression: `1663 passed, 4 failed`; the four failures are known branch/environment baseline failures (`test_director_quality_v24_offline_replay`, `test_director_quality_v3_final_spine_topology_preflight_wiring`, `test_real_llm_gray_selection`, `test_targeted_missing_fact_api`). No Phase F test failed.
- Production release gate: blocked by development-environment and pre-existing baseline conditions (production config intentionally skipped, stale local DB missing `storyboard_shots.scene_id`, backend health timeout).

## 发布与同步证据

- Starting implementation HEAD: `1bdef09`
- Formal audit baseline: `434fa124e686ed16aedaafafeb57d2cdb4aac293`
- Implementation commit: `36301d7948fd6e4dc2b3b9a5068ee0c80848cedc`
- Final remote HEAD: verified against `git ls-remote origin refs/heads/codex/visual-authoring-provider-canary-reconcile` at push completion; the exact hash is reported with the remote link below.
- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Working tree: clean
- Remote synchronization: verified by `git ls-remote`
- GitHub Actions Run ID: unavailable; no authenticated run listing was available in this environment, and no external Provider call was triggered.
- External Provider calls: `0`
- Phase-F-induced backend failures: `0`

## Definition of Done audit

| Requirement | Evidence |
| --- | --- |
| Current PromptIR is the only generation semantic source | `_resolve_execution_inputs` calls the current PromptIR resolver and deterministic adapter |
| Caller prompt/reference/provider override blocked | Pydantic `extra=forbid`; request contains only adapter/profile/confirmation fields |
| Explicit model profile and no secret persistence | `_resolve_profile`, profile fingerprint, secret-free snapshot tests |
| Preview is provider-free | 13 Phase F tests and Episode 1 preview artifact show `provider_calls=0` |
| Stale PromptIR/asset/reference/model/transport semantics fail closed | drift, integrity, semantic-loss tests; all provider calls `0` |
| One call, zero retries, serialized claim | conditional DB claim, `logical_provider_calls=1`, `transport_retry_count=0` |
| Candidate bytes/checksum/mime/dimensions/lineage | fake PNG trace and `media_candidate_records` schema |
| Successful replay is idempotent | same fingerprint returns `reused=true`, `provider_calls=0` |
| No official promotion or authority mutation | candidate status and before/after authority proof artifacts |
| Real Provider status honest | `real_provider_canary_executed=false`, opt-in gate documented |
