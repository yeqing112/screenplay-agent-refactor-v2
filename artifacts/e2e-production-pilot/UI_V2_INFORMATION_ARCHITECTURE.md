# UI V2 Information Architecture

## Existing shell retained

The current React/Tailwind `ProductWorkspace`, workspace shell and navigation remain in place:

- 项目控制台
- 内容准备
- 改编方向
- 剧本工作台
- 镜头工作台
- 创作画布
- 资产中心
- QA 修复
- 任务中心
- 导出中心
- 模型管理

## Production workspace hierarchy

```text
Workspace shell
└── 标准视图 | 专业视图
    └── Production Workspace V2 read model
        ├── Project status / blocker / one next action
        ├── Entity-first asset readiness
        └── Shot workspace
            ├── Overview
            ├── Assets
            ├── IMAGE lane
            │   ├── generation preparation
            │   ├── candidates
            │   ├── current OfficialMedia
            │   └── history / lineage
            ├── VIDEO lane
            │   ├── generation preparation
            │   ├── source Official IMAGE
            │   ├── candidates
            │   ├── current OfficialMedia
            │   └── history / lineage
            └── blockers / next action
```

## Disclosure rules

Standard view answers `现在什么状态、缺什么、下一步是什么、哪张是正式版本`. Professional view adds the lineage and raw IDs in expandable details. Loading, unavailable, blocked, empty and ready states are rendered explicitly; blank panels are not used as status.

## Asset hub

Cards are keyed by backend entity IDs and current Production Asset pointers. Manual shot-media records remain visible only as `Legacy / Historical`. They do not replace ProductionAsset, ShotAssetBinding or OfficialMedia.

## Tasks and canvas

The existing task center and ReactFlow canvas remain reachable through the shell. Their canonical Production status uses the V2 projection; temporary browser recovery data remains navigation-only. If the projection is unavailable, production actions stay disabled.
# Production truth boundary

Production Workspace V2 is the execution-facing read model. Canvas, Task Center, and batch generation must use its current lane readiness; legacy adopted media is a display/history field. Delivery must remain blocked when the current OfficialMedia projection is missing or stale.
