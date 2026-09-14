# Director Quality V2.4.1 — Targeted Tail Pilot Report

执行时间：2026-09-14 12:16 UTC
模型：`mimo-v2.5`（profile `local-llm-2vydoz`）
来源冻结：`artifacts/director-quality-v2-4-b2-freeze.json`
结果产物：`artifacts/director-quality-v2-4-1-targeted-tail-pilot-20260914T115313Z.json`

## 1. 执行边界

- 仅处理冻结 B2 中 `tail_repair.triggered=true` 的 15 个场景；
- 未重新运行 first-pass planner，未重新生成 B2 baseline；
- 未生成图片或视频；
- 未写入 Production、Storyboard、Production Shadow 或对象存储；
- 每个 root cause 最多两次修复尝试，失败后回退原合法 candidate；
- 不接受模型直接输出 canonical patch，所有候选必须先通过 typed Repair IR 与 deterministic compiler。

## 2. 结果摘要

| 指标 | 结果 |
|---|---:|
| 选中场景 | 15 |
| 实际执行场景 | 15 |
| Tail Repair Execution Coverage | 100% |
| Root Cause 执行数 | 27 |
| MiMo 调用数 | 54（每个 root cause 两次） |
| IR First Pass Valid | 0 / 27 |
| IR Final Valid | 0 / 27 |
| Canonical Compile | 0 / 27 |
| Candidate Contract Pass | 15 / 15（回退 baseline） |
| 接受 root cause | 0 |
| 回退 root cause | 27 |
| Tail Repair Success Rate | 0% |
| DQ 平均（Before） | 44.286 |
| DQ 平均（After） | 44.286 |
| DQ 平均变化 | 0 |
| CV After | 未重放（保持 before 值） |
| Fact Override Accepted | 0 |

## 3. 失败原因

54 次调用均未返回要求的 `director_tail_repair_ir_v1` 结构。MiMo 返回了旧式或自由结构（例如 `repair_patch`、`emotion_arc_repairs`、`shot_modifications`、`patch` 等），触发 typed IR 的 forbidden-field 校验；FORMAT_REPAIR 重试同样不合规。系统没有增加 alias、放宽白名单或接受模型生成的 canonical path。

这属于 provider 输出契约不合规，不是事实覆盖被接受，也不是生产链路故障。所有 rejected output 均未应用，候选指纹保持 baseline。

## 4. 门禁判定

Targeted Tail Pilot **未通过**：

- 覆盖率 100% 达标；
- IR First-Pass / Final Valid 均为 0%，未达到协议门槛；
- Canonical Compile 为 0%，未达到 100%；
- Tail Repair Success Rate 0%，DQ Delta 0；
- Candidate Contract Pass 仅来自回退 baseline，不能证明修复候选通过；
- 无事实覆盖接受、无 Production/Storyboard/Shadow/媒体/存储副作用。

按 V2.4.1 计划，本轮必须 STOP：

1. 不执行 Full 24；
2. 不开启 Production Shadow；
3. 不写入 Production Storyboard；
4. 不自动重试真实 MiMo。

## 5. 下一步（未执行）

需要先在不放宽 canonical contract 的前提下完成 provider 适配：

- 为 MiMo 请求增加其实际支持的结构化输出约束（若账户/端点支持）；
- 保留原始响应摘要、解析重试、HTTP 调用数与 token/cache/latency 审计字段；
- 明确区分 provider adapter 与通用 IR validator；
- 重新通过 provider-free hard gate，并取得新的显式确认后再试 Pilot。
