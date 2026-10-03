# 75API MiniMax H3 默认 VIDEO 零调用审计

## 结果

- 75API H3 适配与传输边界：通过
- 相关单元与边界测试：13 passed
- 当前 VIDEO 默认：`local-video-7deneh` / `minimax-h3-async` / `MiniMax-H3`
- 当前 75API profile：0
- 本轮真实 Provider 调用：0
- 真实 VIDEO Final Closure：未执行

## 默认切换门禁

当前运行注册表没有 `75api-minimax-h3` profile，运行环境也没有可用的 75API credential。此时把 VIDEO 默认切到 75API 会得到不可提交的配置，因此默认值保持现状，未写入伪造的 profile 或 credential 状态。

## 后续条件

1. 在模型注册表保存 `https://www.75api.com` + `minimax_h3_no_audios` 的 75API profile。
2. 通过运行时 secret 路径提供 API Key。
3. 完成 zero-call selector、payload、image-conditioned、5–15 秒和最多 8 张参考图验证。
4. 新建独立 VIDEO closure budget 后，才允许真实提交 initial 与 regenerate。

详细机器可读审计见同目录的 `PRODUCTION_UI_V3_75API_H3_DEFAULT_VIDEO_ZERO_CALL_AUDIT.json`。
