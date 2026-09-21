# PHASE_H2_ASSET_AUTHORITY_SCHEMA_REVIEW

## Review status

`PHASE_H2_ASSET_AUTHORITY_SCHEMA_APPROVED_PENDING_MIGRATION`

本次审核批准现有 `phase_h2_asset_authority_schema_proposal.md` 作为 H2 Production Asset Authority 的迁移设计基线。批准仅覆盖 schema contract 与迁移设计，不代表已执行 migration，也不代表已经建立生产资产或 StoryboardShot binding。

本轮没有修改 models、API、Candidate、A–G2 authority 链，也没有调用 Provider/Image/Video；Official Media 仍不属于 H2 foundation scope。

## Why a new Production Asset Authority is required

Production Asset Authority 需要回答“某本书中某个角色、场景或道具实体当前被哪一个不可变资产版本代表”，并能被 StoryboardShot 精确绑定、校验和标记 stale。现有模型无法同时提供以下闭环：

1. 实体级、typed 的 canonical identity 与唯一 authority row。
2. 不可变版本、文件层证据、视觉身份快照和 payload fingerprint 的分离。
3. 每个实体/作用域唯一的 current pointer，以及 authority → pointer → version 的 exact resolver。
4. `StoryboardShot` 到 authority/version 的持久化 binding、fingerprint 和 stale 传播。
5. Official Media promotion 前重新验证 currentness、revision drift、tamper 和 stale 状态。

因此 H2 必须新增 Production Asset Authority 层，而不能用现有 JSON projection 或 reference media 记录拼接出“看似绑定”。

## Why `VisualReferenceAuthority` cannot be reused

`VisualReferenceAuthority` 的语义是 reference media：它负责图片/文件、checksum、storage、reference token 和 reference lock。它证明的是一份参考媒体文件的身份与锁定状态，不是角色、场景或道具实体的生产身份。

直接复用会产生三类错误：

- 把 entity identity 与 asset file identity 混在同一 authority 中；
- 让 reference media 的生命周期替代 production version/currentness；
- 使 PromptIR、StoryboardShot 和 Official Media 误以为 reference row 就是可生产资产。

`VisualReferenceAuthority` 可以作为 Production Asset Version 的可选 `source_reference_json` 证据，但不能成为 Production Asset Authority，也不能被迁移升级。

## Entity responsibilities

### 1. Authority

`production_asset_authorities` 表示书内一个生产实体的稳定身份和当前选择。核心字段为 `authority_id`、`book_id`、`asset_type`、`canonical_id`、`current_version_id`、`authority_fingerprint`、`status` 及 stale 字段。authority 不以 URL、filename、prompt 或 `meta_info` 作为身份。

唯一性为 `book_id + asset_type + canonical_id`。`asset_type` 仅允许 `character`、`scene`、`prop`。Authority 生命周期为：

- `ACTIVE`：实体可被 exact resolver 解析；其 current pointer/version 必须满足 currentness 校验。
- `STALE`：实体定义、current version 或上游 authority contract 已失效；下游 binding/PromptIR/Media validation 必须 fail closed，不能自动替换或 retry。

### 2. Version

`production_asset_versions` 表示 authority 下的一次不可变资产版本。核心字段为 `asset_version_id`、`authority_id`、单调 `revision`、`storage_identity`、`checksum`、`visual_identity_hash`、`source_reference_json`、`payload_json`、`payload_hash`、`status` 及 stale 字段。

`storage_identity` 可以为空，表示文件尚未落盘；它不能被用作实体身份。新版本只能新增 row，再移动 current pointer；不得原地修改已被引用的版本。Version 生命周期为：

- `CURRENT`：被 authority current pointer 选中且所有 fingerprint/currentness 校验通过。
- `SUPERSEDED`：保留历史 lineage，但已被新的 current version 替代；不能作为新的 production binding。
- `STALE`：版本内容、来源、hash 或上游契约失效；任何 resolver、binding 和 promotion 都必须拒绝。

### 3. Pointer

`production_asset_pointers` 表示某个 authority 在明确 `scope_key` 下选择的 current version。核心字段为 `pointer_id`、`authority_id`、`current_version_id`、`scope_key`、`pointer_fingerprint`、`status` 及 stale 字段。

Pointer 生命周期为：

- `ACTIVE`：该 scope 的唯一 current pointer，且指向同一 authority 的 `CURRENT` version。
- `STALE`：pointer fingerprint、authority current version、version hash 或 scope 校验失败；resolver 必须停止。

resolver 只允许 exact scope，不得 latest fallback。它必须同时校验 authority、pointer、version 的归属、revision、payload hash、fingerprint 和 stale 状态。

### 4. Binding

`storyboard_shot_asset_bindings` 表示一个 `StoryboardShot` 在指定 `binding_role` 下对 Production Authority/Version 的正式引用。核心字段为 `storyboard_shot_id`、`binding_role`、`canonical_id`、`authority_id`、`asset_version_id`、`binding_fingerprint`、来源 ShotPlan fingerprint、状态及 stale 字段。

Binding 生命周期为：

- `ACTIVE`：shot、role、canonical identity、authority/version 和来源 fingerprint 全部匹配，且资产仍 current。
- `STALE`：资产版本被替换、authority/pointer stale、revision drift、来源 shot plan 变化或 fingerprint/tamper 校验失败；不得静默改绑。

同一 shot 的同一 role/canonical identity 只能有一个 active binding。Binding 不从 prompt、filename、`asset_links`、`meta_info` 或手工 JSON 推导。

## Character / Scene / Prop structure

采用四张通用 typed 表，而不是复制三套结构相同的表：

- `asset_type=character`：`canonical_id` 指向角色实体；typed wrapper 暴露 Character Authority/Version/Pointer/Binding 语义。
- `asset_type=scene`：`canonical_id` 指向场景实体；typed wrapper 暴露 Scene 语义。
- `asset_type=prop`：`canonical_id` 指向道具实体；typed wrapper 暴露 Prop 语义。

三类实体共享相同 lineage、currentness、stale 和 binding contract；差异只在 typed identity/payload 校验，不在表结构中复制。`VisualMakeup`、`VisualLocation`、`VisualProp` 继续作为 identity definition 或 legacy registry，不能被当作 authority/version/pointer，也不回填为新的 production rows。

## PromptIR and Official Media contract

PromptIR 只保存 `authority_id`（以及需要审计时的 `asset_version_id` 引用快照），不保存图片 URL、filename，也不拥有资产定义。PromptIR 的引用解析失败、authority stale、version drift 或 binding stale 时必须 fail closed。

Official Media promotion 前必须重新解析每个 shot 的 binding，并验证 authority current pointer、version status、revision、payload/checksum/fingerprint 和 binding source fingerprint。任何 stale、缺失、tampered 或 drift 都必须拒绝 promotion。H2 foundation 不创建 Official Media，也不改变 A–G2 authority 链。

## Review decision and verification basis

审核结论为：`PHASE_H2_ASSET_AUTHORITY_SCHEMA_APPROVED_PENDING_MIGRATION`。迁移仍需单独评审和执行；本轮不创建 Alembic 文件。

已有同一基线 HEAD（`78e06959bae400748a94ecd82bd2eb9c564bf4e0`）的验证证据保持有效：Phase F 51 passed；Phase C–E/迁移 77 passed；G2 16 passed；Migration hardening 为 `MIGRATION_CHAIN_HARDENING_READY`；Golden 5/5；Web 301 passed；production build passed；Full backend 1717 passed，4 个既有基线失败。Full E2E 仍为 false。
