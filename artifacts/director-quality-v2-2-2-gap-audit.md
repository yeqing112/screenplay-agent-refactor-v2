# Director Quality V2.2.2 — Rejection Observability / Failure Audit

**审计阶段：** Step 1（只读审计；未修改代码、未调用真实 MiMo、生图、视频、对象存储或生产 API）  
**审计基线：** `24ba481` / `origin/codex/unify-formal-workspace`  
**V2.2.1 Pilot：** `artifacts/director-quality-v2-2-1-mimo-pilot-20260913T161906Z.json`  
**V2.2.1 结果：** 12 scenes、Final Contract 12/12、13 fallback、Creative Retention 46.15%、Production Shadow OFF。

## 1. 当前 raw provider output 在哪里解析

真实 provider 返回值首先在 `core/llm.py::call_llm` 中作为 response content 返回；`core/llm.py::call_llm_json` 随后执行字符串清理、`parse_json_object` 和 required-key 检查。Pilot runner 的 planner/repair 调用分别位于 `scripts/run_director_quality_v2_2_mimo_pilot_authorized.py`，调用结果以 `raw` 变量传入 `core/director_quality_v22.py::process_patch_pipeline`。

## 2. 解析前原始 patch 是否还存在

在内存中存在：`process_patch_pipeline(raw_output=raw)` 接收 provider 解析后的 Python object，随后立即进入 `deterministic_repair_document`。但当前持久化 artifact 只保存 `raw_digest`，不保存每个 provider patch 的原文、索引或字段摘要。`core.llm` 仅保存 response hash、长度和 prompt hash，不保存 response body；这符合不落敏感全文的原则，却无法回溯 patch 级证据。

## 3. 哪一层最适合捕获 raw patch

最合适的边界是 `process_patch_pipeline` 接收到 `raw_output` 后、调用 `deterministic_repair_document` 之前。此时已经完成 JSON parse，但尚未改变 patch shape、path 或 value。应按 provider `patches`/auxiliary 数组索引生成 trace，并只保存结构化 patch 摘要与指纹，不把整段 prompt 或 provider response 写入日志。

## 4. 哪一层最适合捕获 raw path

同一边界逐项读取 raw patch 的 `changes` key、JSON Patch `patch[].path`、扁平 `path`，或 nested field key；捕获后再交给 `collect_path_resolution_metrics` 和 `resolve_patch_path`。这能同时记录原始 selector（例如 `3`）、raw path 和后续 canonical path，而不是只保留规范化后的字段。

## 5. 当前 shot identity 在哪个阶段丢失

provider item 的 `plan_shot_id` 在 normalize 前仍可读；numeric selector 的 resolved ID 在 resolver 内部形成。丢失发生在两处：一是 `collect_path_resolution_metrics` 的失败记录只保存 `plan_shot_id`、`raw_path`、`code`，没有 provider item index/原始 selector；二是 `process_patch_pipeline` 构造 fallback 时只从 normalized item 取 target。V2.2.1 artifact 中 13 条 fallback 的 `plan_shot_id`/`proposal_id` 均为空，验证了这个观测缺口。

## 6. canonical path 在哪里形成

唯一 resolver 为 `core/director_patch_path_resolver.py::resolve_patch_path`，返回 `ResolvedPatchPath(plan_shot_id, path, raw_path, source_format, alias_hit)`。Normalizer 的 `canonical_path`、`normalize_patch_item`、repair output normalizer 和 deterministic repair 均复用该 resolver；compiler 随后把相对 canonical path 转为 `/shots/{index}/...` pointer。

## 7. allowed-path check 在哪里执行

resolver 先将 contract 的 allowed paths 转为相对路径集合并进行白名单匹配；`director_patch_compiler._assert_path_authority` 还会对 raw/canonical pointer 再次执行 immutable 与 allowed-path 校验；validator 对已编译 operation 做最终 allowed-path 检查。当前是 fail-closed，多义、越权和事实字段不会因 trace 改造而放行。

## 8. FORBIDDEN_PATH 在哪个 stage 产生

当前 code 可能在以下层产生同类 code：

- `PATH_RESOLUTION / ALLOWED_PATH_CHECK`：resolver 抛出 `DIRECTOR_PATCH_PATH_FORBIDDEN`；
- `VALUE/STRUCTURE normalization`：normalizer 发现 forbidden root/child field；
- `CONTRACT_VALIDATION / PATCH_MERGE`：compiler 的 `_assert_path_authority` 或 partial acceptance 记录 forbidden path。

当前 artifact 把它们压成 `root_cause=FORBIDDEN_PATH`，没有统一 `rejection_stage`，因此无法回答具体是哪一层误杀。

## 9. 当前 fallback artifact 为什么无法回溯 raw path

`process_patch_pipeline` 返回的 fallback 只含 `scene_id`、target（有时为空）、root cause、code、attempt count、final action 和分类；Pilot runner再将其复制到 scene artifact。`core.llm` 有意只写 response hash/length。结果是 13 条 V2.2.1 fallback 虽可按场景计数，却缺少 raw patch、raw path、canonical candidate、allowed match、rejection stage 和原始 item index。

## 10. 如何增加观测而不记录敏感 prompt 全文

新增 bounded `RejectionTrace`：保存稳定 trace id、scene/episode、provider item index、raw patch 的结构化安全副本、raw patch fingerprint、raw path、value type、shot selector、canonical/parsed path、resolver rule、allowed match、normalization rule、stage、issue code、repair attempt 摘要、final action 和 fallback 分类。长 reason、strategy、prompt body、provider response body 只保存截断安全摘要或 fingerprint；API key/Authorization 永不进入 trace。已有 `RepairAttempt.repair_operation` JSON 字段可以继续保存 redacted operation metadata。

## 11. 是否需要 DB migration

本轮不需要 migration：Observability Pilot 只写 timestamped artifact，运行时 ledger 已有 JSON `repair_operation`、fingerprint、issue/target、attempt 和 status 字段。若未来要求对 RejectionTrace 做生产级查询，再以 additive migration 增加独立表/索引；该范围不应在 V2.2.2 混入。

## 12. 本轮涉及文件（审计后的最小范围）

预期只触及：

- 新增 `core/director_rejection_trace.py`；
- `core/director_quality_v22.py`（在 raw capture、normalization、validator、repair、fallback 处传递 trace）；
- `scripts/run_director_quality_v2_2_mimo_pilot_authorized.py` 和 V2.2.2 observability/recovery runner（artifact 输出）；
- `core/director_patch_path_resolver.py`（仅必要的 resolution rule metadata，不放宽白名单）；
- 新增 trace/classification/recovery 测试；
- V2.2.2 gap、analysis、metrics、final report artifacts。

不改 SceneBlocking、FactSnapshot、Materializer、Prompt Compiler、质量权重或媒体生产链路。

## 13. 测试计划

先写 deterministic tests：raw-before-normalize、raw path/shot identity、numeric selector、canonical path、allowed match、每个 rejection stage、TRUE_FORBIDDEN/SAFE_ALIAS/SAFE_ENVELOPE_VARIANT/CONTRACT_MISMATCH/COMPILER_BUG/AMBIGUOUS/INVALID_VALUE、unknown root cause fail-closed、recovery rule registry、Fact Override 不可恢复。再跑 Provider Raw → Trace → Parse → Resolve → Compile → Validate → Reject/Repair → Fallback 的集成测试；最后回归 V2.2.1、V2.2、V2.1、Director、Production、SceneBlocking、Golden、compileall、diff-check。

## 14. 同 12 场复跑计划

1. deterministic tests 全绿后，用相同 frozen Golden、approved evidence、structural ShotPlan 和 `mimo-v2.5` 执行 Observability-only 12-scene Pilot；不添加 recovery rule，不触碰生产/Storyboard/媒体/对象存储。
2. 读取 Observability artifact，逐条输出 13（或实际观察到的全部）fallback 的 trace、raw/canonical path、stage、allowed match、classification 和安全恢复建议。
3. 仅依据 analysis 中明确、无歧义的证据登记 recovery rule，再用完全相同的 12 场景执行 Recovery Pilot。
4. 对比 V2.2.1、Observability-only、Recovery 三组；只输出 SAFE_TO_SHADOW 与 VALUABLE_ENOUGH_TO_SHADOW，不自动开启 Shadow，也不扩 Stage B。

## 审计结论

V2.2.1 的 resolver 和 contract 已经安全地 fail-closed，但 rejection evidence 在 normalization 前没有被逐 patch 捕获，导致 13 个 `FORBIDDEN_PATH` fallback 无法区分 TRUE_FORBIDDEN、SAFE_ALIAS、SAFE_ENVELOPE_VARIANT、CONTRACT_MISMATCH、COMPILER_BUG 或 AMBIGUOUS。本轮第一优先级应是完整 trace 与证据分类；在 Observability analysis 之前不得继续扩大 resolver 或猜测 recovery rule。
