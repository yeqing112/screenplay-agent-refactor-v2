# Real Production Pilot V1：潮汐回声

日期：2026-09-13
项目：`book_id=990402`，第 1–3 集
执行 profile：`production`；允许真实 MiMo；禁止真实生图、视频和对象存储。

## Executive Summary

Production 内容链已验证到 Materializer、Prompt Compiler Phase A 和 Qualification Loop：第 2 集与第 3 集共 40 个镜头完成确定性物化，Phase A `pass=40/40`，最终 Qualification `qualified=40/40`。3 个镜头首轮被 ShotPlan 动作预算阻断，局部修复后全部通过，因此首次无需修复的合格率为 `37/40 = 92.5%`。第 1 集在 SceneBlocking 层因两场人物空间位置未声明而 fail-closed，未继续生成 ShotPlan，也未物化镜头。当前 Pilot 不是媒体生产放行：所有已物化镜头的 `production_status` 仍为 `blocked`，原因是本轮明确禁止媒体与对象存储调用。

## 测试项目与实际执行链

样本为新导入的真实小说《潮汐回声》（`book_id=990402`），不复用 `990401`，执行第 1–3 集。每集均按以下 production 路径运行：

`Novel/Source → Fact Resolver → FactSnapshot → ScriptIR → Script Validation → Local Repair（如需） → Qualified ScriptIR → Asset Registry Sync → DirectorTreatment → SceneBlocking → ShotPlan V2 → Executability Preflight → Local Repair（如需） → Approved ShotPlan → Storyboard Materializer → Prompt Compiler Phase A → Qualification Loop → Final Prompt`

Production profile 下未调用 `StoryboardAgent.run()`；Materializer 只接受 Approved ShotPlan 的确定性投影。事实/结构 blocker 先保留原始 Candidate、Validation、Repair 和 Final 证据，再决定是否继续下游。

## 分集结果

| 集数 | ScriptIR | Treatment | Blocking | ShotPlan / 镜头 | Phase A | Qualification | 结论 |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | qualified（1 次修复） | 2 场 approved | 0 approved / 2 needs_review | 0 | 0 | 0 | 被 `SPATIAL_UNKNOWN` 阻断 |
| 2 | qualified | 2 场 approved | 2 场 approved | 2 / 19 | 19/19 pass | 19/19 | 内容链通过，媒体 readiness 未执行 |
| 3 | qualified（1 次修复） | 2 场 approved | 2 场 approved | 2 / 21 | 21/21 pass | 21/21 | 内容链通过，媒体 readiness 未执行 |

## 关键指标

- 场景总数：6；已物化场景：4；场景级 blocker：2；场景 blocker rate：`2/6 = 33.33%`。
- 已物化镜头：40；ShotPlan→StoryboardShot 映射：40/40，一一对应，无新增或丢失镜头。
- First Pass Qualification Rate：`37/40 = 92.5%`（仅以已物化镜头为分母；第 1 集在镜头规划前阻断，不混入分母）。
- Final Automatic Qualification Rate：`40/40 = 100%`（同上）。
- Human Intervention Rate：镜头级编辑/修复为 `0/40 = 0%`；另有 4 次场景计划显式审批门事件，二者不混算。
- Auto Repair Yield：`3/3 = 100%`，限定于有明确 ShotPlan `ACTION_BUDGET_EXCEEDED` 证据的镜头修复；其它层级修复仍按原始 artifact 保存。
- Production Blocker Rate：`40/40 = 100%`（已物化镜头口径），这是媒体 readiness 被本轮策略性禁止执行造成的 fail-closed 状态，不是内容 Qualification 失败。
- 连续性：40/40 镜头保留结构化 continuity contract；由于禁止媒体调用，只完成结构连续性验证，未宣称视觉/视频连续性通过。

## A–L 指标完整清单

机器可读的逐集与总体明细见 `real-production-pilot-v1-metrics.json` 的 `required_metrics`。关键口径如下：

- Fact：25 条事实中 13 条已确认、11 条为可保留未知、1 条 conflict；未发现需要通过猜测解决的 blocking unknown。
- ScriptIR：6/6 场景覆盖，0 个验证 blocker；E1 与 E3 各有 1 次局部修复且成功。
- Asset：E2/E3 的角色、场景、道具 canonical registry 覆盖均为 100%；E1 因上游阻断未运行。媒体参考图 readiness 本轮未执行。
- DirectorTreatment：6/6 场景覆盖，0 blocker，0 needs_review。
- SceneBlocking：4/6 场景通过；E1 两场有 `SPATIAL_UNKNOWN`，axis/eyeline warning 均为 0。
- ShotPlan：4 个 approved plan、40 个镜头；首轮 3 个 blocker，3 个修复尝试全部成功，最终无剩余 ShotPlan blocker。
- Executability：3 个 action-budget blocker，dialogue/camera-motion/entry-exit conflict 均为 0。
- Materializer：计划 40、物化 40、mapping `100%`、unmapped `0`、extra `0`。
- Prompt Compiler：Phase A 覆盖 `40/40`，无 blocked、fallback、missing binding 或 IR validation error。
- Qualification：首轮 `37/40 = 92.5%`，ShotPlan 局部自动修复 yield `3/3 = 100%`，最终自动合格 `40/40 = 100%`；镜头级人工编辑/修复 `0/40 = 0%`，另有 4 次显式审批门事件。
- Continuity：结构化合同 `40/40`；硬连续性、道具、人物、场景状态及画面方向冲突均为 0。媒体连续性因禁止供应商调用而未验证。
- MiMo：详见下节；成本字段不可用时不估算金额。

## MiMo 审计

按 `request_fingerprint` 去重所有 Pilot artifact，共 46 次唯一调用：prompt 134,731、cached 21,632、completion 76,870、total 211,601 tokens，cache hit rate 16.06%，平均延迟 27,035.5ms。审计只保存模型、指纹、token/cache、延迟和阶段信息，不保存密钥、原始提示词或响应。15 次内容链调用未绑定 episode；按阶段记录的 episode-scoped 调用为 E1=11、E2=12、E3=8。

## Root Cause Top 10（本样本实际出现 5 类）

1. `SPATIAL_UNKNOWN`：第 1 集两场未声明人物位置/空间锚点，生产链按责任层阻断。
2. `DUPLICATE_SCENE_NAME`：ScriptIR 场景名重复，已在 ScriptIR 层修复。
3. `UNBOUND_BEAT_ID`：Treatment beat 未使用冻结的 ScriptIR beat id，已在 Treatment 层修复。
4. `ACTION_BUDGET_EXCEEDED`：第 2 集两个镜头动作预算超限，按 ShotPlan 层将时长从 4s 调整为 6s；未通过缩短 Prompt 掩盖。
5. `IDENTITY_FIELD_DROPPED`：候选 Treatment 丢失资产身份字段，已恢复冻结名称。

未发现的根因不会伪造为零风险；上述列表仅报告本 Pilot evidence 中真实出现的诊断。

## `needs_information` / `conflict` 实例

- `needs_information`：E1 的两场 SceneBlocking 均缺少可验证的人物位置/空间锚点；系统没有猜测或降级为 warning。
- `conflict`：本 Pilot 未产生新的已确认 conflict；动作预算问题以 `ACTION_BUDGET_EXCEEDED` 在 ShotPlan 层修复并重新验证。

## 审计缺口与下一步

- 第 1 集必须在剧本/SceneBlocking 责任层补齐人物空间证据后重新验证；不得在 ShotPlan 或 Prompt 层猜测。
- 需要单独建立统一 repair-attempt ledger，才能计算可信的 Auto Repair Yield、每层首次通过率和人工编辑率。
- 媒体阶段需在受控环境完成资产 readiness、图片回收、对象存储可访问性、视频提交、失败恢复、QA 和连续性验收；本报告不替代这些证据。
- 当前最大瓶颈是“结构链已通过但媒体 readiness 未执行”，其次是第 1 集的空间证据缺口。

## 局部阻断验证

E1 两场 SceneBlocking 的 `needs_review` 只阻断各自场景向 ShotPlan 的传播；E2/E3 独立完成 Treatment、Blocking、ShotPlan、Materializer、Compiler 与 Qualification。没有因为 E1 blocker 全局停机，也没有用历史项目补数，证明阻断传播是局部的。

## 与 990401 Before/After

本 Pilot 不复用 `990401`。可比基线只有旧样本的结构审计结论，不能声称质量百分比直接可比：

| 指标 | 990401 旧 direct LLM | 990402 Production Pilot |
|---|---:|---:|
| 生成路径 | direct LLM，ShotPlan 可绕过 | Qualified IR→Approved ShotPlan→Materializer |
| 场景资产覆盖 | 0 个 scene asset | E2/E3 registry 100%，E1 上游阻断未运行 |
| ShotPlan 覆盖 | 0/19 scenes | 4/4 approved scenes |
| Storyboard↔ShotPlan 映射 | 无统一证据 | 40/40（100%） |
| Compiler state | 164 shots 缺失 | Phase A 40/40（100%） |
| Executability blocker | 14 | 3，且 3/3 局部修复成功 |
| 首次合格率 | 未形成同口径指标 | 37/40（92.5%，物化镜头口径） |
| Final blocker | 重复 Prompt symptoms，缺少统一门禁 | 40/40 媒体阻断（本轮禁止媒体调用）；内容 Qualification 0 blocker |

本表比较的是结构能力和可审计证据，不是同一文本样本上的质量实验。

## 最终判断

1. **Production Pipeline V2 是否显著提高首次合格率？** 在本次可比口径（已物化镜头）下，首次无需修复合格率为 `92.5%`，达到并超过 85% 目标；但 `990401` 没有同口径首次合格率，不能宣称统计显著性，只能确认当前链路已能量化并控制首次 blocker。
2. **是否解决 990401 的主要结构问题？** 已解决其核心结构缺口：Production 不再绕过 ShotPlan，40/40 镜头有 Materializer 一一映射和 Phase A 状态；重复/未绑定/动作预算问题在责任层被拦截或修复。旧样本的媒体与 Prompt 重复症状仍需独立回放验证。
3. **当前最大剩余瓶颈是哪一层？** 媒体 readiness/对象存储可访问性是进入 Production Pass 的首要瓶颈；内容链内部的首要瓶颈是 E1 SceneBlocking 空间证据。
4. **下一阶段最值得投入的 3 个优化点？** 补齐 E1 空间证据；统一 repair-attempt ledger；在受控 staging 完成资产、图片、视频、QA 与连续性闭环。

## 当前真正瓶颈

1. 媒体 readiness 尚未执行，导致所有已物化镜头在 Production Pass 仍保持 blocked；这是进入图片/视频阶段前的首要外部条件。
2. E1 的 SceneBlocking 空间证据不足，必须在责任层补齐人物位置/锚点，不能由 ShotPlan 或 Prompt 猜测。
3. Repair attempt ledger 目前跨 artifact 分散，虽已能对本轮 ShotPlan 修复计算 3/3，但仍需统一事件模型才能稳定比较各层 repair yield。

## 下一轮最值得投入的 3 项优化

1. 补齐 E1 空间证据并复跑局部链路，验证 blocker 清除后不会污染其它集。
2. 建立统一 repair-attempt ledger，自动计算每层 first-pass、repair yield 和人工干预率。
3. 在受控 staging 执行资产 readiness→图片回收→多参考视频→QA/连续性验收，保持稳定公网对象存储与供应商调用的 fail-closed 门槛。

## 安全边界

- `workflow_profile=production` 未调用 `StoryboardAgent.run()`。
- 未调用真实生图、视频、对象存储；未处理 GitHub Actions/CI。
- 未删除、覆盖或清理历史产物；所有 Candidate、Repair、Validation 与 Final Qualified 证据保留在 artifacts 中。
