# 75API MiniMax H3 默认 VIDEO 零调用审计

## 复查结果

- 75API H3 适配与传输边界：通过
- 相关单元与边界测试：13 passed
- 当前 VIDEO 默认：`local-video-ex8l4t` / `75api-minimax-h3` / `minimax_h3_no_audios`
- 当前 75API profile：1
- 本轮真实 Provider 调用：0
- 真实 VIDEO Final Closure：未执行

## 默认切换门禁

模型管理中的切换已经写入运行注册表：`local-video-ex8l4t` 当前是 VIDEO 默认，provider 为 `75api-minimax-h3`，传输绑定为 `75api-minimax-h3.video.v1`。模型配置结构校验通过，并且该校验没有发起真实扣费任务。

这个默认 profile 对应仓库已有的 75API MiniMax H3 适配器。飞书页面当前展示的是 GROK1.5（`grok-imagine-video-1.5-preview`）合同，两者的模型名、时长、分辨率和图片数量限制不同，需要保持为独立 profile。

## 后续条件

1. 新建独立 VIDEO closure budget；v3 的 reserve 不继承。
2. 保持 zero-call selector、payload、image-conditioned、5–15 秒和最多 8 张参考图门禁。
3. 预算获批后，才允许真实提交 initial 与 regenerate。

详细机器可读审计见同目录的 `PRODUCTION_UI_V3_75API_H3_DEFAULT_VIDEO_ZERO_CALL_AUDIT.json`。
