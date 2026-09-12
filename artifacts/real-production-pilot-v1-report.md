# Real Production Pilot V1：潮汐回声

日期：2026-09-13
项目：`book_id=990402`，第 1–3 集
执行 profile：`production`；允许真实 MiMo；禁止真实生图、视频和对象存储。

## 结论

Production 内容链已验证到 Materializer、Prompt Compiler Phase A 和 Qualification Loop：第 2 集与第 3 集共 40 个镜头全部完成确定性物化，Phase A `pass=40/40`，Qualification `qualified=40/40`。第 1 集在 SceneBlocking 层因两场人物空间位置未声明而 fail-closed，未继续生成 ShotPlan，也未物化镜头。当前 Pilot 不是媒体生产放行：所有镜头的 `production_status` 仍为 `blocked`，原因是本轮明确禁止媒体与对象存储调用。

## 分集结果

| 集数 | ScriptIR | Treatment | Blocking | ShotPlan / 镜头 | Phase A | Qualification | 结论 |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | qualified（1 次修复） | 2 场 approved | 0 approved / 2 needs_review | 0 | 0 | 0 | 被 `SPATIAL_UNKNOWN` 阻断 |
| 2 | qualified | 2 场 approved | 2 场 approved | 2 / 19 | 19/19 pass | 19/19 | 内容链通过，媒体 readiness 未执行 |
| 3 | qualified（1 次修复） | 2 场 approved | 2 场 approved | 2 / 21 | 21/21 pass | 21/21 | 内容链通过，媒体 readiness 未执行 |

## 关键指标

- 场景总数：6；已物化场景：4；场景级 blocker：2；场景 blocker rate：`2/6 = 33.33%`。
- 已物化镜头：40；ShotPlan→StoryboardShot 映射：40/40，一一对应，无新增或丢失镜头。
- First Pass Qualification Rate：`40/40 = 100%`（仅以已物化镜头为分母；第 1 集在镜头规划前阻断，不混入分母）。
- Final Automatic Qualification Rate：`40/40 = 100%`（同上）。
- Human Intervention Rate：`4/4 = 100%`，表示 4 个已物化场景计划均经过显式批准，不代表人工编辑比例。
- Auto Repair Yield：本轮不发布伪精确比例。历史 artifact 按层记录修复，缺少统一 attempt ledger；指标 JSON 明确标记 `not_normalized`。
- 连续性：40/40 镜头保留结构化 continuity contract；由于禁止媒体调用，只完成结构连续性验证，未宣称视觉/视频连续性通过。

## MiMo 审计

按 `request_fingerprint` 去重所有 Pilot artifact，共 46 次唯一调用：prompt 134,731、cached 21,632、completion 76,870、total 211,601 tokens，cache hit rate 16.06%，平均延迟 27,035.5ms。审计只保存模型、指纹、token/cache、延迟和阶段信息，不保存密钥、原始提示词或响应。15 次内容链调用未绑定 episode；按阶段记录的 episode-scoped 调用为 E1=11、E2=12、E3=8。

## Root Cause Top 10（本样本实际出现）

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

## 与 990401 Before/After

本 Pilot 不复用 `990401`。可比基线只有旧样本的结构审计结论：旧路径允许在结构证据不足时进入自由生成，缺少统一的 ShotPlan→Materializer 一一映射和阶段级审计。本次 `990402` 将缺失证据在 SceneBlocking 层 fail-closed，并对 40 个已物化镜头完成确定性映射与 Phase A/Qualification 证据；两者不是同一数据集，不能声称质量百分比直接可比。

## 安全边界

- `workflow_profile=production` 未调用 `StoryboardAgent.run()`。
- 未调用真实生图、视频、对象存储；未处理 GitHub Actions/CI。
- 未删除、覆盖或清理历史产物；所有 Candidate、Repair、Validation 与 Final Qualified 证据保留在 artifacts 中。
