# Director Quality Benchmark V2 — Repository Audit

审计日期：2026-09-13
分支：`codex/unify-formal-workspace`
远程 HEAD：`d43a06d`（已核验与本地一致）
范围：Director Benchmark、ShotPlan、Camera Library、SceneBlocking V2、Executability、Qualification/Repair、Production Skill、DirectorTreatment、Pilot artifacts。

本审计阶段只读完成：未修改业务代码，未调用真实 LLM、图片、视频或对象存储。

## 1. 当前 ShotPlan 是否仍偏 deterministic template

是。`core/shot_plan.py::build_shot_plan()` 当前按每个 Treatment beat 生成一个镜头，镜头结构主要是固定模板：

- `purpose` 仅由 beat type 映射；未知类型回退为 `coverage`；
- `camera` 固定为 `MS / eye_level / static / slow / center`；
- `action_beats` 默认只把 beat event 放入首个动作；
- `entry_state`/`exit_state` 为通用参与者和最后事件；
- 没有基于场景目标、信息揭示、情绪递进或权力变化的镜头选择。

这条路径仍然具有重要价值：它是无 LLM 环境的 fallback、回归基线和失败恢复路径，不应删除或替换。

## 2. 当前 camera 默认值

当前每个 beat 的默认值为：

```json
{
  "shot_size": "MS",
  "angle": "eye_level",
  "movement": "static",
  "speed": "slow",
  "camera_side": "center"
}
```

默认时长为 `duration_seconds`，缺省 `4` 秒，并限制最小值为 `1` 秒。`core/camera_library.py` 已有较完整的标准镜头、景别、角度、转场和光影词库，但 ShotPlan builder 当前没有按导演意图消费该库。

## 3. Director Benchmark 当前实际检查项

`core/director_benchmark.py::score_runtime()` 当前只检查 7 项结构门槛：

1. DirectorTreatment approved；
2. Treatment beat_map 非空；
3. SceneBlocking approved；
4. SceneBlocking unknowns 为空；
5. ShotPlan approved；
6. 每个镜头存在 camera；
7. 每个镜头有正时长。

当前 `score` 是通过项比例，不是导演质量分。

## 4. 是否已有真正的导演质量指标

没有。当前没有：

- 镜头动机覆盖率；
- 情绪递进或信息策略评分；
- 表演指导覆盖率；
- 镜头重复/冗余率；
- 视觉叙事率；
- 景别/角度多样性指数；
- Blind Preferred Rate；
- 0–100 的 Director Quality Score。

现有 Pilot V1 的 `37/40` 和 `40/40` 是 Shot Qualification 指标，不能代表导演质量。

## 5. 可直接支持导演质量评分的字段

现有字段已经能支撑一部分评分与证据关联：

- DirectorTreatment：`dramatic_objective`、`audience_question`、`character_intents`、`beat_map`、`relationship_power_shift`、`audience_emotion`、`information_strategy`、`performance_direction`、`visual_strategy`、`coverage_strategy`、`edit_rhythm`、`constraints`；
- SceneBlocking V2：`participants`、`camera_axis`、`creative_decisions`、`derived_constraints`、`source_spatial_facts`；
- ShotPlan：`plan_shot_id`、`beat_id`、`purpose`、`dramatic_function`、`event`、`participants`、`camera`、`duration_hint_seconds`、`action_beats`、`entry_state`、`exit_state`、`continuity_contract`、`asset_bindings`；
- Camera Library：标准化 `shot_size`、运动、角度及其情绪/用途说明；
- Executability：动作时间预算、镜头运动和首尾状态的可执行性检查；
- Qualification/Repair：可保存候选、诊断、局部修复和 rollback fingerprint。

## 6. 仍缺失的创意字段

ShotPlan JSON 尚未稳定支持以下 Shot-level Creative Contract 字段：

- `why_this_shot`；
- `emotion.start/end/intensity`；
- `performance_direction`（目标、可见行为）；
- `composition`（主体、构图关系、负空间）；
- `edit`（cut reason、hold after action）；
- `information_strategy`（reveals、withholds、audience_focus）；
- 受控的 `auxiliary_shots`/reaction/insert 与其来源 beat；
- planner 的 `director_mode`、来源证据摘要、fallback 原因。

这些字段应先进入 ShotPlan JSON 或 `model_info/meta`，不必立即新增数据库列。

## 7. Controlled Director Creative Planner 应放在哪一层

应放在：

`Approved DirectorTreatment + Approved SceneBlocking V2 + FactSnapshot/SceneCanonical + Deterministic ShotPlan Candidate`
与
`Director ShotPlan Quality Validator / Executability`
之间。

建议新增 `core/director_creative_planner.py`：

- 输入上游已批准事实与结构；
- 只产生 Creative ShotPlan Candidate；
- 不直接写 ShotPlan approved、不触发媒体生成；
- 失败时返回明确的 `director_mode=deterministic_fallback`；
- 默认只运行在 shadow/benchmark mode，达标前不切 Production default。

## 8. 是否需要数据库 migration

Benchmark 与 planner 候选阶段不需要新的数据库 migration。现有 `ShotPlan.shots`、`model_info`、`evidence_fingerprint`、`schema_version` 足以保存候选和评分证据；Benchmark 报告使用 artifact 文件。

只有在后续需要按维度查询历史评分、Blind Review 结果或 planner 运行记录时，才考虑新增表。当前应避免迁移扩大范围，保留 Production Pipeline V2/SceneBlocking V2 已有迁移。

## 9. 如何保证 Production Pipeline 主链不被破坏

1. 保留 `core/shot_plan.py` 作为 deterministic baseline/fallback；
2. planner 仅在 shadow/benchmark mode 接线，不改变 production 默认；
3. validator 先检查事实不可变、beat 顺序、资产绑定、SceneBlocking source facts 和 executability，再评分创意质量；
4. LLM 只能修改白名单创意字段，任何事实越权统一 `DIRECTOR_FACT_OVERRIDE` 并 fail-closed；
5. 有限增加 reaction/insert/establishing/transition，按 beat 限制 0–2 个并保留来源；
6. 失败时回退 deterministic candidate，并在 metadata 标明 fallback，不伪装成 planner 成功；
7. 不修改 Production Gate 阈值，不调用图片/视频/对象存储。

## 10. 建议实施文件清单

新增或修改范围应保持最小：

- `core/director_creative_planner.py`（新增）；
- `core/director_quality_validator.py`（新增）；
- `core/director_benchmark.py`（保留结构评分，增加独立质量评分 API）；
- `core/shot_plan.py`（只增加兼容 creative contract 投影，不改变 baseline 默认）；
- `api/shot_plan_api.py`（增加 shadow/benchmark 预览与候选确认门禁，不默认切生产）；
- `core/qualification_loop.py` / `core/repair_ledger.py`（复用现有 ledger，target_layer=`DIRECTOR_CREATIVE`）；
- `models/shot_plan.py`（原则上无需改列）；
- `tests/` 下新增 planner、validator、benchmark、fallback、集成测试；
- `artifacts/director-quality-v2-golden-scenes.json`、`director-quality-v2-report.md`、`director-quality-v2-metrics.json`。

## 11. 测试清单

### Unit

- creative contract schema 与白名单；
- `DIRECTOR_FACT_OVERRIDE` fail-closed；
- SceneBlocking `SOURCE_FACT` 不可覆盖；
- camera repetition detector；
- motivated shot validator；
- redundant shot detector；
- 十维评分与权重；
- director local repair 与 RepairAttempt ledger；
- planner 失败 deterministic fallback。

### Integration

`Approved Treatment → Approved SceneBlocking V2 → Baseline ShotPlan → Controlled Planner Candidate → Quality Validator → Executability → Materializer`，确认 planner 不修改上游事实、不直接生成媒体。

### Regression

- Production Pipeline V2 现有后端回归；
- SceneBlocking V2 回归；
- Golden Regression `5/5`；
- 前端仅在 API/类型受影响时构建并回归。

## 12. Pilot 执行计划

1. 从《潮汐回声》现有三集及已有 fixture 选择至少 8 个场景，覆盖双人对话、悬疑、信息揭示、情绪转折、权力变化、人物入场、关键道具、少对白/无对白；
2. 生成 Golden Scene 清单，记录 `scene_id`、类型、选择理由和导演挑战；
3. 对每个场景用完全相同的 Qualified ScriptIR、FactSnapshot、Treatment、SceneBlocking 生成 Version A（当前 deterministic baseline）与 Version B（controlled planner）；
4. 先运行 deterministic structural/creative validators，再执行 blind review 数据结构；评分器不得知道 A/B 来源；
5. V2 实现和本地测试全部通过后，才允许仅对 Golden Scenes 做真实 MiMo 调用；禁止图片、视频、对象存储；
6. 每次真实调用记录 stage、scene、model、request fingerprint、prompt/cached/completion tokens、latency、retry、status；
7. 输出 `director-quality-v2-report.md` 与 `director-quality-v2-metrics.json`，真实报告必须同时展示 baseline、planner、失败案例、幻觉/越权和 fallback。

## Baseline 结论

当前系统的结构生产链已稳定，但导演质量仍主要由固定镜头模板决定。下一阶段的正确边界是“受控创意候选 + 程序事实/结构/可执行性验证 + 可回退 baseline”，而不是改写 Production Pipeline 或放宽门禁。Audit 完成后再开始实现。

## 13. Final As-Built Verification（2026-09-13）

本节与上方 Baseline Audit 分开记录，表示本轮实现后的实际状态。

### 已落地

- 新增 `core/director_creative_planner.py`：受控导演创意候选、白名单字段、事实投影校验、有限辅助镜头、显式外部调用门槛和 deterministic fallback。
- 新增 `core/director_quality_validator.py`：十维导演质量评分，以及 `CAMERA_REPETITION`、`UNMOTIVATED_SHOT`、`REDUNDANT_SHOT`、`EMOTIONAL_FLATLINE`、`POWER_SHIFT_NOT_VISUALIZED` 诊断。
- 新增 `core/director_local_repair.py`：仅允许 `DIRECTOR_CREATIVE` 路径的 bounded repair，并可接入既有 `RepairAttempt` ledger。
- `core/issue_router.py` 增加导演创意层路由；未识别的创意问题仍保留 `DIRECTOR_QA`，不扩大兜底范围。
- `core/director_benchmark.py` 保留 Structural Quality，同时独立输出 `director_quality_score`、十维分数和 KPI；没有修改生产门禁阈值。
- 新增 ShotPlan shadow/benchmark API：`shot-plan/creative-preview`、`shot-plan/creative-llm-draft`（默认不调用外部模型，后者必须 `confirmed=true + allowExternalCall=true`）。
- 新增 Director Benchmark compare API 与盲评结构；不写入 approved ShotPlan，不触发 Storyboard/媒体生产。
- 新增 `scripts/run_director_quality_v2_benchmark.py` 与 8 个 Golden Director Scenes、报告和指标 artifact。

### 不变与安全边界

- `core/shot_plan.py` deterministic baseline 未删除、未改为 LLM 默认路径。
- Production Pipeline V2、SceneBlocking V2、Materializer、Prompt Compiler、Qualification Loop 主链未重构。
- Production Materializer 反向测试继续 mock `StoryboardAgent.run()`；生产正常路径调用次数为 0。
- 事实、beat 顺序、资产绑定、首尾状态、连续性合同和 production-critical chronology 的越权会 `DIRECTOR_FACT_OVERRIDE` 并 fail-closed。
- 本轮未调用真实 LLM、MiMo、生图、视频或对象存储；未处理 GitHub Actions/CI；未清理历史产物。

### 本地验证证据

- 后端全量：`728 passed`。
- 前端 Vitest：`49 files / 291 tests passed`。
- 前端生产构建：`npm run build --prefix web` 成功。
- Golden artifact：8 个场景，`provider_calls=0`、`media_calls=0`、`object_storage_calls=0`，`fact_override_count=0`。
- 离线 shadow 对比：Baseline 平均 `41.91`，Planner surrogate 平均 `86.13`，平均差值 `+44.22`；该结果不能替代真实 LLM blind judge。

### 尚未宣称完成的项目

- 真实 MiMo Golden Scene Pilot 尚未执行（当前仍是离线收口阶段）；因此尚不能据此把 Planner 切换为 Production default，也不能宣称达到 Media Production Pilot。
- Blind review 已提供 Version A / Version B 数据结构，但尚未有真人或独立 Judge 偏好样本，`preferred_rate` 保持 `null`。
