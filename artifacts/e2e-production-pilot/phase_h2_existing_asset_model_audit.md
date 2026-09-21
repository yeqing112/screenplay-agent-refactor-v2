# PHASE_H2_EXISTING_ASSET_MODEL_AUDIT

## Scope

本轮只审计现有资产模型与生产绑定能力，不创建 migration、不修改 Candidate、不把 Reference Asset 升级成 Production Asset，也不调用 Provider/Image/Video。审计范围覆盖 `VisualReferenceAuthority`、`VisualAssetPointer`、`VisualAssetVersion`、legacy Asset Definition、`VisualReferenceAsset`、ShotPlan/Storyboard 绑定与 PromptIR 资产引用。

## 结论

`PHASE_H2_ASSET_AUTHORITY_SCHEMA_REQUIRED`

现有能力可以复用为底层组件，但不能直接证明 Production Asset Truth：

- `VisualAssetVersion` + `VisualAssetPointer`：**部分可复用**。已有 asset type、canonical identity、revision、payload hash、exact scope resolver、stale 状态与 fail-closed 校验。
- `VisualReferenceAuthority`：**只能用于 Reference**，不能复用为 Production Asset Authority。它绑定的是图片/文件 checksum、storage、token 和 reference lock。
- `VisualMakeup` / `VisualLocation` / `VisualProp`：**只能作为 Identity Definition/legacy registry**，没有不可变 version、current pointer、authority fingerprint 或 shot binding。
- `VisualReferenceAsset`：**只能用于 Asset File/Reference 层**；`image_url`、`local_path`、`reference_token`、`checksum` 不等于实体的 Production Asset Authority。
- ShotPlan/Storyboard/PromptIR：目前绑定主要是 JSON/PromptIR projection；没有 `StoryboardShot -> Production Asset Authority/Version` 的规范化、可解析、可 stale 的 binding 记录。

## Existing model audit

| 现有能力 | 可复用范围 | 不能证明的事项 | 判定 |
|---|---|---|---|
| `VisualAssetVersion` | 通用版本载体；asset type/key、canonical identity、revision、payload hash、stale lifecycle | 没有 `authority_id`、typed storage/checksum/visual identity hash、实体级 authority envelope | Partial |
| `VisualAssetPointer` | exact scope current pointer；current version；payload/status/stale 校验 | 没有 Production Authority 归属、没有 shot binding、没有 authority fingerprint | Partial |
| `resolve_current_visual_asset_authority` | pointer→version 精确 resolver；拒绝 stale、hash tamper、scope mismatch、未 qualified | resolver 结果不是持久化 Production Asset Authority；不能解析 shot binding | Reusable primitive |
| `propagate_visual_asset_staleness` | version/pointer/reference/PromptIR stale 传播 | 没有 Production binding stale rows，也没有 Official Media precondition | Partial |
| `VisualReferenceAuthority` | reference media authority；image identity/checksum/storage/token/lock | 没有实体 authority 语义；将其升级会混淆 Asset Identity 与 Asset File | Reference only |
| `VisualMakeup` | 角色视觉定义/legacy identity registry | 可变行；无 version/pointer/authority_id；不能做生产绑定 | Definition only |
| `VisualLocation` | 场景 identity/scene_id/canonical facts | 可变行；无 version/pointer/authority_id；不能做生产绑定 | Definition only |
| `VisualProp` | 道具 identity/canonical facts | 可变行；无 version/pointer/authority_id；不能做生产绑定 | Definition only |
| `VisualReferenceAsset` | 具体图片/文件/引用 token | `image_url`/filename/local path 不能证明实体资产；legacy mutable reference | Asset File/Reference only |
| `ShotPlan.asset_bindings` | 上游 canonical identity intent | JSON identity，不是 pointer lineage；无法独立 resolver/stale | Upstream intent only |
| `StoryboardShot.asset_links` / `meta_info` | legacy output/derived links | 禁止作为正式绑定；容易退化为 manual JSON/meta binding | Legacy only |
| PromptIR `asset_authority_bindings` | 只读引用与编译快照 | PromptIR 不拥有资产；当前存在未解析角色引用和空 reference authority | Reference only |

## Required fields gap

现有 generic tables 不同时满足 H2 要求：

- Authority：缺 `authority_id`、entity canonical id 的唯一 authority row、`current_version_id`、authority fingerprint/status。
- Version：缺明确的 `storage_identity`、`checksum`、`visual_identity_hash`、source reference 字段；不能把这些字段只塞进任意 payload JSON。
- Pointer：缺与 Production Authority 的 FK/identity 绑定和 pointer fingerprint；目前只指向 generic VisualAssetVersion。
- Shot Binding：缺正式 `StoryboardShot + asset_type + authority_id + version_id` 表；现有 ShotPlan/Storyboard/PromptIR JSON 不能替代。
- Currentness：已有 asset/prompt stale primitive，但没有完整覆盖 Production Shot Binding 与 Official Media 前置验证。

## Evidence

- `models/visual_authority.py`
- `models/visual.py`
- `core/visual_asset_authority.py`
- `models/storyboard.py`
- `core/shot_plan.py`
- `core/prompt_ir_phase_e.py`
- `alembic/versions/v5e6f7g8h9i0_add_visual_asset_authority.py`
- `artifacts/e2e-production-pilot/phase_h_asset_binding_audit.md`
- `artifacts/e2e-production-pilot/episode_01_phase_f_real_authority_fake_provider_trace.json`
- `artifacts/e2e-production-pilot/phase_e_production_boundary_audit.json`

## Gate

当前不能输出 `PHASE_H2_PRODUCTION_ASSET_BINDING_READY`，也不能触发真实 E2E。下一步只能先评审 schema proposal。
