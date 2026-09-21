# PHASE_F_REPLAY_PROFILE_CONTRACT_AND_REAL_AUTHORITY_PILOT_CLOSURE_READY_FOR_REVIEW

## 本轮范围

本轮只收口 successful replay current validation、ProviderExecutionProfile secret boundary、transport/generation 参数分离，以及真实 A–E → F SQLite integration pilot。没有调用真实外部 Provider、没有新增 migration、没有 promotion、retry、QA 或 Phase G 行为。

## Replay contract

Execute 现在固定按以下顺序执行：

```text
URL / execution identity
→ confirmation token
→ current A–E / PromptIR authority resolve
→ GenerationPayload rebuild
→ provider request fingerprint drift check
→ candidate lineage validation
→ state claim or zero-call reuse
```

成功 replay 只有在 current authority、payload、profile、reference、request fingerprint 和 Candidate lineage 全部一致时才返回 `reused=true`；同 current replay 为 `provider_calls=0`。错误 token、PromptIR/asset/reference/profile drift、Candidate 缺失或 lineage tamper 均 fail closed，Provider 不被调用。

## ProviderExecutionProfile

新增 `core/provider_execution_profile.py`，使用 `provider_execution_profile_v1` 的正向 allowlist：

- `generation_params`：模型生成参数。
- `transport_config.timeout_seconds`：HTTP transport contract。
- `credential`：只保留 `configured` 与 `source_identity`。
- `adapter`、provider、model、endpoint identity 绑定到 profile fingerprint。

raw API key、Authorization、Bearer、nested token、未知 registry 字段不会进入 canonical profile、fingerprint、request snapshot 或 artifact。仅 API key rotation 且 credential source identity 不变时，profile fingerprint 保持不变。

## Transport contract

`openai-compatible`、`shapi-openai-images`、`shapi-gemini-image` 均只从 `generation_params` 构造 Provider body，`timeout_seconds=37` 通过 `AsyncClient(timeout=37)` 生效且不进入 JSON body。GenerationPayload semantic fingerprint 不绑定 transport timeout；provider execution profile/request fingerprint 绑定 transport contract。

## Real Authority Integration pilot

证据文件：`episode_01_phase_f_real_authority_fake_provider_trace.json`

- 数据库：真实临时 SQLite，Alembic head `y8h9i0j1k2l3`。
- A–E：真实 ScriptIR、DirectorTreatment、SceneBlocking、ShotPlan、Storyboard materialization、PromptIR pointer/version/authority。
- trace 保存上述 authority 的真实 id/revision/payload hash/fingerprint before/after；核心链路均为非空，且 before/after 完全一致。
- Phase F：真实 `preview_generation_canary()` 与 `execute_generation_canary()`；只在 `_call_provider` 边界注入 deterministic 1×1 PNG fake provider。
- fake provider calls：1；external provider calls：0。
- candidate：真实 canonical local storage、SHA-256 checksum、`1×1`、`image/png`、`MEDIA_CANDIDATE`。
- authority before/after：完全一致；authority mutations：0。
- Phase F 表计数从 `0/0` 变为 `1/1`，新增对象只有 `GenerationExecutionRecord` 与 `MediaCandidateRecord`。
- resolver monkeypatch：`false`；asset/storyboard resolver monkeypatch：`false`。

旧的 `episode_01_phase_f_fake_provider_trace.json` 仅作为 synthetic unit/state-machine proof，不再作为 authority mutation proof。

## Schema provenance

现有 migration 保留且未新增：

```text
migration_present=true
migration_revision=y8h9i0j1k2l3
migration_architecture_review=ACCEPTED
preimplementation_human_approval_provenance=NOT_VERIFIED
schema_status=IMPLEMENTED_PENDING_FORMAL_APPROVAL
```

不再声称未被当前对话证明的人工批准状态。

## 验证

- Phase F core regression：`24 passed`。
- Replay/profile contract：`2 passed`。
- Transport contract：`3 passed`。
- Real authority trace contract：`1 passed`。
- Phase F 合计：`30 passed`；migration chain hardening：`7 passed`。
- 真实 pilot：SQLite + Alembic upgrade + A–E persisted lineage + fake provider，1 candidate，0 external calls。
- Secret marker scan：测试 secret marker 在 artifacts/DB snapshots 中无命中。
- migration 数量：未增加。

完整后端回归本轮结果：`1680 passed, 4 failed`。4 个失败均为既有 baseline/environment 失败，分别为 `test_director_quality_v24_offline_replay`、`test_director_quality_v3_final_spine_topology_preflight_wiring`、`test_real_llm_gray_selection`、`test_targeted_missing_fact_api`；未发现 Phase F 新增失败。

Phase C–E、Golden、full backend、Web 的历史结果按上一阶段报告保留；本轮未执行真实 Provider，因此没有 Phase-F-induced external side effect。

## 证据索引

- `phase_f_generation_execution_contract.json`
- `phase_f_provider_request_audit.json`
- `episode_01_phase_f_real_authority_fake_provider_trace.json`
- `tests/test_generation_canary_phase_f_replay_profile_contract.py`
- `tests/test_generation_canary_phase_f_transport_contract.py`
- `tests/test_generation_canary_phase_f_real_authority_integration.py`
