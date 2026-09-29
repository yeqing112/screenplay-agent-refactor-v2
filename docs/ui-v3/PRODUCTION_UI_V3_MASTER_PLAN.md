# Production UI V3 Master Plan

## North star

让创作成员围绕“当前对象、当前证据、唯一下一步”工作，同时让专业成员可以追踪版本、血缘和执行记录。

## Product decisions

1. 项目首页是进度和决策入口，不是所有模块的堆叠。
2. 任务中心是行动队列，不是数据库状态浏览器。
3. 镜头工作台是单镜头生产与审核空间。
4. 资产和模型设置是支持性页面，不抢占创作主线。
5. 任何 AI 产出都必须经过人工审核和版本化。

## Deliverables

- 统一 shell、状态语言和 blocker 聚合。
- V3 镜头工作台和审核抽屉规格。
- 标准/专业双视图。
- 迁移期间的旧页面回退路径和证据链接。

## Non-goals

- 不新增后端 API。
- 不替换已有 Runtime、Production Workspace V2 或 provider。
- 不自动调用真实 LLM、图像或视频 provider。
- 不自动修改剧本或 Source Fact。

