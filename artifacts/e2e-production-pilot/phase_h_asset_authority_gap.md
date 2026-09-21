# PHASE_H_ASSET_AUTHORITY_GAP_REQUIRED

## 缺少什么

1. **Character Asset Authority**：Episode 01 的 4 个角色没有正式 `VisualAssetVersion` / `VisualAssetPointer`；15 个 PromptIR 镜头中的角色引用共有 26 次无法解析。
2. **VisualReferenceAuthority**：场景和道具虽然在 Phase F snapshot 中有 2 个 scene pointer 与 9 个 prop pointer，但 `VisualReferenceAuthority` 数量为 0；所有 reference authority fingerprint、reference authority ref、reference token 都为空。
3. **Production-scoped Official Media**：15 个镜头没有逐镜头 OfficialMediaPointer。G2 的 1 条官方链没有 Episode/Shot 生产作用域，只能作为合同测试证据。

## 为什么影响 Production Truth

- 没有角色 Authority，PromptIR 的 `subjects` 只是身份字符串，无法证明实际使用的可追溯角色资产。
- 没有 reference authority，场景/道具的 pointer/version 不能解析到锁定、校验过的 reference media；使用 legacy reference、文件名、Prompt 文本或 latest fallback 都会破坏 Production Truth。
- 没有每个镜头的 Official Media，无法完成 `Media Validation → Explicit Promotion → Production Resolve`，也无法宣称完整镜头媒体链路。

## 最小补充方案

- 仅补齐角色的 version/pointer lineage。
- 为实际使用的场景和道具建立精确 reference authority，并锁定 checksum/storage/token mapping。
- 让 15 个 PromptIR 镜头的所有资产引用通过 exact Authority/Pointer resolver。
- 对 15 个 production shot 逐一执行有 scope 的媒体验证和显式 promotion。

禁止通过新增临时字段、Prompt 字符串、文件名、latest fallback、自动生成或自动 retry/repair 来绕过上述缺口。

## Gate

`FULL_REAL_END_TO_END_PRODUCTION_ACCEPTANCE_TRIGGERED=false`
