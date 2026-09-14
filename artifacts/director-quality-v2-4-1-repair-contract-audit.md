# Director Quality V2.4.1 — Repair Contract Audit

审计基线：`d99c3c5c3b432aec432c132172f07b952188b043`

审计日期：2026-09-14

## 范围与证据

本审计只读检查以下实现与冻结结果：

- `core/director_tail_repair_executor.py`
- `core/director_tail_repair.py`
- `core/director_tail_repair_acceptance.py`
- `core/director_patch_schema.py`
- `core/director_patch_normalizer.py`
- `core/director_patch_compiler.py`
- `core/director_patch_validator.py`
- `core/director_creative_contract.py`
- `core/director_quality_validator.py`
- `core/director_creative_value.py`
- `core/repair_ledger.py`
- `core/llm.py`
- `api/model_registry.py`
- `scripts/run_director_quality_v2_4_targeted_tail_pilot.py`
- `artifacts/director-quality-v2-4-targeted-tail-pilot-report.md`
- `artifacts/director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json`

未执行真实 LLM、生图、视频、对象存储或生产写入。

## 1. 53 个 forbidden-field failure 的 shape

冻结 Pilot 结果没有保存原始模型响应，只保存了每次 attempt 的解析错误。因此当前可直接验证的是错误字段集合，而不是逐条原文。证据中的主要 shape 为：

1. **Request/context envelope 被模型原样回显**：`protocol_version`、`root_cause`、`failed_dimensions`、`relevant_opportunities`、`relevant_beats`、`relevant_shots`、`scene_strategy_subset`、`immutable_contract_subset`、`previous_intervention`、`validator_findings`、`target_metric`、`attempt_number`。
2. **Repair 层元数据混入输出顶层**：`patch_type`、`patch_version`、`target_dimension`。
3. **Canonical-like / 自定义 patch envelope**：第二次错误明确出现 `patch_type`、`patch_version`、`target_dimension`，说明模型返回的是自定义修复协议，而非 `director_creative_patch_v1`。

由于原始 response 未持久化，不能声称存在更多未观测字段；后续实现必须保存 bounded raw-response fingerprint/shape 审计，而不保存 secrets。

## 2. 格式非法但语义可能安全表达的输出

若仅包含以下语义信息，并且能无歧义映射到已允许 scope，则可能安全表达为 Repair IR：

- edit：`cut_reason`、`hold_after_action_seconds` 等现有 contract 字段；
- emotion/performance：现有 `emotion` 与 `performance_direction` 白名单字段；
- information：现有 `information_strategy` / `audience_focus` 等白名单字段；
- camera/composition：现有 camera/composition 白名单字段。

这些语义不得直接进入 canonical patch；必须先通过 typed Repair IR，再由 deterministic compiler 生成 canonical patch。

## 3. 无法安全转换的任意结构

以下内容在当前边界下必须拒绝或标记 ambiguous：

- `root_cause`、`target_dimension`、`scene_strategy_subset`、`immutable_contract_subset`、`repair_plan`、`director_notes`、`analysis` 等 Repair Request metadata 被当作 patch；
- 任意 `path`/JSON Pointer，尤其是未经过 plan_shot_id resolution 的路径；
- identity、scene canonical identity、source fact、participants source truth、blocking source fact、ShotPlan immutable topology、ScriptIR、FactSnapshot；
- 未知顶层字段、未知 shot id、空/no-op patch、无法确定目标字段的自然语言描述。

## 4. MiMo/provider structured-output 能力

当前 `core/llm.py` 的 `call_llm` 会在 `response_format` 为 dict 时原样放入 OpenAI-compatible payload；`call_llm_json` 只在环境变量 `LLM_JSON_RESPONSE_FORMAT=1` 时默认发送 `{\"type\":\"json_object\"}`。代码没有 provider capability discovery，也没有 JSON Schema/strict structured output 或 tool/function calling 的专门适配与验证。

因此当前只能确认：

- JSON object mode：**可发送，但不是账户级能力证明**；
- JSON Schema：**未证实支持**；
- strict structured output：**未证实支持**；
- tool/function calling：**未实现专门路径**。

后续必须按 profile/provider 能力显式配置，不能伪造“structured output 已启用”。

## 5. repair_callable 与 parser 边界

`core/director_tail_repair_executor.py` 中 `raw = repair_callable(request)` 后立即执行 `parse_creative_patch(raw)`。因此 repair_callable 的 raw output 直接进入 canonical patch parser，没有 Repair Semantic IR 中间层。

## 6. 第二次 retry 是否利用前次错误

否。Executor 仅递增 `attempt_number`，每次深拷贝相同 context；没有传递 previous raw output、previous parse error、exact schema violation，也没有区分 FORMAT_REPAIR 与 SEMANTIC_REPAIR。

## 7. Request/Output 语义混淆

是。`_minimal_context` 返回的是包含 root cause、target metric、immutable contract subset 等 Request metadata 的 envelope；模型被要求返回 canonical patch，导致 Request metadata 被回显到 output 顶层并触发 53 次 forbidden-field。

## 8. execution_coverage 语义

当前 `executed_roots` 仅在 accepted 时递增，最终 `execution_coverage = executed_roots / triggered_count`。因此该指标实际是 accepted-root ratio，不是 executed scenes / selected scenes，也不是 attempted root causes / selected root causes。

## 9. Acceptance wiring

`evaluate_repair_acceptance` 已支持 `creative_value_before/after`、`over_directing_before/after`、`shot_inflation_before/after` 参数及相应回退原因；但 Executor 调用时只传入 quality、contract、fact_override、structural_blocker，没有传入上述三组运行时指标。

## 10. Repair scope 到 scorer 的可达路径

当前存在部分可达路径：

- `WEAK_EDIT_STRATEGY → edit → EDIT_RHYTHM`：有 `cut_reason`/hold 等字段与 scorer 信号；
- `WEAK_EMOTION_ARC → emotion/performance_direction → EMOTIONAL_PROGRESSION/PERFORMANCE_DIRECTION`：有路径，但需 synthetic proof；
- `WEAK_INFORMATION_STRATEGY → information_strategy → INFORMATION_STRATEGY`：有路径，但需 synthetic proof；
- `PERFORMANCE_DIRECTION_WEAK → performance_direction → PERFORMANCE_DIRECTION`：有路径，但需 synthetic proof；
- `CAMERA_LANGUAGE_GENERIC → camera/composition → SHOT_DIVERSITY/VISUAL_STORYTELLING`：存在候选字段，但 scorer 敏感度需测试；
- `OVER_DIRECTING`、`UNDER_DIRECTING`：当前 scope 较宽，必须以 matrix 与 synthetic candidate 证明合法字段能改善目标维度；否则标记 `UNREPAIRABLE_BY_CURRENT_SCORER` 或 `SCORER_SENSITIVITY_GAP`。

## 结论

四个初始假设 A-D 均被当前代码与冻结结果支持。V2.4.1 的必要修复是建立 `director_tail_repair_request_v1` 与 `director_tail_repair_ir_v1` 的分离协议、typed IR validator、确定性 IR compiler、真正的 corrective retry、分离后的 metrics 与 runtime acceptance wiring；不得放宽 `director_creative_patch_v1`。

