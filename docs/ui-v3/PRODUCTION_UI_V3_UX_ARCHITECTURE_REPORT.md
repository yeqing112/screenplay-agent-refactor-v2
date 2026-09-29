# Production UI V3 UX Architecture Report

## Executive summary

本轮完成正式产品工作台的 UX/UI 架构审计和 V3 设计基线。结论是：现有 Runtime、真实数据投影、候选与正式媒体分离、版本和任务深链基础可复用；主要问题集中在信息层级、状态语言、重复 blocker 和镜头页职责过载。

## Audited evidence

真实项目“潮汐回声”（990402）在项目列表、项目控制台、任务中心、资产中心、模型管理、剧本工作台、内容准备和镜头工作台中完成浏览审计。截图位于 `output/playwright/`。

观测到的样本状态包括：项目 10 章、约 0.3 万字、3 集、42 镜；Production Workspace V2 显示 9%，当前因剧本过期、正式资产缺失和导演方案未完成而阻塞；任务中心显示 56 个任务、50 个等待上游。

## Architecture

V3 采用“项目 → 集 → 场 → 镜头 → 资产/提示词/媒体 → 审核”的对象层级。项目首页只做全局判断，任务中心只做行动队列，镜头工作台只做单镜头生产与审核。所有页面共享 canonical state、Next best action、BlockerGroup、VersionRail 和 ReviewDrawer。

## Governance

- Source Fact、ScriptIR 和既有权威投影保持只读事实边界。
- 用户编辑进入草稿或新版本。
- AI 仅生成建议或候选，人工批准后才形成正式版本。
- Prompt lineage、provider metadata、execution record 和审核记录在专业视图可追踪。

## Implementation order

1. 状态语言与 blocker 聚合。
2. 项目首页唯一下一步。
3. 任务中心按行动分层。
4. 镜头工作台三栏结构与审核抽屉。
5. QA、导出和模型设置统一组件。

## Acceptance checklist

- [x] 完成真实 UI 截图证据。
- [x] 输出用户旅程、信息架构、Screen inventory。
- [x] 输出 Shot Studio、Review、状态语言和设计系统规格。
- [x] 输出前端架构和迁移计划。
- [x] 明确禁止真实 provider 调用、后端迁移和自动改剧本。
- [ ] 后续实施阶段完成组件重排和可用性验证。

