# 阶段九：真实图片生成 UI 闭环与持久化说明

## 本阶段目标

把分镜生产中的图片生成体验补成完整闭环：

- 用户只从一个统一入口触发图片任务
- UI 清楚显示生成中 / 成功 / 失败
- 版本节点、采用状态和模型来源都可见
- 刷新后图片节点、失败状态和来源 metadata 不丢

## 当前实现

### 1. 统一图片生成入口

- 镜头节点、参考资产节点、右侧属性面板和批量生成，最终都会进入同一套任务流：
  - 前端：`web/src/prototyping/SceneComposer.tsx` -> `runRealGeneration`
  - 请求序列化：`web/src/prototyping/sceneComposerTaskService.ts`
  - 后端任务入口：`/api/prototyping/generate-image`

- 是否走 Mock / 真实 provider，不由用户手动选择技术实现，而由当前默认图片模型决定：
  - `prototype-task-adapter` => Mock
  - `openai-compatible` => 真实 / fake 图片 provider

### 2. 生成中状态

- 创建 pending 图片节点时，前端会立即写入：
  - `taskStage=queued`
  - `startedAt`
  - `modelProfileId`
  - `modelName`
  - `provider`
  - `usesMock`
  - `sourceNodeId`
  - `sourceAssetId`
  - `prompt`

- UI 会显示：
  - 当前阶段
  - 任务来源
  - 当前模型
  - Provider
  - 开始时间

- 同一来源节点的同类任务正在运行时，会阻止重复启动：
  - 镜头 -> 分镜图
  - 参考资产 -> 参考图
  - 分镜图 -> 视频
  - 已有视频 -> 新视频分支

### 3. 生成完成后的回填

- 任务成功后，节点会更新：
  - 标题 / 版本号
  - 预览图
  - `assetId`
  - `assetUri`
  - `modelProfileId`
  - `modelName`
  - `provider`
  - `usesMock`
  - `prompt`
  - `completedAt`
  - `sourceNodeId`
  - `sourceAssetId`

- 真实和 Mock 任务完成后，摘要会分别写成：
  - `真实分镜图资产`
  - `Mock 分镜图资产`

### 4. 失败恢复

- 失败节点会保留：
  - `errorMessage`
  - `taskStage=error`
  - `lastErrorAt`

- 失败任务会进入：
  - 失败任务中心
  - 问题清单

- 用户可以：
  - 在节点面板重试
  - 在失败任务中心重试
  - 切回 Mock 后继续生成

### 5. 采用版本与持久化

- 前端采用版本仍通过：
  - `adoptVersion(...)`
  - `persistAdoptedVersion(...)`

- 后端保存到 `StoryboardShot.asset_links` 时会：
  - 保留全部图片版本
  - 保证同一镜头只有一个 `adopted=true`
  - 重新采用时更新原有 adopted 标记

### 6. 模型注册表 API Key 保留

本阶段修复了一个关键持久化问题：

- 之前当前端重新保存模型注册表、但没有重新输入 `api_key` 时，后端会把已有密钥擦空
- 现在 `save_registry(...)` 会在以下条件下保留已有密钥：
  - 同一 profile id
  - 前端本次未提供新的 `api_key`
  - 旧 profile 已有有效密钥
  - provider 不是 Mock

这能避免：

- 重启后 fake / 真实图片 provider 失效
- UI 看起来默认模型还在，但实际生成时报“缺少 API Key”

## metadata 字段说明

阶段九重点补齐后的图片任务 metadata 结构如下：

```json
{
  "source": "real",
  "provider": "openai-compatible",
  "modelProfileId": "stage8-image-fake",
  "modelName": "fake-image-model",
  "usesMock": false,
  "prompt": "镜头提示词",
  "createdAt": "2026-06-26T13:00:00Z",
  "startedAt": "2026-06-26T13:00:00Z",
  "completedAt": "2026-06-26T13:00:03Z",
  "sourceNodeId": "shot-8",
  "sourceAssetId": "image-previous-id",
  "assetScope": "shot",
  "assetSubject": "8",
  "imageRole": "storyboard"
}
```

## fake / 真实 provider 配置建议

### fake 图片 provider

- `provider = openai-compatible`
- `base_url = http://127.0.0.1:8891/v1`
- `model_name = fake-image-model`
- `api_key = secret-test-key`

### 错误 provider（失败链路）

- `provider = openai-compatible`
- `base_url = http://127.0.0.1:8899/v1`
- `model_name = bad-image-model`
- `api_key = bad-test-key`

## 持久化检查建议

1. 在分镜生产中选择镜头生成图片
2. 等待节点完成回填
3. 刷新页面
4. 确认以下信息仍在：
   - 图片版本节点
   - 预览图
   - 采用状态
   - `modelProfileId`
   - `provider`
   - `usesMock`

## 当前自动化覆盖

- `tests/test_model_registry.py`
  - 保留已有 API Key
  - 真实视频默认保护
  - embedding / image / video 默认项

- `tests/test_generation_adapters.py`
  - 真实图片 adapter 成功
  - 认证失败错误映射

- `tests/test_creative_task_persistence.py`
  - 图片任务 trace metadata
  - 图片资产落库
  - 采用版本切换持久化

- `web/src/prototyping/sceneComposerTaskService.test.ts`
  - pending 节点 metadata
  - 完成节点 metadata
  - Mock / 真实来源区分
