# 生产推进下一步清单

生成时间：2026-09-12 21:05（Asia/Shanghai）

## 当前事实

- active 生产样本：`990400`，1 个项目、3 个镜头。
- 最新统一门禁：`artifacts/production-release-gate-2026-09-12T12-58-31-143Z.md`。
- 确定性回归：`651 passed`；Golden：`5/5`；前端生产构建通过。
- H3 只读预检：`990400 / E1 / S1`，6 秒、2 张锁定多参考；当前参考图不是 provider 可访问公网 URL。

## 操作员输入（必须由用户提供）

1. 在正式工作台创建或导入至少 2 个真实项目，累计补足至少 27 个真实镜头，不能复制、伪造或激活孤儿证据。
2. 在真实镜头中保留至少一条 `needs_information` 意图状态和一条 `conflict` 节拍状态，用于验证门禁不会把缺证据误判为通过。
3. 如执行外部灰度，明确确认模型费用、七牛参考图发布和 H3 提交；未确认时只允许预检。

## 执行顺序

### A. 样本登记

```powershell
npm run validate:sample-registry
npm run register:production-sample -- --book-id <真实书号> --book-id <真实书号>
```

登记命令默认 dry-run；只有设置确认令牌后才写入注册表。

### B. 质量门禁

```powershell
npm run audit:shot-planning:gate
npm run audit:storyboard:zero-error-gate
```

要求：至少 30 个真实 active 镜头，且覆盖 `ready / needs_information` 与 `ready / conflict`。

### C. Prompt Compiler 灰度

先执行 clone-only 预检；真实 LLM 必须显式设置运行开关和确认令牌，只保存候选草案，不直接写 Prompt Version。

### D. H3 媒体灰度

先发布已锁定场景/人物参考图，再提交 1 个短样本；验证图片回收、视频回填、任务状态、连续性证据和 QA。临时七牛域名只允许本次灰度，稳定 HTTPS 域名仍是正式生产前置条件。

### E. 最终放行

```powershell
npm run gate:production
```

只有生产配置、样本数量/状态、Prompt 审计、确定性回归和 3 项目真浏览器写入链路全部通过，才可进入上线评审。

## 明确不做

- 不使用 `991119` 孤儿证据凑样本。
- 不复制历史镜头、伪造状态或通过白名单掩盖 warning/error。
- 不在未确认时调用 LLM、GPT Image 2、MiniMax H3 或上传对象存储。
- GitHub 云端 CI 与智能导演台 Agent 扩展继续后置。
