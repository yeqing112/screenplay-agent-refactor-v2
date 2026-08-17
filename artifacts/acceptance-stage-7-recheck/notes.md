# 阶段七复验报告：模型统一管理

复验时间：2026-06-26 07:25  
结论：代码与 fresh 后端运行态通过；当前 `4173 -> 8765` 预览链路仍需重启后端后再作为最终运行态通过。

## 本轮复验范围

1. 模型管理 UI 是否正常展示 LLM / 图片 / 视频三类配置。
2. 图片默认模型是否能保存并持久化。
3. 真实视频 provider 在未接入 adapter 前是否不能作为默认视频模型。
4. 生图任务是否继续透传 `model_profile_id`。
5. 后端单测、前端测试和生产构建是否通过。

## 自动化结果

- `python -m py_compile api/model_registry.py api/server.py api/generation_adapters.py core/llm.py`：通过。
- `python -m unittest tests.test_model_registry -v`：5 tests passed。
- `npm run test`：8 files / 64 tests passed。
- `npm run build`：通过；仍有 Vite chunk size warning，非阻断。

## 关键修复复验

### 1. 代码层面

通过。

`api/model_registry.py` 已新增：

- `VIDEO_REAL_DEFAULT_ENABLED = False`
- `_is_profile_allowed_as_default`

并且 `resolve_defaults` 与 `save_registry` 都通过该函数过滤默认项。

后端测试新增并通过：

- `test_save_registry_rejects_real_video_as_default_until_adapter_ready`

### 2. Fresh 后端运行态

通过。

在 fresh 后端 `http://127.0.0.1:8017` 上，通过 API 尝试把真实视频模型 `stage7-fresh-real-video` 设置为默认，最终返回：

```json
{
  "requestedVideoDefault": "stage7-fresh-real-video",
  "resolvedVideoDefault": "builtin-mock-video",
  "resolvedVideoProvider": "prototype-task-adapter",
  "pass": true
}
```

证据：`api-fresh-8017-recheck.json`

### 3. 当前预览服务链路

未最终通过，需要重启后端。

当前前端预览 `http://127.0.0.1:4173` 代理到 `http://127.0.0.1:8765`。该 `8765` 运行服务仍表现为旧逻辑：通过 API 尝试把真实视频模型设为默认时，仍解析为真实视频默认项。

证据：`api-recheck.json`

关键字段：

```json
{
  "requestedVideoDefault": "stage7-recheck-real-video",
  "resolvedVideoDefault": "stage7-recheck-real-video",
  "resolvedVideoProvider": "openai-compatible",
  "realVideoDefaultBlocked": false
}
```

判断：不是代码仍错，而是当前 `8765` 服务未加载最新代码。fresh 后端已经证明最新代码行为正确。

### 4. 模型管理 UI

通过。

截图：`03-model-registry.png`

确认点：

- “模型注册表”可打开。
- LLM / 图片 / 视频三类配置可见。
- 图片和视频默认模型提示可见。
- 真实视频配置显示“当前工作台尚未接入真实视频 provider，暂时不能作为视频生成默认项”。
- UI 截图未见乱码。

### 5. 生成任务模型 profile 透传

通过。

通过 `generate-image` 传入 `model_profile_id=builtin-mock-image` 后，启动响应与最终任务结果均保留模型配置。

证据：`api-recheck.json`

关键字段：

```json
{
  "model_profile_id": "builtin-mock-image",
  "uses_mock": true,
  "modelProfileId": "builtin-mock-image",
  "provider": "prototype-task-adapter"
}
```

## 复验截图和证据

- `01-project-list.png`
- `02-project-opened.png`
- `03-model-registry.png`
- `browser-recheck.json`
- `api-recheck.json`
- `api-fresh-8017-recheck.json`
- `backend-fresh-8017.log`
- `backend-fresh-8017.err.log`

## 最终判断

阶段七代码修复已经达到验收标准。

但如果以用户当前打开的 `4173` 预览服务为准，还需要重启 `8765` 后端服务，让它加载最新 `api/model_registry.py`。重启后再跑一次 `api-recheck`，预期 `resolvedVideoDefault` 应为 `builtin-mock-video`。
