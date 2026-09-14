# Director Quality V2.4.2c — Repository Audit

审计时间：2026-09-15
审计范围：`core/director_tail_repair_ir.py`、Provider Contract、Request、Executor、IR compiler、bounded context、V2.4.2b canary runner/artifacts，以及 `core/llm.py`。

## 结论

当前 V2.4.2b 的 IR 校验规则只存在于 `director_tail_repair_ir.py` 的条件分支中，Provider Contract 仅暴露字段名称集合，系统提示词没有 nested typed constraints。Validator 与 Provider Contract 因此已经发生 contract drift；这可以解释 emotion/performance 的真实失败，但不能解释为 provider/executor wiring 故障。当前校验是 fail-fast，FORMAT_REPAIR 只能收到纯文本错误，且 canary artifact 将同一个 sample 的多次 attempt 拆成多条 trace，`repair_rollback_count` 也是 attempt-oriented。

## 逐项审计

1. **Nested constraints 所在位置**
   - `core/director_tail_repair_ir.py::_validate_value`：`edit` 文本非空、hold 非负、duration 正数、`emotion.intensity` 0..10、performance 必填文本非空。
   - 同文件 `validate_repair_ir`：顶层字段、repair type/root cause、target dimensions、shot decision 对象、允许字段、`performance_direction` 非空 list 与 item object、`performance_emphasis` 非空字符串、semantic decision 必须存在、fingerprint 校验。
   - `core/director_tail_repair_ir_compiler.py` 再次调用该 Validator；canonical patch validator 位于 `core/director_patch_*`，不是 Provider-visible IR contract 的来源。

2. **Provider Contract 当前暴露内容**
   `build_provider_output_contract()` 暴露 schema version、required top-level keys、repair types、root cause 映射、target dimensions、每类 semantic field 名称、禁止 canonical paths 及系统计算 fingerprint。`semantic_fields` 只有字段名集合，没有类型、范围、最小长度/数量、required child fields 或 ID 集合。

3. **未暴露给 Provider 的 Validator rules**
   `duration_seconds > 0`；hold 字段 `>= 0`；emotion intensity `0..10`；文本字段非空；performance_direction 非空 array；item 必须 object；`character_id/objective/visible_behavior` 非空；`performance_emphasis` 非空；shot decision 至少一个 semantic group；未知 plan shot ID；root-cause/type 相容性；fingerprint 归一化规则。Provider 也没有收到 allowed character IDs。

4. **emotion/performance 失败解释**
   可以。V2.4.2b emotion 的越界 intensity 与空 `performance_emphasis`，以及 performance 的空 `performance_direction`，都正好命中未暴露的 typed/minItems/minLength/required-child 约束。其余 transport、JSON parser、canonical compile、contract boundary 指标均正常。

5. **Fail-fast**
   是。`validate_repair_ir` 在遇到第一个错误时立即抛出 `RepairIRSchemaError`，不会收集同一 response 的其余错误。

6. **多错误返回**
   当前只能返回第一个错误；异常只有单一 `path/code/message`（且部分分支未设置 code）。

7. **FORMAT_REPAIR 错误形态**
   当前是纯文本。Executor 将 `str(exc)` 放入 `previous_validation_errors`，没有结构化 diagnostics packet。

8. **结构化 diagnostics**
   不存在统一的 `path/code/expected/actual_type` 结构；`RepairIRSchemaError` 仅携带可选 `path` 与 `code`，`actual` 信息未结构化保存。

9. **System prompt typed constraints**
   不包含 number range、minItems、minLength 或 required child fields；只插入 JSON 序列化后的字段名映射。

10. **Canary sample trace**
    是。同一 `sample_id` 在 `director-quality-v2-4-2b-protocol-canary-20260914T155655Z.json` 中出现多条 sample entry（attempt 1/2 分开），导致 artifact 结构不是“一 sample → 多 attempts”。

11. **Rollback count 语义**
    `build_summary()` 使用每个 rejected attempt 累加 `repair_rollback_count`，属于 attempt-based legacy metric，不是 sample/root-cause-based。Executor 另有 root-cause/scene coverage 字段，但尚未在 canary artifact 中拆分为 attempt rejection、root-cause rollback、scene rollback、accepted root-cause。

## V2.4.2c 必要修复边界

- 新建 Repair IR Semantic Spec SSOT，并让 Validator、Provider Contract、System Prompt、FORMAT_REPAIR diagnostics、minimal skeleton 与测试从同一 spec 派生。
- 保持 strict/fail-closed，不接受空 list、空 string 或越界数值；仅增加 collect-all diagnostics 与旧异常 API 兼容。
- 为 performance request 提供 scoped `allowed_character_ids`，禁止虚构角色 ID。
- Canary 仅修复新 artifact 的 sample grouping/metrics/coverage 命名；不回写 V2.4.2b 历史 JSON，也不扩大样本或调用媒体链路。

## Final As-Built Verification

实现完成后验证时间：2026-09-14 16:42 UTC（本地执行环境时间戳）。

- Semantic Spec SSOT：PASS，版本 `director_tail_repair_semantic_spec_v1`。
- Validator、Provider Contract、System Prompt、minimal skeleton 均从同一 spec 派生：PASS。
- Collect-all diagnostics 与旧 `RepairIRSchemaError` 兼容：PASS；emotion 多错误可一次返回，performance empty array 返回 `EMPTY_ARRAY/minItems=1`。
- `allowed_character_ids` 已进入 scoped request，并对 performance `character_id` 做 fail-closed 校验：PASS。
- FORMAT_REPAIR packet 具备结构化 errors、typed constraints、minimal skeleton 与 allowed IDs：PASS。
- Canary sample grouping 已变为 one sample → multiple attempts；metrics 已拆分 attempt/root-cause/scene 语义：PASS。
- Provider-Free Hard Gate：PASS；完整本地回归 `1003 passed`。
- Real MiMo（仅冻结 4 samples，最多 8 attempts）：4 semantic attempts / 4 HTTP requests，4/4 First Pass、4/4 Final IR、4/4 Canonical Compile、4/4 Candidate Contract Pass；Fact Override Accepted=0、Request Echo=0、Unknown Provider Shape=0。
- 最终状态：`PROTOCOL_CANARY_PASSED`，`READY_FOR_TARGETED_TAIL_REEVALUATION=true`。未执行更大 Pilot、Production Shadow、图片/视频/对象存储链路。

历史 V2.4.2b JSON 保持不变；其中 `repair_rollback_count` 仍是 attempt-oriented legacy metric。
