# 阶段四验收记录：整集批量生产、失败任务中心与导出前检查

验收时间：2026-06-25

## 结论

通过。

阶段四的核心能力已经跑通：本集检查能识别整集缺口；批量分镜图和批量视频会为每个镜头发起独立任务；生成后状态会回填到左侧列表、画布和检查面板；导出前检查能判断可交付；失败任务中心能展示失败任务、同会话重试失败任务，并且未处理失败任务刷新后仍能恢复展示。

## 工程检查

- `npm run test`：通过，6 个测试文件，55 个测试全部通过。
- `npm run build`：通过。
- 构建提示：主 JS chunk 超过 500 kB。这是性能/发布优化项，不阻塞阶段四功能验收。

## 验收路径与结果

1. 项目列表
   - 状态：通过。
   - 证据：`01-project-list.png`
   - 说明：能进入“神农架历险记”。

2. 第 1 集本集检查
   - 状态：通过。
   - 证据：`03-inspection-panel.png`
   - 说明：第 1 集已被前序验收补齐，检查面板显示 8/8 分镜图、8/8 视频、8/8 已采用、8/8 入成片，并显示“当前本集已经具备交付条件”。

3. 查找可批量生产样本
   - 状态：通过。
   - 证据：`inspect-第2集.png`、`inspect-第3集.png`
   - 说明：第 2 集和第 3 集存在 8 个缺分镜图、8 个缺视频、8 个未入成片镜头，可用于批量验收。

4. 第 2 集检查面板
   - 状态：通过。
   - 证据：`12-episode2-inspection-before-batch.png`
   - 说明：检查面板列出缺分镜图、缺视频、未入成片，并提供“为缺分镜图镜头批量生成分镜图”和“为缺视频镜头批量生成视频”。

5. 批量生成分镜图
   - 状态：通过。
   - 证据：`13-episode2-batch-image-after.png`
   - 关键请求：8 个 `POST /api/prototyping/generate-image -> 200`
   - 说明：第 2 集 8 个镜头分别发起独立分镜图生成任务。

6. 批量分镜图回填
   - 状态：通过。
   - 证据：`14-episode2-inspection-after-images.png`
   - 说明：检查面板从“已有分镜图 0”更新为“已有分镜图 8”，缺视频仍为 8，状态准确。

7. 批量生成视频
   - 状态：通过。
   - 证据：`15-episode2-batch-video-after.png`
   - 关键请求：8 个 `POST /api/prototyping/generate-video -> 200`
   - 说明：每个镜头使用对应分镜图作为上游来源生成视频。

8. 批量视频、采用和成片状态回填
   - 状态：通过。
   - 证据：`16-episode2-inspection-after-videos.png`
   - 说明：检查面板更新为 8 个已有视频、8 个已采用视频、8 个已入成片；成片序列引用更新为第 2 集视频版本。

9. 导出前检查
   - 状态：通过。
   - 证据：`17-episode2-export-check.png`
   - 说明：第 2 集显示“本集可导出 / 可交付”，同时列出参考图完整度 2/3 的风险镜头，并提供“可跳转”入口。

10. 刷新后回填
    - 状态：通过。
    - 证据：`18-episode2-after-refresh.png`
    - 说明：刷新后第 2 集仍显示分镜图、视频、成片状态，未见 `???` 乱码。

11. 失败任务制造
    - 状态：通过。
    - 证据：`27-created-failure-same-session.png`
    - 关键请求：`POST /api/prototyping/generate-video`，请求体含 `simulate_error: true`
    - 说明：通过“模拟重试失败”制造视频失败任务。

12. 失败任务中心展示
    - 状态：通过。
    - 证据：`28-failure-center-same-session-before-retry.png`
    - 说明：失败任务中心显示待处理失败、关联镜头、失败原因、重试、查看节点、标记已处理。

13. 失败任务重试
    - 状态：通过。
    - 证据：`29-failure-center-same-session-after-retry.png`
    - 关键请求：再次发起 `POST /api/prototyping/generate-video`，请求体含 `simulate_error: false`
    - 说明：失败中心范围内的“重试”可重新发起真实生成。

14. 未处理失败任务刷新后恢复
    - 状态：通过。
    - 证据：`30-unhandled-failure-before-refresh.png`、`31-unhandled-failure-after-refresh.png`
    - 说明：制造未处理失败任务后刷新，第 2 集失败任务中心仍显示待处理失败任务和重试入口。

## 发布级观察

- 本轮批量与失败中心脚本没有捕获到 duplicate key、`Failed to fetch` 或静态资源 404。
- 构建存在 chunk size 警告，建议后续发布阶段做代码分包，但不影响当前阶段四功能。
- 第 1/2 集仍有“参考图完整度 2/3”的风险提示，这是业务风险提示，不是流程阻塞。

## 截图清单

- `01-project-list.png`
- `03-inspection-panel.png`
- `12-episode2-inspection-before-batch.png`
- `13-episode2-batch-image-after.png`
- `14-episode2-inspection-after-images.png`
- `15-episode2-batch-video-after.png`
- `16-episode2-inspection-after-videos.png`
- `17-episode2-export-check.png`
- `18-episode2-after-refresh.png`
- `27-created-failure-same-session.png`
- `28-failure-center-same-session-before-retry.png`
- `29-failure-center-same-session-after-retry.png`
- `30-unhandled-failure-before-refresh.png`
- `31-unhandled-failure-after-refresh.png`

