# 分镜真实场景资产 readiness 审计

- 生成时间：2026-08-24T15:06:04.870579
- 模式：只读 / 未修改真实项目
- 确认令牌：`7c149e27416df10b`
- 项目数：1
- 阻塞项目数：0
- 分镜镜头数：14
- 真实场景资产数：2
- 唯一场景名数：2
- 缺失场景名数：0
- 受影响镜头数：0
- 可进入提示词批量 apply：是

## 项目汇总

| 项目 | 分镜镜头 | 真实场景资产 | 唯一场景名 | 缺失场景名 | 受影响镜头 | 状态 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| #75 深夜便利店 | 14 | 2 | 2 | 0 | 0 | ready |
## 使用建议

1. 对 `missing_visual_location` 的场景，先在资产中心补真实 `VisualLocation` 场景资产。
2. 补齐后重新运行本命令，确认 `ready_for_prompt_batch_apply=true`。
3. 再运行 `npm run plan:storyboard-batch-repair`，确认没有 `real_apply_blocker`。
4. 最后才进入受确认令牌保护的 `npm run apply:storyboard-batch-repair`。

如果确认要按本报告创建最小 draft 场景资产，可使用受保护命令：

```bash
APPLY_STORYBOARD_SCENE_ASSETS_REAL=1 \
APPLY_STORYBOARD_SCENE_ASSETS_REPORT=<本报告 JSON> \
APPLY_STORYBOARD_SCENE_ASSETS_CONFIRM=<确认令牌> \
npm run apply:scene-assets
```
