# Production UI V3 Browser User Journey Mock Vertical Slice Report

## 结论

本轮达到 `PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_COMPLETE`。两轮独立浏览器运行均通过可见 UI 完成项目创建、内容导入、Production Skill/改编方向锁定、剧本生成与放行、ScriptIR production preparation、Director Treatment、Scene Blocking、ShotPlan、Storyboard materialization、Production Asset 上传/审核/激活/绑定、PromptIR、IMAGE/VIDEO mock generation、技术验证、人工批准、Official、QA 与 Delivery JSON 登记。

每轮结束后，临时项目均通过项目列表 UI 删除；保护 Book 990400 未写入。生图模型保持 SHAPI 参考地址（https://www.shapi.vip/），运行使用 deterministic builtin mock，不调用真实 SHAPI、LLM、图片或视频 provider。

## 本轮实现

- PromptIR typed Production Asset lineage 兼容历史 canonical ref，并统一 typed version/id 比较。
- Production Asset authority/pointer 增加 Book scope 与跨 Book 隔离迁移。
- Book lifecycle 清理间接 Production Asset、PromptIR、Generation、Candidate、Official、Delivery 记录。
- Storyboard materializer 统一 duration canonicalization 与 projection fingerprint。
- Shot Studio V3 增加 PromptIR 准备、模型选择状态覆盖、候选审核与 canonical Official 状态恢复。
- Generation candidate 创建后执行 deterministic technical validation；IMAGE/VIDEO Official pointer 分 lane 保存，避免 VIDEO 覆盖 IMAGE。
- VIDEO PromptIR 默认声明 `duration_seconds`，满足 canonical generation policy。

## 浏览器结果

| 指标 | 结果 |
|---|---|
| 独立运行 | 2 |
| 每轮步骤 | 18/18 通过 |
| IMAGE 生成/审核/Official | 通过 |
| VIDEO 生成/审核/Official | 通过 |
| QA 与 Delivery export record | 通过 |
| 外部 host | 0 |
| POST response errors | 0 |
| 每轮 mock LLM / IMAGE / VIDEO | 11 / 1 / 1 |
| 保护 Book 990400 写入 | 0 |

## 证据

- [runner summary](../../output/playwright/user-journey-final10/summary.json)
- [run 1](../../output/playwright/user-journey-final10/run-1.json)
- [run 2](../../output/playwright/user-journey-final10/run-2.json)
- [truth audit](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_VERTICAL_SLICE_TRUTH_AUDIT.json)
- [browser QA](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_BROWSER_QA.json)
- [network audit](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_NETWORK_AUDIT.json)
- [UX friction](PRODUCTION_UI_V3_BROWSER_USER_JOURNEY_MOCK_UX_FRICTION.json)
