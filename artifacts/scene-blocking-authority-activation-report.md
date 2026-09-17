# SceneBlocking Authority Contract — Activation Report

日期：2026-09-18  
分支：`codex/scene-blocking-authority-contract`  
基线：`d0a9e1f894da2b914db7f090e09bd780d142d0c9`  
Provider calls：**0**

## Baseline Audit

基线中的 SceneBlocking 生产路径可以从场景名/latest approved 行读取，且下游没有稳定的 scene pointer、exact FactSnapshot binding 或 authority envelope。旧的 `repair_scene_blocking()` 还存在以 validator 通过为由清空 unknowns 的风险。VisualLocation 的 name-only 记录也可能被误当作正式场景约束。

## Final As-Built Verification

本阶段已实现并验证：

- `scene_blocking_authority_contract_v1`：字段、authority class、变更策略、ShotPlan blocking 与 provenance 要求均由真实 ShotPlan consumer 反推。
- `scene_blocking_authority_envelope_v1`：绑定 ScriptIR、DirectorTreatment、exact FactSnapshot、scene asset、canonical payload、contract/validation fingerprints、qualification/stale 状态及激活时间。
- 生产 preview 只解析 current ScriptIR、current Treatment pointer 和 Treatment envelope 绑定的同一 FactSnapshot；不查询 latest confirmed FactSnapshot 作为权威。
- production SceneBlocking 需要 `scene_id` 绑定的 locked 且有 geometry 的 VisualLocation；name-only/空 scene_id legacy asset 仅为 advisory。
- continuity state 明确记录 character、scene、authority class、继承来源与 unresolved 项；geometry backlog 保持在 SceneBlocking authoring boundary，不回写 FactSnapshot。
- candidate 校验禁止修改 scene identity、source spatial facts、participant identity/entry/exit、beat identity/order 或 locked geometry；derived/blocking decisions 只能按白名单编辑。
- unknown 只有带 `RESOLVED_BY_SOURCE`、`RESOLVED_BY_AUTHORED_DECISION` 或 `RESOLVED_BY_DERIVATION` provenance 才能关闭，repair 不会静默清空 unknown。
- confirm 通过单事务创建 approved + `PRODUCTION_QUALIFIED` row、authority envelope 与 current pointer；失败不会更新 pointer。ShotPlan production 只消费该 pointer，缺失或 stale 即 409 fail-closed。
- resolver 对 payload/envelope tamper、ScriptIR/Treatment/FactSnapshot/asset lineage、contract/policy 变化执行 stale 标记并撤销 pointer。

## Verification Evidence

- SceneBlocking authority 专项：**10 passed**。
- SceneBlocking/ShotPlan/Storyboard invariant 关联回归：**25 passed**。
- Extended authority/ScriptIR/production-gate regression：**42 passed**。
- Full backend regression：**1471 passed, 11 failed, 921 warnings**。11 项均为既有历史 artifact/离线 replay/真实数据库样本/环境基线失败；本阶段新增 SceneBlocking authority 测试未产生全量回归失败。
- Frontend Vitest：**291 passed**；frontend production build：通过；Golden：**5/5**；runtime config verification：通过。
- `python -m py_compile api/scene_blocking_api.py api/shot_plan_api.py core/scene_blocking_authority.py`：通过。
- `alembic heads`：`r1a2b3c4d5e6`；新增 migration 可被识别为 head。
- 未调用真实 LLM、MiMo、Embedding、生图、视频或对象存储；未清理/覆盖历史产物。

## Remaining Downstream Backlog

- Storyboard Materializer 当前按已批准 ShotPlan 的 `blocking_id` 消费；其 authority envelope 深校验留待后续 ShotPlan/Storyboard authority 阶段，不在本阶段扩大范围。
- `core/production_policy.py` 的 legacy readiness 视图仍保留；production SceneBlocking/ShotPlan API 已采用更严格 pointer gate。
- Fresh DB migration baseline blocker `f05ab1af29bc` 仍存在：早期迁移可能对不存在的 `episode_outlines` 执行 drop。本阶段未修改历史 migration。

## Closure Decision

`SCENE_BLOCKING_AUTHORITY_CONTRACT_READY`。本阶段完成后不进入 ShotPlan 内容开发、Provider Canary、资产生成、Storyboard、Prompt Compiler 或媒体生成阶段。
