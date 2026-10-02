# Production UI V3 Browser User Journey Mock Vertical Slice Report

## 结论

本轮状态为 **PARTIAL / ASSET_BRIDGE_BLOCKED**。两次独立 mock 浏览器运行均通过可见 UI 完成项目创建、短篇内容导入、Production Skill 与改编方向锁定、剧本生成与锁稿、ScriptIR production preparation、Director Treatment 人工确认、SceneBlocking 确认、ShotPlan 确认，以及 Storyboard materialization。

唯一剩余阻塞是 `production-asset-bridge-through-ui`：V3 页面在两次运行中都没有呈现 `[data-testid="production-asset-bridge"]`，等待 60 秒后进入阻塞。资产阻塞证据步骤仍然通过，因此没有伪造实体资产、图片或视频生成结果，也没有写入完成标志 `PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_COMPLETE`。

## 本轮代码与运行修复

- `core/screenplay_compiler.py`：短但包含场景标题和对白的 mock 剧本可复用，保留参与者投影。
- `api/director_treatment_api.py`：缺失参与者时读取 EpisodeOutline 的源派生角色作为 advisory evidence，不回写 ScriptIR。
- `core/phase_c_shot_plan.py`：兼容 `beat_ref`/`beat_refs`，补齐 legacy reaction refs，并为多动作 beat 提供可执行时长承载。
- SceneBlocking / ShotPlan API 与 authority 校验继续保持版本化、人工确认、不可变 Source Fact 边界。
- E2E runner 记录真实 HTTP 状态、canonical read-only projection、ShotPlan 与 Storyboard materialization 证据。

## 浏览器结果

| 项目 | 结果 |
|---|---|
| 独立运行 | 2 |
| 项目到 Storyboard 可见 UI 链路 | 通过 |
| SceneBlocking confirm | 通过 |
| ShotPlan confirm | 通过 |
| Storyboard materialization | 通过 |
| Production Asset Bridge | 阻塞（两轮均未呈现） |
| 浏览器 console errors | 0 |
| 真实外部 host | 0 |
| mock LLM / IMAGE / VIDEO | 22 / 0 / 0 |

## Provider 与安全边界

生图模型只保留 SHAPI 参考地址：[https://www.shapi.vip/](https://www.shapi.vip/)。本轮未调用 SHAPI，也未调用任何真实 LLM、图片或视频 provider；所有运行仍是 mock runtime。Source Fact 与 ScriptIR 原始事实未被修改，生成候选和确认结果保持版本化并保留人工审核门禁。

## 清理决策

- 已保留两轮最新 JSON、Storyboard/ShotPlan/SceneBlocking/资产阻塞截图和审计文件。
- 已丢弃不属于最新两轮证据的 `output/playwright/user-journey/01-director-runtime.png` 与 `02-director-runtime.png`。
- 两轮 disposable project 已通过 UI 清理：990441, 990442。

## 后续动作

1. 在 V3 production workspace 呈现 Production Asset Bridge。
2. 提供当前 scene 的实体资产上传、审核、激活和绑定状态。
3. 重新运行同一 mock journey；通过后再验证 PromptIR、SHAPI-compatible mock IMAGE/VIDEO、QA 与 Delivery export。

## 证据文件

- [runner summary](../../output/playwright/user-journey/summary.json)
- [run 1](../../output/playwright/user-journey/run-1.json)
- [run 2](../../output/playwright/user-journey/run-2.json)
- [truth audit](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_TRUTH_AUDIT.json)
- [browser QA](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_BROWSER_QA.json)
- [network audit](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_NETWORK_AUDIT.json)
- [UX friction](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_UX_FRICTION.json)
