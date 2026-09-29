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

