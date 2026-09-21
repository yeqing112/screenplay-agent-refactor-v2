# PHASE_H_ASSET_AUTHORITY_GAP_REQUIRED

## Scope

本报告执行 `PHASE_H_PRODUCTION_ASSET_BINDING_AUDIT_AND_REAL_E2E_GATE` 的只读审计。审计对象是 Episode 01、book `990401`，覆盖 ScriptIR → Director Treatment → Scene Blocking → ShotPlan → Storyboard → PromptIR → Generation/Media Authority 的生产证据。未新增字段、表或临时绑定；未调用 Provider、LLM、图片或视频服务。

## Gate result

`PHASE_H_ASSET_AUTHORITY_GAP_REQUIRED`

`FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_TRIGGERED=false`

阻断条件如下：

- **角色资产 Authority 缺失**：ScriptIR 有 4 个角色实体，15 个 PromptIR 镜头共出现 26 次未解析的角色资产引用；Phase F authority snapshot 中 `character:*` VisualAssetPointer/Version 为 **0**。
- **VisualReferenceAuthority 缺失**：Phase F authority snapshot 中 `VisualReferenceAuthority` 为 **0**；场景和道具虽然有 VisualAssetPointer/Version，但没有正式 reference authority、锁定状态或 reference token。
- **Official Media 不完整**：Episode 01 的 15 个镜头没有 production-scoped OfficialMediaPointer。G2 只有 1 条孤立 pilot 官方链，未带 Episode 01 shot scope，不能计入任何镜头。

因此命中 STOP B（角色/场景/道具没有完整正式 Authority）与 STOP A（绑定不能仅依靠 PromptIR 字符串或部分引用）。不进入 Real E2E，不进入 Phase I。

## Asset Audit

### Character

| 检查项 | 结果 |
|---|---:|
| ScriptIR 角色实体 | 4 |
| Character VisualAssetVersion | 0 |
| Character VisualAssetPointer | 0 |
| Character VisualReferenceAuthority | 0 |
| PromptIR 角色引用未解析次数 | 26 |
| 结论 | **FAIL** |

PromptIR 的 `subjects` 与 `identity_refs` 能证明镜头意图引用了角色，但这不构成正式 Authority。所有角色引用均缺少 `book:990401:character:*` 的版本和当前指针。

### Scene

| 检查项 | 结果 |
|---|---:|
| ScriptIR 场景 | 2（E01_SC001=8 镜头，E01_SC002=7 镜头） |
| Scene VisualAssetVersion/Pointer | 2 |
| Scene VisualReferenceAuthority | 0 |
| 绑定状态 | 只有 pointer/version lineage，缺少 reference authority |
| 结论 | **FAIL** |

### Prop

| 检查项 | 结果 |
|---|---:|
| ScriptIR 直接道具实体 | 5 |
| PromptIR 实际 prop identity refs | 9 |
| Prop VisualAssetVersion/Pointer | 9 |
| Prop VisualReferenceAuthority | 0 |
| 已验证缺口 | `PROMPT_IR_REQUIRED_REFERENCE_AUTHORITY_MISSING`（示例：`prop:TICKET`） |
| 结论 | **FAIL** |

`phase_e_production_boundary_audit.json` 明确记录：`latest_fallback=false`，但 required current reference authority 缺失会以 409 fail closed。不能用 legacy `VisualReferenceAsset`、文件名、PromptIR 文本或 `latest` 替代 Authority。

## Production Chain

| 链路阶段 | 审计结果 | 证据 |
|---|---|---|
| Script | PASS | ScriptIR production eligible；2 scenes |
| Director | PASS | 2 treatment authorities + 2 pointers，production qualified |
| Blocking | PASS | 2 blocking authorities + 2 pointers，fresh |
| ShotPlan | PASS | 2 authoritative scene plans |
| Storyboard | PASS | 2 materialization pointers，15 shots |
| PromptIR | STRUCTURAL PASS / PRODUCTION BLOCKED | 15 PromptIR pointers，但角色 Authority 和 reference authority 缺失；Phase E boundary 以 409 fail closed |
| Asset | **FAIL** | 角色 0 个 pointer；reference authorities 0 个 |
| Media | **FAIL** | production-scoped official media 0/15 |

## Episode 01 Shot Asset Completeness

逐镜头矩阵已生成：[phase_h_episode_01_asset_matrix.json](phase_h_episode_01_asset_matrix.json)。每个镜头记录了 `shot_id`、角色绑定、场景绑定、道具绑定、reference authority、PromptIR 依赖和 official media 状态。

- 目标镜头数：15（E01_SC001=8，E01_SC002=7）。
- PromptIR 条目：15/15，PromptIR pointer：15/15。
- 角色正式资产解析：0 个角色 pointer，15/15 镜头至少有一个缺失角色 Authority。
- 场景正式 reference authority：0/15 镜头。
- 道具正式 reference authority：0/15 镜头涉及的道具引用。
- production-scoped Official Media：0/15 镜头。
- `ASSET_BINDING_COMPLETE`：**false**。

## 最小补充方案（只做 Authority 补齐，不扩展 Media Authority）

1. 为 Episode 01 的每个角色建立正式 `VisualAssetVersion` 与唯一当前 `VisualAssetPointer`，包含 canonical identity、scope、revision、payload hash 和 production-qualified 状态。
2. 为两个场景和所有实际使用道具创建与当前 asset version 精确绑定的 `VisualReferenceAuthority`，锁定 reference media、checksum、storage reference、token mapping 与 authority fingerprint。
3. 重新编译/验证 PromptIR，使每个角色、场景、道具引用都有可解析的 Authority/Pointer/reference lineage；禁止 latest、文件名、Prompt 文本 fallback。
4. 对 15 个镜头分别产生并显式 Promotion production-scoped Official Media；在此之前不得执行真实 Provider。

## Provider / E2E accounting

- Audit provider calls: **0**
- Audit LLM calls: **0**
- Audit image calls: **0**
- Audit video calls: **0**
- Real E2E: **未触发**
- G2 isolated pilot official chain: 1 version / 1 authority / 1 pointer；不属于 Episode 01 production scope。

## Current runtime DB cross-check

`work/db/screenplay.db` 当前是 legacy runtime snapshot：`visual_asset_versions=0`、`visual_asset_pointers=0`、`visual_reference_authorities=0`、`official_media_versions=0`、`official_media_pointers=0`，且 `prompt_ir_versions` 表不存在。它不能证明 H 阶段已完成，反而与上述 gap 结论一致。

## Evidence

- `episode_01_script_ir_phase_a.json`
- `episode_01_director_treatment_phase_b.json`
- `episode_01_scene_blocking_phase_b.json`
- `episode_01_shot_plan_phase_c.json`
- `episode_01_storyboard_handoff_phase_c.json`
- `episode_01_prompt_ir_phase_e.json`
- `phase_e_production_boundary_audit.json`
- `phase_e_prompt_ir_revision_asset_pointer_audit.json`
- `episode_01_phase_f_real_authority_fake_provider_trace.json`
- `phase_g2_media_validation_trace.json`
- `phase_g2_official_media_trace.json`

## Verification

本轮验证不改变审计结论：G2 独立合同测试 16 passed；迁移硬化 `MIGRATION_CHAIN_HARDENING_READY`；Golden 5/5；Web 301/301 与生产构建通过；完整后端 1717 passed、4 个既有分支基线失败。Phase F 同一 HEAD 的 51 passed、Phase C–E/迁移同一 HEAD 的 77 passed 证据保留在 `PHASE_F_FINAL_REPORT.md`。一次合并定向集合出现并发 promotion 非确定性失败，但独立 G2 重跑全绿，未改变资产 Authority 缺口判断。
