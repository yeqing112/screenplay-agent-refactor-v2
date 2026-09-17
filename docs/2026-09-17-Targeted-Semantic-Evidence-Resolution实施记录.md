# Targeted Semantic Evidence Resolution 实施记录

## 目标与边界

本阶段在既有 SourceEvidenceIndex、FactSnapshot、MissingFactManifest 与 Fact Coverage gate 之上增加自然语言证据定位能力。检索只返回 immutable source anchors；解析先形成结构化 proposal，再经过 exact evidence 与 semantic support 校验，不能直接写入 FactSnapshot。默认 provider-free，不调用真实 LLM/MiMo 或媒体 Provider。

## 实现

- Candidate Anchor Retrieval：按 manifest item 的 entity/alias、predicate、expected value 对 SourceEvidenceIndex 锚点做确定性排序，返回原文、source hash、字符/字节偏移、词法命中、scope 与 ranking；支持单一明确前文实体的简单代词承接。
- Semantic Resolver：输出 `fact_key`、subject/predicate/scope、`proposed_value`、`supporting_anchor_refs`、`exact_quotes`、`resolution_type`、confidence、ambiguity 与冲突锚点；没有可验证锚点时保持 unresolved。
- Exact Evidence Verification：锚点、package/version、source hash、exact quote、offset、manifest scope 均重新校验；虚构 quote/anchor 直接拒绝。
- Semantic Support Validation：将“evidence 存在”和“evidence 支持事实”分离；仅 entity/predicate/value 明确共现或结构化声明可进入候选，Provider proposer 的输出仍需同一校验。
- Merge/coverage：通过既有 `merge_fact_snapshot_records` 与 `verify_fact_coverage`，不建立第二套 authority 或阈值；只有 coverage sufficient 才能打开 ScriptIR gate。

## 当前结果

对当前 6 个 required missing facts 的 provider-free 诊断由 runner 写入：

- `artifacts/director-quality-v3-targeted-semantic-evidence-resolution-result.json`
- `artifacts/director-quality-v3-targeted-semantic-evidence-resolution-stage.json`
- `artifacts/director-quality-v3-targeted-semantic-evidence-resolution-report.md`

若源材料无法定位事实，最终仍为 `FACT_COVERAGE_INSUFFICIENT` 与 `BLOCKED_PENDING_TARGETED_MISSING_FACTS`，不得猜测或降阈值。
