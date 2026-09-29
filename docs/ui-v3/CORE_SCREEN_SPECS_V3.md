# Core Screen Specs V3

本文件把核心页面从“信息架构”推进到可用于视觉方向阶段的交互规格。它不实现组件，也不创建新的后端规则。

## 1. Project Home / Production Dashboard

**布局**：顶部项目身份和数据新鲜度；第一屏为唯一下一步；中段为集卡片和 Production Pipeline；右侧/下方为 Review Inbox、Active Generation、Blocking Issues、Recent Results。

**集卡片**：显示集名、完成镜头数、待审核数、生成中数、阻塞数和 `继续制作`。不显示数据库状态码。

**行为**：点击 blocker 或 review item 一次进入正确的 episode/shot/context；自动制作先展示预计范围和人工审核次数，再进入活动流。

## 2. Review Inbox

**布局**：左侧筛选（待我处理、按类型、按集），中央 review item 列表，右侧 Review Drawer。列表项显示类型、集、镜头、缩略图、原因、AI 建议和当前版本。

**行为**：`A` 批准、`R` 要求修改、`Space` 预览；危险操作需要二次确认。批准后不离开队列，自动定位下一条待审核项。

## 3. Shot Studio

**布局**：左 Shot List；中 Main Canvas；底部 Timeline/Pipeline；右 Context。Main Canvas 根据阶段切换导演方案、关键帧、图片候选、视频和对比审核。

**行为**：左右箭头切换镜头；上下文始终显示场景、集、时长和上游版本；生成结果先进入候选，审核后才成为正式媒体。

## 4. Keyframe Review

**布局**：START/MIDDLE/END 三列 Storyboard Card，底部显示镜头时长和连续性轨迹。卡片内使用大图/占位预览，文字只做解释。

**卡片字段**：时间、画面描述、人物状态、场景状态、情绪、摄影、运动、引用资产和来源版本。

**行为**：逐帧 `要求修改`，整组 `批准并继续`；批准后顺序调用 review → compile → 刷新 production state，前端不绕过编译阶段。

## 5. Image Review

**布局**：候选 Grid；选中候选进入 Compare；左侧为当前关键帧，右侧为候选大图；底部为一致性检查和版本信息。

**行为**：支持 Grid、Compare、Select；`采用`、`要求重做`、`驳回`均写入审核记录；provider 和 request id 收进生产详情。

## 6. Video Review

**布局**：视频播放器为主；START/END 对照和 ShotDirection 摘要为辅；右侧显示连续性检查和评论。

**行为**：播放、暂停、逐帧、全屏；`通过`创建正式视频，`要求重做`保留原因并生成恢复任务。

## 7. Asset Library

**布局**：人物、场景、道具、风格、媒体五类筛选；资产卡显示身份、当前正式版本、参考图、使用镜头、一致性状态和历史。

**行为**：资产优先绑定已有正式版本；没有正式资产时主 CTA 为补齐/绑定，不把文件上传误认为已可生产。

## 8. Task / Activity

**布局**：Review Inbox 独立于 Activity；Activity 用时间线展示“已提交、模型处理中、等待结果、已完成”；Blocking Issues 只放技术或依赖异常。

**行为**：检测已有 task 时主按钮是 `继续等待已有任务`；失败任务提供查看原因、重试当前版本和回退。

## 9. Model Center

**布局**：按用途展示图片、视频、文本、向量模型卡；卡片包含模型、状态、成本提示和能力。Provider、协议和密钥在高级设置中。

**行为**：普通生产页选择能力类型，不选择 provider；付费操作在执行前显示能力和预计请求数量。

## 10. Screen-wide states

每个核心页面都必须支持：loading skeleton、empty guidance、inline error with recovery、stale explanation、review waiting、running activity 和 professional details。状态不能只用颜色表示。
