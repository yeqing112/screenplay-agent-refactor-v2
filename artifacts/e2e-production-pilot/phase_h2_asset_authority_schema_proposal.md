# PHASE_H2_ASSET_AUTHORITY_SCHEMA_PROPOSAL

## Decision

只提出最小 schema，不执行 Alembic migration。建议使用一套带 `asset_type` 的通用 Production Asset Authority 表，提供 character/scene/prop 的 typed service/API wrapper；不复制三套完全相同的表，也不复用 `VisualReferenceAuthority`。

## Proposed tables

### 1. `production_asset_authorities`

- `authority_id`（唯一）
- `book_id`
- `asset_type`（character / scene / prop）
- `canonical_id`
- `asset_key`
- `current_version_id`
- `authority_fingerprint`
- `status`
- `stale_status`
- `stale_reasons`
- `created_at` / `updated_at`

唯一约束：`book_id + asset_type + canonical_id`。authority 是实体身份与当前版本选择的生产真相，不保存图片 URL 作为身份。

### 2. `production_asset_versions`

- `asset_version_id`（唯一）
- `authority_id`（FK）
- `revision`
- `storage_identity`（可为空，表示尚无文件；不能用 URL 推导身份）
- `checksum`
- `visual_identity_hash`
- `source_reference_json`
- `payload_json`
- `payload_hash`
- `status`
- `stale_status`
- `stale_reasons`
- `created_at`

版本必须不可变；新版本只能通过新 row + pointer movement 产生。`storage_identity`、`checksum` 是文件层证据，`visual_identity_hash` 是视觉身份快照，三者与 authority identity 分离。

### 3. `production_asset_pointers`

- `pointer_id`
- `authority_id`（FK）
- `current_version_id`（FK）
- `scope_key`
- `pointer_fingerprint`
- `status`
- `stale_status`
- `stale_reasons`
- timestamps

唯一约束：每个 authority/scope 只有一个 current pointer。Resolver 必须 exact scope；禁止 latest fallback，并校验 authority.current_version_id、version.authority_id、payload hash、fingerprint 和 stale 状态。

### 4. `storyboard_shot_asset_bindings`

- `binding_id`
- `book_id` / `episode` / `storyboard_shot_id`
- `binding_role`（character / scene / prop）
- `canonical_id`
- `authority_id`（FK）
- `asset_version_id`（FK）
- `binding_fingerprint`
- `status`
- `stale_status`
- `stale_reasons`
- `source_shot_plan_authority_fingerprint`
- timestamps

唯一约束：`storyboard_shot_id + binding_role + canonical_id`。写入时同时解析 authority/pointer/version；解析失败或 currentness 不一致就 fail closed。Shot Binding 不从 prompt、filename、manual JSON 或 meta 字段推导。

## Resolver and lifecycle requirements

1. `resolve_production_asset_authority(asset_type, canonical_id, scope)`：只读 exact authority → pointer → version。
2. `resolve_shot_asset_bindings(storyboard_shot_id)`：逐 binding 校验 authority/version/fingerprint/stale/currentness。
3. 版本移动时标记受影响 binding、PromptIR 和 Media validation stale；不自动替换、不自动 retry/repair。
4. PromptIR 只保存 `authority_id` / `asset_version_id` 的引用快照，不拥有资产定义。
5. Official Media promotion 前必须重新解析所有 shot binding，并拒绝缺失、stale、tampered 或 revision drift。
6. Reference media 继续由 `VisualReferenceAuthority` 管理；它可以作为 version 的可选 file/reference evidence，但不是 Production Asset Authority。

## Migration guardrails

- 先评审 schema 与 resolver contract，再写 migration。
- 不回填 legacy `VisualMakeup` / `VisualLocation` / `VisualProp` 为 production authority。
- 不把 `VisualReferenceAsset` 或 `VisualReferenceAuthority` 强行升级。
- 不修改 Candidate、Official Media 或 A–G authority 链。
- 不调用 Provider/Image/Video；H2 foundation pilot 的调用数必须保持 0。
