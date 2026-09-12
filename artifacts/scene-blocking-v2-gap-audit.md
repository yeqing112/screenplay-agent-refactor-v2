# SceneBlocking V2 — Fact / Creative Spatial Authority Gap Audit

审计日期：2026-09-13
远程基线：`codex/unify-formal-workspace` @ `b624c42`
范围：SceneBlocking、FactSnapshot、DecisionPacket、Production Policy、Qualification/Repair、ShotPlan、Visual 资产及 Real Production Pilot V1 证据。
本阶段只做审计，不修改业务代码，不调用真实 MiMo、生图、视频或对象存储。

## 1. 当前 V1 实际数据结构

`models/scene_blocking.py` 的 `SceneBlocking` 目前以 JSON 文本列保存：

- `participants`：`character_id/name/position/facing/anchor/source`；
- `beat_transitions`：`beat_id/event/blocking_change/entry_state/exit_state`；
- `spatial_rules`、`unknowns`、`evidence_fingerprint`、`model_info`；
- 兼容状态字段：`status`、`execution_status`、`quality_status`、`production_status`、`workflow_profile`；
- 上游引用：`treatment_id/treatment_revision/source_script_hash`。

`core.scene_blocking.build_scene_blocking()` 只读取 ScriptIR scene 的 `character_blocking`/`blocking`，再按 Treatment 的 `character_intents` 生成参与者。当前没有 `space`、`source_spatial_facts`、`creative_decisions`、`derived_constraints` 或独立 `validation` 字段，也没有 authority 枚举。

## 2. `SPATIAL_UNKNOWN` 的实际触发条件

当 Treatment 声明的任一角色在 ScriptIR scene 的 `character_blocking`/`blocking` 中找不到匹配项，或匹配项没有 `position`、`screen_position`、`blocking` 文本时，V1 写入 `未声明 {name} 的画面位置`，并将 `source` 设为 `missing`，整体状态变为 `needs_information`。`api/shot_plan_api.py` 随后对 approved blocking 的 `unknowns` 做硬阻断。

因此，V1 把“原文没有写屏幕左右/机位/轴线”的创作空白，与“门、楼层、道具位置等生产事实不成立”的事实缺失放进了同一个 `unknowns` 数组。

## 3. Pilot 证据中的 authority 分类

《潮汐回声》E1 两场原始 `SPATIAL_UNKNOWN` 均来自人物未声明画面位置：

- `红伞幻影（一）`：原文/Qualified ScriptIR 没有角色 screen side、camera side 或轴线事实；属于 `CREATIVE_CHOICE`，不应要求用户补录左右站位。
- `红伞幻影（二）`：同样没有角色 screen side、camera side 或普通走位路线；属于 `CREATIVE_CHOICE`，不应直接阻断。

E1 的事实层另有一条 `gushen-age` 冲突，但它不是上述空间 blocker；若该事实进入本场景的生产关键约束，仍应按 `FACT_CONFLICT` 保持 fail-closed。

仍应保持 blocker 的事实类型：入口/出口或楼层在 SceneCanonical 中不存在且无法映射；剧情依赖但资产注册表没有的关键结构；同一时间互斥位置；与上一镜硬冲突的角色/道具状态。这些属于 `SOURCE_FACT` 或 `DERIVED_CONSTRAINT` 失败，不应降级成 warning。

## 4. 现有 FactSnapshot 是否可复用

可以复用，但不应新造 Fact 系统。`core.fact_snapshot` 已有 authority（`source_text/locked_fact/approved_fact/derived_fact/model_observation`）、`confirmed/proposed/conflict/unknown` 状态和 `blocking_unknown/assumable_unknown/creative_unknown` 分类函数。需要在 SceneBlocking 入口增加空间谓词投影：

- 已确认的位置、入口、出口、角色/道具状态投影为 `SOURCE_FACT`；
- 没有事实约束但属于导演调度的字段不写入 FactSnapshot 的“事实”，而作为 `CREATIVE_CHOICE`；
- 互斥或不可映射的空间事实继续生成 `conflict`/`blocking_unknown`。

## 5. 现有 DecisionPacket 是否可复用

可以复用。`core.decision_packet` 已提供 domain、scope、evidence、unknowns、conflicts、allowed_operations 和稳定 fingerprint。SceneBlocking V2 应把 Step A/Step B 的证据和允许的导演操作放入现有 `domain=storyboard` 或 `domain=continuity` packet，不应另建平行决策包。当前 V1 API 尚未为 SceneBlocking 建立 packet，也没有把 authority 分类暴露给前端或审计。

## 6. SceneCanonical 可提供的空间证据

当前仓库没有名为 `SceneCanonical` 的独立模型；等价证据位于 `VisualLocation`：

- `canonical_facts`：可锁定的场景身份、固定结构、空间事实；
- `state_variants`：时间/状态变化；
- `look_profile`：视觉风格，不应被当作位置事实；
- `board_spec`：场景参考板、固定物件和空间关系的扩展载体；
- `key_props`、`description`、`lighting_mood` 等 legacy 字段作为兼容回退。

这些字段足以提供 anchors/zones/entrances/exits/fixed objects 的语义来源，但当前 SceneBlocking 未读取 `VisualLocation`，也未校验 anchor 是否存在。`VisualProp` 的 `canonical_facts/state_variants` 可提供道具状态和交互约束。

## 7. 需要修改的文件

最小改动范围：

1. `core/scene_blocking.py`：拆分 Spatial Evidence Extraction、Director Spatial Planning；加入 `SOURCE_FACT/CREATIVE_CHOICE/DERIVED_CONSTRAINT` 和 V2 语义字段。
2. `api/scene_blocking_api.py`：组装 FactSnapshot、ScriptIR、VisualLocation/VisualProp、Treatment evidence；调用 V2 validator、保留 V1 payload 兼容；审批时冻结 source facts。
3. `models/scene_blocking.py`：优先使用兼容 JSON `spatial_model`/`authority` 扩展列，或在 `meta_info` 中版本化存储；保留旧列读取。
4. `core/qualification_loop.py`、`core/local_repair.py`、`core/issue_router.py`：接入空间 validator 的责任层 repair，并写入运行时 Repair Ledger。
5. `core/decision_packet.py`、`core/fact_snapshot.py`：只做 authority 映射/证据引用扩展，不新造系统。
6. `core/shot_plan.py`：仅适配新的 approved blocking 字段，不重写 ShotPlan；保留已有 V1 兼容输出。
7. `models/visual.py`：原则上无需迁移，复用 VisualLocation/VisualProp 的分层字段。

## 8. 是否需要 Alembic migration

建议需要一个向后兼容的小迁移，原因是运行时 Repair Ledger 需要稳定持久化且 V2 需要可查询的空间模型/authority，而不是长期只塞在不可索引的临时 artifact。迁移不应删除旧列或重写历史数据；可新增 nullable 的 `spatial_model`、`source_spatial_facts`、`creative_decisions`、`derived_constraints`、`validation`（或一个版本化 JSON `spatial_payload`）以及统一 RepairAttempt 表/关联。

如果实现阶段确认现有 `meta_info` 或既有审计模型足以持久化并查询这些字段，则可以不增加 SceneBlocking 列，但必须在设计记录中证明兼容性，并仍为 RepairAttempt 提供正式表或等价持久化模型。迁移应只给新记录写 `scene_blocking_v2`，旧记录保持 V1，不批量标 stale。

## 9. 兼容策略

- V1 读取：没有 V2 payload 时，将 `participants.position/facing/anchor` 视为 legacy source evidence；不得把缺失的屏幕左右自动算作事实 blocker。
- V2 写入：同时保留旧列和 `schema_version=scene_blocking_v2` 语义 payload；`status`/四类状态字段继续由 Production Policy 管理。
- 已批准 E2/E3 blocking 不因兼容改造自动 stale；只有 source fingerprint 或锁定事实变化才重新验证。
- `creative_draft` 可继续输出预览，但 `production` 必须通过 V2 authority validator；不得以 V1 fallback 绕过生产门禁。

## 10. 当前差距结论

V1 的主要问题不是阈值过严，而是 authority 建模缺失：它把导演应该决定的空间自由度当成了用户必须补齐的事实。下一阶段应先在确定性 Step A 提取事实，再在 Step B 生成带 `CREATIVE_CHOICE` 标记的导演调度，最后由 validator 只阻断真实事实冲突和派生约束冲突。完成 V2 schema/validator 与兼容测试后，才允许对 `990402/E1` 做定向真实 MiMo 复跑；本审计阶段不调用外部模型。

## Final As-Built Verification（SceneBlocking V2 implementation checkpoint）

本节与上面的 Baseline Audit 分开记录；Baseline 内容不回写、不覆盖。

- 新增 `scene_blocking_v2` 兼容 payload，保留全部 V1 JSON 列；旧记录仍按 V1 读取，不批量 stale。
- `extract_spatial_evidence()` 只投影 ScriptIR、FactSnapshot 与 VisualLocation 中已有空间事实；`plan_director_spatial()` 单独生成导演选择，并明确标记 `CREATIVE_CHOICE`；程序派生约束标记 `DERIVED_CONSTRAINT`。
- 生产工作流请求 `workflow_profile=production` 时默认使用 V2；未声明 screen-left/right、摄影机侧或 eyeline 不再自动产生 blocker。事实冲突、非法来源锚点、非法参与者/轴线仍 fail-closed。
- 新增 `validate_scene_blocking()` 与有界 `repair_scene_blocking()`；修复只允许作用于创作/派生字段，Source Fact 不可覆盖。
- 新增 `repair_attempts` 表和 `RepairAttempt` 模型；持久化草案发生局部修复时写入运行时记录，包含 issue、层级、指纹、尝试次数和复核状态。
- 生产 Storyboard Materializer 增加 SceneBlocking unresolved/validation 门禁及 ShotPlan cardinality/plan_shot_id 映射校验，仍不会调用 `StoryboardAgent.run()`。
- 指标工具 `core/pilot_metrics.py` 将 approval gate、手工编辑和分层 repair yield 拆开，拒绝重新引入歧义的 `human_intervention_rate`。

本地验证结果（未调用真实 LLM、生图、视频或对象存储）：

- 后端全量：`721 passed`
- SceneBlocking V2 单元/API：`9 passed`
- Production Materializer gate：`5 passed`
- Golden Regression：`5/5`
- Release-gate parser 单测：`passed`
- 前端构建：`npm --prefix web run build` 成功

Episode 1 的 V1b 定向复跑报告将在上述实现验证通过后单独追加，绝不覆盖 Pilot V1 产物；由于本轮链路复用已批准输入且 SceneBlocking V2 为确定性阶段，不需要新增 MiMo 调用。

## Final As-Built Verification（Pilot V1b）

已对 `book_id=990402 / Episode 1` 使用现有 Qualified ScriptIR 与 Approved DirectorTreatment 做定向本地生产链复跑。SceneBlocking V2、ShotPlan、Materializer、Prompt Compiler Phase A 和 Qualification 均未调用外部供应商；因此本次新增 MiMo 调用数为 0，不产生费用，也不改变历史 Pilot V1 数据。

- 原 Episode 1 的 2 个 `SPATIAL_UNKNOWN` 均属于“原文未规定画面左右/摄影机侧/普通走位”的 `CREATIVE_CHOICE` 缺口，不是必须向用户追问的事实；V2 自动生成 2/2 场景的导演空间选择。
- SceneBlocking V2：2/2 `ready_for_review`；SOURCE_FACT 数量按现有证据保留，未新增 SOURCE_FACT。
- ShotPlan：16 个镜头；Materializer 映射 16/16，`plan_shot_id` 一一对应；Phase A 16/16；Qualification 首轮 16/16、最终 16/16。
- 三集聚合 Scene Pipeline Completion：从 Baseline `4/6 = 66.7%` 提升至 `6/6 = 100%`。
- 三集聚合 Episode Pipeline Completion：从 Baseline `2/3 = 66.7%` 提升至 `3/3 = 100%`。
- 三集聚合镜头口径：已有 E2/E3 40 个镜头 + E1 16 个镜头 = 56；First-Pass `53/56 = 94.64%`（E1 16/16）；Final `56/56 = 100%`。
- 人工空间编辑：0；新增无来源事实：0；真实图片/视频/对象存储调用：0。
- Runtime Repair Ledger：V2 本地复跑未触发修复；新增运行时记录模型已通过持久化路径测试。历史 V1 ledger 保留不覆盖。

证据：

- `artifacts/real-production-pilot-v1b-ep1-blocking-v2-report.md`
- `artifacts/real-production-pilot-v1b-ep1-blocking-v2-metrics.json`
