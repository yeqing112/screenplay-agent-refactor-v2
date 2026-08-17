# 阶段七验收报告：模型统一管理

验收时间：2026-06-26 00:36  
结论：有条件通过。

阶段七的核心链路已经可用：前端可以打开模型管理弹窗，后端提供模型注册表 API，LLM / 图片 / 视频三类 profile 能统一展示，默认模型可以保存并持久化，生成任务能够携带 `model_profile_id`，Mock 图片生成任务也能把 `provider` 和 `modelProfileId` 写回任务结果。

但还有一个必须在下一轮修掉的边界问题：后端 API 允许把真实视频 provider 设为默认视频模型，虽然当前真实视频 provider 尚未接入。UI 已经禁用了这个操作，但 API 层没有兜底，后续如果通过接口、旧数据或脚本写入，会让视频生成默认配置落到不可执行状态。

## 验收项

1. 模型注册表 API
   - 结果：通过
   - 证据：`GET /api/model-registry`、`GET /api/model-registry/defaults` 可返回 LLM / image / video 三类配置。
   - 截图/数据：`api-evidence.json`

2. 默认模型持久化
   - 结果：通过
   - 证据：通过 API 临时新增 `stage7-acceptance-image` 并设为默认图片模型后，`/defaults` 能读回该默认项；随后已恢复原默认配置。
   - 证据字段：`persistenceWorks: true`

3. Mock provider 连通性测试
   - 结果：通过
   - 证据：`POST /api/model-registry/test` 测试 `builtin-mock-image` 返回 `ok: true`。
   - 证据字段：`mockTestWorks: true`

4. 生成任务模型配置透传
   - 结果：通过
   - 证据：`POST /api/prototyping/generate-image` 携带 `model_profile_id=builtin-mock-image` 后，启动响应和最终任务结果均保留该配置，并标记 mock provider。
   - 证据文件：`generation-evidence.json`

5. 前端模型管理入口
   - 结果：通过
   - 证据：分镜工作台顶部显示当前图片/视频默认模型，并可打开“模型管理”弹窗。
   - 截图：`04-model-registry-modal.png`

6. 前端模型编辑能力
   - 结果：基本通过
   - 证据：弹窗中有 LLM / 图片 / 视频分区、默认项标识、测试连接、编辑、删除、新增、API Key、Base URL、模型名、默认参数 JSON 等字段。
   - 截图：`05-model-editor.png`

7. 真实视频模型默认项防护
   - 结果：不通过
   - 证据：API 可把 `stage7-video-real-ui` 这种 `openai-compatible` 视频 profile 设置为默认视频模型。
   - 证据字段：`backendAllowsRealVideoDefault: true`
   - 风险：真实视频 provider 还未接入时，默认视频生成会进入不可执行配置。UI 当前有防护，但后端没有防护。

8. 自动化测试与构建
   - 结果：通过
   - 后端：`python -m unittest tests.test_model_registry -v`，4 tests passed。
   - 前端：`npm run test`，8 files / 64 tests passed。
   - 构建：`npm run build` passed；仅有 Vite chunk size warning，非阻断。

## 验收截图和证据

- `01-project-list.png`
- `02-project-opened.png`
- `03-production-or-prototype-mode.png`
- `04-model-registry-modal.png`
- `05-model-editor.png`
- `browser-evidence.json`
- `api-evidence.json`
- `generation-evidence.json`

## 建议修复项

1. 后端 `save_registry` 应拒绝或自动回退真实视频 provider 默认项，直到真实视频 adapter 接入。
2. `resolve_defaults` 也应做兜底：如果 video 默认项指向真实 provider 且 adapter 未启用，应回退到 `builtin-mock-video`。
3. 返回给前端的错误信息需要保持中文可读；虽然当前 UI 正常，但代码中仍有若干乱码字符串，建议统一清理，避免错误态暴露乱码。
