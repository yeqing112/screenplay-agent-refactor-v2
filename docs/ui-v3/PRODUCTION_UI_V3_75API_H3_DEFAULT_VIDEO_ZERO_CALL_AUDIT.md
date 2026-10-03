# 75API MiniMax H3 默认 VIDEO 零调用审计

## 复查结果

- 75API H3 适配与传输边界：通过
- 当前 VIDEO 默认：`local-video-ex8l4t` / `75api-minimax-h3` / `minimax_h3_no_audios`
- 传输绑定：`75api-minimax-h3.video.v1`
- 本轮真实 Provider 调用：`0`
- 真实 VIDEO Final Closure：未执行

## 默认切换门禁

模型管理中的切换已经写入运行注册表：`local-video-ex8l4t` 当前是 VIDEO 默认，provider 为 `75api-minimax-h3`，传输绑定为 `75api-minimax-h3.video.v1`。模型配置结构校验通过，并且该校验没有发起真实扣费任务。

模型注册表使用无密配置投影，并把 75API H3 的规范凭据绑定到 `profile:local-video-ex8l4t` / `model-registry-profile-secret`。解析链为：`Model Registry → credential_ref/runtime_binding_id → RuntimeCredentialResolver → server-side KV secret lookup → ephemeral credential → transport`。旧 profile 中的 `api_key` 只由后端 resolver 读取，不会进入 canonical profile、public API、execution snapshot 或审计输出。

当前模型管理保存的 Key 已成功在服务端解析：`credential_configured=true`、`resolved=true`、`validated=true`，校验方式为 `model-registry-secret-presence / v1`。该状态只代表本地运行时凭据可解析，不代表 Provider connectivity 已验证。预检只读取本地注册表并在内存中构造 payload，未请求 `https://www.75api.com`，也没有提交 `/v1/videos`。

这个默认 profile 对应仓库已有的 75API MiniMax H3 适配器。飞书页面当前展示的是 GROK1.5（`grok-imagine-video-1.5-preview`）合同，两者保持独立。

## 后续条件

1. Model-management credential successfully resolved by Canonical Runtime。
2. 当前 zero-call 结果为 `READY_FOR_NEW_AUTHORIZED_VIDEO_BUDGET`；这一步没有创建 VIDEO v4 active budget，也没有执行真实提交。
3. 后续如获批新的独立 VIDEO closure budget，仍需保持 zero-call selector、payload、image-conditioned、5–15 秒和最多 8 张参考图门禁。

## Release-readiness backlog

`MODEL_REGISTRY_SECRET_AT_REST_HARDENING`：未来分离 profile metadata 与 credential secret，并接入加密或系统 Secret Manager。本轮不扩大范围，不阻塞当前 credential reconciliation。

详细机器可读审计见同目录的 `PRODUCTION_UI_V3_75API_H3_DEFAULT_VIDEO_ZERO_CALL_AUDIT.json`。
