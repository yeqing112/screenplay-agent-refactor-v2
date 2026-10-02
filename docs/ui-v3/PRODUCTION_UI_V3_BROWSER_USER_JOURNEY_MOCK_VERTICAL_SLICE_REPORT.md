# Production UI V3 Browser User Journey Mock Vertical Slice Report

## 结论

本轮结论为 **PARTIAL / ASSET_BLOCKED**。两次独立浏览器运行均从项目列表开始，并通过可见 UI 完成：项目创建、短篇内容导入、Production Skill 与改编方向锁定、剧本生成、剧本锁稿/放行、ScriptIR production preparation、production Director Treatment 预览/LLM mock 候选/人工确认、Scene Blocking 预览，以及资产中心与项目删除。

生产 Scene Blocking 确认被后端真实门禁拒绝，原因是 `INVALID_AXIS_SUBJECT` 和 `SCENE_ASSET_MISSING`。因此本轮没有伪造 ShotPlan、Storyboard、PromptIR、媒体或交付结果，也没有写入完成标志 `PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_COMPLETE`。

## 本轮代码修复

- `api/script_ir_preparation_api.py`：对不可变 legacy Markdown screenplay 做只读解析，生成版本化 ScriptIR candidate；不改写 `Script` 原文或 Source Fact。
- source anchor 绑定按 immutable evidence block 匹配场景名，不再把所有 blocking requirement 粗暴绑定到 `E0001`。
- `scripts/e2e-production-ui-v3-user-journey.js`：修复默认展开内容表单误折叠；内容等待 120 秒；补齐脚本生成、锁稿/放行、生产准备、Treatment、SceneBlocking 证据、canonical read-only audit；响应错误进入报告。

## 浏览器证据

- 两轮 runner 汇总：[summary.json](../../output/playwright/user-journey/summary.json)
- 真值审计：[PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_TRUTH_AUDIT.json](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_TRUTH_AUDIT.json)
- 浏览器 QA：[PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_BROWSER_QA.json](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_BROWSER_QA.json)
- 网络审计：[PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_NETWORK_AUDIT.json](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_NETWORK_AUDIT.json)
- UX friction：[PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_UX_FRICTION.json](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_UX_FRICTION.json)

## 外部调用与安全

- 真实外部 host：0（列表：[]）。
- mock ledger：LLM 234，IMAGE 0，VIDEO 0。
- SHAPI（https://www.shapi.vip/）本轮没有真实调用；仍按 mock runtime 验收。
- 所有业务 mutation 均由可见 UI 触发；runner 只读取 canonical projection 做审计。
- 990400 保留且本轮写入数为 0；998755 未恢复或创建。
- 本轮调试遗留项目 990403、990404 已通过项目列表 UI 删除。

## 当前阻塞与后续顺序

1. 资产中心需要可见的实体资产上传、审核、激活、绑定入口，并在 Scene Blocking 前可提供当前 scene asset。
2. SceneBlocking 预览需要在提交前修复 camera axis subject，使其引用 participants。
3. 通过后再继续 ShotPlan production confirm、canonical storyboard materialization、PromptIR、SHAPI-compatible mock IMAGE/VIDEO、QA 和 Delivery export。

## 验证结果

- 两次 runner 均无外部 host、无浏览器 console error。
- 两次均通过 UI 删除自己的 disposable project。
- ScriptIR production preparation 两次通过；canonical projection 返回 `read_only=true`、`authority_source=current_authority_pointers_only`。
- SceneBlocking confirm 两次复现同一真实 blocker；未绕过门禁。
