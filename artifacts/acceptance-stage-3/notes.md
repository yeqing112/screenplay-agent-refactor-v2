# 阶段三验收记录：单集短剧成片工作流闭环与版本采用体验收束

验收时间：2026-06-25 00:34-00:37

## 结论

通过。

阶段三核心目标已经达成：用户可以从图片版本节点生成视频，采用视频版本，成片序列会更新，播放预览能展示已采用视频和缺失镜头，刷新后状态仍能回填。

## 工程检查

- `npm run test`：通过，5 个测试文件，48 个测试全部通过。
- `npm run build`：通过。

## 流程验收

1. 项目列表
   - 状态：通过。
   - 证据：`01-project-list.png`
   - 说明：能看到“神农架历险记”，可进入项目。

2. 打开第 1 集创作沙盒
   - 状态：通过。
   - 证据：`02-project-loaded.png`
   - 说明：顶部显示镜头、参考、分镜图、视频、成片、待入成片等总览指标。

3. 自动布局与画布可读性
   - 状态：通过。
   - 证据：`03-auto-layout.png`
   - 说明：画布保留“文本层 / 镜头节点 / 图片版本 / 视频版本 / 成片序列”的层级结构。

4. 下一步行动引导
   - 状态：通过。
   - 证据：`04-shot-next-step.png`
   - 说明：选择镜头 2 后，右侧明确显示“下一步生成视频”，并解释“分镜图已经就绪，可以从分镜图节点发起视频生成，再采用进入成片”。

5. 图片节点点击与遮挡复查
   - 状态：通过。
   - 证据：`05-image-selected.png`
   - 说明：本轮检测到 5 个可见图片节点，5 个中心点击点均未被其它节点遮挡。

6. 图片生成视频
   - 状态：通过。
   - 证据：`06-video-generated.png`
   - 关键请求：
     - `POST /api/prototyping/generate-video -> 200`
     - `GET /api/prototyping/tasks/933c0b950c3a -> 200`
   - 说明：请求体带入 `book_id`、`episode`、`shot_id`、`source_node_id`、`source_asset_id`、`target_kind: video`、`reference_asset_ids`、`duration_seconds`。

7. 视频版本节点与版本管理
   - 状态：通过。
   - 证据：`07-video-selected.png`
   - 说明：视频节点右侧显示版本列表、生成时间、来源、采用状态；未采用版本提供“采用版本”入口。

8. 采用/编入成片
   - 状态：通过。
   - 证据：`08-adopt-state.png`
   - 关键请求：
     - `POST /api/prototyping/adopt-version -> 200`
   - 说明：采用后当前视频显示“当前采用中”，工作流关系显示进入“第 1 集成片序列”。

9. 成片序列查看
   - 状态：通过。
   - 证据：`09-sequence-selected.png`
   - 说明：成片序列能查看引用的视频版本，采用状态可见。

10. 播放预览
    - 状态：通过。
    - 证据：`10-preview.png`
    - 说明：预览面板展示已采用视频；未生成或未采用视频的镜头明确显示“暂无采用视频 / 缺视频”，不会静默消失。

11. 刷新后回填
    - 状态：通过。
    - 证据：`11-after-refresh.png`
    - 说明：刷新后项目、分镜图、视频、成片状态仍能显示，未见 `???` 乱码。

## 非阻塞观察

- 浏览器导航/刷新期间仍会偶发 `GET /api/books net::ERR_ABORTED`、`GET /api/nodes/registry net::ERR_ABORTED`。后续同接口均返回 200，本轮未影响核心流程。
- 控制台有一条 404 静态资源类报错，未影响阶段三主流程。后续如果要做发布级验收，建议追踪具体资源路径并清理。

## 截图清单

- `01-project-list.png`
- `02-project-loaded.png`
- `03-auto-layout.png`
- `04-shot-next-step.png`
- `05-image-selected.png`
- `06-video-generated.png`
- `07-video-selected.png`
- `08-adopt-state.png`
- `09-sequence-selected.png`
- `10-preview.png`
- `11-after-refresh.png`

