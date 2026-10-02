# REAL_IMAGE_RESPONSE_PROJECTION_RECONCILE_REPORT

## 状态

`BLOCKED_REAL_IMAGE_RESPONSE_PROJECTION`

本轮先完成 provider-free 门禁，再按批准的预算执行一次真实 IMAGE 初次提交。第 4 次真实 SHAPI IMAGE 调用返回 `GENERATION_EXECUTION_FAILED`，错误为候选未保留完整、可追踪的 Provider response projection。按规则立即停止，没有执行 regenerate（第 5 次调用为 0），VIDEO 保持冻结。

## 调用预算与结果

| 项目 | 结果 |
| --- | --- |
| 历史真实 SHAPI IMAGE 调用 | 3 |
| 本轮新增真实 IMAGE 调用 | 1（初次提交） |
| 本轮 regenerate 调用 | 0 |
| 累计真实 SHAPI IMAGE 调用 | 4 / 6 |
| 真实 VIDEO 调用 | 0 |
| 浏览器直连 SHAPI | 0；SHAPI 仅由后端访问 |
| 真实 LLM 调用 | 0 |
| Book 990400 写入 | 0 |
| 本轮 disposable Book | 990453，已通过 UI 删除 |
| 本轮 Official Media 写入 | 0 |

## Provider-free 门禁

- SHAPI 无上游 `id` 的响应测试通过：`previewUrl`、`uri`、`providerResponse` 存在；`providerRequestId` 与 `providerTaskId` 非空、相等、以 `shapi-response-` 开头；相同响应确定性相同，不同响应不同。
- 上游 `id` 测试通过：精确保留 `provider-real-id-123`。
- 完整 canonical provider-free 链路通过：transport registry → SHAPI adapter → 本地媒体持久化 → `GenerationExecutionRecord` → `MediaCandidateRecord` → 实际 `validate_media_candidate()` → `MediaValidationRecord` / `MediaPromotionRecord`。
- 技术验证、响应 hash 一致性、密钥不进入结果投影、REVIEW_REQUIRED 门禁均通过；没有 Official Media 行。
- Media Authority 错误映射已保留根错误码；重复 builtin Profile id 在后端和前端来源处做了 canonical 去重。

## 真实调用结果

真实浏览器路径在第 4 次调用时收到 HTTP 502。该调用没有建立可审核候选，也没有 Official Media 写入；dispose 流程完成，`orphan_rows=0`、`ambiguous_rows=0`。由于初次真实提交失败，按照本阶段规则不再尝试 regenerate。

provider-free 测试使用当前源代码通过，但已运行的后端进程未在本次源代码修复后重启；真实调用证据因此保留为失败事实，不能推断当前源码已通过真实 Provider 响应投影。后续若继续，必须先重启后端并重新获得人工批准；本轮不再消耗调用预算。

## 校验

- 后端相关 provider-free / canonical 套件：129 passed
- 前端 production build：通过
- Python `compileall`：通过
- Alembic head：`p1q2r3s4t5u6`
- `git diff --check`：通过
- 真实浏览器运行：1 次；初次 IMAGE 调用后安全停止；VIDEO 未启动

## 产物

- Truth Audit：`docs/ui-v3/REAL_IMAGE_RESPONSE_PROJECTION_RECONCILE_TRUTH_AUDIT.json`
- Browser evidence：`output/playwright/real-image-reconcile-final/summary.json`
- Historical staging evidence：`output/playwright/real-image-staging-final8/summary.json`
