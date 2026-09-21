# PHASE_F_PROVIDER_PARAM_SEMANTIC_BOUNDARY_AND_CONCURRENT_REPLAY_CLOSURE_READY_FOR_REVIEW

## Implementation commit

- Branch: `codex/visual-authoring-provider-canary-reconcile`
- Commit: `0600e3a` (`Close Phase F provider boundary and concurrent replay`)

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

新增 `core/provider_execution_profile.py`，使用 `provider_execution_profile_v2` 的 typed 正向 allowlist：

- `generation_params`：模型生成参数；标量、布尔、数值、尺寸和 `size_by_aspect_ratio` 均显式校验，`aspect_ratio` 支持 `16:9` 等比例值；`default_params` / `transport_config` 容器本身也必须是对象。
- `transport_config.timeout_seconds`：HTTP transport contract。
- `credential`：只保留 `configured` 与 `source_identity`。
- `adapter`、provider、model、endpoint identity 绑定到 profile fingerprint。

raw API key、Authorization、Bearer、nested token、未知 registry 字段不会进入 canonical profile、fingerprint、request snapshot 或 artifact。仅 API key rotation 且 credential source identity 不变时，profile fingerprint 保持不变。

## Semantic boundary decision

`ProviderExecutionProfile` is an execution contract, not a creative layer. All prompt semantics originate from PromptIR / GenerationPayload. Provider profile configuration cannot add or override negative prompts, style instructions, visual facts, blocking, camera semantics, or other creative content.

- `negative_prompt` and `style` in raw provider profile parameters are rejected with `GENERATION_PROVIDER_SEMANTIC_PARAM_FORBIDDEN`.
- A `negative_prompt` present in the request snapshot is copied only from `GenerationPayload.request`; it is never sourced from provider profile configuration.
- `supports_reference_images` and `supports_negative_prompt` are stored under `capabilities`, not `generation_params`.
- `generation_params` contains only the typed execution schema; arbitrary nested objects and unknown keys fail closed.

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

## Concurrent replay closure

并发 claim 丢失后不会再次调用 Provider：`SUCCEEDED` / `REUSED` 赢家重新执行 current candidate lineage 校验；Candidate 缺失或篡改时 fail closed；`RUNNING` 返回 `GENERATION_CANARY_IN_PROGRESS`；其他状态返回冲突错误。新增测试覆盖有效赢家、Candidate 缺失、lineage 篡改和运行中赢家。

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

- Phase F 定向回归（含并发 claim-lost、typed profile、旧核心、replay profile、transport）：`51 passed`。
- Real authority trace contract：`1 passed`。
- Schema contract：typed allowlist、secret-free fingerprint、semantic parameter rejection 均通过。
- migration chain hardening：`7 passed`。
- 真实 pilot：SQLite + Alembic upgrade + A–E persisted lineage + fake provider，1 candidate，0 external calls。
- Secret marker scan：测试 secret marker 在 artifacts/DB snapshots 中无命中。
- migration 数量：未增加。

Phase C–E/migration 定向回归：`77 passed`；Golden：`5/5 passed`；Web：`301 passed`（51 个 test files）；Web production build：`passed`。

完整后端回归本轮结果：`1701 passed, 4 failed`。4 个失败均为既有 baseline/environment 失败，分别为 `test_director_quality_v24_offline_replay`、`test_director_quality_v3_final_spine_topology_preflight_wiring`、`test_real_llm_gray_selection`、`test_targeted_missing_fact_api`；未发现 Phase F 新增失败。

证据分类：Architecture Unit/State Machine proof ✅；Real Authority Integration with Fake Provider ✅；Real External Provider Canary ❌（按本轮范围未执行）。已尝试查询 GitHub Actions API，但返回 HTTP 403 rate limit exceeded；未据此推断 run/job 状态。

规则审计：未发现 successful replay 在 current validation 前直接返回；Provider body 仅通过正向 allowlist 读取 `generation_params`；`timeout_seconds` 只进入 transport client；测试 secret marker 在 artifacts/DB snapshots 中命中数为 `0`。

Phase C–E、Golden、full backend、Web 的历史结果按上一阶段报告保留；本轮未执行真实 Provider，因此没有 Phase-F-induced external side effect。

## 证据索引

- `phase_f_generation_execution_contract.json`
- `phase_f_provider_request_audit.json`
- `episode_01_phase_f_real_authority_fake_provider_trace.json`
- `tests/test_generation_canary_phase_f_concurrent_replay_closure.py`
- `tests/test_generation_canary_phase_f_replay_profile_contract.py`
- `tests/test_generation_canary_phase_f_transport_contract.py`
- `tests/test_provider_execution_profile_schema_contract.py`
- `tests/test_generation_canary_phase_f_real_authority_integration.py`
