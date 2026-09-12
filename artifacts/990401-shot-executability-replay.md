# 分镜可拍性节拍回放报告

生成时间：2026-09-12T14:31:03.422620+00:00

本报告是只读确定性回放：不调用 LLM、不创建 Prompt Version、不修改任何镜头。

## 汇总

- 抽样镜头：164
- 要求最少镜头：未设置
- 样本数量门禁：通过
- 必需意图状态：未设置
- 必需节拍状态：未设置
- 状态覆盖门禁：通过
- 缺少意图状态：无
- 缺少节拍状态：无
- 发布阻塞：无
- 下一步：继续执行真实浏览器回归和受控媒体灰度
- pass：143
- warning：7
- blocked：14
- 意图规划 ready：164 / needs_information：0
- 节拍规划 ready：164 / conflict：0 / needs_information：0
- 缺少已持久化结果、需受控重编译：164

## 优先治理清单

| 镜头 | 时长 | 回放结果 | 意图 | 节拍 | 动作数 | 主要问题 | 建议 |
| --- | ---: | --- | --- | --- | ---: | --- | --- |
| book 990401 / ep 1 / shot 1 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 2 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 3 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 4 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 5 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 6 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 7 | 6s | warning | ready | ready | 3 | 镜头运动与多动作并行，可能降低生成稳定性。 | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 8 | 5s | pass | ready | ready | 4 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 9 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 10 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 11 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 12 | 4s | blocked | ready | ready | 4 | 4 秒镜头包含约 4 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 1 / shot 13 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 14 | 4s | blocked | ready | ready | 3 | 4 秒镜头包含约 3 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 1 / shot 15 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 1 / shot 16 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 1 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 2 | 4s | blocked | ready | ready | 3 | 4 秒镜头包含约 3 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 2 / shot 3 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 4 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 5 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 6 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 7 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 8 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 9 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 10 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 11 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 12 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 13 | 3s | blocked | ready | ready | 4 | 3 秒镜头包含约 4 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 2 / shot 14 | 4s | blocked | ready | ready | 4 | 4 秒镜头包含约 4 个动作单元，建议不超过 2 个。；镜头运动与多动作并行，可能降低生成稳定性。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 2 / shot 15 | 5s | pass | ready | ready | 3 | - | 重新编译以写入结果 |
| book 990401 / ep 2 / shot 16 | 4s | blocked | ready | ready | 3 | 4 秒镜头包含约 3 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 2 / shot 17 | 5s | blocked | ready | ready | 5 | 5 秒镜头包含约 5 个动作单元，建议不超过 4 个。；镜头运动与多动作并行，可能降低生成稳定性。 | 延长至 7s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 3 / shot 1 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 2 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 3 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 4 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 5 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 6 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 7 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 8 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 9 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 10 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 11 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 12 | 2s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 13 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 14 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 15 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 3 / shot 16 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 4 / shot 1 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 4 / shot 2 | 4s | warning | ready | ready | 2 | 最终运动提示词识别到 2 个动作，但结构化节拍仅覆盖约 1 个；请同步节拍或精简运动提示词。 | 重新编译以写入结果 |
| book 990401 / ep 4 / shot 3 | 5s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 4 / shot 4 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 4 / shot 5 | 5s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 4 / shot 6 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 1 | 3s | blocked | ready | ready | 3 | 3 秒镜头包含约 3 个动作单元，建议不超过 2 个。；镜头运动与多动作并行，可能降低生成稳定性。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 5 / shot 2 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 3 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 4 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 5 | 4s | blocked | ready | ready | 3 | 4 秒镜头包含约 3 个动作单元，建议不超过 2 个。；镜头运动与多动作并行，可能降低生成稳定性。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 5 / shot 6 | 3s | blocked | ready | ready | 3 | 3 秒镜头包含约 3 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 5 / shot 7 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 8 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 9 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 10 | 4s | blocked | ready | ready | 3 | 4 秒镜头包含约 3 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 5 / shot 11 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 12 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 13 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 5 / shot 14 | 4s | blocked | ready | ready | 3 | 4 秒镜头包含约 3 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 5 / shot 15 | 3s | blocked | ready | ready | 3 | 3 秒镜头包含约 3 个动作单元，建议不超过 2 个。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 6 / shot 1 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 2 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 3 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 4 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 5 | 3s | warning | ready | ready | 2 | 最终运动提示词识别到 2 个动作，但结构化节拍仅覆盖约 1 个；请同步节拍或精简运动提示词。 | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 6 | 4s | warning | ready | ready | 2 | 最终运动提示词识别到 2 个动作，但结构化节拍仅覆盖约 1 个；请同步节拍或精简运动提示词。 | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 7 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 8 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 9 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 10 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 11 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 12 | 5s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 13 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 14 | 5s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 15 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 6 / shot 16 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 1 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 2 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 3 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 4 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 5 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 6 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 7 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 8 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 9 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 10 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 11 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 12 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 13 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 14 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 15 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 7 / shot 16 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 1 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 2 | 2s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 3 | 3s | warning | ready | ready | 2 | 最终运动提示词识别到 2 个动作，但结构化节拍仅覆盖约 1 个；请同步节拍或精简运动提示词。 | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 4 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 5 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 6 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 7 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 8 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 9 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 10 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 11 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 12 | 5s | warning | ready | ready | 3 | 镜头运动与多动作并行，可能降低生成稳定性。 | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 13 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 14 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 15 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 16 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 17 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 18 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 19 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 20 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 8 / shot 21 | 5s | warning | ready | ready | 3 | 镜头运动与多动作并行，可能降低生成稳定性。 | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 1 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 2 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 3 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 4 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 5 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 6 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 7 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 8 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 9 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 10 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 11 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 12 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 13 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 14 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 15 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 16 | 5s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 17 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 18 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 19 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 20 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 21 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 22 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 23 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 24 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 25 | 4s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 26 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 9 / shot 27 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 1 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 2 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 3 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 4 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 5 | 5s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 6 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 7 | 4s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 8 | 5s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 9 | 3s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 10 | 2s | pass | ready | ready | 1 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 11 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 12 | 4s | blocked | ready | ready | 3 | 4 秒镜头包含约 3 个动作单元，建议不超过 2 个。；镜头运动与多动作并行，可能降低生成稳定性。 | 延长至 6s；删减非核心动作；拆为两个连续镜头 |
| book 990401 / ep 10 / shot 13 | 3s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
| book 990401 / ep 10 / shot 14 | 5s | pass | ready | ready | 2 | - | 重新编译以写入结果 |
