# Final Hybrid V3 Visual Language Specification

**状态：正式 React 实施唯一视觉依据**
**阶段：`PRODUCTION_UI_V3_FINAL_VISUAL_LANGUAGE_COMPLETE` 的设计输入**

## 1. 产品合成

Final V3 不是第四套方向，而是经过产品负责人选择后的固定融合：

> Cinematic on the surface. Precise underneath. Editorial when thinking.

| 来源 | 采用内容 | 位置 |
|---|---|---|
| A · Cinematic Command | 深色中性画布、媒体优先、克制边框、空间层级、warm copper 创作强调 | Global Shell、Dashboard Hero、Shot Studio Main Canvas、Asset Library |
| C · Precision Production | 紧凑 Navigator、状态扫描、Review Inbox 三栏、横向 Pipeline、生产 CTA 使用 cyan | Shot Navigator、Review Inbox、Model / utility 结构、Pipeline |
| B · Editorial Studio | 导演意图、故事阅读、AI Why 的局部 serif 和内容流 | 剧本与导演、Director Treatment、Shot Context 的 Intent |

## 2. 被舍弃的探索方案

- 不保留 A 的低密度 Shot Navigator；最终采用 C 的 Scene grouping、搜索和状态过滤。
- 不让 A 的 copper 承担全部 Primary Action；生产动作固定使用 cyan / blue。
- 不把 B 的大面积 serif 带入 Production UI；serif 只允许在创作阅读局部。
- 不把 C 的高密度队列媒体压缩到不可判断；Review Desk 吸收 A 的大媒体预览。
- 不把 Provider、Endpoint、Credential 放进一级导航或 Context 主区；工程信息统一进入 Production Details drawer。
- 不把技术阻塞混入 Review Inbox；Provider unavailable、Stale source、Missing asset 进入 Blocking Issues。

## 3. Global Shell

一级导航固定为：制片台、剧本与导演、镜头工坊、资产库、交付。右侧显示同步状态、待审核数量、专业视图入口。模型中心和系统设置进入 Workspace menu 或交付二级入口。

## 4. Dashboard

首屏顺序固定为 `Project Context → Next Best Action → Episode Progress / Production State`。Hero 只保留唯一下一步和预计耗时；Review Inbox、Active Generation、Blocking Issues 在首屏可扫描。统计为 compact row，不使用四张大型 KPI card。18–50 镜头使用 segmented rail，超过 50 镜头按 Scene 聚合或缩放。

## 5. Shot Studio

布局固定为 `Shot Navigator | Main Canvas | Context / Review`，底部是 Timeline / Continuity。Navigator 必须支持 Episode、Scene、State filter、镜头号 / 场景 / 角色搜索，Scene grouping，40+ 镜头可滚动；正式实现必须使用 virtualized / windowed list 支持 100+ Shot。Pipeline 是 production state rail，不是页面 Tab；点击只查看历史，不改变 canonical state。

Keyframe Review 使用 START / MIDDLE / END 三联画和 motion / emotion bridge。默认只显示核心变化，camera_state、character_state、scene_state、emotion_state 进入展开详情。Primary CTA 只有“批准并继续”，Secondary 为“要求修改”，Advanced 为“更多 · 驳回”。

## 6. Review Inbox

固定三栏：Filters、Review Queue、Review Desk。Queue 行显示 thumbnail、review type、shot、scene、reason、version、age。Desk 使用大媒体预览，并针对 Keyframe / Image / Video 提供不同证据布局。决策按钮固定在同一位置：批准并继续、要求修改、更多 · 驳回。Approve 后保留 Inbox、自动进入下一条并显示轻量反馈；真正的 undo 必须等后端 API 支持，不得伪造。

## 7. Director / Editorial

左侧 Story / Scene，中间 Director Treatment，右侧 Evidence / Review。内容回答“故事是什么、AI 为什么这样拍、镜头如何表达、情绪如何推进”，不展示 `DirectorReasoningIR` 等内部对象名。Editorial serif 只用于阅读内容局部。

## 8. 状态和可访问性

`official / review / running / waiting / blocked / stale` 必须由 icon + text + color 同时表达。Loading 用 skeleton，Empty Review Inbox 使用“当前没有需要你审核的内容。系统会继续处理已经批准的任务。”。快捷键为 A 批准、R 要求修改、Space 预览、↑↓ 审核项、←→ 媒体 / 阶段；在 input、textarea、select、modal 中不得触发危险动作。

## 9. 响应式目标

1440×900 和 1920×1080 是完整 Production Workspace 目标；1280 必须完整可操作，Context 可折叠；低于 1280 可降级为 drawer based。Final QA 还要覆盖 90%、100%、110% 浏览器缩放。
