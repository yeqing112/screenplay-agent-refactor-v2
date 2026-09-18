# Frontend Authority Truth Closure

日期：2026-09-18  
分支：`codex/shot-plan-authority-contract`  
范围：Production 前端唯一 authority 投影、失败闭环、生成按钮门控、Task Center 来源分类。Provider calls：`0`。

## 1. Dashboard authority closure

- `ProductionWorkspaceSnapshot` 是 Production Dashboard 的唯一 readiness 来源。
- 旧 `dashboardActions` 只在没有 Production load-state（兼容 creative/legacy 页面）时显示。
- projection ready 且 `next_actions=[]` 时显示“当前没有待处理的生产阻塞”，不会退回旧 CTA。
- `episodeProgress` 仅在兼容模式显示；Production 使用 `episodes[].overall_state / overall_progress / blockers / stages`。

## 2. Projection failure fail-closed

- `useProductionWorkspace` 新增 `loading | ready | unavailable`。
- HTTP 错误、超时、malformed schema、非 production workflow、`read_only != true`、authority source 不符、`provider_calls != 0` 均进入 `unavailable`。
- unavailable 时清空旧 snapshot，Dashboard / Shot / Asset / Task 显示“生产状态暂不可用”，不使用 legacy readiness；重试仍通过现有刷新入口。
- 未知 authority state 显示“待确认”，不会被视为生产 ready。

## 3. Task Center origin model

新增 `TaskOrigin`：

- `AUTHORITY_WORKFLOW`：只来自生产投影 blockers/next actions
- `RUNTIME`：真实上传或运行任务
- `RECOVERY`：任务恢复与回收
- `AGENT_RUNTIME`：智能导演台运行记录
- `LEGACY_HEURISTIC`：兼容历史，仅不进入 Production workflow

Production Task Center 只合并前四类；列表明确显示来源标签，例如“来源：权威工作流”。旧 heuristic 任务保留在代码中供兼容模式使用，不参与 Production 状态。

## 4. Shot / Asset authority gate

- Shot Workspace 的分镜图、视频和后续生产动作在 Production 下必须同时满足：projection ready、当前 shot 存在、PromptIR 为 accepted state、reference state 非 blocked/stale/needs_action。
- projection unavailable、shot 不在权威投影、PromptIR stale/unknown 时按钮 disabled；页面明确显示当前权威状态和上游门槛。
- Asset Center 的参考图生成必须命中当前 authority asset，资产状态与 stale 状态通过白名单校验；未知或缺失资产不允许触发生成。
- 资产状态 banner 同样支持 loading/unavailable，避免用户误以为旧资产数据仍可提交。

## 5. Disposable populated fixture

- 后端/默认数据库不写入夹具，不修改 active sample registry。
- fixture 文件：[tests/fixtures/production-workspace-populated/snapshot.json](../tests/fixtures/production-workspace-populated/snapshot.json)
- 前端只在 Vite DEV 且 URL 显式包含 `?workspace_fixture=populated` 时加载 fixture，并注入两条镜头、一个人物、一个场景、一个道具；默认 URL 完全不启用。
- 实际浏览器验收使用 Codex IAB：
  - Dashboard：`/?workspace_fixture=populated`
  - Shot：`/?workspace_fixture=populated&section=storyboard&episode=1&shot=A`
  - Asset：`/?workspace_fixture=populated&section=assets&episode=1`
  - Task Center：`/?workspace_fixture=populated&section=tasks`
- 已确认可见：Dashboard 62% authority spine、单集 4/10 阶段与权威“参考图待锁定”下一步；Shot 显示镜头 A 的 4 秒/中景/固定、PromptIR 已确认、参考图待处理，主动作指向资产中心且媒体动作未放行；Asset Center 显示人物、场景、道具三类资产及当前版本/影响镜头/参考图状态，生产阻塞时对应生成按钮受门控；Task Center 显示“来源：权威工作流”。截图已在本轮真实浏览器会话中展示。

## 6. Verification

- Frontend tests：`51 files / 301 tests passed`
- Frontend build：`npm run build` passed
- Authority / materializer backend regression：`26 passed, 3 warnings`
- Deterministic Golden regression：`5 fixtures / 5 passed / 0 failed`
- Responsive browser checks：`390px / 1024px / 1440px` 已通过；populated Dashboard、Shot、Asset、Task 页面已在真实浏览器复验。
- Provider calls：`0`
- No LLM, image, video, embedding, object storage call was made.
- No authority table or production business data was added/modified.

## 7. Full backend suite historical failures

本轮全量后端实跑结果为 `1528 passed / 11 failed / 927 warnings`。失败均未触及本轮 Production 前端 authority closure 代码；相关历史测试、数据库样本和 artifact 未被修补、重写或清理：

1. `tests/test_director_quality_v24_offline_replay.py`：测试固定期望旧分支 `codex/unify-formal-workspace`，当前分支为 `codex/shot-plan-authority-contract`。
2. `tests/test_director_quality_v3_fact_coverage_foundation.py`（3 项）：当前工作树已有的 Director Quality V3 authority artifact 缺少旧版 `provider_attempts_by_stage`、`fact_coverage_foundation`、`fact_semantic_grounding` 字段。
3. `tests/test_director_quality_v3_fact_semantic_grounding.py`（2 项）：同一历史 authority artifact 缺少旧版 `phase_a_attempt_1_status` 与 semantic grounding 字段。
4. `tests/test_director_quality_v3_final_spine_topology_preflight_wiring.py`：测试期望 dirty-worktree reason，但当前安全逻辑提前返回 `HISTORICAL_RECANARY_RETIRED`。
5. `tests/test_director_quality_v3_fresh_integration_pilot.py`（2 项）：旧数据库 fixture 期望 6 rows（当前 0），旧 provider pilot 期望 3 provider calls（当前 fail-closed 返回 0）。
6. `tests/test_director_quality_v3_semantic_verifier_canary.py`：历史 authority artifact 缺少旧版 `semantic_verifier_canary` 字段。
7. `tests/test_targeted_missing_fact_api.py`：旧测试期望 read-only extraction 不创建 FactSnapshot，当前既有实现创建 1 条。

这些失败是当前工作树既有历史/环境边界；本轮未扩大或掩盖它们。Production authority/materializer 定向回归、Golden 与前端门禁仍以独立结果为准。

## 8. Known boundary

- 本轮未进入 Provider Canary；fixture 仅验证 UI projection、门控与来源分类，不代表媒体供应商可用性。
- 旧 creative/legacy 页面仍保留原有 heuristic，以兼容历史页面；Production 路径已明确隔离。

## 9. Final As-Built Verification

本报告区分此前的 Baseline Audit 与本轮最终实装验证：Baseline 的主要缺口（Dashboard fallback、episode fallback、Task Center 混合 heuristic、projection 失败继续工作、shot/asset 生成未受 authority gate 控制）均已在本轮修复并由单测、构建及真实浏览器 populated fixture 验收覆盖。

状态：`FRONTEND_AUTHORITY_TRUTH_CLOSURE_READY`
