# 分镜真实场景资产 readiness 审计

- 生成时间：2026-08-24T20:53:55.983553
- 模式：只读 / 未修改真实项目
- 确认令牌：`952399f54c81c828`
- 项目数：3
- 阻塞项目数：0
- 分镜镜头数：75
- 真实场景资产数：40
- 场景/角色/道具参考资产数：6
- 唯一场景名数：11
- 缺失场景名数：0
- 受影响镜头数：0
- 生产阻塞场景名数：11
- 生产阻塞镜头数：75
- 可进入缺失绑定修复 apply：是
- 可进入提示词批量 apply：否

## 项目汇总

| 项目 | 分镜镜头 | 真实场景资产 | 参考资产 | 唯一场景名 | 缺失场景名 | 生产阻塞场景 | 受影响镜头 | 绑定状态 | 生产状态 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| #5 神农架历险记 | 20 | 32 | 4 | 3 | 0 | 3 | 20 | ready | blocked |
| #3 金丝雀 | 34 | 5 | 0 | 5 | 0 | 5 | 34 | ready | blocked |
| #1 苗疆道事 | 21 | 3 | 2 | 3 | 0 | 3 | 21 | ready | blocked |

## 生产可用性阻塞清单

### #5 神农架历险记

| 场景名 | 资产ID | 资产状态 | 参考图 | 横构图图 | locked | selected | 受影响镜头 | 问题 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 部落营地 | 109 | draft | 0 | 0 | 0 | 0 | 8 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |
| 原始丛林上空 | 120 | draft | 1 | 0 | 0 | 1 | 6 | 场景资产状态仍为 draft；场景资产没有符合横构图比例的 selected/locked 参考图 |
| 原始丛林深处 | 121 | draft | 0 | 0 | 0 | 0 | 6 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |

### #3 金丝雀

| 场景名 | 资产ID | 资产状态 | 参考图 | 横构图图 | locked | selected | 受影响镜头 | 问题 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 地下赌场VIP包厢 | 93 | draft | 0 | 0 | 0 | 0 | 8 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |
| 宋氏大厦顶层办公室 | 94 | draft | 0 | 0 | 0 | 0 | 8 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |
| 公立医院病房 | 92 | draft | 0 | 0 | 0 | 0 | 6 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |
| 现代简约别墅客厅 | 96 | draft | 0 | 0 | 0 | 0 | 6 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |
| 高端私人会所走廊 | 95 | draft | 0 | 0 | 0 | 0 | 6 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |

### #1 苗疆道事

| 场景名 | 资产ID | 资产状态 | 参考图 | 横构图图 | locked | selected | 受影响镜头 | 问题 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 陈二蛋与大凤的卧室 | 89 | draft | 1 | 0 | 0 | 1 | 8 | 场景资产状态仍为 draft；场景资产没有符合横构图比例的 selected/locked 参考图 |
| 陈二蛋家厨房 | 90 | draft | 0 | 0 | 0 | 0 | 7 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |
| 麻栗山村口空地 | 91 | draft | 0 | 0 | 0 | 0 | 6 | 场景资产状态仍为 draft；场景资产没有 selected/locked 参考图；场景资产参考图尺寸未验证 |

## 使用建议

1. 对 `missing_visual_location` 的场景，先在资产中心补真实 `VisualLocation` 场景资产。
2. 对 `production_status != ready` 的场景，补正式场景描述并生成/锁定 `VisualReferenceAsset` 参考图。
3. 补齐后重新运行本命令，确认 `ready_for_prompt_batch_apply=true`。
4. 再运行 `npm run plan:storyboard-batch-repair`，确认没有 `real_apply_blocker`。
5. 最后才进入受确认令牌保护的 `npm run apply:storyboard-batch-repair`。

如果确认要按本报告创建缺失的最小 draft 场景资产，可使用受保护命令：

```bash
APPLY_STORYBOARD_SCENE_ASSETS_REAL=1 \
APPLY_STORYBOARD_SCENE_ASSETS_REPORT=<本报告 JSON> \
APPLY_STORYBOARD_SCENE_ASSETS_CONFIRM=<确认令牌> \
npm run apply:scene-assets
```
