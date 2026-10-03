# 75API MiniMax H3 默认 VIDEO 零调用审计

## 复查结果

- 75API H3 适配与传输边界：通过
- 当前 VIDEO 默认：`local-video-ex8l4t` / `75api-minimax-h3` / `minimax_h3_no_audios`
- 传输绑定：`75api-minimax-h3.video.v1`
- 本轮真实 Provider 调用：`0`
- 真实 VIDEO Final Closure：未执行

## 默认切换门禁

模型管理中的切换已经写入运行注册表：`local-video-ex8l4t` 当前是 VIDEO 默认，provider 为 `75api-minimax-h3`，传输绑定为 `75api-minimax-h3.video.v1`。模型配置结构校验通过，并且该校验没有发起真实扣费任务。

模型注册表已经使用无密配置投影，并把 75API H3 的规范凭据绑定到 `env:API75_API_KEY`。解析链为：`Model Registry → credential_ref/runtime_binding_id → RuntimeCredentialResolver → ephemeral credential → transport`。旧 profile 中的 `api_key` 只保留作迁移兼容，不是规范权限来源。

当前环境没有 `API75_API_KEY`，因此预检结果为 `BLOCKED_RUNTIME_CREDENTIAL`：`credential_configured=false`、`resolved=false`、`validated=false`。预检只读取本地注册表并在内存中构造 payload，未请求 `https://www.75api.com`，也没有提交 `/v1/videos`。

这个默认 profile 对应仓库已有的 75API MiniMax H3 适配器。飞书页面当前展示的是 GROK1.5（`grok-imagine-video-1.5-preview`）合同，两者保持独立。

## 后续条件

1. 通过运行时安全配置提供 `API75_API_KEY`，完成凭据解析与验证；不要提交或粘贴密钥。
2. 重新运行纯凭据预检与 zero-call 预检。只有 `configured`、`resolved`、`validated` 全部为真时，状态才可变为 `READY_FOR_NEW_AUTHORIZED_VIDEO_BUDGET`。
3. 新建独立 VIDEO closure budget；v3 的 reserve 不继承。
4. 保持 zero-call selector、payload、image-conditioned、5–15 秒和最多 8 张参考图门禁。
5. 预算获批后，才允许真实提交 initial 与 regenerate。

详细机器可读审计见同目录的 `PRODUCTION_UI_V3_75API_H3_DEFAULT_VIDEO_ZERO_CALL_AUDIT.json`。
