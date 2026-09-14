# 分镜真实场景资产 readiness 审计

- 生成时间：2026-09-11T16:07:50.054502
- 模式：只读 / 未修改真实项目
- 确认令牌：`c4f4f93debd1cf86`
- 项目数：3
- 阻塞项目数：0
- 分镜镜头数：8
- 真实场景资产数：3
- 场景/角色/道具参考资产数：12
- 唯一场景名数：3
- 缺失场景名数：0
- 受影响镜头数：0
- 生产阻塞场景名数：0
- 生产阻塞镜头数：0
- 可进入缺失绑定修复 apply：是
- 可进入提示词批量 apply：是

## 项目汇总

| 项目 | 分镜镜头 | 真实场景资产 | 参考资产 | 唯一场景名 | 缺失场景名 | 生产阻塞场景 | 受影响镜头 | 绑定状态 | 生产状态 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| #990301 导演运行时灰度样本 | 3 | 1 | 3 | 1 | 0 | 0 | 0 | ready | ready |
| #990306 生产就绪度测试 | 2 | 1 | 2 | 1 | 0 | 0 | 0 | ready | ready |
| #990400 导演运行时灰度样本 | 3 | 1 | 7 | 1 | 0 | 0 | 0 | ready | ready |
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
