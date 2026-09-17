# SCRIPT_IR_AUTHORITY_ACTIVATION — Final Local Report

日期：2026-09-18
执行基线：`49a7711a78163577ec109973f334a970630f520c`
Provider calls：`0`

## 结论

本阶段已完成本地确定性收口：`immutable source + approved FactSnapshot + ScriptIR Source Requirement Contract → PRODUCTION_QUALIFIED ScriptIR`。生产路径没有进入 DirectorTreatment、SceneBlocking、资产生成或 ShotPlan；历史用户产物未清理、覆盖或迁移。

## 权威协议

| 项目 | 实现 |
| --- | --- |
| Envelope | `script_ir_authority_envelope_v1` |
| Qualification | `STRUCTURALLY_VALID → SOURCE_COVERAGE_QUALIFIED → AUTHORITY_BOUND → PRODUCTION_QUALIFIED` |
| Source | package/version、raw SHA-256、可重建 SourceEvidenceIndex fingerprint、anchor offsets/lineage |
| Facts | FactSnapshot id、book/episode、revision、records payload hash、confirmed 状态、source fingerprint |
| Contract | `script_ir_source_requirement_contract_v1` + compiled requirement-set fingerprint + coverage fingerprint |
| Pointer | production 只读 `Script.current_script_ir_version_id`，不再 fallback 到最新 qualified |
| Tamper | payload/envelope/source index/FactSnapshot records 不一致时 409 fail-closed |

## 关键行为

- 新增 `POST /api/books/{book_id}/episodes/{episode}/script-ir/activate`；校验通过后在一个事务内写入 envelope、将 draft 标记为 `production_qualified` 并原子更新 current pointer。
- `未命名场景N`、缺失 anchor、错误 source hash、错误 book/episode FactSnapshot、过期 draft、覆盖 payload 均不能激活。
- production resolver 每次读取重新计算 source index、FactSnapshot records hash、coverage、contract/requirement fingerprints，并验证 envelope fingerprint、payload hash、anchor bindings 和 stale 状态。
- Storyboard Materializer 与 Asset Registry production 入口复用 resolver；`status=qualified` 不能绕过 authority。creative_draft 兼容路径保留。
- activation 不删除 downstream backlog；后续仍可从 episode authority context 消费。

## 测试证据

- Authority activation + ScriptIR + SceneBlocking + Materializer + Compiler + Asset Registry 关联专项：**29 passed**。
- 覆盖成功激活、anchor/index 校验、placeholder、draft/source stale、FactSnapshot revision/payload/source 变化、contract/requirement-set 变化、payload tamper、wrong snapshot、pointer no-fallback、失败不更新 pointer，以及 `StoryboardAgent.run()` 反向 mock 调用次数为 **0**。
- 全量后端：**1446 passed，11 failures，907 warnings**。失败均为历史 artifact/环境基线（Director Quality 历史字段漂移、旧离线回放元数据、已退休 provider/dirty-worktree 断言、无迁移历史 real-database pilot、固定测试 book 的残留快照）；本阶段专项及关联生产门禁无失败。
- 前端 Vitest：**49 个测试文件、291 passed**；`npm --prefix web run build` 通过。
- Golden：`npm run test:golden` **5/5 passed**。
- `npm run gate:production` 按 fail-closed 规则保持 **BLOCKED**：当前环境为 development、production sample registry 缺少 active `990400`、active shot 为 0/30，且脚本/真实浏览器子步骤等待 `http://127.0.0.1:18765/health` 超时；这些是发布环境/样本前置条件，不是本阶段 authority 代码失败。
- 未执行 GitHub Actions/CI；未调用真实 LLM、MiMo、Embedding、生图、视频或对象存储。

## 阶段状态

`SCRIPT_IR_AUTHORITY_ACTIVATED`
`qualification_state=PRODUCTION_QUALIFIED`
`stale_status=FRESH`（激活时）
`production writes=0`（真实生产媒体）；仅测试事务写入 authority 版本与 pointer。

下一阶段建议：`DIRECTOR_TREATMENT_AUTHORITY_CONTRACT`，等待新的阶段授权后再进入。
