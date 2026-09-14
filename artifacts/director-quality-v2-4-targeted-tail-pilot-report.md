# Director Quality V2.4 — Targeted Tail Pilot Report

执行时间：2026-09-14 09:03 UTC  
模型：`mimo-v2.5`（profile `local-llm-2vydoz`）  
来源冻结：`artifacts/director-quality-v2-4-b2-freeze.json`  
结果产物：`artifacts/director-quality-v2-4-targeted-tail-pilot-20260914T090340Z.json`

## 1. 执行边界

- 仅处理冻结 B2 中 `tail_repair.triggered=true` 的 15 个场景；
- 未重新运行 first-pass planner；
- 未生成图片或视频；
- 未写入 Production、Storyboard、Production Shadow 或对象存储；
- 每个 root cause 最多两次修复尝试，失败后回退原合法 candidate。

## 2. 结果摘要

| 指标 | 结果 |
|---|---:|
| 选中场景 | 15 |
| 实际执行场景 | 15 |
| Tail Repair Execution Coverage | 100% |
| Root Cause 选择 | 27 |
| Repair 尝试记录 | 54 |
| 接受场景 | 0 |
| 回退场景 | 15 |
| Tail Repair Success Rate | 0% |
| DQ 平均（Before） | 44.286 |
| DQ 平均（After） | 44.286 |
| DQ 平均变化 | 0 |
| CV 平均（Before） | 38.6097 |
| CV After | 未重放 |
| Contract Final Pass | 100%（回退 baseline 后） |

所有场景均保留 baseline candidate，未有未经契约验证的模型输出进入候选或生产链路。

## 3. 失败原因

MiMo 返回的大多数内容是自然语言导演方案或自定义 JSON，而不是要求的
`director_creative_patch_v1` envelope。严格编译器拒绝了这些顶层字段，未放宽白名单：

- 53 次：`document contains forbidden fields`；常见字段包括
  `patch_type`、`patch_version`、`target_dimension`、`root_cause`、
  `scene_strategy_subset`、`immutable_contract_subset` 等；
- 1 次：`TARGET_DIMENSION_NOT_IMPROVED`。

因此本轮失败属于“模型输出契约不合规 / 目标维度未改善”，不是事实覆盖被接受，也不是生产链路故障。所有 rejected output 均未应用。

## 4. 门禁判定

Targeted Tail Pilot **未通过**：

- 覆盖率 100% 达标；
- Success Rate 0% < 80%；
- DQ Delta 0 < +15；
- CV 未重放，不能宣称价值提升；
- 无事实覆盖接受、无新增生产/媒体/存储副作用。

按 V2.4 计划，本轮必须 STOP：

1. 不执行 Full 24 V2.4 Pilot；
2. 不开启 Production Shadow；
3. 不写入 Production Storyboard；
4. 不自动重试真实 MiMo。

## 5. 后续修复建议（未执行）

下一轮若要重试，必须先完成通用化的结构化输出约束与观测补强：

- 在请求层使用供应商支持的 JSON schema / response format（若 profile 能力允许）；
- 在接收层保留原始响应、解析重试次数、HTTP 调用数、token/cache/latency 审计字段；
- 仅允许 `schema_version`、`patches`、`auxiliary_shot_proposals` 通过编译入口；
- 重新通过 provider-free 单元、集成和全量回归；
- 获得新的显式确认后，才可再次运行 Targeted Tail Pilot。

