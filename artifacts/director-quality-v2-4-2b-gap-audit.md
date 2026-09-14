# Director Quality V2.4.2b — Canary Coverage & First-Pass Context Gap Audit

审计日期：2026-09-14
基线：远程 `codex/unify-formal-workspace` @ `a0582074c8776d32e36560fc8dc773b635aedd08`
范围：仅审查 V2.4.2 Provider Contract Canary 的样本选取、修复上下文、Provider request 投影和 provenance；不修改 Frozen B2、不调用任何外部供应商。

## 1. 审计结论

V2.4.2 的 Provider/Executor contract 已对齐，但 Canary 只覆盖了 1 个 `edit` 样本，不能代表多 repair-type 的 MiMo 稳定性。当前实现还存在三个通用缺口：

1. Manifest 直接读取 `row.tail_repair.root_causes`，而不是复用 Executor 使用的 `rank_tail_root_causes_v2()`；Frozen B2 中大量 `tail_repair.root_causes` 被压缩为 `WEAK_EDIT_STRATEGY`，导致选样偏差。
2. Executor 首轮 request 的 `relevant_beats`、`relevant_shots` 均由 runner 显式置空，且没有正式的 `allowed_plan_shot_ids`；Provider 被要求引用输入中的镜头 ID，却没有得到可引用镜头，形成上下文矛盾。
3. `with_attempt()` 为兼容历史调用继续把 `attempt_kind`、`previous_raw_output`、`previous_validation_errors` 投影到顶层；Canary trace 没有把 request fingerprint 从实际 request/audit 链路带出，旧结果因此显示为空字符串。

## 2. 旧 Manifest 为什么只有一个 edit sample

旧 builder 只遍历 Frozen B2 每行的 `tail_repair.root_causes`，并且要求该字段的 root cause 同时能映射到 `REPAIR_SCOPES` 与 `ROOT_CAUSE_TYPES`。真实 Frozen B2 的 triggered rows 大多只记录 `WEAK_EDIT_STRATEGY`，即使同一行的 coverage/quality evidence 能被 ranker 识别出其他候选，也不会进入候选集。最终经过“一种 repair_type 一个样本、同一 scene 不重复”的选择规则，只留下 `V21_FIXTURE_01 / WEAK_EDIT_STRATEGY / edit`。

这不是 Frozen 数据只有一个可修原因，而是 selector 使用了过窄的历史摘要字段。

## 3. Authoritative ranking 的实际覆盖

对 Frozen B2 24 个 scene 直接复用 `rank_tail_root_causes_v2()`，再限制为 `tail_repair.triggered=true`、有完整 evidence candidate/contract、`REPAIR_SCOPES` 可修且 `ROOT_CAUSE_TYPES` 可映射后，得到：

- `edit`：12 个 scene-level candidates（主要来自 `WEAK_EDIT_STRATEGY`）；
- `emotion`：12 个 scene-level candidates（来自 `WEAK_EMOTION_ARC`）；
- `information`：12 个 scene-level candidates（来自 `WEAK_INFORMATION_STRATEGY`）；
- `performance`：19 个 scene/root-cause candidates（来自 `WEAK_EMOTION_ARC` 或 `PERFORMANCE_DIRECTION_WEAK`）；
- `camera`：0 个。

因此 Frozen B2 + Phase B2 evidence 可以确定性提供四类（edit/emotion/information/performance）的更多合法样本；`camera` 当前没有足够的 `shot_diversity_index` 或其他 camera-specific evidence，不能伪造样本。V2.4.2b 应报告 `available_repair_types=[edit, emotion, information, performance]`、`missing_repair_types=[camera]`，并以四类为目标覆盖。

## 4. First Attempt 上下文为什么为空

`scripts/run_director_quality_v2_4_targeted_tail_pilot.py` 当前为每个 scene 构造 record 时固定写入：

```json
{"relevant_beats": [], "relevant_shots": []}
```

Executor 的 `_minimal_context()` 会忠实地把这两个空数组交给 `build_repair_request()`；旧版本没有 root-cause scoped resolver，也没有把 opportunities 的 `beat_id` 映射回 treatment beat 或 structural candidate shot。`allowed_plan_shot_ids` 只在 `FORMAT_REPAIR` attempt payload 中临时出现，首轮不存在。

这使首轮 request 同时要求 Provider 产生非空 `shot_decisions`、且只能引用输入镜头 ID，却没有提供镜头上下文或合法 ID 集合。

## 5. 第一次 MiMo 是否知道合法 plan_shot_id

从 Frozen evidence 的 structural candidate 可以读取合法 `plan_shot_id`；系统内部也能在生成 `before_candidate` 时得到这些 ID。但旧首轮 Provider-facing request 没有暴露 `relevant_shots` 或 `allowed_plan_shot_ids`，因此不能证明 MiMo 在第一次调用时知道哪些 ID 可用。旧 `FORMAT_REPAIR` 才加入 `allowed_plan_shot_ids`，第二次随即生成合法 IR。

## 6. FORMAT_REPAIR 新增的信息

相较首轮，旧实现的第二次 request 在 `attempt` 中新增了：

- `previous_raw_output` 与 `previous_validation_errors`；
- `required_output_schema=director_tail_repair_ir_v1`；
- `allowed_plan_shot_ids`。

其中真正修复协议可执行性的关键是合法镜头 ID 集合和明确 schema；前两项用于解释失败，但不应再作为 Provider-facing 顶层兼容字段发送。

## 7. request_fingerprint 为什么在旧 Canary trace 为空

`build_repair_request()`/`with_attempt()` 实际会计算 `request_fingerprint`，但旧 Canary 汇总只从 provider call wrapper 的 request projection 读取，未把该字段稳定复制到 trace，也未记录独立的 base/attempt/provider 三层 fingerprint。真实结果文件是在该 provenance wiring 修正前生成的，因此 `request_fingerprint`、IR fingerprint 和 canonical patch fingerprint 为空；该历史结果不能事后伪造回填。

## 8. Provider-facing request 是否暴露 legacy 顶层字段

是。当前 `with_attempt()` 为兼容旧调用在顶层追加：

- `attempt_kind`；
- `previous_raw_output`；
- `previous_validation_errors`。

真实 Provider 接收的是序列化后的整个 request，因此这些字段会随请求发送。它们与权威的 `attempt` 对象重复，可能造成模型把 request echo 当成输出协议、误把历史响应当成当前输入，增加 `REQUEST_ECHO` 或格式污染风险。需要在 Provider boundary 使用显式 sanitizer，仅发送 authoritative request fields，并把 retry 细节留在 `attempt` 对象内。

## 9. 审计后的改造边界

后续实现必须：

- Manifest 复用 `rank_tail_root_causes_v2()` 的同语义输入，不创建第二套 detector；
- 新增确定性的 root-cause scoped context resolver，填充 bounded opportunities/beats/shots 与 `allowed_plan_shot_ids`；
- 将 `allowed_plan_shot_ids` 纳入 authoritative request schema，首轮即存在；
- 增加 Provider request sanitizer，移除 legacy 顶层 retry projection；
- 分离 base/attempt/provider request fingerprint，并让 Canary trace 全部非空；
- 只有 Provider-Free Hard Gate 覆盖至少 2 类 repair type 后，才允许本次授权的真实 MiMo Canary。

本审计完成后，才进入代码修改阶段。

## Final As-Built Verification（2026-09-14）

### Baseline Audit 与修复范围

- Baseline 结论保持不变：旧 Canary 只覆盖 1 个 `edit` 样本，首轮 request 缺少镜头上下文，Provider boundary 暴露 legacy retry 顶层字段，旧 trace 的 request fingerprint 为空。
- 本轮没有修改 Frozen B2、canonical patch contract、IR Validator、Director Quality scorer 或任何生产/媒体链路。

### 已实现的不变量

- Manifest selector 已复用 `rank_tail_root_causes_v2()`；真实 Frozen B2 得到 4 类可用 repair types（edit/emotion/information/performance），camera 明确报告为 missing。
- 新增 deterministic `resolve_tail_repair_context()`：按 root cause 选择最多 5 个 opportunities、3 个 beats、4 个 shots；opportunity beat 优先映射到同 beat 的 structural shot，无法映射时使用可解释且稳定的 root-cause fallback。
- `director_tail_repair_request_v1` 首轮即携带 `allowed_plan_shot_ids`；Provider-facing serializer 移除 `attempt_kind`、`previous_raw_output`、`previous_validation_errors` 等 legacy 顶层字段。
- base/attempt/provider request fingerprint 已分层记录；所有本轮真实请求 trace 均非空。

### Provider-Free Hard Gate

- Manifest：4 个样本、4 个 repair types、`FULL_TYPE_COVERAGE`。
- 首轮 relevant shots 非空率：100%；allowed plan shot IDs 非空率：100%。
- Sanitizer、fingerprint consistency、Provider/Executor contract、`json_parse_retries=0`、canonical/fact boundary：全部 PASS。
- 后端完整 regression：997 passed；V2.4.2b/相关专项：27 passed；Golden 5/5；前端 291 passed、构建通过。
- 所有副作用计数：0。

### Real MiMo Canary

- 授权范围内执行 4 samples、最多 8 semantic attempts；实际 6 次 semantic/provider HTTP requests，transport retry 0、parser retry 0。
- First Pass：2/4（50%）；Final IR：2/4（50%）。edit 与 information 首轮通过，emotion 与 performance 首轮及 FORMAT_REPAIR 均未通过严格 IR 校验。
- 对最终合法 IR，Canonical Compile 2/2、Candidate Contract Pass 2/2；Fact Override Accepted 0、Request Echo 0、Unknown Provider Shape 0；fingerprint 6/6 非空。
- 因 First Pass <80% 且 Final IR <100%，最终门禁为 **`PROTOCOL_CANARY_FAILED`**，不得进入 `READY_FOR_TARGETED_TAIL_REEVALUATION`，不得自动执行更大 Pilot。

### Closure decision

V2.4.2b 的覆盖、上下文、Provider request 投影和 provenance wiring 已完成并通过本地验证；真实 MiMo 的多类型协议稳定性未达门槛，必须保留失败状态并等待新的修复/授权。全程未生成图片/视频、未写 Production/Storyboard/Shadow、未访问对象存储或 CI，历史产物未清理或覆盖。
