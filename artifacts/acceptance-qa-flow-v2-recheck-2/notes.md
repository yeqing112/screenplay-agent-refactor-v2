# 分镜视频生成流程再次复验记录

复验时间：2026-06-24 21:40-21:49

## 结论

通过。

本轮复验覆盖工程检查、画布节点点击、图片节点生成视频、预览入口与刷新回填。上次遗留的“画布节点重叠导致普通点击被遮挡”问题已改善；严格过滤 `image-real-*` 图片节点后，4 个可见图片节点中心点均未被其它节点遮挡，普通点击可以选中图片节点并切换右侧属性面板。

## 验收结果

- `npm run test`：通过，5 个测试文件，46 个测试全部通过。
- `npm run build`：通过。
- 项目列表可打开，“神农架历险记 / 第 1 集创作沙盒”加载正常。
- 控制台未出现 React duplicate key 警告。
- 中文显示抽查通过，未见新内容出现 `???`。
- 参考资产层展开/收起控制可用。
- 自动布局后，图片版本节点中心点击点未被遮挡。
- 普通点击图片版本节点后，右侧面板正确显示该分镜图详情与“生成视频”操作。
- 点击“生成视频”成功发出 `POST /api/prototyping/generate-video`。
- 生成视频任务轮询成功，页面生成 `视频 1 v6`。
- 新视频回填到工作流关系中，分镜图输出从 0 更新为 1。
- 成片序列引用更新为新生成的视频版本。
- 播放预览入口可点击。
- 刷新后项目与资产内容仍正常回填。

## 关键请求

生成视频请求成功：

```text
POST /api/prototyping/generate-video -> 200
GET /api/prototyping/tasks/5611c7226d07 -> 200
```

请求体包含：

- `book_id: 5`
- `episode: 1`
- `shot_id: "1"`
- `source_node_id: "image-real-1-i-m-a-g-e-f-0-f-f-9-4-0-7-d-4"`
- `source_asset_id: "image-f0ff9407d4"`
- `target_kind: "video"`
- `reference_asset_ids`: 已带入 7 个参考图资产
- `duration_seconds: 4`

## 轻微观察

浏览器复验中仍偶尔出现页面跳转/刷新造成的 `GET /api/books net::ERR_ABORTED`、`GET /api/nodes/registry net::ERR_ABORTED`，但后续相同接口均返回 200，未影响页面加载与核心流程。可暂定为非阻塞项。

## 截图

截图保存在本目录：

- `01-project-list.png`
- `02-project-loaded.png`
- `09-clean-layout.png`
- `12-strict-image-selected.png`
- `16-before-direct-video-click.png`
- `17-after-direct-video-click-5s.png`
- `18-after-direct-video-click-final.png`

