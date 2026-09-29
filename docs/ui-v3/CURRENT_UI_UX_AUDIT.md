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

## Current navigation and screens

当前 `ProductWorkspace` 仍以 11 个入口组织：项目控制台、内容准备、改编方向、剧本工作台、镜头工作台、创作画布、资产中心、QA 修复、任务中心、导出中心、模型管理。`ProductWorkspaceSectionContent` 在多个入口重复挂载 `ProductionWorkspaceV2Panel`，镜头、资产和项目首页都各自呈现生产状态。这证明当前导航是按功能和 Runtime 投影拼接，而不是按用户工作流组织。

## Duplicate concepts

| 重复概念 | 现有表现 | V3 处理 |
|---|---|---|
| 项目进度 | Project Stage Strip、Production Spine、Episode readiness | 统一为项目进度 + 集卡片 |
| 阻塞 | Dashboard、Production Workspace、资产中心、任务中心 | 一个 blocker resolver，按对象聚合 |
| 生成状态 | Canvas、Storyboard、Production Workspace V2 | Shot Studio 的单一 pipeline |
| 审核 | 导演方案确认、候选晋升、QA、任务按钮 | Review Inbox + Review Drawer |
| 模型配置 | 项目列表入口、模型页面、生成上下文 | Model Center；生产页面只显示只读能力摘要 |

## Workflow friction

以真实样本为例，用户从项目首页处理一个待审核候选，当前可能要在项目控制台、任务中心、创作画布、镜头工作台和资产中心之间跳转；每次还要辨认 episode、shot、候选、正式版本和上游依赖。现有深链基础可复用，但 UI 没有将这些跳转压缩为“一次点击到正确对象”。

## Runtime UI gap audit

| Runtime 能力 | 现有前端证据 | 判定 | V3 入口 |
|---|---|---|---|
| DirectorReasoning | `ProductWorkspaceDirectorTreatmentPanel` 仅覆盖导演方案草案；reasoning 证据没有独立用户面 | 部分覆盖 | Director Review |
| AutomaticStoryboard | `ProductWorkspaceStoryboardSection` 有分镜生成和修复，但与全局状态并置 | 部分覆盖 | Shot Studio / 制片台 |
| StoryboardMaterialization | 前端只显示物化/需要更新状态，没有物化集合的可视化审核 | 缺口 | Shot Studio 生产管线 |
| AutomaticKeyframePlan | `api/automatic_keyframe_api.py` 存在，但 `web/src` 没有对应 keyframe plan 页面或 service | 缺口 | Keyframe Review |
| Keyframe Review | 没有 `KeyframeReview` 组件；现有分镜字段以表单/文本出现 | 缺口 | Review Inbox + Storyboard Card |
| Keyframe Image Production | `api/keyframe_image_production_api.py` 存在，前端没有 keyframe 级生成入口 | 缺口 | Image Review |
| Image Candidate Review | `ProductionWorkspaceV2Panel` 能验证/晋升候选，但仍是技术卡片，不是视觉审核 | 部分覆盖 | Image Review |
| Shot Video Production | V2 有 VIDEO 泳道和生成按钮，视频审核与首尾帧对照缺失 | 部分覆盖 | Video Review |
| Video Candidate Review | 候选列表可见，缺少播放器、对照、批注和统一决策 | 缺口 | Video Review |
| Episode Automatic Production | `api/episode_rendering_api.py` 存在，前端没有“预计范围 → 开始 → 活动流”的集级入口 | 缺口 | 制片台 Episode card |
| Real Episode Pilot | 代码有 pilot/fixture 语义，但没有面向用户的真实集试跑入口和结果页 | 缺口 | 制片台试跑面板 |
| Stale / Recovery | `productWorkspaceRecovery` 和 stale 字段存在，但用户需要在多个页面寻找恢复动作 | 部分覆盖 | 统一恢复抽屉 |
| Production Observability | Task center 显示 `Canonical GenerationExecution`，但没有面向用户的活动流和失败解释 | 部分覆盖 | Activity + 专业详情 |

## Technical debt

- `ProductWorkspaceSectionContent` 在多个 section 重复渲染 V2 投影，导致状态来源和 CTA 竞争。
- 标准视图与专业视图只切换少量字段，尚未真正隔离内部实体和 provider 信息。
- 页面组件直接拼装 fetch 路径和业务状态，部分生产规则仍靠组件条件判断。
- 任务中心数据同时承载 workflow action、项目动态和执行记录，聚合层缺少用户意图模型。
- 真实项目仍显示 `API Proxy` 和内部实体名，说明诊断信息边界未完成。

## Keep / Redesign / Remove

### KEEP

- `web/src/domain/productionWorkspace.ts` 的快照校验、normalize 和候选/正式版本投影。
- `web/src/services/productionWorkspace.ts`、`modelRegistry.ts`、`agent.ts` 等服务层契约。
- `ProductWorkspaceShell` 的项目身份、响应式导航、刷新和标准/专业模式框架。
- `ProductWorkspaceDirectorTreatmentPanel` 的证据预览、人工编辑、确认写入和历史恢复逻辑。
- `ProductWorkspaceStoryboardContinuityPanel`、QA 和导出记录中的版本、回退、证据链能力。

### REFACTOR

- `ProductWorkspaceDashboardSection`：收敛为项目进度、集卡片、唯一下一步和 Review Queue。
- `ProductWorkspaceTasksSection`：按用户行动聚合任务，拆出 Activity stream。
- `ProductionWorkspaceV2Panel`：改为 Shot Pipeline 和技术详情抽屉的渲染器。
- `ProductWorkspaceStoryboardSection`：拆出 Shot Studio、Keyframe Review、Image Review、Video Review。
- `ProductWorkspaceAssetsSection`：改为资产身份、正式版本、使用镜头和一致性状态。
- `ProductWorkspaceModelsSection` / `ModelRegistryModal`：业务能力卡片优先，provider 详情后置。

### REPLACE

- 当前按功能拼接的一级导航，替换为“制片台 / 剧本与导演 / 镜头工坊 / 资产库 / 交付与设置”。
- 当前以 `待处理/等待上游` 混排的任务列表，替换为 Review Inbox、Activity、Blocking Issues 三种视图。
- 当前文本/字段型关键帧与候选审核，替换为视觉优先 Storyboard Card、Media Viewer 和 Review Drawer。

### REMOVE（仅在 V3 parity 和 UX acceptance 后）

- Dashboard、Storyboard、Assets 中重复挂载的独立 `ProductionWorkspaceV2Panel` 实例。
- 面向普通用户的 `API Proxy`、`Canonical GenerationExecution`、`FORMAL_ASSET_BINDINGS` 等一级文案。
- 旧版“跳页面找生成按钮”的交互和重复的 blocker 卡片。

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
