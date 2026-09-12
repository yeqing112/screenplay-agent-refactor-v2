# screenplay-agent-refactor-v2 功能变更说明

## 2026-09-13 — Production Pipeline V2 M2：FactSnapshot 权威层

- 新增 `models/fact_snapshot.py`、`core/fact_snapshot.py` 与 `/api/books/{book_id}/episodes/{episode}/fact-snapshots/*` deterministic build/list/confirm API。
- FactRecord 明确 `source_text/locked_fact/approved_fact/derived_fact/model_observation` authority，冲突值、锁定事实未确认和缺证据均不会静默通过。
- 新增 `blocking_unknown/assumable_unknown/creative_unknown` 路由；仅生产关键未知阻断，创作型未知不被误判为 blocker。
- 新增 Alembic `l5f6g7h8i9j0_add_fact_snapshots.py`，确认后写入版本化 FactRecord，保留 previous snapshot 与 source fingerprint。
- M2 测试：FactSnapshot/authority/unknown routing **7 passed**。未调用真实 LLM、图片、视频或对象存储。

## 2026-09-13 — Production Pipeline V2 M1：ScriptIR 版本化与导演运行时路由

- 新增 `models/script_ir.py`、`core/script_ir.py`、`core/script_renderer.py` 与 `/api/books/{book_id}/episodes/{episode}/script-ir/*` deterministic build/confirm/read API。
- 新增 Alembic `k4e5f6g7h8i9_add_script_ir_versions.py`；Script 保留 Markdown/旧 JSON 兼容内容，同时记录当前确认的 ScriptIR 版本引用。
- production profile 的 DirectorTreatment、SceneBlocking、ShotPlan 预览现在只消费 qualified ScriptIR；无 qualified 版本时 fail-closed，creative_draft 继续兼容旧内容。
- 旧 Markdown 仅可一次性 legacy reconstruction，并标记 `needs_review`；确认前不会成为生产事实。
- M1 测试：ScriptIR/renderer/director-runtime **6 passed**，Treatment/Blocking/ShotPlan 回归 **21 passed**。未调用真实 LLM、图片、视频或对象存储。

## 2026-09-13 — Production Pipeline V2 M0：统一状态协议与工作流 Profile

- 新增 `core/production_policy.py`，集中定义 `execution_status`、`quality_status`、`production_status` 与 `workflow_profile`，并提供 fail-closed 生产边界评估。
- `Script`、`StoryboardShot`、`DirectorTreatment`、`SceneBlocking`、`ShotPlan` 增加兼容性状态字段；旧 `status` 保留作为 legacy 数据。
- 新增 Alembic 迁移 `j3d4e5f6g7h8_add_unified_artifact_states.py`，所有字段可升级/降级。
- `/api/pipeline/storyboard` 支持 `workflow_profile`；显式 `production` 在后续里程碑证据尚未齐备时返回可行动的 409 阻断，不能被 `require_shot_plan=false` 绕过；默认 `creative_draft` 保持兼容且永远不进入正式生产。
- M0 测试：`tests/test_production_policy.py` 6 passed；相关 Treatment/Blocking/ShotPlan/Storyboard 回归 29 passed。未调用真实 LLM、图片、视频或对象存储。

## 2026-09-12 — 生产样本登记支持批量原子校验

- `scripts/register-production-sample.py` 的 `--book-id` 现在可重复传入，可一次预览多个候选项目。
- 批量登记采用“先全部校验、后一次确认、原子写入”策略：任一项目缺少 `books` 主记录、剧本或镜头证据时，整批拒绝且不修改注册表。
- 重复请求只读复用当前 active/retired 状态；不会创建、复制或补齐镜头，也不会把孤儿证据（如 `991119`）自动激活。
- 新增两项批量行为回归；`pytest -q tests/test_production_sample_registry.py` 当前为 `12 passed`。
- 使用 `990401` 与 `990402` 执行 dry-run，按预期整体拒绝（项目不存在且无剧本/镜头证据），`would_write=false`、`written=false`，当前注册表保持不变。

## 2026-09-12 — 近期生产优先任务回归复验

- 批量登记改动后的 `npm run check:production` 已通过：后端 `648 passed`、Golden `5/5`、运行时配置检查、发布门禁不变量和前端生产构建均通过。
- 本次回归没有调用真实 LLM、图片、视频或对象存储；生产放行门禁仍按真实样本数量、状态覆盖、生产配置和媒体公网可达性独立 fail-closed。
- 最新 `npm run gate:production` 已完成并生成 `artifacts/production-release-gate-2026-09-12T12-03-24-007Z.{json,md}`：确定性回归通过，样本注册表通过；发布配置、3/30 镜头与状态覆盖、Prompt 30 镜头覆盖、生产真浏览器样本数量仍按事实阻断。
- 最新 H3 只读预检报告为 `artifacts/minimax-h3-gray-2026-09-12T12-06-36-815934Z.{json,md}`：自动选中 `990400 / E1 / S1`，6 秒时长与 2 张锁定多参考均正确；API Key 已配置，但参考图 `0/2` 可提交，因本地 URL 不具备 provider 可访问性而未调用供应商。
- 定时数据库备份与恢复演练已复验成功：`artifacts/database-backups/screenplay-20260912T120754Z.sqlite`，源库与恢复库均完整性 `ok`、48 张表一致、`source_mutated=false`，临时恢复库已清理。
- `npm run test:release-gate` 在本轮样本与备份改动后复验通过，继续保证生产门禁的 fail-closed 不变量。
- 本地正式工作台运行态复核通过：API `127.0.0.1:18765/health` 返回 200，Web `127.0.0.1:5175/` 返回 200；前后端进程均在监听。
- 读取正式工作台 `990400` 资产清单并生成只读预检：场景锁定参考图为 asset `13`、人物“林晚”锁定参考图为 asset `8`，两者均为本地 `/api/prototyping/manual-media/...` 地址；清单证据保存在 `artifacts/990400-visual-assets-preflight.json`，未修改资产状态。
- 两个本地媒体端点均可由本机读取（HTTP 200、`image/png`，约 2.46 MB 与 2.13 MB），问题已明确收敛为“公网/provider 可达性”，不是本地文件缺失。
- 对象存储迁移只读计划已复核并保存为 `artifacts/990400-storage-migration-plan-preflight.json`：12 个资产需要发布（含锁定参考图），七牛凭据已配置；当前仍使用私有 bucket 的临时 HTTP `clouddn.com` 域名，因此 `migration_apply_supported=false`，系统拒绝永久迁移写入。
- 对七牛临时域名执行只读 HEAD：域名可连通但返回 HTTP `401`，确认当前阻塞是 bucket 私有访问/缺少签名 URL，而非 DNS 或网络不可达。
- 补齐 H3 灰度脚本的通用 `--allow-unstable-public-assets` 请求级开关：仅显式用于灰度时才把临时七牛域名传入存储发布和提交 payload，生产门禁仍拒绝该域名；回归 `tests/test_minimax_h3_gray_selection.py` + `tests/test_public_asset_storage.py` 为 `16 passed`，未执行上传或供应商调用。
- 使用新开关执行只读 H3 预检，报告为 `artifacts/minimax-h3-gray-2026-09-12T12-18-12-742390Z.{json,md}`；报告明确记录临时域名仅灰度允许，未启用发布时仍为 `0/2`、未调用外部服务。
- H3 临时域名灰度开关改动后的完整 `npm run check:production` 已通过：后端 `649 passed`、Golden `5/5`、发布门禁不变量、运行时配置检查和前端生产构建均通过。
- 进一步修正 H3 灰度发布路径：所有参考图/首帧发布现在强制 `force_storage=true`，临时域名不能绕过安全门；完整回归仍为 `649 passed`、Golden `5/5`、前端构建通过。
- H3 脚本新增独立存储发布确认令牌 `MINIMAX_H3_STORAGE_CONFIRM=CONFIRM_MINIMAX_H3_REFERENCE_PUBLISH`；请求发布但未提供令牌时只生成阻塞报告，不执行七牛上传。专项脚本回归现为 `4 passed`。
- 对象存储二次确认与强制安全门改动后的完整 `npm run check:production` 已通过：后端 `650 passed`、Golden `5/5`、发布门禁不变量、运行时配置检查和前端生产构建均通过。
- 在未设置 `MINIMAX_H3_STORAGE_CONFIRM` 时执行“请求发布 + 临时域名灰度”预检，报告 `artifacts/minimax-h3-gray-2026-09-12T12-33-21-736253Z.json` 明确显示 `storage_performed=false`、`actual_provider_submission=false`，并返回存储确认阻塞；验证了不会误上传。
- 存储发布确认门的新增回归后的完整 `npm run check:production` 已通过：后端 `651 passed`、Golden `5/5`、发布门禁不变量、运行时配置检查和前端生产构建均通过。
- 正式工作台 H3 UI 专项回归通过：机器提示词导出面板与分镜工作台共 `39 tests passed`，临时七牛开关、多参考模式和提交摘要交互均保持可用。
- 优化 H3 真实提交确认框：根据当前模式明确提示“锁定参考图将上传至对象存储”或“临时七牛地址仅本次灰度”，避免费用确认与资产上传确认混淆；前端专项测试 `39 passed`，生产构建通过。
- `npm run e2e:business` 隔离业务回归通过：正式工作台主流程、QA 修复/回滚和验收记录均通过，fixture `999902` 已自动清理，未调用外部服务。
- `npm run e2e:machine-prompt-export` 隔离真浏览器回归通过：H3 多参考字段、WebUI 导出和编辑后导出均通过，fixture `999903` 已自动清理。
- 当前真实样本只读真浏览器巡检通过：`990400` 的 10 个正式工作台模块可达、无业务阻塞、未写库；报告：`artifacts/e2e-real-sample-regression-2026-09-12T12-49-26-481Z.json`。该结果仍不替代生产要求的 3 项目/30 镜头门禁。
- 正式工作台媒体预检（`990400 / E1 / S1`，临时七牛灰度开关开启）返回 `ready_for_real_submit=true`、`reference_will_be_published_before_submit`，且 `mutated=false`、`provider_call=false`；证据：`artifacts/990400-h3-media-preflight-unstable.json`。

## 2026-09-12 — 生产回归最新结果

- `npm run check:production` 实跑通过：后端 `643 passed`、Golden `5/5`、运行时配置检查和前端生产构建全部通过。
- 真实 active 镜头仍为 `3/30`，因此可拍性/提示词质量门禁继续 fail-closed；本次回归未调用真实 LLM、图片、视频或对象存储。
- 新增 `npm run gate:production` 统一运行生产配置、样本注册、可拍性、Prompt 和完整回归门禁；失败步骤不会短路，并生成可追溯 JSON/Markdown 报告。
- 新增 `npm run test:release-gate`，回归发布门禁的生产环境 fail-closed 规则。
- 统一门禁实跑结果按预期阻断：当前本地为开发环境且仅有 3/30 个真实镜头；完整回归为 641 passed、Golden 5/5。
- 最新统一门禁报告已生成，结构化列出 `needs_information`、`conflict` 和样本数量阻塞原因；没有触发外部模型或媒体调用。
- 备份调度能力加入后的统一门禁复核已完成，完整回归仍通过，发布质量门禁继续按真实样本不足 fail-closed。
- 只读数据库核对确认其余历史书籍没有剧本来源，未将其纳入 active 样本或用于凑足质量门禁数量。
- 样本注册表校验新增 `available_candidates` 只读字段，帮助发现真实项目但不自动激活或修改注册表。
- 新增受控 `register:production-sample`：仅凭已有剧本/镜头证据登记真实项目，默认预览，显式确认后原子写入；不创建或复制镜头。
- 新增 `backup:database:scheduled` 时间戳备份入口，支持完整性校验和可选恢复演练；不覆盖、不删除源库或旧备份。
- `check:production` 现纳入发布门禁不变量测试，避免门禁逻辑回归而主生产回归仍显示通过。
- 定时备份新增跨平台 Node 转发入口与 `backup:database:scheduled:restore-drill` 稳定命令，修复 Windows npm 吞掉长参数导致恢复演练未实际执行的问题。
- 真实 Prompt Compiler 灰度自动范围改为读取 `production-sample-registry.json` 的 active 项目；不再隐式扫描旧书号，新增 active 范围选择回归。
- 上述改动后的完整生产回归为 `643 passed`、Golden `5/5`，前端生产构建通过；真实样本与生产环境配置门禁仍按事实 fail-closed。
- 最新统一 `gate:production` 报告为 `artifacts/production-release-gate-2026-09-12T10-57-48-356Z.{json,md}`；完整回归 `643 passed`，发布阻塞条件未变化。
- 正式工作台真浏览器只读回归通过：`990400` 的 10 个模块可达且无业务阻塞；仍只有 3 个真实镜头，不能替代全局 30 镜头门禁。
- H3 只读预检自动选中 active 样本 `990400 / E1 / S1`，确认 6s 时长和 2 张多参考图；因参考图尚未发布为 provider 可访问 URL 而保持 fail-closed，未调用供应商。
- 新增 `npm run e2e:real-samples:release`，生产回归强制至少 3 个真实项目样本；普通 `e2e:real-samples` 仍保留本地开发自适应模式。
- 已用当前数据库验证该入口在 1 个样本时按预期 fail-closed（`expected at least 3`）。
- `gate:production` 已纳入生产真浏览器回归步骤，统一报告不会遗漏 UI 业务证据。
- 使用隔离占位值验证 `config:verify:production` 的 staging 全通过路径；正式环境仍必须注入真实密钥和稳定 HTTPS 域名。
- 门禁报告增强证据可追溯性：统一解析子门禁 JSON 返回的 `report`/`artifact` 路径，直接关联可拍性和 Prompt 审计报告，不扫描 artifacts 目录猜测旧报告；新增回归覆盖该行为。
- 样本注册校验新增只读 `orphan_evidence` 诊断：发现脚本/镜头存在但缺少 `books` 主记录的孤儿证据时明确排除出候选，不自动激活或删除；当前发现 `991119`，不影响 active 样本集合。
- 生产安全门禁新增 `API_RATE_LIMIT_DISTRIBUTED_ASSERTED`：只有共享/反向代理限流实际部署并由运维显式声明后，staging/production 配置才可通过；应用层固定窗口限流仍仅作为单进程兜底。正反例回归已覆盖。
- 生产安全配置校验新增模板占位值和示例域名拒绝规则，避免 `<secret>`、`<32+ chars>`、`example.com` 等值在部署时造成假绿；开发环境默认配置不受影响。
- 安全收口后完整 `npm run check:production` 复验通过：后端 `646 passed`、Golden `5/5`、运行时配置检查和前端生产构建均通过。
- 最新 `npm run gate:production`（11:29）仍按事实阻断：开发环境、3/30 真实镜头、缺少 `needs_information`/`conflict`、生产真浏览器样本不足；确定性回归继续通过。

## 2026-09-12 — 可拍性门禁增加状态覆盖校验

- `audit:shot-planning:gate` 现在同时要求至少 30 个真实 active 镜头，以及意图 `ready / needs_information`、节拍 `ready / conflict` 四类状态覆盖。
- 缺少样本数量或状态覆盖时报告照常落盘并 fail-closed；规则不依赖书号、角色、镜头或关键词特例。
- 新增门禁纯函数回归测试；本地生产回归 `617 passed`、Golden `5/5`、运行时配置检查和前端生产构建均通过。
- 只读生产就绪接口复核 `990400` 为 `pass`（3 镜、2 资产、0 blocker、0 warning）；该局部结果不替代全局样本数量与状态覆盖门禁。

## 2026-09-12 — 可配置 API Token Guard

- 新增默认关闭的 API Token Guard；启用后统一保护 `/api/*`，支持 Bearer、`X-API-Key` 和配置 Cookie，健康检查与 CORS 预检保持可用。
- 未配置或短于 32 字符的 Token 会 fail-closed；本地默认配置和既有前端行为不变。
- 细粒度角色授权、密钥轮换和生产反向代理注入仍是上线前待办。

## 2026-09-12 — 可选 API 角色授权

- 新增 `API_AUTH_ROLE_TOKENS` JSON 配置，支持 `viewer`、`editor`、`admin` 三档令牌；GET/HEAD 要求 viewer，写入方法要求 editor，admin 兼容全部方法。
- 角色配置出现未知角色或弱令牌时 fail-closed；未配置角色令牌时保留原单 Token admin 兼容路径。

## 2026-09-12 — 生产安全配置放行检查

- 新增 `npm run config:verify:production`，生产/预发布环境强制检查认证、角色令牌、HTTPS CORS、限流和稳定对象存储域名；开发环境明确跳过并输出原因。
- 补齐 `DEPLOYMENT_ENV` 运行配置读取，并通过安全配置正/反例回归。
- 生产安全检查新增旧执行层保护：正式环境必须关闭 `ENABLE_LEGACY_NODE_API`。

## 2026-09-12 — 生产回归复核

- 完整 `check:production` 实跑通过：后端 626 项测试、Golden 5/5、运行时配置检查和前端生产构建全部通过。
- 可拍性与 Prompt 质量门禁仍保持独立 fail-closed，原因是当前真实 active 镜头只有 3 个，未达到 30 个及异常状态覆盖要求。
- 加入旧执行层生产门禁后的完整回归为后端 627 项测试通过、Golden 5/5、配置检查和前端构建通过。
- 可拍性回放报告新增发布阻塞与下一步动作字段，统一由实际证据推导，便于普通用户定位缺口。
- 相关改动后的完整生产回归为后端 629 项测试通过、Golden 5/5、配置检查和前端构建通过。
- 新增只读生产样本注册表校验，确认 active 项目存在真实剧本和镜头证据且不与 retired 集合重叠。
- 场景资产 readiness 审计默认范围改为 active 样本注册表，移除硬编码历史书号，避免非生产项目污染上线结论。
- 加入注册表校验后的完整生产回归为后端 632 项测试通过、Golden 5/5、配置检查和前端构建通过。
- 新增生产部署放行运行手册，明确认证、HTTPS、限流、旧执行层关闭、备份恢复和上线抽查步骤。

## 2026-09-12 — 可选 API 限流兜底

- 新增默认关闭的 `API_RATE_LIMIT_*` 配置，对 `/api/*` 按 token 哈希或客户端 IP 施加固定窗口限流。
- 超限返回 `429`、`Retry-After` 和 `X-RateLimit-*`；健康检查与 CORS 预检不计数。
- 这是单进程应用层兜底，多进程生产环境仍需由反向代理或共享限流器提供分布式策略。

## 2026-09-12 — SQLite 备份与恢复前置

- 新增 `npm run backup:database -- --output <path>`，通过 SQLite 在线 backup API 创建备份并校验源库/目标库完整性。
- 默认拒绝覆盖已有备份，采用临时文件和原子替换；源数据库不会被删除或修改。
- 新增备份工具回归测试；定时、异地备份与恢复演练仍需在部署环境完成。
- 增加跨平台 Node 转发入口，修复 Windows npm 对 `--output` 参数转发不稳定的问题；文档命令现在可直接使用。
- 新增 `verify:database-restore` 非破坏性恢复演练：在临时 SQLite 中恢复备份并校验完整性与表清单，不接触源库。

## 2026-09-12 — 外部生成确认与多参考灰度预检收口

- 分镜图片/视频真实 Provider 请求统一要求 `confirmed=true` 与 `allowExternalCall=true`；未确认时不创建任务、不调用供应商。
- H3 灰度预检自动发现当前有效样本，默认使用多参考图，首帧仅在显式 `--use-first-frame` 时启用。
- 真实浏览器 Agent E2E 自动读取当前项目和资产，不再依赖已清理的历史样本。
- 生产门禁后端 `601 passed`、Golden `5/5`、前端构建通过；真实媒体调用仍需单独确认。

## 2026-09-12 — 真实业务 Director Runtime 验收

- 使用 `990400 / 第1集` 完成 DirectorTreatment → SceneBlocking → ShotPlan 批准链复核。
- Storyboard readiness 为 `allowed=true`；Director Benchmark `run_id=3` 得分 `100/100`，6 项检查全部通过。
- 本次为确定性验收，不调用外部 LLM、图片或视频供应商；默认 ShotPlan 强制门禁暂不自动开启。

## 2026-09-12 — 990400 媒体提交前置检查

- `990400 / 第1集 / 镜头1–3` 的 H3 多参考预检确认当前锁定场景与人物参考图均存在，但默认状态因本地 URL 不可被供应商访问而阻断。
- 在请求级显式允许七牛临时域名后，三镜预检均为 `ready_for_real_submit=true`，仅保留“提交前将发布”警告；未上传对象、未创建任务、未调用供应商。
- 分镜台预检阻断提示改为通用可行动文案：明确区分稳定 HTTPS 域名与仅限灰度的临时七牛地址，并保留重新预检入口；不改变后端阻断或外部调用门槛。

## 2026-09-12 — 云端 CI 实跑延期

- 根据当前本地优先推进节奏，暂缓触发 GitHub 云端 CI；现有 workflow、artifact 归档和 Step Summary 配置保留不变。
- 本地生产门禁继续作为当前验证依据；云端干净环境实跑仍列为正式上线前必做项，不标记为已完成。

## 2026-09-12 — 正式工作台导航可访问性补强

- 左侧正式工作台导航为当前页面项增加 `aria-current="page"`，让读屏器和自动化工具能识别当前位置。
- 所有导航按钮补齐统一 `focus-visible` 焦点环，键盘用户可清楚看到当前焦点且不改变既有点击、门禁和路由行为。
- 新增 `ProductWorkspaceShell` 导航可访问性回归测试；前端全量 `49 files / 288 tests`、生产构建和 `npm run check:production` 均通过。

## 2026-09-12 — 运行态与视频输入详情默认折叠

- 分镜台“生成与恢复”保留两张主动作卡，将当前镜头运行态、任务 ID 和恢复列表默认收进“执行详情”。
- 首帧、多参考图、编译载荷来源和任务模式默认收进“视频输入详情”，降低普通用户的首屏技术噪声；展开后信息与原逻辑完全一致。
- 不改变生产门禁、显式确认、任务回收或审计；分镜台专项测试 28/28、前端生产构建通过。

## 2026-09-12 — 分镜台状态文案统一

- “当前资产状态”不再直接显示 `pending`、`ref_ready` 等内部状态码，统一映射为“待准备”“参考图可用”“已锁定”等普通用户可读文案。
- 未知状态统一显示“待确认”，原始状态仍由后端和诊断链路保留，不改变门禁判断。
- 前端全量回归 `48 files / 286 tests`，生产构建通过。
- 扩展状态映射后重新执行完整 `npm run check:production`：后端 `600 passed`、Golden `5/5`、运行时配置校验和前端生产构建全部通过。
- 状态映射扩展后的再次门禁复核仍为后端 `600 passed`、Golden `5/5`、前端构建通过；未调用真实 LLM 或媒体供应商。

## 2026-09-12 — 正式工作台导航分组状态同步

- 核对正式工作台实现，确认左侧导航已按“创作 / 生产与检查 / 管理”分组；现有路由、入口和门禁保持不变。
- 任务计划同步标记该项完成；模型/存储进一步拆分仍保留为后续工作。

## 2026-09-12 — 分镜台步骤化 UI 生产门禁复核

- 在最近的动作卡与素材步骤改动完成后重新执行完整 `npm run check:production`。
- 后端确定性回归 `600 passed`，Golden 回归 `5/5`，运行时配置校验通过，前端全量 `48 files / 275 tests` 与 TypeScript/Vite 生产构建通过。
- 同步修正文档中的过时下一阶段描述，明确当前剩余工作为真实浏览器视觉证据、运行态信息继续收敛、真实业务项目的 Director Runtime 验收和 CI/nightly 固化。
- 本次仅更新验证记录与计划文档，不改变生产数据、模型配置或外部调用边界。
- 真实样本 Playwright 回归已复跑 `990400`：10 个工作台模块可达、无阻塞、无控制台业务错误；报告见 `artifacts/e2e-real-sample-regression-2026-09-12T03-09-39-341Z.json`。
- 同步任务计划：将已落地的手动/nightly 灰度 workflow、M1 DirectorTreatment 切片和第二次 MiMo clone-only 灰度标记为完成；保留 CI 实际运行、真实业务 Director Runtime 批准和默认 ShotPlan 门禁作为未完成项。
- active 样本提示词审计已复跑 `990400` 的 3 个镜头：`0 errors / 0 warnings`；报告见 `artifacts/storyboard-prompt-real-sample-audit-2026-09-12T03-19-44-953Z.json`。

## 2026-09-12 — CI 生产门禁证据归档

- Required CI 在生产门禁后新增 artifact 上传，保存 `artifacts/**` 与前端 `web/dist/**`，保留 14 天，便于发布审查和失败回放。
- 新增 GitHub Step Summary，明确门禁结果、覆盖范围和“禁止外部 LLM/provider 调用”的安全边界。
- 不改变门禁判定逻辑；CI 实际云端运行仍需在仓库环境中完成一次验证。

## 2026-09-12 — 分镜图/视频动作卡拆分

- 生成与恢复区域默认展开，首帧和视频动作拆成两张独立卡片，分别说明用途、前置条件和当前步骤，避免普通用户误把“生成视频”当作首帧动作。
- 视频卡在没有已采纳分镜图时直接展示可读提示，并继续沿用原有门禁；任务回收和创作画布入口保留在动作区上方。
- 详细运行态、多参考输入摘要和恢复信息仍保留在面板内，不改变真实生成、确认和审计逻辑。
- 更新分镜台组件断言；前端全量测试 `48 files / 274 tests` 和生产构建通过。

## 2026-09-12 — 准备素材步骤承接绑定详情

- 镜头工作台的场景、人物、道具绑定详情从“更多工具”迁移到“准备素材”，与参考图预览和媒体上传放在同一生产步骤。
- 绑定详情明确显示资产 ID、变体、参考状态、绑定来源和引用 token；修改入口继续统一回资产中心，避免在镜头页出现两套写入逻辑。
- “更多工具”保留诊断、Prompt 版本、回滚和编译上下文等专家能力，减少普通用户首屏认知负担。
- 前端全量测试 `48 files / 274 tests`、生产构建和生产回归均保持通过。

## 2026-09-12 — 分镜台镜头/步骤 URL 承接

- 正式工作台支持 `section=storyboard&episode=<集数>&shot=<镜头>&step=<步骤>` 上下文；刷新或分享链接后可直接回到对应镜头和步骤。
- 选项卡切换会用 `history.replaceState` 更新 URL，不新增历史噪音，也保留宿主应用已有查询参数。
- 仅接受已知工作台和步骤值，非法参数安全回退到默认工作台/“看懂镜头”；不改变生产门禁或外部调用边界。
- 机器提示词导出真浏览器回归已增加 URL 上下文断言。

## 2026-09-12 — 机器提示词导出回归改为独立临时夹具

- `e2e:machine-prompt-export` 不再依赖已清理的 `book 75` 或任何正式项目，默认使用保留号段的临时项目 `999903`。
- 新增 `scripts/seed-machine-prompt-export-fixture.py`，为回归准备锁定改编方向、剧本放行、结构化镜头、锁定场景/人物参考图和 baseline Prompt Version。
- 测试开始前自动创建夹具，结束后删除夹具、导出记录、提交意图任务、KV 状态和脚本决策文件；支持 `E2E_MACHINE_PROMPT_BOOK_ID` 显式指定隔离号段。
- 真实浏览器机器提示词导出回归通过；前端 `48 files / 274 tests`、生产构建和 `npm run e2e:business` 均通过。

## 2026-09-12 — 镜头工作台步骤化 UI 第一阶段

- 将镜头工作台首屏重组为六个按生产顺序排列的选项卡：看懂镜头、准备素材、生成分镜图、生成视频、检查结果、更多工具。
- 当前镜头的状态、唯一主动作和上游放行状态保持在步骤内容上方；导演分镜语言默认位于“看懂镜头”，机器提示词、诊断、版本、恢复和导出等低频能力仅在对应步骤或“更多工具”中展开。
- 步骤标签显示可读的完成标记，并保留已有生成、采纳、验收和参考资产状态；切换镜头会恢复到“看懂镜头”，避免把上一个镜头的操作上下文误带入当前镜头。
- 步骤导航补齐标准 Tab 语义、面板关联和键盘方向键/Home/End 切换；任务中心或创作画布可通过 `initialStoryboardStep` 将用户直接带到对应步骤。
- 未删除任何生产能力，未改变后端生产门禁、外部调用确认、多参考视频输入、版本回滚或审计边界。
- 前端组件测试覆盖步骤导航语义与 active panel；全量前端测试、生产构建和正式工作台业务回归均通过。

## 2026-09-12 — 临时七牛域名灰度放行链路补齐

- 正式工作台新增请求级“本次灰度允许使用临时七牛公网地址”开关，默认关闭；切换镜头时自动清除，避免授权意外复用。
- 该开关同时透传只读媒体预检与真实 H3 提交，只有显式勾选并通过二次确认后才允许使用七牛临时域名；生产环境仍要求稳定 HTTPS 自定义域名。
- 修正机器提示词真实提交接口此前未向多参考图公网化函数透传灰度放行参数的问题，避免 UI 已授权但后端仍拒绝。
- 只读媒体预检现在会识别已配置的对象存储发布桥：本地/不可达参考图在存储可发布且已明确灰度授权时标记为“提交前将发布”，不再错误阻断；真正上传、签名和可读性仍由提交阶段再次权威校验。
- 将灰度授权与“真实提交 H3”从深层“更多导出”中提升到机器提示词卡片顶部；授权仍默认关闭并按镜头重置，但用户无需展开多层面板即可理解和执行主动作。
- 未改变模型默认配置、导演分镜、锁定资产或任何真实生成任务；前端构建与相关后端回归通过。

## 2026-09-12 — 场景资产后批量提示词修复预检与生产回归

- 对 `990301 / 990306 / 990400` 共 8 个镜头重新执行只读审计：历史数据仍为 `24 error / 80 warning`；批量克隆式预检修复后为 `0 error / 4 warning`。
- 剩余 4 条 warning 均来自 `990306` 两个旧的“仅场景、无角色、无动作”测试镜头：其 `structured_shot` 未声明角色资产与 action beats。系统保留为源数据质量债，不用书号、镜头号或关键词特例静默过滤，也未修改真实项目。
- `npm run check:production` 通过：后端 `598 passed`、Golden 回归 `5/5`、运行时配置校验通过、前端生产构建通过。
- 真实 Prompt 批量 apply 仍未执行；必须在用户明确确认后，使用最新预检报告的确认令牌，并为每个镜头建立可回滚基线。

## 2026-09-12 — 8 镜头确定性 Prompt 修复落库

- 经用户确认，按预检令牌对 `990301 / 990306 / 990400` 共 8 个镜头执行确定性 Model Adapter 修复；未调用外部 LLM，不生成图片或视频。
- 每个镜头均先创建 `batch-quality-repair-current-baseline` 回滚版本，再写入新的 Prompt Version；8/8 个基线与新版本关系校验通过。
- 后审计结果为 `0 error / 4 warning`；剩余 warning 仍是 990306 两个旧测试镜头缺少结构化角色范围与 action beats 证据，未被静默过滤。
- 生产 readiness 复核显示 990306 的两个镜头仍为 `blocked`：缺少 `core_action`、入/出镜状态，不能仅凭补齐提示词放行；该项目需先补导演分镜证据或从生产验收样本中剔除。
- 后审计报告：`artifacts/storyboard-prompt-real-sample-audit-2026-09-11T16-59-44-617Z.json`；apply 报告：`artifacts/storyboard-batch-repair-apply-20260911T165930Z.json`。
- 真浏览器样本巡检适配了已清理旧项目的本地数据库：样本不足 5 个时默认只运行实际存在的样本，发布/CI 可用 `E2E_REAL_SAMPLE_REQUIRE_MINIMUM=1` 恢复硬门槛；只读巡检对 Agent 更新 reconcile 请求使用本地 mock，避免自动通知写入被误判为业务变更。当前 `990400` 单样本巡检通过，10 个工作台模块可达、无控制台错误。
- 新增根目录 `production-sample-registry.json`，将 `990306` 标记为 retired（保留数据库与历史报告，不再进入默认生产样本）；显式样本列表也会遵守该注册表。用 `990306,990400` 验证时仅选择 `990400`，真浏览器巡检通过。
- Prompt 审计默认读取该注册表的 active 样本；当前 `npm run audit:storyboard` 审计 `990400` 的 3 个镜头，结果 `0 error / 0 warning`。
- 经用户确认完成真实 `mimo-v2.5` clone-only 灰度：`990400 / 第1集 / 镜头1–3`，3/3 通过，after-audit `0 error / 0 warning`，无 repair、无 fallback，源项目未写入；总耗时 50.689 秒，缓存命中率约 8.86%（8192 / 92455 prompt tokens）。
- 灰度报告：`artifacts/storyboard-real-llm-gray-20260911T201321Z.json`；模型主机为 `api.xiaomimimo.com`，3 次请求均 HTTP 200、JSON 解析成功。

## 2026-09-11 — 场景参考图计划防止镜头风格泄漏与批量待确认清单

- 修正只读场景参考图计划：分镜的临时灯光/天气只作为分镜证据，不再隐式写入可复用场景资产或参考图提示词；场景提示词仅消费场景四层语义及明确的兼容字段。
- 新增 `scripts/merge-scene-reference-plans.py` 与 `review:scene-reference-batch`，可把任意多个只读场景计划合并为一份人工审核清单，带批量指纹、影响镜头、完整提示词和 API 请求草案。
- 批量清单明确 `writes_performed=false`、`external_calls_performed=false`，不会自动生成图片、调用模型或替换锁定参考图。
- 新增回归测试，验证计划脚本与正式 `_build_scene_asset_prompt_contract` 输出完全一致，并阻止镜头级灯光泄漏。
- 场景计划新增源资产快照指纹；资产在计划生成后发生变化时，生成排队和计划应用都会拒绝继续，要求重新生成只读计划。

## 2026-09-12 — 三本样本场景参考图真实生成完成

- 经用户确认，真实提交并完成 `990301 / 990306 / 990400` 三个场景参考图任务；新图均保存到本地 `uploads/manual-media` 并登记为 `candidate`。
- 质量审计确认新候选图均为横向可用尺寸，并提供 `candidate_reference_dimensions` 与 `landscape_candidate_count`；系统仍不自动选中、锁定或替换原有参考图。
- 当前待人工决策：每个场景选择候选图后，再执行受保护的选中/锁定与场景计划应用。

## 2026-09-12 — 三本样本场景参考图锁定与门禁恢复

- 经用户确认锁定 `990301#11`、`990306#12`、`990400#13`；旧失效锁定图降为候选并保留，未删除任何文件。
- 三份场景计划已通过快照指纹校验并正式写入，场景描述、负向约束和镜头绑定同步更新。
- 开启尺寸校验后，三本样本从 `3` 个生产阻断恢复为 `0`，受影响的 `8` 个镜头全部满足场景资产 readiness。
- Prompt Compiler + 场景资产专项回归 `48 passed`；未触发视频生成。
- 针对这 3 本样本的 8 个镜头运行只读提示词审计：历史数据仍有 `24 error / 80 warning`；克隆式批量预检可将 error 降为 `0`。8 个镜头当前没有历史 Prompt Version，但受保护 apply 会在每个镜头编译前创建当前快照基线，报告已明确标注该行为。

## 2026-09-11 — 场景资产四层语义编译

- 新增 `SceneCanonical / SceneState / SceneLook / SceneBoardSpec` 四层语义字段，旧 `VisualLocation` 字段继续作为兼容与审计来源。
- 场景基准图默认空间结构优先；状态和摄影 Look 仅在显式提供时叠加，避免雨夜、潮湿、冷暖调色永久污染场景身份。
- 新增确定性场景提示词检查，并在资产中心展示状态/风格混入本体及空间事实缺失提醒。
- 新增迁移 `h1b2c3d4e5f6_add_layered_scene_semantics.py`；不自动修改旧资产或已锁定参考图。
- 资产中心新增四层语义编辑器与生成模式选择器；服务端支持 `combined/canonical/state/look` 按层渲染，保存与生成均不覆盖旧锁定图。
- 道具资产新增 `PropCanonical / PropState / PropLook` 分层字段、迁移和可视化编辑器，按层生成与场景使用同一显式契约。
- 新增只读场景语义审计脚本 `audit:scene-semantic-lint`；当前样本 3 个场景资产发现 2 个历史状态混层 warning、无阻断，不自动迁移或改写。
- 场景资产中心新增只读“参考图质量计划”，识别失效/缺失主图并列出候选，锁定图仍需人工审核后替换。

## 2026-09-11 — 场景资产参考图统一为四视图场景设定板

- 修正场景资产仍沿用旧“单张 16:9、不分格、不做多视角”合同的问题；该合同与项目此前约定的场景空间多视图参考结构不一致。
- 场景参考图现在统一编译为一张 16:9 横向 `2×2` 四宫格：左上主视角空间全景、右上反向视角、左下侧向视角、右下关键细节视角。
- 四格强制继承同一场景、时间、天气、固定陈设、材质和光线方向；场景中不出现人物、角色、人脸、文字或标题。
- 资产接口、场景参考图计划脚本和生成排队边界使用同一确定性模板；服务端会在排队前重编译场景提示词并强制 `aspect_ratio=16:9`，避免旧页面或直接 API 调用绕过合同。
- 场景负向约束不再禁止“四宫格/多视角”，改为禁止额外分格、错位拼图、三/六/九宫格等冲突布局。
- 旧场景参考图不会自动变更；需要在资产中心按新模板重新生成并重新审核/锁定。
- 过滤导入/就绪流程生成的“最小场景资产”占位描述：该操作元数据仍保留在原始审计字段，但不会再进入供应商提示词；计划脚本与正式 API 共用同一通用占位识别规则。

## 2026-09-11 — SHAPI GPT Image 2 渠道可用性诊断

- 发现当前 SHAPI 账户 `/v1/models` 未提供 `gpt-image-2`，因此生成请求被上游以 `No available channel` 拒绝；不是提示词或六宫格编译问题。
- 模型连接检测现在会把“模型不在账户目录”判为不可用并返回可用模型列表；生图适配器也会给出明确的渠道诊断，不再建议无效重试。

## 2026-09-11 — 人物资产生图恢复六宫格编译合同

- 修正人物资产接口直接转发旧 `visual_prompt_zh` 的问题；原文继续保留为审计源，供应商请求统一使用确定性的六视图/六宫格人物定妆编译结果。
- 人物参考图负向约束补充禁止单人海报、证件照、标题/姓名文字、广告排版、单视图等内容，降低生成海报式肖像的风险。
- 前端资产摘要优先采用后端编译后的 `rendered_prompt_preview`；场景和道具的既有提示词优先级不变。
- 新增生成入口级兜底：即使浏览器携带旧提示词，服务器在排队前也会按人物资产快照重新渲染六宫格提示词，并记录原始输入与替换标记，避免旧页面状态再次提交单人海报提示词。

## 2026-09-11 — 资产参考图生成改为显式精修模式

- 修正资产中心将“首次生成参考图”与“基于已有图精修”混用的问题：人物、场景、道具首次生成默认不再携带已有参考图。
- 新增“使用已有参考图进行精修”显式开关；仅用户主动开启时才提交已选/已锁定参考图，避免 SHAPI GPT Image 2 因不支持参考图而拒绝普通生图请求。
- 保留已有参考图与锁定状态，不自动删除资产、不自动切换模型；支持参考图的精修任务仍可使用 PoYo GPT Image 2 等兼容模型。

## 2026-09-11 — SHAPI 图片模型切换至 GPT Image 2

- 因 SHAPI 平台下架 `nano-banana-2`，正式工作台的 SHAPI 图片配置已切换为 `shapi-openai-images / gpt-image-2`，保留原有 API Key 与默认图片模型槽位。
- SHAPI 预设列表移除已下架的 Nano Banana 2，仅保留 GPT Image 2；PoYo 平台的 Nano Banana 2 预设与适配器不受影响。
- SHAPI GPT Image 2 按当前已验证能力仅开放文生图，不接受参考图、图片 URL、文件上传或负向提示词；遇到这些输入时由适配器明确拒绝，不静默丢失资产约束。
- 前端模型管理文案与专项测试已同步，未发起真实生图调用。

## 2026-09-11 — 真实灰度样本证据补齐与安全门禁复验

- 新增通用样本脚本 `scripts/seed-storyboard-gray-sample.py`：创建含结构化场景/人物资产、锁定参考图、导演动作、起止状态和 action beats 的可复现实例；按传入项目 ID 幂等重建，不包含书号/角色/镜头特例逻辑。
- 使用样本 `990301 / 第1集 / 镜头1` 完成 deterministic mock clone-only 验证：`1/1 passed`，after-audit `0 errors / 0 warnings`；源项目未改写。
- 新增记录 `docs/2026-09-11-真实灰度样本准备与门禁验收记录.md`，明确真实 `mimo-v2.5` 调用仍需用户显式确认，且仅允许临时克隆、回滚、清理。
- Prompt Compiler、Decision Evidence、Director Benchmark 专项回归 `41 passed`。

## 2026-09-11 — 第二次真实 MiMo clone-only 灰度通过

- 经用户显式确认，使用当前默认 `mimo / mimo-v2.5` 对 `990301 / 第1集 / 镜头1` 完成一次真实调用；结果 `1/1 passed`，after-audit `0 errors / 0 warnings`，compiler diagnostics `pass`。
- 真实调用仅发生在临时克隆 `999905`，随后回滚并清理；源项目未修改，未创建正式 Prompt Version、图片或视频任务。
- 非敏感遥测：输入 `28,841`、输出 `587`、总计 `29,428` tokens，缓存命中 `0`（首次唯一请求），延迟约 `16,046ms`。
- 报告：`artifacts/storyboard-real-llm-gray-20260911T000429Z.json|md`；缓存收益需另行显式确认后再做重复请求，不自动重试。

## 2026-09-11 — MiMo Prompt Compiler 前缀缓存复测通过

- 经用户再次显式确认，对同一证据包执行第二次真实 `mimo-v2.5` clone-only 调用；结果 `1/1 passed`，after-audit `0 errors / 0 warnings`。
- 供应商返回输入 `28,841` tokens，其中缓存 `28,800`，命中率 `99.8578%`；输出 `638`，总计 `29,479` tokens；延迟约 `11,712ms`。
- 结果证明当前稳定 system/template 前缀 + 动态任务后缀的组织方式可被 MiMo 复用；该数值仅为样本观测，不承诺 SLA。临时克隆已回滚清理，源项目无写入。
- 报告：`artifacts/storyboard-real-llm-gray-20260911T000856Z.json|md`。

## 2026-09-11 — 多样本缓存观察样本准备

- 灰度样本扩展为同一场景/人物资产下的 3 个不同动态镜头（`1–3`），用于区分稳定前缀与动态后缀的实际表现。
- deterministic mock 批量 clone-only 验证 `3/3 passed`，after-audit `0 errors / 0 warnings`；每个临时克隆均已回滚清理。
- 多样本真实调用仍需用户一次明确确认；在确认前不调用供应商、不产生额外费用。

## 2026-09-11 — MiMo 多样本真实缓存观察完成

- 经用户显式确认，对共享稳定资产、不同动态后缀的 3 个镜头执行真实 `mimo-v2.5` clone-only 调用，结果 `3/3 passed`，after-audit `0 errors / 0 warnings`，无 fallback。
- 供应商返回总输入 `87,052`、缓存 `12,288`（聚合命中率 `14.1157%`）、输出 `1,777` tokens；平均延迟 `16.876s`，最大 `18.461s`。
- 不同动态后缀每次约命中 `4,096` tokens；同一请求重复时曾达到 `99.8578%`。该差异表明供应商当前窗口的跨请求缓存有限，不能把单请求高命中率当作通用 SLA。
- 保持现有公开协议实现，不添加未经确认的私有缓存参数，不自动切换模型/思考开关；后续继续以多版本样本观察为准。
- 报告：`artifacts/storyboard-real-llm-gray-20260911T001706Z.json|md`。

## 2026-09-11 — Director Runtime 端到端确定性验收

- 新增 `tests/test_director_runtime_e2e.py`，覆盖 DirectorTreatment → SceneBlocking → ShotPlan → Storyboard readiness → Director Benchmark 的完整批准/门禁链路。
- 测试只使用本地 mock LLM，不调用供应商、不生成媒体；验证最终 Benchmark `pass / score=100`，并在 teardown 中清理临时项目。

## 2026-09-11 — 真实模型灰度工作流受保护入口

- 新增 `.github/workflows/storyboard-real-llm-gray.yml`，提供手动触发和可显式开启的定时灰度入口。
- 手动运行必须输入 `RUN_REAL_LLM_GRAY`，并配置 `real-llm-gray` 环境的 `MIMO_API_KEY`；定时运行还需仓库变量 `ENABLE_REAL_LLM_NIGHTLY=true`。
- 工作流固定执行证据完整样本的 clone-only 验证，上传 JSON/Markdown 报告；不会进入 Required CI，不创建正式版本或媒体任务。

## 2026-09-11 — ShotPlan 门禁配置化灰度开关

- 新增 `REQUIRE_SHOT_PLAN_BY_DEFAULT` 配置项；默认 `false` 保持兼容，部署可在完成真实业务验收后统一开启。
- `StoryboardRequest.requireShotPlan` 改为读取该配置的默认值，显式请求字段仍可覆盖；不增加书号、镜头号或项目特例。
- 新增回归覆盖配置开关，验证关闭/开启时请求默认值分别为 `false/true`。
- 完整生产门禁复验：后端 `581 passed`、Golden `5/5`、运行时配置校验通过、前端构建通过。

## 2026-09-10 — Director Runtime V1.0 M1 DirectorTreatment 首个切片

- 新增独立 `DirectorTreatment` 领域模型及 Alembic `e8f9a0b1c2d3`，保存场景目标、观众问题、人物意图、Beat Map、权力变化、视听策略、约束/未知项和来源指纹。
- 新增确定性 Shadow builder；相同场景证据输出稳定 `prompt_fingerprint`，并明确 `llm_called=false`，不修改剧本、镜头或 `AgentPlan`。
- 新增只读证据包预览 API；默认不落库，`persist=true` 仅幂等保存 `draft` 草案，不调用 LLM、不修改剧本或镜头。
- 新增受控 LLM 候选 API；必须显式 `confirmed=true + allowExternalCall=true`，候选只进入 DecisionPacketRecord 并按证据指纹去重，不直接创建批准 Treatment 或修改镜头。
- 新增人工确认 API `POST /api/books/{book_id}/episodes/{episode}/director-treatment/confirm`：确认时重建证据包并校验脚本/资产指纹，候选过期即拒绝并标记 `superseded`。
- 批准后创建新的 `approved` revision，旧版本转为 `superseded`，同时保存 `rollback_anchor`；新增修订列表 API供工作台回放。
- 剧本工作台新增导演方案卡：证据预览、真实 LLM 二次确认、候选编辑和正式版本确认；不改变剧本/镜头自动写入边界。
- 前端回归新增导演方案卡覆盖，当前 `48 files / 272 passed`。
- 当前仍处于 Shadow/Assist 阶段，下一步为完整候选差异/修订历史回放及 Blocking/ShotPlan 接入。

## 2026-09-10 — Director Runtime V1.0 M2 SceneBlocking 只读切片

- 新增独立 `SceneBlocking` 模型、迁移 `e9a0b1c2d3e4` 和确定性 Spatial Engine。
- 新增空间调度预览/历史 API；仅允许 approved DirectorTreatment 进入，未声明位置保留为 unknown，不凭空生成空间事实。
- 当前仍为只读草案，未修改 StoryboardShot；下一步接人工确认、版本回滚和 ShotPlan 门禁。

## 2026-09-10 — Director Runtime V1.0 M2 SceneBlocking 确认门禁

- 新增 SceneBlocking 人工确认/版本化 API，复验证据指纹、保留回滚锚点并自动 supersede 旧版本。
- 新增 ShotPlan readiness 硬门禁：所有场景必须有 approved Blocking 且无 unresolved unknowns 才能放行。
- 实际 ShotPlan 生成器接入与连续性空间验收仍待完成。

## 2026-09-11 — Director Runtime V1.0 M3 ShotPlan 只读切片

- 新增独立 `ShotPlan` 模型、迁移 `f0a1b2c3d4e5` 和确定性 builder。
- 新增 ShotPlan 预览/历史 API；只接受 approved DirectorTreatment + approved SceneBlocking，禁止直接修改 StoryboardShot。
- ShotPlan 人工确认、回滚和正式分镜生成门禁仍待完成。

## 2026-09-11 — Director Runtime V1.0 M3 ShotPlan 确认门禁

- 新增 ShotPlan 人工确认/版本化 API；确认前必须补齐景别、机位、运动和正时长，旧版本自动 supersede 并保留回滚锚点。
- 新增 Storyboard readiness 硬门禁，防止未批准或含未知信息的 ShotPlan 进入正式分镜生成。
- approved ShotPlan 接入实际 StoryboardShot 生成器与镜头级差异回放仍待完成。
- 显式 `requireShotPlan=true` 的分镜任务现在会把 approved ShotPlan 的 beat/purpose 来源指针回填到 StoryboardShot `meta_info`，不覆盖镜头内容。
- 镜头级差异回放已提供 API；默认强制 ShotPlan 门禁仍待切换。

## 2026-09-11 — Director Runtime V1.0 M4 Director Benchmark

- 新增确定性 Director Benchmark 与只读报告 API，统一检查 DirectorTreatment、SceneBlocking、ShotPlan 的批准、证据和可执行性。
- 新增 `DirectorBenchmarkRun` 与迁移 `g0a1b2c3d4e5`，提供运行记录 POST/GET 历史 API；保存样本标签、模型标识、报告和时间，便于回放与模型对比。
- API 增加 FastAPI lifespan 启动迁移钩子，直接启动 Uvicorn 时会先幂等执行 Alembic，再对外提供新路由，避免新表缺失导致运行时 500/404。
- 报告和运行记录不调用真实 LLM，不改变剧本、镜头或生产资产；`mutated=true` 仅表示保存了 Benchmark 运行记录。
- 后端全量回归 `579 passed`，Golden `5/5`，运行时配置校验和前端生产构建均通过。
- 已按显式确认完成一次真实新样本灰度（`990306 / 第1集 / 镜头1`，当前默认 `mimo-v2.5`）；源项目未改动，临时克隆已回滚清理。模型返回可解析候选且编译诊断为 pass，但后审计仍发现静态提示词过短、缺少结构化人物资产，因此灰度判定失败，报告保存在 `artifacts/storyboard-real-llm-gray-20260910T173602Z.json`。
- 编译响应现回传非敏感 `llm_request_audit` 摘要，灰度报告会记录尝试次数、输入/缓存/输出 token、缓存命中率和延迟；不记录密钥、原始提示词或原始模型响应。
- 真实灰度脚本新增通用证据前置门禁：源镜头若同时缺少导演动作、对白、起止状态和结构化动作节拍，则直接输出 `needs_information` 报告并停止，不克隆、不调用供应商，避免对空证据重复计费。
- 新增 Benchmark 汇总 API `GET /api/books/{book_id}/episodes/{episode}/director-benchmark/summary`，按模型返回运行次数、通过率、平均分和最近运行时间，不重新执行模型调用。
- 下一步是显式确认后的真实新样本灰度，记录命中率、fallback、延迟、缓存和费用；Required CI 继续保持完全确定性。

## 2026-09-10 — Director Runtime V1.0 M0 Release Foundation

- 新增 5 个 ID-free Golden Project 夹具及 `npm run test:golden`，覆盖对白权力变化、悬疑揭示、动作阻挡、多人物调度和道具连续性；当前 `5/5` 通过。
- pytest 默认使用临时 SQLite、上传目录和 Chroma 目录，避免清理历史项目后测试依赖旧 book ID 或污染开发数据；全量后端 `577 passed`（含 M1/M2/M3/M4 Runtime 回归）。
- `check:production` 现为全量确定性测试 → Golden 回归 → `config:verify` → 前端构建，不调用收费模型，也不依赖历史真实项目审计。
- 正式本地运行时默认统一 API `18765`、Web `5175`，旧 `8765/5173` 不再作为可执行默认值；CI 触发覆盖 `codex/**` 分支。
- 详细验收记录：`docs/2026-09-10-Director-Runtime-V1-M0验收记录.md`。

## 2026-09-10 — 分镜生成模式与导演语义持久化收口

- 正式分镜生成 API 与工作台默认使用 `director_llm`；`deterministic_safe` 仅能显式选择，旧 `forceLlm` 参数继续兼容。
- CLI 的单集与完整管线入口同步显式使用 `director_llm`，避免命令行与正式工作台产生不同的分镜质量路径。
- 任务状态记录实际 `generation_mode`，便于回放、成本审计和失败恢复；不自动切换模型或绕过外部调用确认。
- `StoryboardShot` 新增并贯通 `camera_speed`、`shot_purpose`、`emotion_arc`，覆盖 LLM/fallback、数据库、API、刷新、Prompt Compiler、导出和拆镜继承。
- 新增 Alembic 迁移 `d7e8f9a0b1c2_add_storyboard_director_semantics.py`，会从旧 `meta_info.structured_shot` 安全回填，不覆盖已有非默认值。
- 全量后端回归 `554 passed`、前端 `48 files / 271 tests`、生产回归 `152 passed + build + 125-shot audit` 均通过。当前 warning 仍作为可追踪质量债，不被伪装为无警告放行。

详细验收记录：`docs/2026-09-10-分镜生成模式与导演语义持久化验收记录.md`。

## 2026-09-10 — MiMo 前缀缓存优化与成本遥测

- Prompt Compiler 将镜头专属 delivery contract 与修订要求移到动态任务后缀，system prompt 保持跨镜头稳定，减少 MiMo 前缀缓存分叉。
- 新增 canonical JSON、请求指纹和 MiMo/OpenAI `prompt_tokens_details.cached_tokens` 解析。
- LLM 审计新增输入/输出 Token、缓存命中 Token、命中率、延迟和请求指纹；供应商未返回缓存明细时保持不可观测，不伪造为 0。
- 新增缓存工具与 Prompt Compiler 稳定前缀回归测试；未改变模型选择、显式确认和媒体生成边界。
- 详细方案：`docs/2026-09-10-MiMo前缀缓存优化方案与执行记录.md`。

## 2026-09-10 — 拆镜草案增加导演语言边界校验

- 拆镜候选现在必须是可视化动作节拍；对白、说话人标签、引号和括号舞台标记会在保存/应用前被拒绝。
- 对已有不合规草案，应用接口统一返回 422 并要求重新生成，不会创建新镜头或迁移任何关联数据。
- 新增结构回归用例，防止导演分镜语言残留被误当成机器动作节拍。

## 2026-09-10 — book14 可拍性拆镜草案保存

- 为 9 个可拍性阻塞镜头保存通用拆镜草案，来源为当前可拍性校验结果；未直接拆镜、未清空原媒体或提示词。
- 草案状态均为 `draft`；镜头 2、5、14、18 具备可应用的多段候选，其余镜头当前仅有单段/延长或删减建议，需人工调整后才能应用。
- 应用拆镜仍需单独显式确认，并会创建新镜头、迁移关联数据及要求后续 Prompt 重编译。

## 2026-09-10 — book14 阻塞镜头修复版本写入

- 经用户确认，将 packet `286–294` 的 9 个修复候选写入镜头 `2、3、5、7、10、11、14、18、23` 的新 Prompt Version。
- 新版本分别为 `23、8、8、8、9、9、7、9、7`，所有接口均返回 `generation_triggered=false`。
- 版本写入后重新体检，9 个可拍性阻塞仍被保留（动作节拍/时长需进一步修订），未被提示词版本写入误判为通过；资产治理告警也继续保留。

## 2026-09-10 — book14 阻塞镜头真实 LLM 修复候选

- 经用户明确确认，调用当前 `mimo-v2.5` 为镜头 `2、3、5、7、10、11、14、18、23` 生成候选 Prompt 草案。
- 9/9 全部返回 `ready_for_review`；只读诊断显示镜头 7、23 通过，其余仅保留结构化事实、剧本残留或重要道具等 warning，无新增硬错误。
- 本阶段只保存候选草案，未创建 Prompt Version、未修改镜头、未生成图片或视频；需人工审核后才能写入版本。

## 2026-09-09 — book14 阻塞镜头证据包冻结

- 为第 1 集镜头 `2、3、5、7、10、11、14、18、23` 创建/复用 Prompt Compiler 证据包 `286–294`。
- 9 个证据包均为 `ready_for_llm_review`，无关键 unknowns；接口确认 `llm_called=false`，未创建新版本、未生成图片或视频。
- 后续若需真实 LLM 修复，必须逐次显式确认并继续沿用证据指纹校验。

## 2026-09-09 — 生产体检按镜头实际绑定资产收敛

- 生产前质量体检优先只检查当前分镜上下文中实际绑定的角色、场景和道具；未被镜头引用的库内/`shot_only` 资产不再污染本集门禁。
- 对缺少稳定 `asset_type`/`asset_id` 的旧镜头保留全库回退，避免历史数据因缺少绑定元数据而被静默放过。
- 新增回归测试，验证资产范围标记为 `bound_to_shots` 时未绑定资产不会进入体检结果；本次不修改真实项目数据。

## 2026-09-09 — book14 Prompt 候选审核与版本写入收口

- 在用户明确确认后，逐包复核并写入 `book 14 / 第 1 集 / 镜头 1–24` 的 24 个 Prompt Version；写入前均校验证据指纹与锁定资产。
- 版本确认接口返回 `generation_triggered=false`，本次没有再次调用 LLM，也没有触发图片或视频生成。
- 五项目 125 镜 zero-error gate 复跑通过：`0 error / 409 warning`；剩余 warning 作为可追踪质量债保留。

## 2026-09-09 — 智能导演台真浏览器回归适配可变项目状态

- `e2e-agent-browser-flow` 不再把“项目改编方向未锁定”写死为必现文案；已锁定项目仍验证真实工作台承接、目标镜头定位和原有门禁。
- 将只读 Prompt 草案过期诊断与模拟过期承接的 409 响应标记为预期冲突，未分类浏览器控制台错误现在会使回归失败。
- 使用正式工作台端口运行真浏览器流程通过：自由对话、动作确认承接、资产/QA 跳转、过期保护、项目动态、焦点管理和窄屏适配均通过。

## 2026-09-09 — Prompt Compiler 剧本残留检测增强

- 补强通用 `screenplay_prompt_residue` 诊断：除角色名加冒号、方括号和“画面切”外，还识别无标签感叹句对白、中文引号对白、括号舞台动作及对白叙述动词。
- 规则只依赖文本结构信号，不绑定书号、角色名或镜头号；对“压低声音”等纯视听氛围描述保留为正常画面语言，避免误报。
- 新增对白残留回归用例；Prompt Compiler、异步编译和修复链路共 75 项测试通过。
- 该规则升级后，book 14 候选仍保持“仅草案、未写版本、未触发生成”的边界；人工审核时将能准确标出镜头 5、8、11、14 等残留剧本语言。
- 二次只读审查结果见 `artifacts/book14-prompt-drafts-audit-20260909.md`，新增识别镜头 5、8、11、14、17、20 的对白/舞台风险。
- 新增候选诊断只读复核接口；正式工作台打开候选时会按当前规则刷新诊断，不会调用 LLM 或产生版本写入。

## 2026-09-09 — book 14 Prompt 候选真实 LLM 灰度

- 经显式确认，使用当前 `mimo / mimo-v2.5` 对 `book 14 / 第 1 集` 的 24 个冻结证据包执行串行候选生成。
- 镜头 1–16 首次成功保存 `ready_for_review` 候选；镜头 17–24 首次因供应商返回 `402 Payment Required` 失败，额度恢复并再次确认后已全部重试成功。
- 所有候选均未创建 Prompt Version、未修改镜头、未生成图片或视频；结果记录见 `artifacts/book14-prompt-drafts-llm-gray-20260909.md`。

## 2026-09-09 — 机器提示词导出 E2E 端口隔离

- `npm run e2e:machine-prompt-export` 的自启动模式改为显式读取 API/前端 URL 端口，并默认使用隔离端口 `18769 / 5177`。
- 后端通过 `uvicorn api.server:app` 按目标端口启动，前端代理同步指向该 API；保留 `E2E_API_URL`、`E2E_WEB_URL` 与 `E2E_START_SERVERS=0` 覆盖能力。
- 默认自启动回归已通过，不再因浏览器工具占用 8765 或正式工作台端口而误失败；测试使用 mock 门禁，不触发真实模型费用。

## 2026-09-09 — 编译兜底提示词去除长舞台标记

- 修正 Model Adapter 运动合约兜底：长段 `[...]` / `【...】` 舞台标记不再因长度上限泄漏到机器提示词。
- 修正人物性别事实自动补齐短语的标点形式，避免“角色性别事实：...”被误判为角色对白标签并触发硬门禁。
- 新增回归覆盖长舞台标记、运动合约兜底和性别事实补齐；五项目克隆修复验证已通过。
- 为 `book 14 / episode 1` 的 24 个历史镜头冻结 Prompt 证据包（packet `259–282`），仅生成证据、未调用 LLM、未修改镜头或 Prompt Version。

## 2026-09-09 — 编译层自动补齐人物性别权威事实

- Prompt Compiler 现在会基于当前镜头绑定资产，在静态提示词缺失显式性别名词时自动补入“角色性别事实”短语；该规则适用于所有项目和模型，不修改导演原文或资产事实。
- 如果候选提示词出现与权威性别相反的显式描述，仍由 `character_gender_authority` 硬门禁阻断，不做静默覆盖。
- 新增回归覆盖“缺失事实自动补齐、冲突事实继续阻断”，避免旧样本因规则升级无法重新编译。

## 2026-09-09 — 75api MiniMax H3 图片条件视频适配

- 新增独立 `75api-minimax-h3` provider，模型名固定为 `minimax_h3_no_audios`，不覆盖现有 Metaso `minimax-h3-async` 配置。
- 按 75api `/v1/videos` 协议发送顶层 `prompt`、`seconds`、`aspect_ratio`、`resolution`、`images` 字段；不发送音频字段。
- 强制首帧图或多参考图输入，拒绝文生视频、混合输入、超过 8 张参考图及 5–15 秒之外的时长，不做静默截断。
- 支持 `queued/processing/completed` 状态轮询、`video_url` 提取及受鉴权的 `/v1/videos/{task_id}/content` 回收，并保留 `id/task_id` 审计信息。
- 真实提交意图现在冻结当前视频模型配置 ID；确认阶段检测到模型漂移会拒绝提交，避免等待确认时误发到另一 provider。
- 正式工作台按实际输入选择多参考图或采纳首帧模式，不再始终强制多参考图；参考图数量上限按当前 provider 能力读取。
- 新增适配器与模型管理回归测试，后端 43 项目标测试、前端模型管理测试和生产构建通过。

## 2026-09-08 — Prompt Compiler 继承结构化人物性别事实

- 修正新版 Prompt Compiler 上下文未传递 `VisualMakeup.meta_info.structured_result.gender` 的缺口；人物绑定摘要与 canonical profile 现在统一暴露权威性别。
- 旧的扁平静态提示词即使包含相反性别，也不会再被当作可靠事实；候选草案必须通过人物性别生产硬校验后才能进入人工确认。
- 修正 Shot IR `action_beats.description` 未投影到运动合同 `action` 的兼容缺口；运动合同已纳入证据指纹，旧候选不会因规则升级被静默复用。
- 新增 authority context 回归，覆盖结构化性别进入绑定摘要与 canonical profile 的链路；未调用 LLM、未写入 Prompt Version。

## 2026-09-08 — 道具参考图提示词合同统一

- 修正道具资产提示词模板与运行时生产合同的冲突：默认产物统一为单张 1:1 / 4:3 主参考图，不再要求六视图网格、多角度拼图或横向 contact sheet。
- 运行时新增通用历史模板残留过滤，只清理网格/多视角/设定板等模板语句，保留道具的形制、材质、颜色、关键状态和时代事实；原始字段仍完整保留用于审计。
- `structured_variant_fields` 新增 `safe_reference_description`，便于 UI、导出和后续模型适配区分原始描述与实际提交文本。
- 既有候选参考图不会被静默覆盖；需要重新生成时由用户确认后生成新版本，再进行视觉审核和锁定。
- 新增回归覆盖，确保“单张主参考图 + 资产事实”合同不会再次混入 `2行3列`、`六视图` 等互相矛盾要求。
- `book 990309` 灰度中，最终道具候选图 97 已按稳定字段生成并锁定；旧候选图因证据变化保留为 `stale`，未被删除。
- 修正未绑定镜头资产重复生成时的版本号计算：现在按 `VisualReferenceAsset` 全局历史（含 stale）递增，不再重复使用 `v1`。

## 2026-09-08 — Agent 资产/QA 承接与过期证据浏览器回归

- `npm run e2e:agent-browser` 新增资产中心、QA 工作台的动作提案承接验证；资产上下文可精确落到“神秘女人”，QA 列表可见，且不绕过原工作台写入门禁。
- 新增过期证据前端回归：模拟确认时项目事实变化，UI 保持抽屉打开并明确提示重新发起请求，不发生错误导航；预期 409 不计入控制台噪声。
- 新增截图证据 `artifacts/real-browser-agent-handoff-assets.png`、`artifacts/real-browser-agent-handoff-qa.png`；服务端过期指纹行为继续由 `tests/test_agent_chat_api.py` 覆盖。

## 2026-09-08 — 项目动态处理动作收敛

- 智能导演台项目动态补充“稍后提醒”和“已解决”操作，同时保留“已知悉”；状态写入既有审计接口，不改变项目事实或生产门禁。
- 真浏览器回归覆盖状态流转 `acknowledged → snoozed → resolved`，并保持控制台无非预期错误。

## 2026-09-08 — 智能导演台可访问性与窄屏收口

- 对话抽屉打开后自动聚焦输入框，关闭后将焦点还给浮动入口；增加 `aria-modal` 语义，避免键盘用户迷失位置。
- 抽屉在 390px 窄屏下使用视口约束，不产生横向溢出；真浏览器脚本已加入焦点与宽度断言。

## 2026-09-08 — Agent 动作提案真浏览器承接验收

- `npm run e2e:agent-browser` 现覆盖普通对话、动作确认卡、确认承接、精确镜头定位及原工作台放行门禁可见性。
- 使用独立 Playwright Chromium 与隔离 mock，避免真实模型费用；服务端幂等、指纹过期和无副作用协议继续由 Agent API 回归覆盖。
- 验收样本：`book 75 / 第 1 集 / 镜头 3`，浏览器控制台错误为 0。记录见 `docs/2026-09-08-智能导演台动作提案真浏览器验收记录.md`。

## 2026-09-08 — Agent 动作提案安全承接

- 对自由对话返回的副作用动作提案补充 `audit_id` 追踪和 `POST /api/agent/audit/{id}/handoff-confirm` 确认接口。
- 用户确认后只记录承接意图并打开正式工作台，不执行资产/剧本写入、Prompt Version 覆盖或图片/视频生成；原工作台的证据、锁定、版本、预算和最终确认门禁保持生效。
- 正式工作台通过统一 `smart-director:navigate` 事件接收镜头/资产上下文；“稍后处理”不改变项目事实。
- 新增后端动作承接回归，Agent 对话与草案相关测试通过，前端 Agent 测试及生产构建通过。

## 2026-09-08 — 主动汇报 SSE 事件流

- 新增只读 `GET /api/agent/updates/stream`，按 `sinceId` 推送新增项目动态；无新事件时返回心跳并关闭，避免长连接占用。
- 智能导演台打开时优先建立事件流，连接失败或浏览器不支持时继续使用原有轮询；事件流不会创建动态、调用模型或触发生产操作。
- SSE 冒烟验证返回 `text/event-stream` 和 heartbeat，主动汇报回归及前端生产构建通过。
- 新增可重复的 `npm run e2e:agent-browser`（独立 Playwright Chromium）真实页面验收脚本，避免依赖桌面浏览器扩展桥接。

## 2026-09-07 — 智能导演台自由对话与主动项目汇报基线

- 新增 `AgentProjectUpdate` 持久化模型与迁移，统一记录项目进度、问题、失败、建议和待确认事项，支持证据指纹、去重键、已知悉/解决/稍后提醒状态。
- 新增项目事实驱动的主动汇报引擎：基于服务端剧本、分镜、资产、QA 和任务快照生成进度与风险更新；同一证据包重复检查不会刷屏。
- 新增 `/api/agent/updates/reconcile`、`/api/agent/updates`、`/api/agent/updates/summary` 和状态更新接口；Agent 时间线与任务中心可识别项目动态。
- 新增 `/api/agent/chat` 自由对话接口：普通问答、进度分析和图片/文档理解直接回复；修改、覆盖、生成等副作用只返回受控动作提案，不执行生产操作。
- 智能导演台抽屉接入项目动态、未读标记和后台周期检查；发送消息不再强制经过“预览 LLM → 确认调用”流程。
- 回归：主动汇报/自由对话后端 4 项通过，Agent 相关后端 13 项通过，前端相关测试 6 项通过，生产构建通过。

## 2026-09-07 — 生产门禁与修复预检协议同步

- `--zero-error-gate` 现在按语义只阻塞真正的审计 error；warning 仍完整写入报告，供生产质量债治理，不再被误判为零错误门禁失败。显式 `AUDIT_STORYBOARD_STRICT=1` 仍可启用零 warning 强策略。
- 场景参考资产只读规划脚本改为从模型注册表解析当前默认图片模型，避免硬编码旧供应商；当前会自动跟随正式工作台的 `nano-banana-2`。
- 批量修复、质量修复和真实灰度脚本同步 `confirmed=true + allowExternalCall=true` 双确认协议；克隆预检遇到编译器 fail-closed 时保留候选诊断并生成报告，不会中断整批预检或写入真实项目。
- 生产回归验证：后端 143 项通过、前端构建通过、五项目 125 镜头零 error 门禁通过；历史样本仍保留 321 条 warning 作为可追踪质量债。
- MiMo `mimo-v2.5` 官方模型页提供 OpenAI-compatible `image_url` 多模态请求示例（图片、音频、视频输入）；因此 Agent 的“支持图片理解”开关可在完成供应商确认后安全开启，系统仍以显式能力配置作为实际发送门禁。

## 2026-09-07 — 智能导演台会话与多模态安全收口

- Agent 会话恢复现在完整保存初始用户消息、助手建议、计划和附件引用；追加消息会更新会话时间，历史排序保持正确。
- 附件引用增加项目归属与可用状态校验，禁止跨项目越权引用；草案去重限定为同一项目和同一证据包。
- 视觉附件仅在显式确认外部调用且 Agent 模型开启“支持图片理解”时，以内存 data URL 传入 LLM，不发布到对象存储。
- 模型管理新增普通用户可理解的“支持图片理解”开关；预览、会话和草案调用均保持可审计、可回放且不自动执行生产操作。

## 2026-09-06 — 生产对象存储域名门禁统一

- 将“生产参考资产必须使用自定义 HTTPS 域名、不得使用七牛 `clouddn.com` 临时域名”的判定下沉至 `core/public_asset_storage.py`，不再只依赖模型管理页的展示状态。
- 需要强制发布到对象存储的生产输入（包括 H3 多参考图、视频交接帧以及正式迁移）现在会在上传前统一拒绝 HTTP、临时 `clouddn.com` 或无效配置；不会写入对象、改写资产引用或向外部视频模型提交不稳定 URL。
- 迁移执行器复用同一核心规则，消除前后端及不同写入路径的判定分叉；新增回归覆盖，确认临时 HTTP 域名不会触发七牛上传。

## 2026-09-03 — 剧本 QA 可控闭环方案（beat + edits + criteria）

- 明确从“整段重写 + 行号定位 + 复检重跑全套 QA”收敛为“beat 锚点 + 编辑操作协议 + 每题可判定通过条件”，使迭代可终止、可合并、可验收。
- 新增设计文档 `docs/2026-09-03-剧本QA可控闭环最佳方案.md`，同步进《产品重构蓝图》与《产品重构阶段任务与验收标准》（阶段 1.0b）。
- 核心：剧本派生稳定 `beat_id` 索引；QA 挂 `beat_id` 而非行号；LLM 输出锚定 `edits[]`（replace/insert_after/delete + beat_id + new_text）；复检只对 target 的 `resolution_criteria` 断言；结构/矛盾项自动、主观项转人工队列。不新增书号/角色/关键词特例。
- 已实施阶段 A：新增 `core/script_beat.py`（确定性剧本 beat 索引），识别场景标题、`[场景结束]`、`[视觉证明N]`、`**[动作]**`/`**[动作开始/结束]**`、`**[开场]**`、`**[人物入场]**` 与对白；`beat_id = ep{ep}-s{scene}-b{n}` 稳定锚点，start_line/end_line 随版本重算。真实样本 `book 990309` 第 1 集解析 148 beat（3 场景），幂等且无误分类；回归 `tests/test_script_beat.py` 3 项通过。
- 已实施阶段 B：新增 `core/script_beat.py::find_issue_beats`（QA 定位 → beat_ids，归一化子串命中或单场景行区间重叠才算可靠）与 `core/qa_resolution.py::build_resolution_criteria`（给出可判定 `contains_required`/`structure_present`，否则 `requires_human`）。已接入 QA 决策包 scope（`beat_ids/beat_anchor_reliable/resolution_criteria`）；无可靠 beat 或非可判定项一律降级为人工，不进入可写路径。回归 `tests/test_qa_resolution.py` 4 项、相关 18 项通过。
- 已实施阶段 C：新增 `core/script_edit.py`（`validate_edits`：beat 存在、no-op、结构标记保护、操作数上限、同拍冲突拒绝、可传冻结指纹 stale 校验；`apply_edits`：按 beat 顺序重建文本并保留结构）。新增 `POST /api/books/{book_id}/qa/{episode}/apply-edits`：校验→应用→`ScriptVersion`（`change_type=qa_edit`，meta 存 `pre_apply_beats`/`applied_edits`，行号随内容重算），可选复检；绝不调用 LLM。实测冲突编辑返回 `409` 且不写入。回归 `tests/test_script_edit.py` 7 项、相关 14 项通过。
- 已实施阶段 D：`core/qa_resolution.py::evaluate_resolution_criteria`（按 `contains_required`/`structure_present`/`requires_human` 对当前剧本判定），新增只读 `POST /api/books/{book_id}/qa/decision-packets/{packet_id}/scoped-check`（只评估该包 `resolution_criteria`，不重跑全套 QA、不写任何数据）。只读 harness 给出“达标即终止”的判定信号；`requires_human` 返回 `passed=True` 但由路由转人工。回归 `tests/test_qa_resolution.py` 6 项、相关 16 项通过。
- 已实施阶段 E：`core/qa_resolution.py::route_issue`（`beat_anchor_reliable` 且可判定 criteria → `auto`，否则 `human`）；`apply-edits` 扩展接受 `resolution_criteria`，应用后校验达标则写 `QAIssue.fix_status=resolved`、否则 `needs_refinement`。回归 `tests/test_qa_resolution.py` 9 项、相关 18 项通过。
- 新增锚定编辑协议 `propose_edits`：`core/decision_draft.py` 支持决断 LLM 输出 `edits[]`（replace/insert_after/delete + beat_id ∈ scope.beat_ids + new_text），validator 逐条校验并剔除非法项；局部修订包 scope 现写入 `beat_ids/beat_anchor_reliable` 并将 `propose_edits` 加入 allowed_operations。回归 30 项通过。
- `validate_edits` 新增两类守卫生效：`replace` 新文本不得重复相邻 beat 已有内容（防重复结尾）；结构标记 beat（场景结束/画面渐隐/动作边界/标题）禁止改写。局部修订包 `beat_ids` 现在排除结构 beat。真实验证（`book 990309` / `qa-ep1-1ecd390f`）：LLM 成功输出 `propose_edits` 单条 `replace`（`proposed_content=0`、无冲突），但目标为 `[画面渐隐]` 结构标记，`apply-edits` 返回 `409 结构标记禁止改写`、未写入；重新转发后包 `beat_ids` 为 b40–b47 且不含 `[画面渐隐]`。回归 31 项通过。
- 全自动闭环跑通：`build_resolution_criteria` 对“场景结束标记缺失”改为 `structure_present`（需存在含 `[场景结束]` 的 beat）；一次性验证书 `990321` 上 `apply-edits`（`insert_after` 加 `[场景结束]`，版本 2）→ `structure_present` 判定 `passed=true` → `QAIssue.fix_status=resolved`。验证书已清理。闭环 `edits[] → apply-edits → 达标判定 → resolved` 全链路验证完成。
- 人工队列路由：新增 `GET /api/books/{book_id}/qa/{episode}/routing-plan`（只读）与 `POST /api/books/{book_id}/qa/{episode}/route-human-queue`。按 `route_issue`（`beat_anchor_reliable` + 可判定 criteria）决定 auto/human；把 `human` 项标记 `human_review_required=True`/`routing=human`/`status_reason=转人工定稿`。已对 `book 990309` 第 1 集执行：5 项 open 全部 `human`、`auto=0`，未改动剧本（最大版本仍为 v18）。QA 自动化到此收敛，主观项转人工定稿队列。
- 前端 QA 列表为人工定稿项加醒目徽章：`ProductWorkspaceQaSection` 新增 `isHumanReview` 判定（`meta_info.routing=human` / `human_review_required` / `statusReason` 含“人工定稿”），列表行显示琥珀色“人工定稿”徽章。真浏览器核对：`book 990309` QA 页 5 项主观工单均显示该徽章（badgeCount=5），前端生产构建通过。
- 服务端回归说明：阶段 E 验证时误对 `book 990309` 发送了合法 `delete` 编辑，实际写入并生成版本 17；已立即用回滚端点到版本 18 恢复至 v16 内容（被删叙述与视觉证明4 已还原，beat 数 148）。当前剧本内容正确；后续仅用明确非法（结构标记/冲突）编辑做非破坏性校验。

## 2026-09-02 — QA 整集修复任务化

- 新增受控 QA 批量修复异步执行模式：用户明确发起后，接口立即返回 `task_id`，避免多条 LLM 修复将浏览器连接占用至超时。
- 新增 `GET /api/books/{book_id}/qa/auto-fix/tasks/{task_id}`，可读取持久化的排队、执行、复检、完成或失败状态；服务重启后仍可从 `TaskRun` 恢复。
- 异步模式复用既有逐条选项选择、diff 守卫、修复版本与整集 QA 复检；它不自行创建任务、不跳过人工触发，也不触发任何媒体生成。
- 新增自动化回归，验证后台任务能完成一条真实 QA 工单并写入可查询结果。
- QA 结构预检改为按统一结束标记语法识别 `【场景结束】`、`[场景结束]`、Markdown 包裹和淡出标记；带强调的收束句按去除 Markdown 后的真实末尾标点判定，避免格式误报。
- `DecisionPacket` 的真实 LLM 草案调用新增持久化 in-progress 占位锁；相同证据包在模型返回前的重复请求统一返回进行中状态，避免并发点击产生重复模型调用与重复计费。
- QA 草案新增单问题局部修订合同，并把分集大纲、Bible、Production Skill 与未关闭 QA 上下文纳入证据；没有经场景交叉校验的精确行段时，候选只能输出人工审阅策略，不能携带可写入剧本正文。

## 2026-08-30 — 结构变换通用回滚锚点

- 为镜头的结构变换新增通用 `state_snapshot` 回滚锚点：它保存变换后、首次重编译前的完整镜头状态，而非伪造一条历史机器提示词。
- 拆镜确认写入现在会原子地为两个结果镜头建立状态快照锚点；后续任何声明结构来源的变换也可复用同一数据结构。
- 新增受保护接口 `POST /api/books/{book_id}/production-readiness/repair-plan/rollback-anchors`：默认只预检，只有当前计划指纹与 `confirmed=true + allow_write=true` 同时成立才为历史变换镜头补建锚点。
- 生产修复计划会在“仍待首次重编译”的变换镜头优先选择状态快照；完成编译后恢复使用普通 Prompt Version 作为后续修复基线。
- 回滚状态快照时恢复动作、连续性、镜头参数、参考绑定、提示词与元数据，避免只回滚提示词而让分镜结构保持错误状态。
- 正式工作台体检卡新增“预检补建状态锚点 → 确认建立状态锚点”两步操作；不会自动修改历史镜头。
- 经操作者确认，已在 `book 75 / episode 1` 验证历史迁移路径：12 个已声明拆镜结果全部建立状态锚点，计划中的缺失锚点降为 0；未触发编译或媒体生成。

## 2026-08-29 — 可拍性结果持久化与视频生成门禁

- 编译后的核心动作、动作节拍、连续性和 `pass / warning / blocked` 结果现在同时写入 `structured_shot`、`prompt_compile_context` 与 `shot_ir`。
- 正式工作台展示镜头时长、核心动作、动作节拍和可执行建议，低频明细默认折叠。
- 视频生成遇到 `blocked` 时返回 409 并阻止提交；`warning` 需要用户显式确认后才允许继续。
- warning 覆盖写入 `meta_info.executability_overrides`，并保留在任务请求快照中。
- 新增 `npm run audit:shot-executability`：默认对正式样本书生成只读 30 镜头节拍回放报告，不调用 LLM、不改写镜头。
- 拆镜建议从单一标签升级为两个连续镜头的候选动作分配与推荐时长草案。
- 对 book 75 的 pass 镜头完成首批确定性结果回填（2、3、5、7、9、10、11）；未调用 LLM、未改写提示词、未触发媒体生成。
- book 75 的其余 blocked/warning 镜头也已回填为只读治理元数据，使工作台可直接显示阻塞原因与拆镜草案；视频门禁随之对全部 14 个镜头生效。
- 修复旧 Prompt Compiler 运行时上下文刷新会丢弃 `core_action`、`action_beats`、连续性与 `executability` 字段的问题。
- 正式工作台新增“保存拆镜草案”：将可拍性建议保存为待人工确认的两段候选镜头，不直接修改原镜头。book 75 / 镜头 1 已完成真实接口回归。
- 正式工作台新增“确认应用拆镜草案”：会新增第二镜头、顺延同集镜头号，保留参考绑定但清空旧提示词和媒体，避免错误复用旧产物；必须二次确认后执行。
- 拆镜应用时归档原媒体关联，不删除底层资产，后续可据此审计或恢复。
- 可拍性校验新增最终运动提示词动作解析与结构化节拍漂移检测，修复“结构化节拍通过、真实视频提示词过载”被误判的问题；book 75 / 镜头 3 已改判为 blocked。

## 2026-08-29 — 分镜图提示词结构化与参考图命名规范

> 对应分支：`codex/unify-formal-workspace`
> 背景：分镜图提示词需要保留导演语言的创作意图，但提交给生图模型时必须经过结构化编译，且参考图要能明确区分人物、场景、道具用途。

### 变更概览

- `Model Adapter` 新增 `storyboard_image_prompt_sections_v1`：
  - 画面定格
  - 资产锚点
  - 构图关系
  - 当前帧动作
  - 资产视觉事实
  - 光线与情绪
  - 一致性与禁止项
- Prompt Compiler 读取结构化基线后仍输出自然中文 `visual_prompt_static`，避免把字段标题当作模型画面内容。
- 明确禁止把人物定妆设定板、六视图、参考图生成模板等内容混入分镜首帧提示词。
- 正式镜头工作台新增“结构化分镜图提示词”展示区，位于导演分镜语言下方，可直接查看画面定格、资产锚点、构图关系、当前帧动作、资产视觉事实、光线情绪和一致性禁止项。
- 修正输出接口兼容刷新逻辑：历史 Prompt Compiler 上下文重建时保留 `model_adapter.static_prompt_sections`，避免数据库已有结构但前端拿不到。
- 已对 `book 75 / episode 1 / shot 3` 执行安全重编译，生成 `prompt version v12`，结构化 sections 已进入 API 输出。
- 参考图 payload 新增语义字段：
  - `reference_name`
  - `reference_label`
  - `reference_role`
  - `reference_purpose`
  - `weight`
- 修复正式镜头工作台普通“生成视频”入口的 H3 提交链路：
  - 真实视频 provider 会先将多参考图发布为公网可访问 URL，再提交给 H3。
  - 存在多参考图时不再混用本地首帧 `/api/prototyping/manual-media/...`，避免云端 provider 读取不到本地资源导致 HTTP 400。
  - 任务记录会保留 `reference_public_assets` / `first_frame_public_asset`，方便失败追踪。
- 七牛公网 URL 校验增加短重试，并在 H3 多参考图公网化失败时返回具体 `reference_asset_id`，避免偶发访问超时或单张坏图时无法定位。
- 修复本地手动上传资产的公网中转死锁：`/api/prototyping/manual-media/...` 在后端任务内会直接读取 `uploads/manual-media` 本地文件，不再从同一个 Uvicorn 进程 HTTP 回调自己，避免页面生成视频时 30 秒超时。
- 修复普通分镜视频生成的提交规格：
  - 前端未显式传 `durationSeconds` 时，后端使用当前分镜 `shot.duration`，避免模型默认 `5s` 覆盖分镜时长。
  - MiniMax H3 的 `max_reference_images=0` 不再被错误压成 1；多参考默认按最多 9 张提交。
- MiniMax H3 提交失败诊断增强：HTTP 400/401/403/404/429 等上游错误会保留响应 body 到 `provider_response`，并尽量把上游 `message/error/detail` 拼入错误文案，方便定位平台字段限制。
- H3 多参考提交改为统一镜像策略：配置七牛后，场景、人物、道具等所有参考图都会先复制到同一对象存储，再提交给视频 provider，避免混用第三方 CDN 导致 provider 侧拉取失败。
- 分镜生成质量治理方案落档：新增镜头意图规划、动作时长节拍、可拍性校验，以及过载镜头的延长/删减/拆镜建议；该方案已同步进入产品蓝图与生产级上线冲刺清单。
- 分镜可拍性治理第一阶段开始实现：新增 `core/shot_executability.py`，并将 `core_action`、`action_beats`、`executability` 接入 Prompt IR；已覆盖动作过载、镜头运动冲突和起止状态缺失的纯函数校验与回归测试。
- 新增规范文档：`docs/2026-08-29-分镜图提示词结构与生图参考命名规范.md`，记录常见生图参数、GPT Image 2 / PoYo 参数口径、WebUI 参考图命名方式和项目内部命名约定。

### 验证结果

- `python -m py_compile api/server.py core/model_adapter.py api/generation_adapters.py`：通过。
- `python -m unittest tests.test_storyboard_prompt_compile tests.test_generation_adapters tests.test_visual_asset_library`：62 tests OK。
- `python -m unittest tests.test_storyboard_prompt_compile tests.test_visual_asset_library`：46 tests OK。
- `npm --prefix web run build`：通过。

---

## 2026-08-28 — H3 多参考视频与手动资产上传闭环

> 对应分支：`codex/unify-formal-workspace`
> 背景：MiniMax H3 / metaso 视频生成主路径应是“多参考图 + 机器提示词”，不是单一首帧驱动；同时生产中所有关键图片资产都需要支持人工上传兜底。

### 变更概览

- H3 视频适配层改为多参考图优先：
  - 存在 `reference_images` 时，payload 使用 `role=reference_image`，最多 9 张。
  - 多参考图存在时不再同时混入 `first_frame`，避免模式语义冲突。
  - 仅在没有参考图时，才回退到首帧图生视频；再无首帧时回退文生视频。
- 机器提示词真实提交入口新增 `useReferenceImages / referenceAssetIds`，正式工作台真实提交 H3 默认启用多参考图，首帧只作为兼容兜底。
- 普通镜头“生成视频”链路放开旧首帧硬门槛：只要存在已采纳分镜图或已选中/锁定参考图，就具备视频输入条件。
- 新增手动媒体资产上传入口：
  - `POST /api/books/{book_id}/storyboard/{episode}/{shot_id}/manual-media-assets`
  - `POST /api/books/{book_id}/visual-assets/{asset_type}/{asset_id}/manual-reference-assets`
  - 支持 PNG / JPG / WebP。
  - 上传为分镜图时写入 `StoryboardShot.asset_links.images` 并可直接采纳。
  - 上传为参考图时写入 `VisualReferenceAsset`，默认 `locked`，并同步到当前镜头 `asset_links.references`，后续可被 H3 多参考视频生成读取。
  - 资产中心现已支持人物、场景、道具直接手动上传参考图；手动上传图与模型生成图进入同一套参考图版本、锁定和同步机制。
  - 新增 `/api/prototyping/manual-media/{filename}` 用于本地预览；真实提交 H3 前仍通过对象存储中转为公网 URL。
- 模型管理文案从“首帧公网中转”修正为“参考资产公网中转”。
- H3 灰度脚本默认改为多参考预检，新增 `--publish-reference-images`；首帧预检/发布保留为兼容模式。

### 验证结果

- `python -m py_compile api/server.py api/generation_adapters.py scripts/validate-minimax-h3-gray.py`：通过。
- `python -m unittest tests.test_generation_adapters tests.test_storyboard_prompt_compile`：通过。
- `npm --prefix web run build`：通过。

---

## 2026-08-28 — 对象存储后台配置与迁移规划

> 对应分支：`codex/unify-formal-workspace`
> 背景：H3 视频生成需要公网可拉取参考资产；仅靠 `.env` 配置不利于后台添加、替换和后续迁移对象存储。

### 变更概览

- 新增对象存储后台配置 API：
  - `GET /api/public-asset-storage/config`
  - `PUT /api/public-asset-storage/config`
- 配置第一版支持七牛 Kodo，字段包括 Provider、本地后端地址、Bucket、Region、公网访问域名、对象前缀、私有 Bucket、AccessKey / SecretKey。
- AccessKey / SecretKey 支持后台保存状态检查，但接口响应不会回显密钥；前端留空保存会保留已保存密钥。
- 模型管理页新增“对象存储 / 参考资产公网中转”配置卡，可在正式工作台内完成对象存储添加或更换配置。
- 新增只读迁移规划 API：`GET /api/public-asset-storage/migration-plan`。
  - 扫描视觉参考资产与镜头资产链接。
  - 识别已在目标对象存储、本地/内联待发布、外部可读、外部不可读、未知来源等状态。
  - 当前只生成迁移计划，不会自动搬迁云对象或改写数据库引用。
- 自动迁移执行被明确列为下一阶段受保护能力：必须先 dry-run、生成确认令牌，再允许写入对象存储和改写资产引用。
- 真实 H3 灰度时发现 MiniMax H3 不接受 SVG 首帧 URL；对象存储中转层已补 SVG -> PNG 栅格化，保证本地 SVG 占位/历史首帧发布给视频 provider 时使用 PNG。

### 验证结果

- `python -m py_compile core/public_asset_storage.py api/server.py scripts/validate-minimax-h3-gray.py`：通过。
- `python -m unittest tests.test_public_asset_storage tests.test_storyboard_prompt_compile tests.test_generation_adapters`：通过。
- `npm --prefix web run build`：通过。
- `python scripts/validate-minimax-h3-gray.py --book-id 3 --episode 1 --shot-id 3 --allow-real --publish-first-frame`：真实灰度通过；H3 provider 返回 `succeeded`，并回写视频资产。该样本使用的是占位首帧转 PNG，证明技术链路打通；正式画面质量灰度仍需使用 GPT Image 2 生成的真实首帧。

---

## 2026-08-28 — 七牛公网资产中转接入第一版

> 对应分支：`codex/unify-formal-workspace`
> 背景：本地局域网运行的项目无法把首帧图直接交给云端视频模型拉取；H3 图生视频真实提交前必须保证首帧 URL 可被 provider 公网访问。

### 变更概览

- 新增公共资产存储配置，第一版支持七牛 Kodo：
  - `PUBLIC_ASSET_STORAGE_PROVIDER=qiniu`
  - `QINIU_BUCKET=ai-ku01`
  - `QINIU_REGION=z2`
  - `QINIU_PUBLIC_BASE_URL`
  - `QINIU_BUCKET_PRIVATE=true`
- 新增 `core/public_asset_storage.py`：
  - 检查公网 HTTP/HTTPS URL 是否可访问。
  - 支持把本地路径、局域网 API URL、data URI 或仍可下载的 URL 上传到七牛。
  - 私有 Bucket 默认生成限时签名下载 URL。
- H3 真实提交入口接入首帧公网化：
  - 若首帧原 URL 已可访问，直接使用。
  - 若首帧不可访问但可经七牛中转，则使用七牛签名 URL。
  - 若首帧源图无法读取或中转后仍不可访问，则拒绝真实提交，避免 provider 扣费失败。
- H3 灰度脚本新增首帧 URL 可达性检查：
  - 自动候选不再只看“是否外部 URL”，会实际检查 URL 是否可拉取。
  - `404` 或本地 `/api/prototyping/assets/...` 会成为真实提交 blocker。
  - 新增 `--publish-first-frame` 显式开关；默认 dry-run 不会向七牛写入对象。

### 当前七牛控制台核对

- Bucket：`ai-ku01`
- 区域：华南-广东，对应 `z2`
- 访问控制：私有
- 当前域名：`tkgj4ur0t.hn-bkt.clouddn.com`
- 限制：该域名是七牛测试域名，页面提示每日限回源总流量、30 天回收且不支持 HTTPS；适合临时开发，不适合生产。

---

## 2026-08-28 — H3 视频时长改为由分镜决定

> 对应分支：`codex/unify-formal-workspace`
> 背景：视频生成不应固定为 5 秒；镜头节奏应由分镜 `duration` 决定，H3/metaso 适配层只负责转换为平台可接受的提交参数。

### 变更概览

- 正式镜头工作台的 H3 真实提交前摘要改为显示分镜推导出的时长。
- 真实提交 MiniMax H3 时，`durationSeconds` 不再写死为 `5`，而是从当前镜头 `duration` 推导。
- 推导规则：
  - 有效分镜时长：四舍五入为整数秒。
  - 平台提交范围：按 H3 支持范围夹取到 `4s–15s`。
  - 缺失或非法时长：使用默认 `5s`，并在摘要/报告中标明来源。
- `scripts/validate-minimax-h3-gray.py` 灰度脚本同步改为默认读取分镜时长；仅显式传入 `--duration-seconds` 时才视为命令行覆盖。
- H3 预检摘要与灰度报告新增“时长来源”，避免 UI 摘要、脚本报告、实际提交参数不一致。

### 验证结果

- `npm --prefix web test -- ProductWorkspaceMachinePromptExportPanel.test.ts ProductWorkspaceStoryboardRepairActions.test.tsx`：通过，9 tests。
- `npm --prefix web run build`：通过。
- `python -m py_compile scripts/validate-minimax-h3-gray.py`：通过。
- `npm run validate:minimax-h3-gray -- auto`：通过；dry-run 未触发 provider call。自动候选 `book 14 / episode 1 / shot 1` 的原始分镜时长为 `3s`，报告显示按 H3 平台范围提交为 `4s`。
- `npm run e2e:machine-prompt-export`：通过；真浏览器验证 H3 提交前摘要显示分镜来源时长。

---

## 2026-08-28 — H3 真实提交前摘要

> 对应分支：`codex/unify-formal-workspace`
> 背景：metaso MiniMax H3 真实提交即将进入账号灰度，用户二次确认前必须看清实际提交规格，避免“点了真实提交但不知道提交了什么”的生产风险。

### 变更概览

- 正式镜头工作台的机器提示词导出区新增“真实提交 H3 前摘要”。
- 摘要显示：
  - 平台：`metaso.cn MiniMax H3 兼容 API`
  - Base URL：`https://metaso.cn/api/minimax`
  - 模型：`MiniMax-H3`
  - 规格：`768P / 分镜时长 / 16:9`
  - 时长来源：分镜 `duration`，并按 H3 平台范围提交
  - 模式：首帧图生视频或文生视频
  - AIGC 水印：关闭
  - Prompt 长度
- 当前没有采纳首帧时，摘要会明确提示后端会按文生视频提交，并建议优先补齐首帧再做真实灰度。
- 新增 `ProductWorkspaceMachinePromptExportPanel.test.ts` 锁定摘要文本。

### 验证结果

- `npm --prefix web test -- ProductWorkspaceMachinePromptExportPanel.test.ts modelRegistryModal.test.ts ProductWorkspaceStoryboardRepairActions.test.tsx`：通过，17 tests。
- `npm --prefix web run build`：通过。

---

## 2026-08-28 — metaso MiniMax H3 兼容 API 收口

> 对应分支：`codex/unify-formal-workspace`
> 背景：确认目标接入平台为 [metaso.cn/minimax-h3](https://metaso.cn/minimax-h3)，其 ComfyUI 插件使用 MiniMax H3 兼容协议：`base_url=https://metaso.cn/api/minimax`，token 为 `mk-` 开头，create/query 路径沿用 `/v2/video_generation` 与 `/v2/query/video_generation/{task_id}`。

### 变更概览

- 模型管理中 `minimax-h3-async` 的推荐 Base URL 从官方域名改为 `https://metaso.cn/api/minimax`。
- H3 推荐默认参数新增 `aigc_watermark=false`；真实请求中只有显式开启时才发送 `aigc_watermark: true`。
- H3 adapter 增加 `fail / expired` 失败状态兼容，并优先读取 `task.error.message`。
- 新增 mock 测试锁定 metaso create URL、默认不发水印、开启水印时发送 `aigc_watermark=true`，以及 `fail / expired` 状态失败处理。

---

## 2026-08-28 — MiniMax H3 默认分辨率收口为 768P

> 对应分支：`codex/unify-formal-workspace`
> 背景：metaso.cn MiniMax H3 兼容平台支持 `768P / 2K`，真实灰度阶段应优先采用低成本、低风险默认值；用户仍可在模型配置中显式切换为 `2K`。

### 变更概览

- MiniMax H3 adapter 在未配置 `default_params.resolution` 时，默认使用 `768P`。
- 模型管理中 `minimax-h3-async` 的推荐默认参数从 `resolution=2K` 改为 `resolution=768P`。
- 保留 `2K` 合法值校验，显式配置 `2K` 时仍会按 `2K` 提交。

---

## 2026-08-28 — MiniMax H3 机器提示词导演口令清洗

> 对应分支：`codex/unify-formal-workspace`
> 背景：H3 灰度脚本自动候选已能选出带外部首帧的真实镜头，但报告发现模型提交字段仍可能残留 `画面开场 / 画面切` 这类导演剪辑口令。产品边界需要进一步收紧：导演分镜语言允许保留创作表达，提交给模型的机器提示词必须更像标准化执行语言。

### 变更概览

- **机器字段清洗**
  - `compile_machine_prompt` 在生成 `visual_timeline` 与 `observable_action` 时，对 `start_state / action_process / end_state / dialogue` 先进入统一机器文本清洗。
  - `director_shot_text` 不做清洗，继续保留用户可编辑的导演分镜语言。
  - H3 / 通用 WebUI 导出不再直接带出 `画面开场 / 画面切 / [画面` 等剪辑口令。

- **Adapter 规则补齐**
  - `sanitize_machine_prompt_text` 新增对 `画面开场`、`镜头开场` 的清理。
  - 既有 `画面切 / 镜头切 / 对白 / 台词` 等清洗规则继续用于把导演口令转换为连续镜头机器语言。

- **灰度脚本维护**
  - `scripts/validate-minimax-h3-gray.py` 改用 timezone-aware UTC 时间，去除 Python `datetime.utcnow()` deprecation warning。

### 验证结果

- `python -m unittest tests.test_machine_prompt_export tests.test_model_adapter`：通过，13 tests。
- `python -m py_compile scripts/validate-minimax-h3-gray.py`：通过。
- `npm run validate:minimax-h3-gray -- auto`：通过；自动候选仍为 `book 14 / episode 1 / shot 1`，报告 `warnings: []`，未触发真实提交；当前唯一 blocker 为视频 profile 仍未配置为 `minimax-h3-async`。

---

## 2026-08-27 — MiniMax H3 真实外网灰度脚本

> 对应分支：`codex/unify-formal-workspace`
> 背景：二段式 H3 真实提交入口已经落地，但生产前仍需要一个默认 dry-run、强门禁、可审计的真实账号灰度脚本，防止手工误触付费接口。

### 变更概览

- **新增灰度验证脚本**
  - 新增 `scripts/validate-minimax-h3-gray.py`。
  - 新增 npm 入口：`npm run validate:minimax-h3-gray`。
  - 默认只做 dry-run 预检：读取真实镜头、加载 H3 机器提示词导出、检查视频模型配置、首帧、prompt 长度和真实提交门禁。
  - 默认不登记任务、不提交 MiniMax、不写回视频资产。

- **真实提交强门禁**
  - 真实模式必须同时满足：
    - `--allow-real`
    - `MINIMAX_H3_GRAY_REAL=1`
    - `MINIMAX_H3_GRAY_CONFIRM=CONFIRM_MINIMAX_H3_SUBMIT`
    - `MINIMAX_H3_GRAY_WHITELIST` 精确包含 `book_id:episode:shot_id`
    - 当前视频模型或显式模型 profile 为 `minimax-h3-async`
    - MiniMax API Key / base URL 已配置
  - 真实模式走正式后端接口：
    - 先登记 `machine_prompt_api_submission`
    - 再调用确认式 provider submit
    - 最后读取 task 状态与视频资产写回结果

- **报告输出**
  - 输出 `artifacts/minimax-h3-gray-*.json|md`。
  - 报告包含 target、H3 prompt 预览、任务模式、首帧、provider readiness、blockers、warnings、真实运行门禁和 PowerShell SOP。
  - 支持 `npm run validate:minimax-h3-gray -- auto` 自动选择候选镜头：优先外部 URL 首帧、无既有视频、无高风险动作，并把遗留导演标记 / 灰度安全风险写入报告。

### 验证结果

- `npm run validate:minimax-h3-gray -- 75 1 1`：通过；输出 dry-run 报告后已清理 artifacts。
- `npm run validate:minimax-h3-gray -- auto`：通过；自动候选当前选择 `book 14 / episode 1 / shot 1`，未触发真实提交。2026-08-28 已补机器提示词导演口令清洗后，自动候选报告的 prompt warning 已清空，剩余 blocker 为视频 profile 尚未切换到 `minimax-h3-async`。

---

## 2026-08-27 — 机器提示词二段式 MiniMax H3 真实提交链路

> 对应分支：`codex/unify-formal-workspace`
> 背景：MiniMax H3 adapter 第一阶段已经具备 v2 create/query 与轮询回收能力，但机器提示词 API 提交仍停留在“登记意图”。本轮把该链路升级为二段式：先登记，再由用户显式确认后真实提交 H3。

### 变更概览

- **新增确认式真实提交接口**
  - 新增 `POST /api/prototyping/tasks/{task_id}/submit-machine-prompt-provider`。
  - 仅允许 `generation_chain=machine_prompt_api_submission` 的任务进入该接口。
  - 必须传入确认口令 `CONFIRM_MINIMAX_H3_SUBMIT`，否则拒绝提交。
  - 真实提交仅允许使用 `minimax-h3-async` 视频模型；默认 mock 或其他 provider 会被拒绝。

- **机器提示词到视频资产回写**
  - 从导出快照中抽取 MiniMax H3 `integrated_multimodal_description` 作为真实视频 prompt。
  - 若当前镜头存在采纳首帧，优先走 H3 首帧图生视频；否则走文生视频。
  - 提交后任务保留 `kind=machine_prompt_api_submission`，同时升级 `target_kind=video`、`actual_provider_submission=true`。
  - provider 返回视频 URL 后复用现有视频资产写回链路，记录 `externalTaskId / providerRequestPayload / providerResponse`。

- **正式工作台二段式按钮**
  - 导出高级区保留“登记 API 提交任务”。
  - 新增“真实提交 H3”按钮，点击后需要浏览器二次确认。
  - 任务中心文案从“等待适配器接入”更新为“已登记，需二次确认才真实提交”或“已真实提交，等待回收”。

### 验证结果

- `python -m unittest tests.test_storyboard_prompt_compile.StoryboardPromptCompileTests.test_machine_prompt_provider_submit_requires_confirmation_token tests.test_storyboard_prompt_compile.StoryboardPromptCompileTests.test_machine_prompt_provider_submit_sends_h3_prompt_and_writes_video_asset`：通过
- `npm --prefix web test -- productWorkspaceTaskCenterData.test.ts ProductWorkspaceStoryboardRepairActions.test.tsx`：`16 passed`
- `npm run e2e:machine-prompt-export`：通过；仅验证导出与登记，不触发真实 H3
- `npm run check:production`：通过；93 个 Python 测试、前端 build、五项目 113 镜 `0 error / 0 warning`

---

## 2026-08-27 — MiniMax H3 异步视频适配层第一阶段

> 对应分支：`codex/unify-formal-workspace`
> 背景：机器提示词链路已经能导出 MiniMax H3 WebUI 字段并登记 API 提交任务；下一步需要让后端正式具备 H3 v2 create/query 的 provider adapter，但不能默认触发真实扣费任务。

### 变更概览

- **新增 `minimax-h3-async` provider**
  - 模型注册表允许新增 video 能力的 MiniMax H3 异步模型。
  - 默认 base URL 当前建议为 `https://metaso.cn/api/minimax`，模型名为 `MiniMax-H3`。
  - “测试当前草稿”只做配置结构校验，不发起真实视频生成。

- **新增 MiniMax H3 v2 适配器**
  - 创建任务：`POST /v2/video_generation`。
  - 查询任务：`GET /v2/query/video_generation/{task_id}`。
  - 支持文生视频 payload：text + `ratio`。
  - 支持首帧图生视频 payload：text + `image_url` / `role=first_frame`，并按官方约束不发送 `ratio`。
  - 轮询成功后从 `content.url` 等兼容结构提取视频 URL。
  - 任务恢复链路可通过统一 reconcile 继续查询 MiniMax H3 任务。

- **模型管理 UI 同步**
  - 视频供应商列表新增 `minimax-h3-async`。
  - 默认参数建议包含 `resolution=768P`、`duration=5`、`ratio=16:9`、轮询间隔和超时。
  - 页面文案改为“MiniMax H3 可配置，但视频默认不强制切换；真实生成需显式发起”。

### 验证结果

- `python -m unittest tests.test_generation_adapters tests.test_model_registry`：`27 passed`
- `npm --prefix web test -- modelRegistryModal.test.ts productWorkspaceModels.test.ts`：`14 passed`
- `python -m unittest tests.test_storyboard_generation_flow tests.test_poyo_creative_task_state tests.test_task_persistence tests.test_storyboard_prompt_compile`：`36 passed`
- `npm --prefix web run build`：通过

---

## 2026-08-27 — 机器提示词 API 提交任务链第一版

> 对应分支：`codex/unify-formal-workspace`
> 背景：机器提示词导出已经支持 WebUI / Markdown / CSV / API JSON，但“API 提交”必须和普通导出分离，先进入可追踪任务中心，再接真实 provider，避免导出动作被误解为真实外发。

### 变更概览

- **新增 API 提交任务登记**
  - 新增 `POST /api/books/{book_id}/storyboard/{episode}/{shot_id}/machine-prompt-api-submissions`。
  - 将当前机器提示词导出快照登记为 `machine_prompt_api_submission` 创意任务。
  - 第一版只保存提交意图和 payload：`api_submission=true`，但 `actual_provider_submission=false`。
  - provider 状态固定为 `pending-generation-adapter / waiting_for_generation_adapter`，不调用真实模型。

- **正式工作台接入**
  - 机器提示词导出面板新增“登记 API 提交任务”按钮。
  - 成功后提示用户可到任务中心跟踪，不自动离开当前镜头上下文。
  - 任务中心将该任务识别为提示词类任务，并显示“等待真实模型适配器”，不再 fallback 为视频任务。

- **真实浏览器回归扩展**
  - `npm run e2e:machine-prompt-export` 在原有导出闭环基础上新增 API 提交任务登记验证。
  - E2E 会查询 `/api/books/75/creative-tasks?limit=30`，确认任务存在且 `actual_provider_submission=false`。
  - 测试结束自动清理本次新增导出记录和 `mpapi-*` 任务。

### 验证结果

- 后端专项：`python -m unittest tests.test_storyboard_prompt_compile tests.test_production_export_records`，`30 passed`
- 前端专项：`npm --prefix web test -- ProductWorkspaceStoryboardRepairActions.test.tsx ProductWorkspaceDeliverySection.test.tsx productWorkspaceDelivery.test.ts productWorkspaceTaskCenterData.test.ts productWorkspaceTaskCenterState.test.ts productWorkspaceTaskCenterSelectedTaskPanel.test.tsx productWorkspaceTaskCenterDetailPanels.test.tsx`，`39 passed`
- 前端生产构建：`npm --prefix web run build`，通过
- 机器提示词真实浏览器流：`npm run e2e:machine-prompt-export`，通过
- 正式工作台真实业务流：`npm run e2e:business`，通过
- 生产总回归：`npm run check:production`，通过；五项目 113 镜 `0 error / 0 warning`

---

## 2026-08-24 — 补齐正式工作台真浏览器主链路回归

> 对应分支：`codex/unify-formal-workspace`
> 背景：手工真浏览器流程已经证明正式工作台主链路可走通，但固定回归中仍有部分关键动作由 API 代替 UI 操作，无法完全防住真实用户路径退化。

### 变更概览

- **强化 `npm run e2e:business` 真浏览器主链路**
  - 改编方向改为通过 UI 选择候选、锁定 Production Skill、锁定项目主方向，并验证后端持久化。
  - QA 修复改为通过 UI 填写修复片段、预览 diff、应用修复并复检、确认回滚。
  - 新增创作画布与模型管理断言，覆盖剧本/分镜/资产/图片/视频/QA/交付图谱，以及 LLM/Embedding/Image/Video 默认模型链路。
  - 继续验证提示词锁定、镜头验收记录保存、资产中心、任务中心、导出中心和旧入口不可见。

- **修复 QA 脚本回滚版本乱码**
  - 回滚版本 label 从损坏文本 `鍥炴粴鍒?` 修正为 `回滚到`。
  - 后端测试与真浏览器 E2E 均新增“不出现乱码”的断言。

### 验证结果

- `python -m unittest tests.test_qa_workbench_flow`：`14 passed`
- `node --check scripts/e2e-formal-workspace-business-flow.js`：通过
- `npm run e2e:business`：通过

---

## 2026-08-22 — 生产级推进：旧执行层前端残留清理

> 对应分支：`codex/unify-formal-workspace`
> 背景：单一正式工作台收敛后，前端仍残留旧 DevCanvas/节点执行层组件，虽然已经不可达，但会继续放大维护面并误导后续开发。

### 变更概览

- **删除不可达旧前端组件**
  - 删除 `AgentNode`、`HistorySidebar`、`PromptSelector`、`ResultsPanel`、`pipelineLayout` 和 `types/nodes`。
  - 删除前复核当前 `web/src` 已无正式工作台 import 依赖。

- **同步当前真实架构**
  - `README.md` 改为项目列表 -> 正式工作台的单入口描述。
  - `ARCHITECTURE.md` 改为 `ProductWorkspace` 架构，标注 `nodes/` 与 `/api/workflows*`、`/api/nodes*`、`/api/runs*` 为 legacy 兼容层。
  - 蓝图、实施方案、阶段任务验收标准同步“禁止重新形成巨型工作台组件”的当前口径。

- **保留后端兼容层**
  - 暂不删除 `/api/workflows*`、`/api/nodes*`、`/api/runs*`。
  - 原因：历史 workflow/run 数据、后端 HTTP 错误测试和 API 兼容策略需要独立迁移/封存决策。

### 验证结果

- 前端单元测试：`221 passed`
- 前端生产构建：通过
- 后端兼容接口专项：`python -m unittest tests.test_api_http_errors`，`6 passed`
- 正式工作台业务 E2E：`npm run e2e:business`，通过

### 后续建议

1. 对 legacy 后端执行层做专项只读化/封存/删除评估。
2. 增加源码守卫，避免正式工作台重新引入旧节点执行层 UI/type。
3. 待创作画布领域接口稳定后，再迁移仍被正式工作台使用的 `/api/prototyping/*` 创意任务兼容接口。

---

## 2026-08-22 — 前端工作台收敛为正式工作台

> 对应分支：`codex/unify-formal-workspace`
> 背景：项目曾同时保留正式工作台、旧版生产、创作沙盘、高级编排和产品原型 Demo，导致真实用户入口分散、维护面过大。经依赖梳理后，本轮按“先补正式能力，再删除旧入口和旧代码”的方式收敛。

### 变更概览

- **正式工作台补齐旧能力**
  - QA 修复页新增人工修复片段、diff 预览、应用修复并复检，以及脚本修复版本回滚。
  - 镜头工作台新增提示词锁定/解除锁定，以及验收记录提交表单。

- **统一前端入口**
  - `CanvasPage` 只渲染正式工作台，不再加载旧版生产、创作沙盘、高级编排。
  - 正式工作台侧栏移除旧工作台跳转按钮。
  - 项目列表移除 `产品原型 Demo` 入口；历史本地 `blueprint-demo` 状态会回到项目列表。

- **清理旧前端实现**
  - 删除旧版生产、ReactFlow 高级编排、创作沙盘、产品原型 Demo 及对应测试。
  - 将正式工作台仍使用的输出归一化、模型注册表和 `useBookOutputs` 迁移到正式目录：
    - `web/src/domain/bookOutputs.ts`
    - `web/src/services/modelRegistry.ts`
    - `web/src/hooks/useBookOutputs.ts`
  - `bookOutputs` 不再依赖旧原型 mock/model 类型。

- **同步蓝图与任务计划**
  - 将《产品重构蓝图》《产品重构实施方案》《产品重构阶段任务与验收标准》《LibTV 化融合重构计划》《生产级上线冲刺清单》统一到单一正式工作台口径。
  - 明确 `创作画布` 是正式工作台内的一级模块，历史 `创作画布 Beta` 表述仅代表当时阶段名称。
  - 将 `/api/workflows*`、`/api/nodes*`、`/api/runs*` 列为下一阶段后端旧执行层审计范围。

### 验证结果

- 前端单元测试：`221 passed`
- 前端生产构建：通过
- `npm run e2e:smoke`：通过
- `npm run e2e:qa`：通过
- 新增并执行 `npm run e2e:business`：通过
  - 使用浏览器从项目列表进入正式工作台，验证旧工作台入口不可见。
  - 覆盖内容准备、剧本工作台、镜头工作台、资产中心、任务中心、导出中心、QA 修复。
  - 验证提示词锁定、验收记录保存、QA diff 预览、应用修复生成脚本版本、脚本回滚恢复原文等业务状态真实落库。
- 后端 QA/分镜相关专项：`28 passed`
- `git diff --check`：通过（仅 Windows 换行提示）

### 后续建议

1. 将 `npm run e2e:business` 纳入后续大改后的固定回归，避免只验证页面可渲染而漏掉真实业务状态流转。
2. 保留本轮仍被正式工作台调用的 `/api/prototyping/*` 后端接口，下一阶段再专项审计 `/api/workflows*`、`/api/nodes*`、`/api/runs*` 与旧执行层。
3. 不删除历史 workflow/run/task 数据，只处理不可达前端代码。

---

## 2026-08-21 — 视觉资产接口测试基线修复

> 对应提交：本提交 `Restore visual assets GET endpoint`
> 背景：上一轮长任务持久化提交后，完整后端测试仍暴露 `tests.test_visual_asset_library` 失败。专项排查确认不是测试 fixture 缺失，而是 `GET /api/books/{book_id}/visual-assets` 未注册为 FastAPI 路由，导致真实 HTTP 调用返回 404。

### 变更概览

- **恢复视觉资产读取接口**
  - 将既有 `get_visual_assets(book_id)` 函数重新挂载为 `GET /api/books/{book_id}/visual-assets`。
  - 保留原有序列化逻辑：场景、道具、角色妆造、参考图与 storyboard 绑定归一化输出均不变。

### 验证结果

- 视觉资产专项回归：`18 passed`
- 后端聚焦回归：`37 passed`
- 前端单元测试：`304 passed`
- `npm run e2e:smoke`：通过
- `npm run e2e:qa`：通过
- 前端生产构建：通过
- `git diff --check`：通过（仅 Windows 换行提示）

### 后续建议

1. 在 API 路由层增加轻量清单测试，避免“函数存在但路由未注册”的回归再次悄悄出现。
2. 将 visual setup task 与 storyboard prompt compile task 纳入统一任务表。
3. 为 `task_runs` 增加 TTL/归档清理策略。

---

## 2026-08-21 — 长任务状态持久化底座

> 对应提交：本提交 `Persist production task run states`
> 背景：继续按全面复盘结论推进生产硬化，先解决 pipeline、storyboard、creative task 纯内存状态导致的刷新/重启后不可恢复问题。

### 变更概览

- **持久化任务表**
  - 新增 `TaskRun` 模型与 `task_runs` 表。
  - 新增 Alembic 迁移 `d4e5f6a7b8c9_add_persistent_task_runs.py`，并将历史双 head 收敛为单 head。
  - 记录 `task_id / task_kind / status / progress / book_id / episode / payload / error / timestamps`。

- **任务状态写入与恢复**
  - `script pipeline` 创建、进度更新、完成、异常时写入 `task_runs`。
  - `storyboard pipeline` 创建、分集进度、partial/done/error 收口时写入 `task_runs`。
  - `creative image/video/reference-image task` 通过 `_stamp_creative_task_state()` 统一写入 `task_runs`。
  - 查询 pipeline/storyboard/creative task 时，若内存 dict miss，会从 DB 恢复并回填内存缓存。
  - `creative-tasks` 项目列表接口合并 DB 历史任务与当前内存任务，并优先显示当前进程内最新状态。

- **用户可见恢复文案**
  - 分镜失败/断点恢复提示改回干净中文，去除旧测试中暴露的乱码期望风险。

### 新增/更新测试

- 新增 `tests/test_task_persistence.py`，覆盖：
  - pipeline task 内存 miss 后从 DB 恢复。
  - storyboard task 内存 miss 后从 DB 恢复。
  - creative task 内存 miss 后从 DB 恢复并出现在项目任务列表。

### 验证结果

- 任务/长链路相关后端回归：`36 passed`
- `npm run e2e:smoke`：通过
- `npm run e2e:qa`：通过
- 前端单元测试：`304 passed`
- 前端生产构建：通过

### 当前发现的既有问题

- `python -m unittest discover tests` 当前仍会在 `tests.test_visual_asset_library` 出现多项失败，主要表现为 visual assets endpoint 返回 404 或 payload 缺少 `locations`。
- 该问题单独运行 `python -m unittest tests.test_visual_asset_library` 也复现，判断为既有 visual asset 测试/接口状态脱节；本轮未扩大范围修复。

### 仍建议后续推进

1. 为 `task_runs` 增加 TTL/归档清理策略。
2. 将 visual setup task 与 storyboard prompt compile task 也纳入统一任务表。
3. 专项修复 `tests.test_visual_asset_library` 对应的视觉资产接口回归问题。

---

## 2026-08-21 — 生产安全边界与 QA 修复 E2E 加固

> 对应提交：本提交 `Harden API safety boundaries and QA repair E2E`
> 背景：按全面复盘结论，优先补齐上线前必须具备的 API 安全边界、健康检查和高风险 QA 写入链路真实流程验证。

### 变更概览

- **API 安全边界**
  - CORS 从 `* + credentials` 改为环境变量驱动的本地前端白名单。
  - 新增 `API_CORS_ORIGINS / API_CORS_ALLOW_CREDENTIALS` 配置，保留部署时覆盖能力。
  - 新增 `/health` 健康检查端点。

- **上传安全**
  - `/api/upload` 增加安全文件名清洗，阻断路径穿越。
  - 默认仅允许 `.txt / .md / .markdown`。
  - 新增 `UPLOAD_MAX_BYTES / UPLOAD_ALLOWED_EXTENSIONS / UPLOAD_DIR` 配置。
  - 上传文件为空、超限、扩展名不支持时返回明确 HTTP 错误。

- **真实流程 E2E**
  - 新增 `npm run e2e:qa`。
  - 新增 `scripts/e2e-qa-workbench.js`，自动创建临时 QA fixture 项目，真实浏览器打开 QA 修复页，并执行：
    - issue 同步
    - 修复预览 diff
    - 应用修复生成版本
    - 回滚版本
    - 清理临时 fixture
  - `e2e:smoke / e2e:qa` 的 Vite 启动增加 `--strictPort`，避免端口冲突时误连到漂移端口。

### 新增/更新测试

- 新增后端安全测试：`tests/test_api_security.py`
- 新增 E2E：`scripts/e2e-qa-workbench.js`

### 验证结果

- 后端聚焦回归：`26 passed`
- `npm run e2e:smoke`：通过
- `npm run e2e:qa`：通过
- 前端单元测试：`304 passed`
- 前端生产构建：通过

### 仍建议后续推进

1. 将 `_pipeline_tasks / _storyboard_tasks / _creative_tasks` 从纯内存状态升级为 DB 持久化任务表。
2. 补全 API 认证/授权策略；当前仅完成 CORS 与上传安全边界。
3. 给上传后的导入链路增加更完整的端到端 fixture，覆盖“上传 -> 导入 -> 内容准备状态恢复”。

---

## 2026-08-21 — 生产工作区 E2E Smoke 测试固化

> 对应提交：本提交 `Add production workspace E2E smoke test`
> 背景：将上一阶段人工执行的真实用户流程验证沉淀为可重复运行的自动化 smoke test，降低后续 agent/人工迭代破坏主工作区流程的风险。

### 变更概览

- 根目录新增 `npm run e2e:smoke`。
- 新增 `scripts/e2e-smoke.js`，自动拉起后端与 Vite 前端，并通过 Playwright Chromium 执行真实浏览器流程。
- 自动选择本地数据库中更适合 smoke 的项目，优先选择已有剧本与分镜数据的项目。
- 覆盖首页项目列表、进入正式产品工作区、核心工作区 tab 切换、章节详情懒加载、QA 修复页加载。
- 捕获浏览器端 4xx/5xx 响应、console error/warning 与 page error，作为 smoke 失败条件。
- 支持 `E2E_START_SERVERS=0` 复用已运行服务，支持 `E2E_API_URL / E2E_WEB_URL / E2E_HEADLESS` 覆盖默认配置。

### 验证结果

- `npm run e2e:smoke`：通过。

---

## 2026-08-21 — 生产链路护栏与 Prompt 编译稳定化

> 对应提交：`69b272e Stabilize production pipeline guardrails and prompt compilation`
> 背景：复核上一版由其他 agent 新增的短剧库、约束引擎、人物质检与前端工作台增强后，修复其中的生产风险，并补齐关键回归测试与真实用户流程验证。

### 变更概览

- **生产安全护栏**
  - 别名解析的 `pending_confirm` 不再自动合并中置信候选，只记录为人工确认项。
  - 人物画像 QA 合并候选需要更强身份依据；角色合并新增性别冲突拒绝。
  - 人物合并前端增加确认弹窗，并兼容 FastAPI `detail` 错误返回。

- **约束与校验链路**
  - 空 `enum / pattern / min_length` 不再误判通过。
  - 开场/结尾规则改为场景级校验，避免每个镜头都错误套用。
  - 分镜 validator 去重场景级违规。
  - 新增 `core/validators/shadow_validation.py`，在分镜生成后以 shadow mode 记录违规，不阻断、不修复、不改写产物。
  - `violation_logger` 新增同事务写入能力，供 shadow validation 安全落库。

- **Prompt IR 与分镜编译**
  - 分镜 prompt compile 会把规则编译后的 `ShotIR` 序列化进入版本 metadata。
  - `duration / camera_angle / camera_movement / transition / shot_purpose / camera_speed` 等字段写回结构化镜头与 DB。
  - 异步 prompt compile 从手写线程切换为 FastAPI `BackgroundTasks`。

- **剧本改写安全**
  - `RewriteAgent.run_perfect()` 会捕获初始最佳剧本快照。
  - QA 分数回退时恢复 DB 中的最佳剧本内容，并写出 `episode_XX_script_best.md`。
  - 台词精修不再截断前 8000 字；新增长剧本截断/场景缺失保护。

- **Bible QA 修复**
  - Bible 生成后 QA 现在校验刚生成的新文档，而不是旧 DB Bible。
  - Bible QA 自动修复限定在目标人物标题段落内，并使用精确标题匹配，避免误改同名前缀人物。

- **API 与前端产品体验**
  - 章节列表接口不再返回正文，单章详情懒加载正文。
  - 章节、人物、任务、workflow、prompt、book/outline/script 更新等错误返回统一改为 `HTTPException`。
  - 修复 QA 工作台真实流程 500：中文关键词正则改为稳定 Unicode 范围。
  - 分镜生成前端 payload 不再硬编码 `[1]`，改为按目标集数生成 `[1..episodeCount]`。
  - ProductWorkspace section 改为 `React.lazy + Suspense`，生产构建不再出现 >500k chunk 警告。

### 新增/更新测试

- 新增后端回归：
  - `tests/test_api_http_errors.py`
  - `tests/test_bible_agent.py`
  - `tests/test_chapter_api.py`
  - `tests/test_p0_guardrails.py`
  - `tests/test_shadow_validation.py`
- 更新后端回归：
  - `tests/test_rewrite_agent.py`
  - `tests/test_storyboard_prompt_compile.py`
- 新增前端回归：
  - `web/src/components/ProductWorkspace.test.ts`

### 验证结果

- 后端聚焦回归：`79 passed`
- 前端单元测试：`304 passed`
- 前端生产构建：通过，无大 chunk 警告
- `git diff --check`：通过（仅 Windows CRLF 提示）
- 真实用户流程测试：
  - 首页项目列表加载正常。
  - 进入 `深夜便利店 #75` 正常。
  - 内容准备、人物质检、剧本工作台、镜头工作台、资产中心、QA 修复、任务中心、导出中心均可真实点击加载。
  - 章节正文懒加载通过。
  - 测试中发现并修复 `/api/books/75/qa/workbench` 500。

### 仍建议后续推进

1. 将 shadow validation 从 storyboard 扩展到更多生产链路。
2. 为 QA workbench 增加更完整 E2E：预览修复 → 应用修复 → 复检 → 回滚。
3. 给可运行的空分镜项目准备专用 E2E fixture，真实覆盖批量分镜生成按钮与多集 payload。

---

> 最近一次版本（基于 commit `1e2367d init: screenplay-agent-refactor-v2 初始提交`）以来的所有功能改动。
> 编写时间：2026-08-20
> 适用对象：接手开发的同事

---

## 一、变更概览

| 类别 | 文件数 | 新增行数 | 说明 |
|------|--------|----------|------|
| Agent 层 | 7 | +1,292 | 读取、圣经、改写、编剧、人物质检等 |
| API 层 | 1 | +435 | 新增 6 个角色管理端点 |
| Core 库 | 5+11 新 | +696/+3,000+ | 短剧库、约束引擎、校验器、别名解析增强 |
| 前端 | 11 改+2 新 | +154/+486 | 人物质检面板、章节查看器、一键生成按钮 |
| Prompt | 3 | +187 | 别名解析增强、分镜提示词增强 |
| 合计 | 60+ 文件 | ~7,300+ 行 | |

---

## 二、核心功能改动详解

### 2.1 短剧专用库系统 (`core/short_drama_library.py`)

**新增文件，519 行。** 提供 10 个结构化知识库，注入到所有 LLM prompt 中：

| 库名 | 说明 |
|------|------|
| `EPISODE_BEAT_ENGINE` | 5 拍节拍引擎：hook → setup → friction → spike → button |
| `EPISODE_EMOTION_NODES` | 8 个情绪时间节点 |
| `HOOK_LIBRARY` | 4 类钩子：开场钩/片尾钩/中段钩/系列钩 |
| `SHORT_DRAMA_CONFLICT_PATTERNS` | 8 种冲突模式：身份反转、公开羞辱、复仇重生等 |
| `SHORT_DRAMA_DIALOGUE_RULES` | 黄金法则 + 6 种台词类型 + 禁忌模式 |
| `SHORT_DRAMA_VISUAL_GRAMMAR` | 构图、镜头时长、表情优先级、AI 一致性 |
| `SHORT_DRAMA_PACING_TEMPLATES` | 4 种节奏模板：60s/90s/120s/180s |
| `SERIES_ARCHITECTURE_LIBRARY` | 按阶段的剧集结构 |
| `COMMON_PITFALLS` | 8 个致命陷阱及修复方案 |
| `EMOTION_CHECKPOINT_LIBRARY` | 5 种情绪检查点：虐/满足/甜/燃/悬疑 |

**用途：** 在 `api/server.py` 的 `_build_prompt_compiler_diagnostics()` 中注入到分镜 prompt。

### 2.2 约束引擎 (`core/constraint_engine.py`)

**新增文件，664 行。** 自动生成 + 注册 + 校验约束规则：

- 7 个自动生成器：镜头运动、情绪、镜头目的、速度、时长、短剧规则、格式
- `ConstraintRegistry`：约束注册表，支持按 ID 查询
- `ConstraintValidator`：校验器，支持 Levenshtein 模糊匹配修复枚举值
- `Violation` 数据结构：记录违规字段、严重级别、修复策略

### 2.3 校验器体系 (`core/validators/`)

**新增 7 个文件，~1,000 行：**

| 文件 | 功能 |
|------|------|
| `programmatic_repair.py` | 确定性修复引擎：枚举模糊匹配、范围钳位、禁忌值替换 |
| `screenplay_validator.py` | 剧本校验：冲突类型枚举、台词长度、场景结构、致命陷阱、钩子检查 |
| `storyboard_validator.py` | 分镜校验：镜头级约束、场景级检查（开场必须是钩子、结尾必须有悬念） |
| `prompt_validator.py` | 提示词校验：术语一致性、情绪动作、短剧节奏元素 |
| `violation_logger.py` | 违规日志：持久化到 `AgentViolationLog` 表 |
| `violation_repair_orchestrator.py` | 修复调度器：3 级调度（程序化 → 混合 → LLM），重校验循环 |

### 2.4 人物画像质检 (`core/portrait_qa.py`)

**新增文件，322 行。** 解决「一人多角」「性别混乱」问题：

**5 项检测：**
1. **性别缺失**：gender 为空或"人物"
2. **孤立 profile**：仅出场 1 章、无关系链接、无外貌描述
3. **疑似重复**：外貌相似度 > 30% + 章节互补（无重叠）
4. **性别冲突**：同一 canonical 下 gender 不一致
5. **合并操作**：`merge_characters()` 合并 aliases、fragments、stages

### 2.5 别名解析增强 (`core/alias_resolver.py`)

**修改文件，+91 行。** 关键改动：

1. **新增跨章数据聚合**（91-111 行）：从所有章节收集 `appearance_fragments` 和 `relationships`
2. **Prompt 增强**（201-273 行）：每个角色现在传入 gender、外貌片段（去重，最多 8 条）、人物关系（最多 6 条）
3. **输出格式扩展**：LLM 现在返回 `pending_confirm`（中置信度合并）和 `gender_conflicts`
4. **中置信度合并处理**（133-149 行）：自动加入合并组但标记「需确认」

**对应 Prompt 改动** (`prompts/alias_resolve.txt`)：
- 新增「外貌比对规则」「关系网络规则」「性别一致性规则」
- 输出格式增加 `pending_confirm` 和 `gender_conflicts`

### 2.6 剧本生成增强 (`agents/scriptwriter.py`)

**修改文件，+547 行。** 关键改动：

- **逐场景生成** (`_generate_scenes_sequentially`)：将剧本拆分为场景依次生成
- **场景状态传递** (`SceneState`)：场景间传递角色状态、道具状态
- **场景完成校验** (`_validate_scene_completion`)：确保每个场景结构完整
- **场景结尾续写** (`_continue_scene_ending`)：处理跨场景续写
- **结构化编译** (`_compile_with_structure`)：使用结构化生成框架

### 2.7 改写增强 (`agents/rewrite.py`)

**修改文件，+227 行。**

- **回归保护** (`_calculate_similarity`)：基于字符 n-gram 的相似度计算，防止改写偏离
- **多轮改写** (`run_perfect`)：目标 QA 评分 9+ 的迭代改写
- **台词精炼** (`_refine_dialogue`)：专门优化对话质量

### 2.8 结构化场景状态 (`core/production_skill.py`)

**修改文件，+519 行。**

- **CharacterState / PropState / SceneState** 数据结构：结构化传递场景状态
- **性格行为护栏**：内向/神秘/疲惫/古怪性格的行为约束
- **性别推断**：从名字后缀推断角色性别
- **大纲状态推断**：可见/隐藏/过渡状态

### 2.9 修复集成 (`core/repair/integration.py`)

**修改文件，+84 行。** 原为 no-op 的 `apply_structural_repair_directives()` 现已实现：

- `CONSTRAINT_FIX`：场景开头/结尾修复
- `PROP_FIX`：道具修复
- `CHARACTER_FIX`：角色修复

---

## 三、新增 API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| `GET` | `/api/books/{id}/chapters` | 章节列表（含原文） |
| `GET` | `/api/books/{id}/chapters/{ch_id}` | 单章详情 |
| `GET` | `/api/books/{id}/characters` | 角色列表 |
| `GET` | `/api/books/{id}/characters/qa` | 人物画像质检报告 |
| `POST` | `/api/books/{id}/characters/merge` | 合并两个角色 |
| `POST` | `/api/books/{id}/characters/resolve-aliases` | 重新归并别名 |
| `PATCH` | `/api/books/{id}/characters/{ch_id}` | 修改角色属性 |
| `GET` | `/api/books/{id}/characters/{ch_id}/appearance` | 外貌片段详情 |

---

## 四、新增前端组件

### 4.1 CharacterQAPanel (`web/src/components/CharacterQAPanel.tsx`)

**新增文件，344 行。** 侧边栏「人物质检」入口：

- 显示所有角色列表（性别、身份、aliases）
- 性别冲突列表 → 用户选择正确性别
- 疑似重复角色 → 用户点击「合并」
- 「重新归并别名」按钮 → 触发 alias resolver
- 「重新检测」按钮 → 刷新 QA 报告

### 4.2 ChapterViewer (`web/src/components/ChapterViewer.tsx`)

**新增文件，142 行。** 集成在「内容准备」section 底部：

- 章节标签切换
- 原文阅读器（serif 字体，60vh 高度滚动）
- 章节摘要展示
- 前后翻页导航

### 4.3 一键生成按钮

**修改 `ProductWorkspaceScriptsSection.tsx` + `ProductWorkspaceStoryboardSection.tsx`：**

- 剧本工作台空状态显示「一键生成剧本」按钮
- 镜头工作台空状态显示「一键生成分镜」按钮
- 按钮触发后台管线任务，带 loading 状态

---

## 五、管线流程改动

在 `api/server.py` 的 `run_script_pipeline()` 中：

1. **Portrait 前自动运行别名归并**：`resolve_aliases(book_id, session)`
2. **Portrait 后自动运行质检**：`run_portrait_qa(book_id, s)`
3. 性别冲突和高置信度合并候选作为 warning 输出到前端

---

## 六、数据库改动

### 新增表

```sql
-- 违规日志表 (models/violation_log.py)
CREATE TABLE agent_violation_logs (
    id INTEGER PRIMARY KEY,
    agent_type VARCHAR(50),     -- 'storyboard', 'screenplay', 'prompt'
    book_id INTEGER,
    episode INTEGER,
    violation_id VARCHAR(100),  -- 约束 ID
    field VARCHAR(200),         -- 违规字段路径
    severity VARCHAR(20),       -- 'error', 'warning', 'info'
    repair_strategy VARCHAR(50),-- 'programmatic', 'hybrid', 'llm'
    repair_result TEXT,         -- JSON 修复结果
    regression BOOLEAN DEFAULT 0,
    created_at DATETIME
);
```

### 无 schema 变更

所有现有表结构不变。新功能使用已有字段或 JSON 字段存储。

---

## 七、配置改动

| 文件 | 改动 |
|------|------|
| `config.py` | `LLM_MAX_TOKENS` 从 8192 → 24000 |
| `web/vite.config.ts` | API proxy 目标端口从 18765 → 8765 |

---

## 八、已知问题

### 需要修复（生产就绪前）

| 严重度 | 问题 | 位置 |
|--------|------|------|
| CRITICAL | CORS 允许所有来源 | `server.py:49-55` |
| CRITICAL | 无认证/授权 | 全局 |
| CRITICAL | 文件上传路径穿越 | `server.py:562` |
| CRITICAL | 无文件类型/大小限制 | `server.py:554-565` |
| 已修复 | `return {...}, 404` 实际返回 200 | 已在 `69b272e` 统一改为 `HTTPException` |
| HIGH | 无外键约束 | 所有 model |
| HIGH | 无数据库索引 | `book_id` 查询 |
| MEDIUM | 内存任务状态无 TTL | `_pipeline_tasks` 等 |
| MEDIUM | SQLite 并发写入限制 | 生产环境瓶颈 |

### 功能待完善

1. 分镜尚未集成约束引擎的完整校验循环
2. 别名解析器对「完全不同的名字但同一人」的场景识别能力有限
3. 人物画像 stage 分割未触发（需要角色出场 ≥5 章 + ≥3 条外貌片段）
4. 前端无全局 ErrorBoundary
5. 无 `/health` 健康检查端点

---

## 九、测试文件

根目录有 15+ 个 `test_*.py` 文件，为集成/验收测试。`tests/` 目录有 46 个单元测试文件。

**注意：** 根目录的测试文件是临时测试脚本，不是正式测试套件。部分文件（如 `check_scripts.py`、`verify_buttons.py`）可以在确认不需要后删除。

---

## 十、环境依赖

- **LLM API**：mimo-v2.5 (`https://api.xiaomimimo.com/v1`)，通过 model registry 配置
- **本地 Ollama**：`http://10.126.126.2:11434`（deepseek-r1:14b, gemma4:12b, nomic-embed-text）
- **数据库**：SQLite (`work/db/screenplay.db`)
- **向量库**：ChromaDB（内嵌）
- **前端**：React 18 + TypeScript + Vite

---

## 十一、关键文件速查

| 需要了解 | 文件 |
|----------|------|
| 管线主入口 | `api/server.py:868` (`run_script_pipeline`) |
| 短剧知识库 | `core/short_drama_library.py` |
| 约束引擎 | `core/constraint_engine.py` |
| 校验器 | `core/validators/` (7 个文件) |
| 人物质检 | `core/portrait_qa.py` |
| 别名解析 | `core/alias_resolver.py` |
| 提示词模板 | `prompts/` 目录 |
| 前端入口 | `web/src/App.tsx` |
| 前端工作区 | `web/src/components/ProductWorkspace.tsx` |
| 角色 API | `api/server.py:8194` (characters endpoints) |
# Unreleased

- 修复 MiniMax H3 灰度预检自动候选范围：未显式传入项目时仅使用 `production-sample-registry.json` 的 active 样本，禁止从数据库扫描退休/临时测试项目；新增候选范围回归测试。当前只读预检会正确选中 `990400`，参考图不可公网访问时仍 fail-closed，不触发供应商调用。
- 真浏览器真实样本回归同步收口到 active 样本注册表；有注册表时不再从数据库自动补入未注册项目。当前 `npm run e2e:real-samples` 仅巡检 `990400`，10 个正式工作台模块通过且无业务写入。
- 将 `audit:storyboard:zero-error-gate` 的默认最小抽检量从隐藏的 100 调整为任务计划要求的 30 个真实镜头，并保留环境变量升档能力；当前 3 镜头仍会明确失败并生成报告。

- 2026-09-12：经用户确认，将 `990400 / 第1集 / 镜头1–3` 的真实 `mimo-v2.5` clone-only 灰度候选通过源项目 DecisionPacket 证据指纹校验后写入正式 Prompt Version v4；每镜创建 `state_snapshot` 回滚基线，未生成图片/视频。
- 修复已确认 Prompt 草案的只读诊断在确认后误报 409 的问题：确认导致的提示词字段变化现在可安全复核；若导演分镜、镜头事实或资产绑定在确认后被修改，仍严格按过期证据拒绝。新增回归测试覆盖两条路径。
- 本轮验证：后端 `599 passed`、Golden `5/5`、前端生产构建通过；真浏览器正式工作台 `990400` 10 模块通过，无控制台错误或业务写入。

- 新增镜头媒体预检接口，并接入正式工作台真实 H3 提交前置检查：提交前先验证模型能力、参考图可访问性和临时对象存储 URL 风险；预检只读，不上传、不调用 provider、不创建任务。990400 灰度样本因使用 `example.com` 占位参考图被正确阻断。

- 完成生产回归终态确认：`npm run check:production` 通过（102 个后端回归、前端生产构建、5 项目 122 镜头审计 `0 error / 0 warning`）。
- 真实浏览器回归通过：正式业务闭环、`book 75` 机器提示词导出闭环，以及 `book 14 / 5 / 75 / 3 / 1` 的正式工作台巡检。
- 为 `book 14 / episode 1` 的可拍性超载镜头 2、3、5、7 保存通用 N 段拆镜草案；仅写入待审阅草案，不改写镜头结构、不生成媒体。
- 生产修复计划的资产风险已改为具体、可审阅的人工动作；正式工作台体检卡同步展示，并明确不会自动锁定或猜测权威参考图。
- 新增 GitHub Actions 生产回归门禁，并补齐后端服务运行时依赖声明；CI 不会调用真实外部模型。
- 旧 DevCanvas 节点 API 可通过 `ENABLE_LEGACY_NODE_API=false` 在生产环境统一禁用，正式工作台不受影响。
- 对象存储迁移规划新增确认令牌和只读审计元数据，为受保护迁移执行器建立前置边界。

- 新增只读生产修复计划 API：`GET /api/books/{book_id}/production-readiness/repair-plan`，汇总 blocked/warning 镜头与资产风险，区分可重编译动作和需要人工确认的动作；不修改真实数据。
- 正式镜头工作台体检卡支持直接定位优先 blocked 镜头。
- 经用户确认，完成 `book 75` 首批 7 个可重编译镜头真实批量重编译；任务 `9c192305ce6a` 全部成功，生成新 Prompt Version，未触碰 6 个 blocked 镜头。
- 经用户确认，按倒序应用 `book 75` 6 个拆镜草案，15 镜增至 21 镜；拆分后的新镜头均要求重新编译，当前 executability 无 blocked。

- QA 局部修订合同新增场景位置校验：`场景N开头/末尾/结尾` 与实际行区间不匹配时，一律降级为不可写入的策略草案，避免把受限候选拼接到同场景的错误剧情节拍。
- 全新回归样本 `book 990309` 的草案只读 diff 审查已完成；发现两条“场景 2 末尾”报告的行号实为场景前段，候选未应用，且无剧本、版本或生成任务被修改。
# Unreleased

- 智能导演台模型配置拆分为两层：模型管理只维护供应商与客观能力事实；Agent 设置独立维护思考开关与图片读取策略。
- Agent 预览与真实调用均遵循双确认；图片只有在模型支持且 Agent 明确允许时才以内存数据发送，策略不会修改正式生产模型。
## 2026-09-10

- MiMo 缓存优化 Phase 2：Agent 草案/对话、资产治理和拆镜调用统一记录安全请求指纹与真实用量遥测；Agent 草案去重现在区分模型参数分支，资产重复请求校验证据与请求身份。
- 新增 `agent_audit_logs.request_fingerprint`、`llm_usage` 数据列及 Alembic 迁移 `c6f7a8b9c0d1`。
- 新增 LLM 入口前缀复用审查文档，明确剧本 QA/改写、Reader、Outline、Scene Setup 的后续统一审计范围。
- 新增 `GET /api/agent/usage-summary` 与抽屉累计用量展示；缓存不可观测时明确显示，不伪造命中率。
- 完成用户确认后的两次 MiMo 前缀缓存真实灰度：2 次 HTTP 200，供应商返回累计 2240 缓存 Token / 4526 输入 Token，命中率 49.4918%；报告写入 `artifacts/mimo-prefix-cache-gray-20260910.*`。
## 2026-09-12

- 新增确定性的 `Shot Intent Plan` 与 `Action Timing Plan`：从已声明镜头事实生成可审阅意图和毫秒动作时间线，显式报告缺失信息与时长冲突，不调用 LLM、不猜测、不改写镜头。
- 规划结果接入 `ShotIR` 序列化，新增专项回归覆盖等比分配、显式时长、超配冲突和缺失证据。
- 编译器在采用 LLM 节拍后重新生成规划结果，镜头工作台对信息不足/时长冲突显示可读的下一步入口。
- 新增 `audit:shot-planning:gate` 数量门禁：active 真实镜头不足 30 个时只写回报告并以非零退出，禁止把不足样本误判为上线通过。
