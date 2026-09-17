# Targeted Missing Fact Extraction 实施记录

## 目标与边界

本阶段在现有 FactSnapshot、Source Evidence Index 与语义 grounding 层上补齐定向缺失事实闭环。实现为 provider-free、确定性、fail-closed；不调用真实 LLM/MiMo、生图、视频或对象存储，不修改历史 Recanary 产物。

## 已实现

- `MissingFactManifest`：每项包含 fact key、semantic type、scope/entity、consumer、required/optional、missing reason、已有 evidence 状态、source scope、severity 与 dependency。
- Coverage Evaluator：区分 `ABSENT`、`INSUFFICIENT_EVIDENCE`、`AMBIGUOUS`、`CONFLICTED`、`INVALID`，只有 required 且无阻断项才返回 `FACT_COVERAGE_SUFFICIENT`。
- Targeted Extractor：只读取 manifest 指定事实；仅接受带 immutable anchor 的显式 `FACT:` 结构化声明。自然语言不足时返回 unresolved，不猜测。
- Evidence Validation：校验 schema、anchor locator、精确 excerpt、source hash、值支持、manifest 范围及现有 authoritative fact 冲突。
- Merge：existing authoritative fact 优先；候选不可静默覆盖；冲突与 unresolved 显式保留；新增记录产生新的 revision/payload hash；重复执行使用稳定 idempotency key。
- ScriptIR gate：绑定覆盖率不足快照时返回 `BLOCKED_PENDING_TARGETED_MISSING_FACTS`；只有 `FACT_COVERAGE_SUFFICIENT` 才允许 ScriptIR gate 打开。

## API

- `POST /api/books/{book_id}/episodes/{episode}/fact-coverage/missing-manifest`
- `POST /api/books/{book_id}/episodes/{episode}/fact-coverage/targeted-extract`
- `POST /api/books/{book_id}/episodes/{episode}/fact-coverage/recheck`

上述接口均为只读诊断/预览，不会创建 FactSnapshot 或触发外部调用。

## 当前证据

- required facts：6
- validated candidates：0
- unresolved：6
- merge：`NO_CHANGE`
- coverage：`FACT_COVERAGE_INSUFFICIENT`
- ScriptIR：`BLOCKED_PENDING_TARGETED_MISSING_FACTS`
- provider calls：0

这是合法的 fail-closed 结果，表示当前不可从 immutable source 中验证出所需结构化事实。下一阶段应补充真实可定位的源证据或执行单独授权的语义验证，不得降低 coverage 标准。
