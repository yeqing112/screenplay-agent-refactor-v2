# 真实生成任务接入验收记录

日期：2026-06-24

## 结论

不通过。

## 已通过项

- 前端测试通过：5 个测试文件，33 个测试。
- 前端生产构建通过。
- 真实项目可打开。
- 真实项目已有资产可映射回画布。
- 页面能创建 pending 图片/视频节点，并显示失败状态。

## 阻塞项

图片与视频真实生成任务都无法启动。

- `POST /api/prototyping/generate-image` 返回 422。
- `POST /api/prototyping/generate-video` 返回 422。

响应体显示后端缺少字段：

- `book_id`
- `shot_id`
- `source_node_id`

前端当前发送的是：

- `bookId`
- `shotId`
- `sourceNodeId`
- `aspectRatio`
- `durationSeconds`
- `simulateError`

后端 Pydantic 模型要求 snake_case：

- `book_id`
- `shot_id`
- `source_node_id`
- `aspect_ratio`
- `duration_seconds`
- `simulate_error`

## 截图

- `01-project-list.png`：项目列表
- `02-project-loaded.png`：真实项目进入原型工作台
- `03-image-running.png`：点击生成图片后创建 pending 节点
- `04-image-done.png`：图片任务启动失败，节点进入失败状态
- `05-video-failed-422.png`：视频任务同样 422 失败

