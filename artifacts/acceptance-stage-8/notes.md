# 阶段八验收报告：Embedding 纳管 + 真实图片 Provider 接入

验收时间：2026-06-26 13:00  
结论：通过。

## 验收范围

阶段八按最新口径验收三条主线：

1. 模型注册表扩展 `embedding / 向量模型`，并支持 Ollama。
2. 剧本阶段的向量模型不再只依赖固定 env，而是优先读取模型注册表默认 embedding profile。
3. 第一个真实/fake 图片 provider 打通，Mock 与真实图片生成可切换，失败可恢复。

## 自动化结果

- `python -m py_compile api/model_registry.py api/server.py api/generation_adapters.py core/__init__.py core/vector_search.py core/ingest.py`：通过。
- `python -m unittest tests.test_model_registry tests.test_generation_adapters -v`：10 tests passed。
- `npm run test`：8 files / 64 tests passed。
- `npm run build`：通过；仍有 Vite chunk size warning，非阻断。

## 模型注册表能力扩展

结果：通过。

后端 `CAPABILITIES` 已扩展为：

```text
llm / embedding / image / video
```

浏览器模型管理弹窗可见「向量」分类，能展示：

- 默认向量模型
- provider: `ollama`
- model: `nomic-embed-text`
- base_url
- 向量检索说明
- 测试连接入口

证据：

- `04-stage8-model-registry-current.png`
- `browser-current.json`

## Ollama embedding 配置与测试

结果：通过。

运行态 API 新增并设置默认 embedding profile：

```json
{
  "id": "stage8-embedding-ollama",
  "capability": "embedding",
  "provider": "ollama",
  "base_url": "http://127.0.0.1:11434",
  "model_name": "nomic-embed-text"
}
```

`POST /api/model-registry/test` 返回成功，并提示向量维度。

证据：`api-runtime-current.json`

关键结果：

```json
{
  "embeddingDefaultSaved": true,
  "embeddingTestPassed": true
}
```

## 剧本向量链路读取默认 embedding

结果：通过。

通过 Python 运行态最小验证：临时设置默认 embedding profile 后实例化 `OllamaEmbedding`，确认它读取的是模型注册表 profile，并成功调用 `/api/embed` 返回向量。

证据：`embedding-runtime-python.json`

关键结果：

```json
{
  "profile_id": "stage8-python-embedding",
  "provider": "ollama",
  "model": "nomic-embed-text",
  "base_url": "http://127.0.0.1:11434",
  "vector_count": 1,
  "vector_dim": 4,
  "pass": true
}
```

说明：本轮没有跑完整小说解析到剧本生成的大任务，避免触发大模型长流程；但核心向量封装和 `core/vector_search.py` 已验证会读取默认 embedding profile。

## 真实/fake 图片 provider

结果：通过。

使用本地 fake OpenAI-compatible 图片 provider：

```text
http://127.0.0.1:8891/v1
```

验证内容：

- 图片 profile 可保存为默认。
- 连接测试通过。
- `/api/prototyping/generate-image` 使用真实 adapter。
- 任务最终 `done`。
- 结果为 `data:image/...`。
- metadata 写入 `usesMock=false`、`provider=openai-compatible`、`modelProfileId`。

证据：`api-runtime-current.json`

关键结果：

```json
{
  "imageDefaultSaved": true,
  "imageTestPassed": true,
  "realImageDone": true
}
```

## Mock 生图链路

结果：通过。

使用 `builtin-mock-image` 启动生图任务，任务成功完成，metadata 保留 Mock 来源。

证据：`api-runtime-current.json`

关键结果：

```json
{
  "mockImageDone": true
}
```

## 失败链路

结果：通过。

使用错误 base_url 的图片 profile 启动生图任务，任务进入 `error`，并返回可读错误。

证据：`api-runtime-current.json`

关键结果：

```json
{
  "failureShowsError": true
}
```

## 真实视频默认项防护

结果：通过。

阶段八仍保持阶段七防护：真实视频 provider 未接入时，不能成为默认视频模型，会回退到 `builtin-mock-video`。真实视频连接测试返回 blocked message，而不是误报成功。

证据：`api-runtime-current.json`

关键结果：

```json
{
  "videoDefaultGuard": true,
  "realVideoBlockedMessage": true
}
```

## UI / UX 验收

结果：通过。

截图确认：

- 模型管理标题为「统一管理 LLM、向量、图片和视频模型」。
- 「向量」分类可见。
- Ollama 向量模型可见。
- 图片模型分类可见。
- 真实视频未接入提示仍存在。
- 未发现乱码。
- 未发现旧主命名「导演模式 / 原型工作台 / 高级编辑 / 高级模式」。

证据：

- `01-stage8-home-current.png`
- `02-stage8-project-current.png`
- `03-stage8-production-current.png`
- `04-stage8-model-registry-current.png`
- `05-stage8-embedding-editor-current.png`
- `browser-current.json`

## 验收限制

1. 本轮没有调用真实商业图片模型，只用 fake OpenAI-compatible provider 验证协议、状态、metadata、错误链路。
2. 本轮没有跑完整小说文本到剧本生成的大任务；只验证了 embedding 封装会读取模型注册表，并能真实调用 Ollama `/api/embed`。
3. 生成结果的前端节点采用与刷新持久化主要由 API metadata 和既有分镜生产链路证明；如要做更强 QA，下一轮可专门跑一次 UI 点击生成图片、采用版本、刷新后的截图链路。

## 最终判断

阶段八通过，可以进入下一阶段。

建议下一阶段做「真实图片生成 UI 完整闭环 + 资产持久化强化」或直接进入「真实视频 provider adapter 设计」。我的建议是先做图片闭环强化：让用户在界面上清楚看到真实模型生成、失败、重试、采用、刷新持久化和模型来源，再去接视频。
