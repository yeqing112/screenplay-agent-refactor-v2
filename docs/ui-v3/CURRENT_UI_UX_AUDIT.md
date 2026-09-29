# Current UI/UX Audit

## Scope

本审计针对 `PHASE_PRODUCTION_UI_V3_UX_ARCHITECTURE`，只评估现有正式产品工作台的体验结构、信息架构和状态表达，不修改 React、后端、API 或数据库。

## Evidence

审计基于真实项目“潮汐回声”（项目 ID 990402）和浏览器截图：

- `output/playwright/01-projects-empty.png`：项目空态
- `output/playwright/02-projects-populated.png`：项目列表
- `output/playwright/03-project-dashboard.png`：项目控制台
- `output/playwright/04-shot-workspace.png`：镜头工作台
- `output/playwright/05-task-center.png`：任务中心
- `output/playwright/06-assets-center.png`：资产中心
- `output/playwright/07-model-management.png`：模型管理
- `output/playwright/08-script-workbench.png`：剧本工作台
- `output/playwright/09-content-prep.png`：内容准备

## Findings

### P0：用户无法快速判断唯一下一步

项目控制台同时显示 Production Workspace V2、项目状态摘要、Production Spine、单集 readiness 和当前阻塞。真实样本同时出现“剧本已过期”“导演方案待设计”“场面调度待设计”“镜头规划待确认”“分镜物化需要更新”等状态。页面有“下一步行动”，但多个区域都在重复给出下一步，用户需要自行排序。

**建议**：建立单一 `Next best action` 卡片；所有其它状态只提供证据和跳转，不再重复发布主行动。

### P0：生产状态与任务状态混在一起

任务中心把人工待处理、等待上游、项目动态、系统执行和 `Canonical GenerationExecution` 放入同一列表。样本显示 56 个需要你处理、50 个等待上游，且大量“导演方案待设计”重复出现。

**建议**：拆成“需要我处理”“等待上游”“运行中”“历史”四个明确分区；同一 blocker 按 episode/scene/shot 聚合，默认展示 1 条父任务和子项数量。

### P1：工程词汇直接暴露在标准视图

`PromptIR`、`FORMAL_ASSET_BINDINGS`、`Canonical GenerationExecution`、`Production Asset` 等词对普通创作成员不可读。它们适合专业视图或诊断抽屉。

**建议**：标准视图使用“正式资产未准备”“提示词需要更新”“生成记录”；专业视图保留原始 code、实体名和 API 来源。

### P1：镜头工作台承担过多职责

镜头页同时承担全局阶段导航、生产阻塞、IMAGE/VIDEO 双泳道、镜头列表、分镜步骤、Prompt、导演语言、媒体验收和工程诊断。视觉层级无法表达当前正在编辑的对象。

**建议**：镜头页固定为“镜头上下文 + 主工作区 + 审核抽屉”三栏；把全局 readiness 和任务流移至项目侧栏或任务中心。

### P1：项目入口缺少继续制作语义

项目卡片主要展示阶段标签、章节、字数、场次和镜头数，没有明确主行动。`API Proxy: http://127.0.0.1:18765` 直接出现在用户界面。

**建议**：卡片增加“继续制作”按钮和一行阻塞摘要；API proxy 放入诊断面板。

### P1：模型管理在错误的决策层级出现

项目列表把模型管理放在全局入口，工作台又有模型管理页面。标准用户容易把模型选择误解为创作步骤。

**建议**：模型配置仅在管理员设置和生成前上下文中出现；生成页显示“当前图像模型/视频模型”只读摘要。

### P2：空态、加载态、错误态缺少统一语言

不同页面使用“未开始”“待处理”“需要更新”“暂不能继续”“暂无候选”等词，但没有统一的含义和行动规则。

**建议**：采用 `ready / needs_input / waiting_upstream / running / review / blocked / stale / failed / empty` 状态词表，所有状态都带“原因 + 下一步 + 是否可跳过”。

## Strengths to preserve

- 正式工作台已经按创作、生产与检查、管理分组。
- Production Workspace V2 体现了 IMAGE 与 VIDEO 独立泳道、候选与正式版本分离、正式版本需要审核。
- 任务可携带 episode、shot、blocker code 和目标页面，具备深链接基础。
- 资产、提示词、媒体和导出均已通过服务层访问，适合在不改 API 的前提下重排体验。

## Priority backlog

1. 统一 blocker 聚合和唯一下一步。
2. 标准视图隐藏工程词汇，专业视图提供诊断。
3. 重构镜头页三栏布局和审核抽屉。
4. 项目卡片增加继续制作与阻塞摘要。
5. 统一状态、空态、错误态和版本语言。

