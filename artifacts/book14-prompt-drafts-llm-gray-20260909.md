# book 14 / 第 1 集 Prompt 候选草案真实 LLM 灰度

- 日期：2026-09-09
- 模型：`mimo / mimo-v2.5`
- 范围：24 个已冻结 Prompt 证据包（packet `259–282`）
- 调用策略：串行、`confirmed=true + allowExternalCall=true`；镜头 17–24 在额度恢复后重新确认并重试
- 写入边界：仅保存候选草案；未创建 Prompt Version、未修改镜头、未生成图片或视频

## 结果

| 镜头 | Packet | 结果 | 供应商 HTTP | 候选诊断 |
|---:|---:|---|---:|---|
| 1 | 259 | success | 200 | pass |
| 2 | 260 | success | 200 | pass |
| 3 | 261 | success | 200 | warning（2） |
| 4 | 262 | success | 200 | pass |
| 5 | 263 | success | 200 | pass |
| 6 | 264 | success | 200 | warning（1） |
| 7 | 265 | success | 200 | warning（1） |
| 8 | 266 | success | 200 | warning（1） |
| 9 | 267 | success | 200 | pass |
| 10 | 268 | success | 200 | warning（2） |
| 11 | 269 | success | 200 | warning（2） |
| 12 | 270 | success | 200 | warning（2） |
| 13 | 271 | success | 200 | warning（1） |
| 14 | 272 | success | 200 | warning（1） |
| 15 | 273 | success | 200 | pass |
| 16 | 274 | success | 200 | warning（1） |
| 17 | 275 | success（重试） | 200 | warning（1） |
| 18 | 276 | success（重试） | 200 | warning（1） |
| 19 | 277 | success（重试） | 200 | pass |
| 20 | 278 | success（重试） | 200 | pass |
| 21 | 279 | success（重试） | 200 | pass |
| 22 | 280 | success（重试） | 200 | pass |
| 23 | 281 | success（重试） | 200 | warning（1） |
| 24 | 282 | success（重试） | 200 | warning（1） |

第一次调用镜头 17–24 时供应商返回 `402 Payment Required`；失败审计仍保留，额度恢复后经再次确认已全部重试成功。

## 下一步

- 人工审核镜头 1–24 的候选，确认后再逐镜创建新 Prompt Version。
- 候选仍未生效；任何版本写入都必须重新校验证据指纹和锁定资产。

当前候选汇总：10 个诊断为 `pass`，14 个诊断为 `warning`，没有候选进入 `blocked`。warning 主要集中在木鱼/木桶/木匣子视觉事实覆盖、和尚甲/和尚乙/和尚丙权威属性继承，以及镜头 24 的对白稿残留；这些必须在人工审核阶段处理或明确接受。
