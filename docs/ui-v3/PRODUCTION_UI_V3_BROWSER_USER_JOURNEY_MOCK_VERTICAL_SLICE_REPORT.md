# Production UI V3 Browser User Journey Mock Vertical Slice Report

## 结论

本轮完成了真实前端 + 真实后端/SQLite + 确定性 mock runtime 的浏览器验收切片。两次连续运行均从项目列表开始，通过可见 UI 完成新建项目、短篇内容输入、内容准备、Production Skill 锁定、改编方向锁定、剧本/镜头工作台导航，并通过 UI 删除各自 disposable 项目。

当前结论为 **PARTIAL / ASSET_BLOCKED**：资产中心没有 Production Asset，因而 IMAGE/VIDEO 生成、Official Media、交付导出无法继续。报告保留此阻塞，不以旧数据或直接数据库写入补齐。

## 本轮改动

- 新建项目 modal 通过 `POST /api/books` 创建真实项目，并在完成后使用真实 `book.id`。
- 修复短篇导入项目身份：`ingest()` 支持写入当前 Book，pipeline 在已有 `book_id` 时拒绝生成第二个项目。
- 删除项目时清理项目级 Production Skill / 改编方向 KV，避免 SQLite 复用 ID 后继承上一轮锁定状态。
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

两次运行均从项目列表开始，步骤结果均为通过：项目创建、短篇导入、Production Skill、改编方向、剧本/镜头工作台和资产门禁观察。每轮都记录了真实 `POST /api/books`、`POST /api/pipeline/script`、Skill/改编状态写入以及 `DELETE /api/books/{id}`，并通过 UI 删除项目。两轮没有外部 host、浏览器 console error 或未处理 blocker。

## 外部调用与安全

- 真实外部 host：`0`
- mock LLM ledger calls：`57`
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

## 验证记录

- `npm --prefix web test -- --run`：445 tests passed。
- `npm --prefix web run build`：通过。
- `python -m compileall -q api core`：通过。
- `git diff --check`：通过。
- 浏览器 runner：两次连续运行，每轮步骤通过并通过 UI 删除 disposable project；外部 host `0`、console error `0`。
- 后端全量 pytest 本轮完成 `2000 passed, 4 failed, 2 errors`；失败项集中在既有 Phase pilot/视觉资产兼容测试。SceneBlocking 生产确认回归已修复并通过；Phase C、Phase I、Phase J3.1 定向回归均通过。
