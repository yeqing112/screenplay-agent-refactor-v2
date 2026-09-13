# Director Quality Benchmark V2 报告

生成时间：2026-09-13T01:03:42.301955+00:00

## Executive Summary

- Golden Director Scenes：8 个。
- Baseline 平均导演质量分：41.91。
- Creative Planner 平均导演质量分：86.13。
- 平均提升：44.22 分。
- 本次运行完全离线，未调用真实 LLM、生图、视频或对象存储。
- 真实 MiMo Golden Scene Pilot：6 个真实场景、6 次调用，4 个候选通过，1 次事实越权、1 次创意契约越界；未发生数据库、媒体或对象存储写入。
- 真实 MiMo 通过样本平均分：62.41（对应 baseline 36.78，提升 25.63）；未达到 Production Shadow 默认切换条件。

## Golden Scene 说明

场景来源为《潮汐回声》现有批准 Treatment/SceneBlocking（6 个）和仓库已有测试 fixture（2 个）；未写入生产表。

| 场景 | 类型 | 来源 |
|---|---|---|
| 红伞幻影（一） | 双人对话 | 潮汐回声 approved treatment + approved scene blocking |
| 红伞幻影（二） | 悬疑 | 潮汐回声 approved treatment + approved scene blocking |
| 回声照相馆 | 信息揭示 | 潮汐回声 approved treatment + approved scene blocking |
| 暗房门口的试探 | 情绪转折 | 潮汐回声 approved treatment + approved scene blocking |
| 暗房惊魂 | 权力变化 | 潮汐回声 approved treatment + approved scene blocking |
| 暗房惊魂（2） | 人物入场 | 潮汐回声 approved treatment + approved scene blocking |
| 关键道具交接 fixture | 关键道具 | existing_test_fixture |
| 无对白反应 fixture | 无对白或少对白 | existing_test_fixture |

## Baseline 与 Creative Planner

两种方案共享同一 Script/Treatment/SceneBlocking/结构化 ShotPlan 事实投影；Planner 只改变导演创意字段，保留 plan_shot_id、beat、事件、资产绑定、首尾状态和连续性合同。

## 评分与指标

- Structural gate：由既有 `score_runtime` 独立计算；本报告没有把创意分混入结构门禁。
- Director Quality：10 维、0–100 加权评分；平均 delta = **44.22**。
- Blind review：已输出 Version A / Version B 结构，未伪称为真人偏好；本地离线阶段未运行 Judge。
- Fact override：0。
- MiMo token/cache/latency（真实 Pilot）：6 calls，prompt 30,702，cached 0，completion 18,633，total 49,335，cache hit rate 0%，平均延迟 49,457.54ms。

## Real MiMo Golden Scene Pilot

- 范围：仅复用《潮汐回声》三集中的 6 个已批准 Treatment/SceneBlocking 场景；未重新导入剧本，未调用生图、视频或对象存储。
- 结果：4/6 候选通过；第 2 个场景因输出 `scene_name/unknowns` 事实字段触发 `DIRECTOR_FACT_OVERRIDE`，第 4 个场景因辅助镜头缺少来源节拍触发创意契约错误。
- 质量：通过样本 planner 平均 62.41，baseline 平均 36.78，提升 25.63；绝对分数和稳定性均不足以进入 Production Shadow 默认路径。
- 审计：6 次调用均记录模型、请求指纹、token、延迟和状态；cached tokens 为 0，未保存提示词正文或密钥。
- 证据文件：`artifacts/director-quality-v2-mimo-pilot-20260913T012652Z.json`。

## Per-scene Before/After

| 场景 | Baseline | Planner | Delta |
|---|---:|---:|---:|
| 红伞幻影（一） | 61.88 | 88.08 | 26.2 |
| 红伞幻影（二） | 61.45 | 87.85 | 26.4 |
| 回声照相馆 | 28.39 | 81.7 | 53.31 |
| 暗房门口的试探 | 28.61 | 82.24 | 53.63 |
| 暗房惊魂 | 28.39 | 81.7 | 53.31 |
| 暗房惊魂（2） | 28.45 | 81.85 | 53.4 |
| 关键道具交接 fixture | 50.3 | 92.8 | 42.5 |
| 无对白反应 fixture | 47.8 | 92.8 | 45.0 |

## 十维导演质量评分（Planner 平均）

| 维度 | 平均分（0–10） | 权重 |
|---|---:|---:|
| DRAMATIC_CLARITY | 8.0 | 15% |
| SHOT_MOTIVATION | 10.0 | 15% |
| EMOTIONAL_PROGRESSION | 7.36 | 12% |
| VISUAL_STORYTELLING | 10.0 | 12% |
| SPATIAL_CLARITY | 10.0 | 10% |
| PERFORMANCE_DIRECTION | 10.0 | 10% |
| EDIT_RHYTHM | 6.04 | 8% |
| INFORMATION_STRATEGY | 10.0 | 8% |
| POWER_DYNAMICS | 8.0 | 5% |
| SHOT_DIVERSITY | 2.92 | 5% |

## 当前结论

离线 shadow planner 能在不改事实的前提下补齐镜头动机、构图、表演方向和信息策略，但真实 MiMo Pilot 只在 4/6 场景通过，且平均分 62.41；因此当前不得把 creative planner 切为 Production default，必须继续优化输出契约和导演质量后再复测。

## 失败案例与瓶颈

- 旧版 deterministic ShotPlan 的创意字段缺失导致 baseline 分数偏低；这是基线证据而非评分规则放宽。
- 真实 MiMo 输出存在事实字段回写和未绑定辅助镜头，尽管门禁已正确 fail-closed。
- 主要瓶颈：LLM 输出 schema 遵循度、情绪递进与信息揭示的导演决策质量仍不稳定；当前不能仅凭离线 surrogate 分数放行。
