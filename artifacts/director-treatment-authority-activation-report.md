# DirectorTreatment Authority Contract — Activation Report

日期：2026-09-18
阶段：`DIRECTOR_TREATMENT_AUTHORITY_CONTRACT`
基线：`8f0ca2e4305abc6bc5bf43f29e83c8be81a90274`
Provider 调用：`0`

## Baseline Audit

本节保留阶段开始时的审计结论，不代表最终实现：

- DirectorTreatment 主要以 `scene_name` 与 `status=approved` 被下游查找，没有稳定的 `scene_id → current treatment` 指针。
- Production evidence 仍可重新计算 `Script.content` hash，存在绕过 ScriptIR authority lineage 的断层。
- `source_script_revision` 可由客户端请求传入，缺少 production authoritative source revision 约束。
- Approved Treatment 没有不可变 authority envelope、payload hash、stale policy 或锁定资产优先级。
- SceneBlocking/ShotPlan 的 production consumer 可能从“latest approved”推断当前版本。

## Final As-Built Verification

当前正式实现闭合为：

`PRODUCTION_QUALIFIED ScriptIR → DecisionPacket → Treatment Candidate → human approval → authority envelope → current pointer → SceneBlocking gate`

### Authority contract

- 新增 `director_treatment_authority_contract_v1`，由真实 SceneBlocking/ShotPlan consumer 反推字段。
- 明确三类数据：`SOURCE_CONSTRAINT`、`DIRECTOR_DECISION`、`UNKNOWN_UNRESOLVED`。
- Source constraints（scene identity、declared participants、source beats、explicit constraints）在候选校验中不可修改；Director decisions 可编辑；unknowns 不得静默删除。
- Downstream authoring（scene geometry、character blocking、prop continuity、shot coverage、camera placement）保持 backlog，不会被 Treatment 伪造成 source fact。

### Authority envelope and pointer

- `director_treatment_authority_envelope_v1` 绑定 book/episode/scene_id、Treatment revision/id、payload hash、ScriptIR version/revision/hash、上游 ScriptIR authority fingerprint、source package/version/raw hash、SourceEvidenceIndex、FactSnapshot、contract/requirement fingerprints、asset authority、stale state 和时间戳。
- `DirectorTreatmentPointer` 是唯一 production current selection；production 不再使用 latest-approved fallback。
- Authority envelope 与 pointer 在同一事务中创建/更新；失败不会更新 current pointer。
- payload、authority envelope、pointer revision/treatment lineage、authority policy 发生变化都会 fail-closed 并标记 stale。

### Production consumer gates

- DirectorTreatment production preview 只读取当前 production-qualified ScriptIR，并要求显式 `scene_id`；客户端 `source_script_revision` 不参与 production lineage。
- SceneBlocking production 只解析 current Treatment pointer，并验证 scene_id、ScriptIR lineage、payload/envelope hash、FactSnapshot、锁定资产与 scene identity。
- ShotPlan production 复用 current Treatment pointer；Storyboard Materializer 只消费已批准的 ShotPlan。Director benchmark 是只读评分器，不是 production authority consumer。
- Creative/legacy profile 仍可读取旧 `Script.content` 与 latest approved 兼容路径，但不能进入 production。

### Asset authority

资产优先级固定为：

`immutable source > approved source fact > production-qualified ScriptIR > approved/locked production decision > draft/advisory asset > LLM proposal`

只有状态为 locked 且存在有效 reference/image/local path/token 的资产才进入 `LOCKED_PRODUCTION_CONSTRAINT`；其余保持 advisory 或 pending。

### Validation evidence

- Authority contract + Treatment/SceneBlocking production regression：`31 passed`（本阶段定向测试）。
- 生产流程反向测试证明未调用真实 Provider；mock Provider 调用计数为 `0`。
- 已补充 scene_id 强制门禁、pointer revision/lineage 校验、upstream ScriptIR authority 校验、source raw hash 校验、locked asset fingerprint 校验和 stale 标记。
- 全量后端：`1460 passed, 11 failed, 910 warnings`。11 个失败均为既有 Director Quality 历史 artifact 字段漂移、离线 replay branch 断言、历史 provider runner、真实数据库样本/迁移环境与固定测试数据残留；本阶段相关测试无失败。
- Golden：`5/5`；前端 Vitest：`291 passed`；前端 `npm run build`：通过。
- `npm run test:release-gate` 与 runtime config verification：通过。`npm run check:production` 因上述既有 11 个基线失败而返回非零；`npm run gate:production` 按 fail-closed 规则保持 BLOCKED（开发环境、样本注册、镜头覆盖、真实浏览器依赖不足）。
- 全新数据库 Alembic 试跑发现仓库既有早期迁移 `f05ab1af29bc` 在空库上尝试删除不存在的 `episode_outlines`；该问题不属于本阶段新增迁移，已记录为 baseline migration blocker，未修改历史迁移。

### Known baseline failures

- 旧 `test_scene_blocking_v2_api` fixture 原先仅构造 `status=qualified` ScriptIR 和 approved Treatment；已更新为显式 ScriptIR authority + Treatment pointer fixture。
- 仓库全量测试中其他 Director Quality 历史 artifact/real-database pilot failures 属于既有基线，不通过放宽本阶段 gate 处理。

## Stage decision

`DIRECTOR_TREATMENT_AUTHORITY_CONTRACT_READY`

本阶段没有调用真实 LLM/MiMo、生图、视频、Embedding 或对象存储；没有清理或覆盖历史产物；没有进入 SceneBlocking 内容开发、Provider Canary、资产生成、ShotPlan 内容开发或媒体生成。
