# Screen Inventory V3

| Screen | 目标 | 主 CTA | 数据来源 | 状态覆盖 |
|---|---|---|---|---|
| 项目列表 | 选择或新建项目 | 继续制作 / 新建项目 | `/api/books` | loading, empty, error, duplicate |
| 项目首页 | 判断全局进度 | 处理唯一下一步 | production workspace + readiness | ready, blocked, stale |
| 内容准备 | 稳定原始内容 | 确认内容基础 | `/api/books`, chapters, production skill | draft, ready, import error |
| 改编方向 | 锁定项目主方向 | 锁定方向 | adaptation-state, production-skill-state | draft, locked, needs review |
| 剧本工作台 | 审阅集级剧本 | 查看证据 / 锁稿 | book outputs, QA workbench, script decisions | open QA, stale, locked |
| 镜头工作台 | 编辑和审核单镜头 | 保存镜头计划 / 生成候选 | storyboard, production workspace v2 | needs input, ready, candidate, official |
| 创作画布 | 查看跨对象关系 | 继续当前任务 | agent sessions, timeline | idle, running, paused, needs attention |
| 资产中心 | 管理正式视觉资产 | 绑定资产 / 生成参考图 | visual assets, reference assets | missing, draft, approved |
| QA 修复 | 解决可解释问题 | 预览修复 / 应用修复 | QA workbench | open, preview, applied, rollback |
| 任务中心 | 聚合用户行动 | 处理任务 / 重试 | creative tasks + production blockers | needs me, waiting upstream, running, history |
| 导出中心 | 生成交付包 | 创建导出 | export records, QA workbench | ready, blocked, exporting, completed |
| 模型与存储设置 | 管理能力配置 | 保存配置 | model registry, public asset storage | configured, missing key, unhealthy |

## Global shell requirements

- 顶部显示项目名、当前对象、数据新鲜度。
- 右侧固定“唯一下一步”或“当前任务”入口。
- 标准视图显示业务语言，专业视图显示内部实体和 API 来源。
- 所有 mutation 返回版本号、时间和可回退入口。

## Screen contracts

以下契约把每个核心 Screen 的用户目标、动作、数据和状态写成实施前的验收基线。API 是现有契约的使用范围，V3 不新增后端资源。

### Project Home / 制片台

- **Purpose / goal**：5 秒内知道项目进度、当前集、唯一下一步和系统运行中事项。
- **Primary CTA**：`继续制作`，根据 resolver 指向一个 episode/shot/review。
- **Secondary**：查看全部集、打开 Review Inbox、查看活动、查看阻塞详情。
- **Data / APIs**：`/api/books`、`/api/pipeline/book/{bookId}/outputs`、`/api/books/{bookId}/production-workspace`、`production-workspace-v2`、`/qa/workbench`、`/script-decisions`。
- **States**：empty=尚未导入内容；loading=同步项目状态；error=无法读取权威投影；stale=上游内容已更新；ready=可继续；blocked=技术/依赖异常。

### Production Dashboard / Episode card

- **Purpose / goal**：按集展示剧本、导演、分镜、关键帧、图片、视频和整集完成度。
- **Primary CTA**：集卡片上的 `继续制作` 或 `自动制作`。
- **Secondary**：打开集详情、查看审核、暂停/恢复活动。
- **Data / APIs**：production workspace snapshots、episode readiness、`/episodes/{episode}/production-status`（既有 episode rendering API）。
- **States**：empty=没有集；loading=读取集状态；error=集状态不可用；stale=依赖版本变化；ready/running/review/blocked 按 canonical 状态显示。

### Review Inbox / 待我处理

- **Purpose / goal**：聚合 Director、Storyboard、KeyframePlan、Image Candidate、Video Candidate 的人工审核。
- **Primary CTA**：`打开审核`，一次点击定位对象。
- **Secondary**：批准、要求修改、驳回、批量筛选、查看历史。
- **Data / APIs**：creative tasks、director-treatment candidates、keyframe review APIs、media-authority validate/promote、acceptance records。
- **States**：empty=没有待审核；loading=同步队列；error=队列读取失败；stale=候选对应的上游版本已变化；review=等待你审核。

### Shot Studio / 镜头工坊

- **Purpose / goal**：以 Shot 为基本工作单元完成导演、关键帧、图片、视频和连续性。
- **Primary CTA**：随当前阶段变化的唯一动作：`查看导演方案`、`审核关键帧`、`审核图片` 或 `审核视频`。
- **Secondary**：编辑草稿、选择候选、查看版本、打开生产详情、前后镜头切换。
- **Data / APIs**：`/api/books/{bookId}/production-workspace-v2`、storyboard prompt/generation APIs、`/shots/{shot_id}/keyframes`、`/keyframes/{id}/image-production`、media-authority APIs。
- **States**：empty=镜头尚未物化；loading=读取 shot context；error=镜头投影无效；stale=上游 ShotDirection/资产变化；review=候选待审核；running=异步生成中。

### Keyframe Review / 关键帧审核

- **Purpose / goal**：以 START/MIDDLE/END 卡片确认时间点、画面描述、人物/场景状态和摄影动作。
- **Primary CTA**：`批准并继续`。
- **Secondary**：`要求修改`、逐帧编辑、查看来源和历史。
- **Data / APIs**：`GET/POST /shots/{shot_id}/keyframe-plan`、`POST /shots/{shot_id}/keyframe-plan/{version}/review`、`POST .../compile`、`GET/POST /shots/{shot_id}/keyframes`。
- **States**：empty=没有关键帧计划；loading=生成/读取计划；error=计划不可编译；stale=Shot 或资产已变更；review=待人工确认；approved=允许进入图片生产。

### Image Review / 图片审核

- **Purpose / goal**：视觉优先比较图片候选，确认人物和场景一致性。
- **Primary CTA**：`采用`。
- **Secondary**：`要求重做`、驳回、Grid/Compare、查看关键帧和生产详情。
- **Data / APIs**：`/api/keyframes/{keyframe_id}/image-production`、`.../review`、`/api/media-authority/candidates/{id}/validate`、`/api/media-authority/promote`。
- **States**：empty=尚无候选；loading=候选加载/验证中；error=媒体验证失败；stale=关键帧或资产已更新；review=候选待审核；official=已采用正式图片。

### Video Review / 视频审核

- **Purpose / goal**：播放视频并对照 START/END、Prompt 摘要和 ShotDirection。
- **Primary CTA**：`通过`。
- **Secondary**：`要求重做`、暂停/逐帧、查看图片来源、查看连续性。
- **Data / APIs**：现有 storyboard `generate-video`、production workspace V2 VIDEO lane、media-authority candidate validation/promotion、acceptance records。
- **States**：empty=尚无视频候选；loading=视频生成中；error=任务失败；stale=正式图片/ShotDirection 已更新；review=视频待审核；official=正式视频已建立。

### Asset Library / 资产库

- **Purpose / goal**：以身份、正式版本、参考图、使用镜头和一致性状态管理人物/场景/道具/风格/媒体。
- **Primary CTA**：`绑定到镜头` 或 `补齐正式资产`。
- **Secondary**：生成参考图、查看历史、筛选集/类型/状态、打开一致性检查。
- **Data / APIs**：`/api/books/{bookId}/visual-assets/...`、visual-reference-assets、public-asset-storage、authoring proposals。
- **States**：empty=没有资产；loading=读取资产索引；error=资产服务不可用；stale=源事实或版本变化；needs_input=缺少正式视觉资产；official=可供下游引用。

### Task / Activity

- **Purpose / goal**：区分需要用户动作、等待上游、运行中和历史，不让执行记录冒充任务。
- **Primary CTA**：`处理任务`、`查看活动` 或 `继续等待已有任务`。
- **Secondary**：筛选、重试、恢复、打开对象、查看专业详情。
- **Data / APIs**：`/api/books/{bookId}/creative-tasks`、`/api/prototyping/tasks`、`/api/storyboard-prompt-compile-tasks`、`/api/books/{bookId}/qa/workbench`。
- **States**：empty=没有任务/活动；loading=同步队列；error=队列服务失败；stale=任务对应源版本过期；waiting_upstream=等待依赖；running=系统执行中；failed=可恢复失败。

### Model Center / 模型中心

- **Purpose / goal**：查看图片、视频、文本、向量能力是否可用和能力边界。
- **Primary CTA**：管理员 `保存配置`；普通生产用户只读选择图片模型/视频模型。
- **Secondary**：查看能力、健康、成本提示、存储设置和高级协议。
- **Data / APIs**：`/api/model-registry`、`/api/agent/model-config`、`/api/public-asset-storage`。
- **States**：empty=未配置能力；loading=读取注册表；error=配置服务不可用；stale=健康或凭证过期；ready=能力可用；blocked=缺 key/HTTPS/协议。

### Delivery / 交付中心

- **Purpose / goal**：确认 QA、正式媒体和审核证据后创建可追溯交付包。
- **Primary CTA**：`创建导出`。
- **Secondary**：按集筛选、查看 QA、查看导出历史、下载 PDF/记录。
- **Data / APIs**：`/api/books/{bookId}/qa/workbench`、`/api/books/{bookId}/export-records`、`/api/books/{bookId}/export-pdf`。
- **States**：empty=没有可交付集；loading=读取 readiness；error=导出服务失败；stale=交付包引用的正式版本变化；blocked=仍有 QA 或 review；ready=可创建导出。
