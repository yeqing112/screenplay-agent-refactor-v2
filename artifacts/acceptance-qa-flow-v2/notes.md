# 分镜视频生成流程新方案验收记录

日期：2026-06-24

## 结论

不通过。

## 通过项

- `docs/分镜视频生成流程方案.md` 已落档。
- `npm run test` 通过：5 个测试文件，42 个测试。
- `npm run build` 通过。
- 真实项目可进入原型工作台。
- 顶部生产统计、参考资产层开关、播放预览入口可见。
- 展开参考资产层后，节点和连线能展示完整生产结构。
- 场景资产节点可显示“生成参考图”操作。
- `POST /api/prototyping/generate-reference-image` 可成功启动任务。
- 参考图任务返回 200，轮询返回 200，并写入 `asset_links.references`。
- 参考图请求体已使用 snake_case，并包含 `reference_asset_ids`。

## 阻塞项

### 1. 普通用户点击“生成图片”未稳定触发真实任务

在新页面中按普通用户路径操作：

1. 打开项目。
2. 选择镜头。
3. 点击“生成图片”。

结果没有发出 `/api/prototyping/generate-image` 请求。

在另一轮 DOM 强制触发中，请求体能发出，且字段正确，但页面出现 `Failed to fetch`，pending 图片节点变为失败。

因此“镜头 -> 分镜图”主链路未通过浏览器验收。

### 2. 参考图/资产列表出现重复 key warning

控制台多次出现 React warning：

`Encountered two children with the same key`

重复 key 示例：

- `reference-location---image-5ae83adf68`
- `reference-location---image-0088a26e6b`

这会导致列表项重复、遗漏或状态错乱。

### 3. 参考资产出现乱码/问号

页面和 `/api/pipeline/book/5/outputs` 中能看到：

- `?????? 参考图 v1`
- `97??? 参考图 v1`
- 部分中文字段 mojibake

这说明资产 subject/title/prompt 在写入或读取时存在编码/历史脏数据问题。

### 4. 画布点击体验有遮挡问题

展开参考资产层后，部分画布节点位于左侧栏下方，普通点击被左侧栏拦截。需要通过左侧列表或 DOM 精确触发才能选中。用户视角下这是明显交互瑕疵。

## 截图

- `01-project-list.png`
- `02-project-loaded.png`
- `03-reference-layer-expanded.png`
- `04-location-selected.png`
- `05-reference-running.png`
- `06-reference-done.png`
- `07-shot2-selected.png`
- `08-storyboard-image-running.png`
- `09-storyboard-image-done-domclick.png`
- `10-fresh-image-generation.png`

## 建议修复顺序

1. 修复普通点击“生成图片/生成视频”不稳定触发的问题。
2. 修复 reference asset 列表 key 生成逻辑，确保每个列表项 key 唯一。
3. 清理或兼容已写入的乱码资产，并确认新增资产写入全链路 UTF-8 正常。
4. 调整 React Flow 初始 viewport / fitView padding，避免节点被左侧栏遮挡。
5. 复验完整链路：参考图 -> 分镜图 -> 视频 -> 成片序列 -> 刷新回填。

