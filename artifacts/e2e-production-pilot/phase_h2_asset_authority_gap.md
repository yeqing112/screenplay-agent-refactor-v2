# PHASE_H2_ASSET_AUTHORITY_GAP

## Status

`PHASE_H2_ASSET_AUTHORITY_SCHEMA_REQUIRED`

## Why existing models are insufficient

现有 `VisualAssetVersion` / `VisualAssetPointer` 是通用 visual asset authority primitive，但缺少 H2 所需的 Production Asset Authority envelope 与 Shot Binding；`VisualReferenceAuthority` 明确属于 reference media 层，不能强行升级。

Episode 01 当前仍缺：

- CharacterAssetAuthority / CharacterAssetVersion / CharacterAssetPointer
- SceneAssetAuthority / SceneAssetVersion / SceneAssetPointer
- PropAssetAuthority / PropAssetVersion / PropAssetPointer
- StoryboardShot 到上述 authority/version 的正式 binding
- binding stale propagation 与 Official Media promotion 前置校验

## STOP 条件

- STOP B：不能把 `VisualReferenceAuthority` 变成 Production Asset Authority。
- STOP C：PromptIR 字符串、asset filename、`asset_links` 或 `meta_info` 不能作为绑定。
- STOP D：本阶段不自动生成角色、场景或道具图片。

## 当前证据

- Phase F snapshot 有 11 个 generic VisualAssetPointer（2 scene + 9 prop），character pointer 为 0。
- VisualReferenceAuthority 为 0。
- Episode 01 的 15 个 PromptIR shot 中角色引用仍未解析。
- H2 尚未创建任何 Production Authority、Version、Pointer 或 Shot Binding；官方媒体也不创建。
