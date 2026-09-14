# 分镜可拍性节拍回放报告

生成时间：2026-09-13T19:00:04.731622+00:00

本报告是只读确定性回放：不调用 LLM、不创建 Prompt Version、不修改任何镜头。

## 汇总

- 抽样镜头：3
- 要求最少镜头：30
- 样本数量门禁：未通过
- 必需意图状态：ready, needs_information
- 必需节拍状态：ready, conflict
- 状态覆盖门禁：未通过
- 缺少意图状态：needs_information
- 缺少节拍状态：conflict
- 发布阻塞：真实 active 镜头不足（3/30）；缺少意图状态：needs_information；缺少节拍状态：conflict
- 下一步：补充真实 active 镜头，直到达到至少 30 个；在正式镜头工作台补齐意图证据：needs_information；在正式镜头工作台补齐节拍证据：conflict
- pass：3
- warning：0
- blocked：0
- 意图规划 ready：3 / needs_information：0
- 节拍规划 ready：3 / conflict：0 / needs_information：0
- 缺少已持久化结果、需受控重编译：0

## 优先治理清单

| 镜头 | 时长 | 回放结果 | 意图 | 节拍 | 动作数 | 主要问题 | 建议 |
| --- | ---: | --- | --- | --- | ---: | --- | --- |
| book 990400 / ep 1 / shot 1 | 6s | pass | ready | ready | 2 | - | - |
| book 990400 / ep 1 / shot 2 | 5s | pass | ready | ready | 2 | - | - |
| book 990400 / ep 1 / shot 3 | 6s | pass | ready | ready | 2 | - | - |
