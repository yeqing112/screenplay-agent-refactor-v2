# PHASE_H2_ASSET_AUTHORITY_MIGRATION_PLAN

## Plan status

`PHASE_H2_ASSET_AUTHORITY_SCHEMA_APPROVED_PENDING_MIGRATION`

本文只设计迁移，不执行 Alembic migration，不创建 migration 文件，不修改 models/API/Candidate/Official Media，也不调用 Provider/Image/Video。执行前仍需对 DDL、约束和 backfill policy 做独立批准。

## Target tables

### `production_asset_authorities`

建议字段：

- `authority_id`：主键。
- `book_id`：所属书籍，FK 至既有 book/作品表。
- `asset_type`：`character | scene | prop` 的 CHECK。
- `canonical_id`：实体 canonical identity。
- `current_version_id`：可空 FK 至 `production_asset_versions.asset_version_id`；建表阶段允许延迟绑定，数据校验后设为 NOT NULL（若业务要求每个 authority 必须有版本）。
- `authority_fingerprint`：实体身份与 contract 的稳定 fingerprint。
- `status`、`stale_status`、`stale_reasons`、`created_at`、`updated_at`。

### `production_asset_versions`

建议字段：

- `asset_version_id`：主键。
- `authority_id`：FK 至 `production_asset_authorities.authority_id`，`ON DELETE RESTRICT`。
- `revision`：authority 内单调递增。
- `storage_identity`：可空文件存储身份；不承担 entity identity。
- `checksum`、`visual_identity_hash`、`source_reference_json`、`payload_json`、`payload_hash`。
- `status`：`CURRENT | SUPERSEDED | STALE` 的 CHECK。
- `stale_status`、`stale_reasons`、`created_at`。

### `production_asset_pointers`

建议字段：

- `pointer_id`：主键。
- `authority_id`：FK 至 authority，`ON DELETE RESTRICT`。
- `current_version_id`：FK 至 version，`ON DELETE RESTRICT`。
- `scope_key`：不可省略的 exact resolver scope。
- `pointer_fingerprint`、`status`（`ACTIVE | STALE`）、stale 字段和 timestamps。

### `storyboard_shot_asset_bindings`

建议字段：

- `binding_id`：主键。
- `book_id`、`episode`、`storyboard_shot_id`：shot FK 至既有 storyboard shot 表，删除策略为 RESTRICT。
- `binding_role`：`character | scene | prop` 的 CHECK。
- `canonical_id`、`authority_id`、`asset_version_id`：分别保存解析后的实体和版本引用。
- `binding_fingerprint`、`source_shot_plan_authority_fingerprint`、`status`（`ACTIVE | STALE`）、stale 字段和 timestamps。

## Foreign keys and consistency checks

1. Authority → Version 的 `current_version_id` 与 Version → Authority 的 `authority_id` 必须形成同一 authority 的闭环；迁移执行时可先允许 NULL，再在数据校验后收紧。
2. Pointer 的 authority/version 必须同属一个 authority；服务层 resolver 还需验证 authority current pointer、version revision、payload hash 和 fingerprints。
3. Binding 的 `book_id`、shot、authority、version、`binding_role`、`canonical_id` 必须一致；跨 book、跨 asset type 或跨 authority 的写入必须拒绝。
4. 所有生命周期字段使用 CHECK；未知状态不得落库。`stale_reasons` 用结构化 JSON 保存原因，但不能替代 FK/唯一约束。
5. 版本 row 不允许原地变更 lineage 字段；版本替换通过新增 version + pointer movement + stale propagation 完成。

## Indexes and unique constraints

### Unique

- `production_asset_authorities`: `UNIQUE(book_id, asset_type, canonical_id)`，保证 Character/Scene/Prop 每个实体只有一个 authority。
- `production_asset_versions`: `UNIQUE(authority_id, revision)`，保证同一 authority 的 revision 不重复。
- `production_asset_pointers`: 对 active pointer 建唯一约束 `UNIQUE(authority_id, scope_key) WHERE status = 'ACTIVE'`；因此 Character、Scene、Prop 每个 entity 的 production scope 只有一个 current pointer，历史 stale pointer 可保留。
- `storyboard_shot_asset_bindings`: active binding 的 `UNIQUE(storyboard_shot_id, binding_role, canonical_id) WHERE status = 'ACTIVE'`。

### Indexes

- authorities：`(book_id, asset_type, canonical_id)`、`(status, stale_status)`。
- versions：`(authority_id, status, revision)`、`(checksum)`、`(payload_hash)`。
- pointers：`(authority_id, scope_key, status)`、`(current_version_id)`、`(pointer_fingerprint)`。
- bindings：`(storyboard_shot_id, binding_role, status)`、`(authority_id, asset_version_id)`、`(binding_fingerprint)`。

## Migration ordering and transaction boundary

1. 预检既有表/列名、FK 目标、数据库方言及空值策略；失败则不建表。
2. 在单次可回滚 migration 中创建四张表、CHECK、FK、unique constraints 和 indexes。
3. 先运行空库/约束测试与 orphan 检查；再由显式 service/import 流程创建新 authority 数据（不由 migration 隐式推断）。
4. 最后才允许应用层切换到 exact resolver；在 resolver 切换前不产生 production binding。

## Rollback

- 在未写入新生产数据前，rollback 只删除四张新表及其索引/约束，顺序为 bindings → pointers → versions → authorities。
- 若已写入新数据，rollback 必须先停止新 resolver/写入，再导出并审计新表数据，确认没有下游 Official Media 或 A–G2 引用后才允许 drop；否则只执行 forward fix，不强制破坏性回滚。
- 旧的 `VisualReferenceAuthority`、legacy visual rows、Candidate 和 Official Media 数据不得由 rollback 修改。
- migration 不得把 drop/rename 旧表作为回滚手段。

## Impact on old data

- `VisualMakeup`、`VisualLocation`、`VisualProp`、`VisualReferenceAsset`、`VisualReferenceAuthority` 和现有 generic visual pointer/version 保持原样。
- 不回填 legacy visual rows，不根据 prompt、filename、URL、`asset_links`、`meta_info` 或 `ShotPlan.asset_bindings` 猜测 authority/version/binding。
- 既有 generic pointers 可以继续作为 lineage primitive；只有经过显式审核和新服务写入，才允许产生新的 typed Production Authority rows。
- 新表初始可以为空；Episode 01 的 authority/version/pointer/binding 保持未建立，不能伪造 `authority_id`。

## Explicit non-goals and gates

- 不升级或复用 `VisualReferenceAuthority` 作为 Production Asset Authority；reference row 只能作为 version 的 source evidence。
- 不修改 Candidate、Official Media 或 A–G2 authority 链。
- 不生成 Character/Scene/Prop 图片，不调用 Provider/Image/Video。
- 不在本计划中执行 Official Media promotion；promotion 前必须重新验证 authority currentness、version status、binding freshness、hash/fingerprint 和 revision drift。
- migration 完成后仍不能宣称 Full E2E；必须另行通过 H2 binding、PromptIR 和 promotion gate。

## Exit criteria for a future migration run

未来执行时，必须同时提供：migration revision、schema inspection、FK/unique/index 断言、rollback 证据、空库与既有库验证、以及未回填 legacy rows 的审计记录。未满足这些证据前，状态保持 `PHASE_H2_ASSET_AUTHORITY_SCHEMA_APPROVED_PENDING_MIGRATION`。
