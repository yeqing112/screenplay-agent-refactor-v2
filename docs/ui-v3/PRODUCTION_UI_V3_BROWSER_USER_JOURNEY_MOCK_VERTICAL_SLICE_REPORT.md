# Production UI V3 Browser User Journey Mock Vertical Slice Report

## 结论

本轮完成了真实前端 + 真实后端/SQLite + 确定性 mock runtime 的浏览器验收切片。可见 UI 已覆盖项目列表、新建项目、剧本工作台、Director Treatment、SceneBlocking、ShotPlan 和镜头工作台；导演方案、空间调度和镜头计划均通过人工确认边界写入版本。

当前结论为 **PARTIAL / ASSET_BLOCKED**：资产中心没有 Production Asset，因而 IMAGE/VIDEO 生成、Official Media、交付导出无法继续。报告保留此阻塞，不以旧数据或直接数据库写入补齐。

## 本轮改动

- 新建项目 modal 通过 `POST /api/books` 创建真实项目，并在完成后使用真实 `book.id`。
- `E2E_EXTERNAL_RUNTIME=mock` 增加确定性 LLM/IMAGE/VIDEO 适配器和只读 ledger。
- mock IMAGE 返回可解码 PNG，mock VIDEO 返回 deterministic MP4；production 环境拒绝 prototype mock provider。
- 旧剧本缺少结构化 scenes 时，Director Treatment 只读推导稳定 scene identity，不修改 Source Script/ScriptIR。
- SceneBlocking/ShotPlan 确认边界过滤 UI 提交的只读证据字段，只校验候选可编辑字段。
- 增加双次浏览器 runner：`scripts/e2e-production-ui-v3-user-journey.js`。

## 浏览器证据

- 手工完整推进：Director Treatment → SceneBlocking → ShotPlan，当前项目为 book `2` / episode `1` / scene `雨夜旧港`。
- ShotPlan 当前正式批准版本存在，但为 `creative_draft`，`production_status=blocked`，原因是 legacy script 没有生产 ScriptIR authority envelope。
- 资产中心截图：[phase-assets-blocker.png](../../output/playwright/phase-assets-blocker.png)
- 导演/ShotPlan 截图：[phase-director-shotplan.png](../../output/playwright/phase-director-shotplan.png)
- 双次 runner 汇总：[summary.json](../../output/playwright/user-journey/summary.json)

## 双次 runner

两次运行均从项目列表开始，通过 UI 新建并通过 UI 清理 disposable 项目。新项目没有输入内容，因此导航在“内容准备已具备，可以先生成改编方向”门禁处停止；这证明 UI 门禁生效，并没有用 seed/ORM/SQL 越过门禁。两个 disposable 项目已通过 UI 删除。

## 外部调用与安全

- 真实外部 host：`0`
- mock LLM ledger calls：`21`
- mock IMAGE calls：`0`（资产阻塞在生成前）
- mock VIDEO calls：`0`（资产阻塞在生成前）
- 运行期没有调用 SHAPI、MiniMax、OpenAI 或真实媒体供应商；`shapi.vip` 仅作为后续真实 provider 选型信息，未被调用。
- runner 的所有 mutation 均来自页面 UI 事件；网络记录只用于审计。
- 未恢复或复用 `998755`，未写入 `990400`。

## UX friction

1. 新项目创建后仍需完成内容准备和改编方向，导航按钮按门禁禁用，用户容易误以为创建失败。
2. legacy script 没有结构化场景时，旧数据可继续进入 Director Treatment，但当前 ShotPlan 仍不能满足 production authority。
3. 资产中心缺少从当前无资产状态直接开始“上传 → 审核 → 激活 → 绑定”的可见入口，生成链路因此停止。
4. Windows 中文输入在隔离旅程中曾出现乱码，建议下一轮固定 UTF-8 请求与数据库连接编码。

## 后续动作

先补齐资产中心的可见摄取/审核/激活/绑定链路，再补 ScriptIR production qualification；完成后才能继续 PromptIR、mock IMAGE/VIDEO、running reload recovery 和 Delivery export。
