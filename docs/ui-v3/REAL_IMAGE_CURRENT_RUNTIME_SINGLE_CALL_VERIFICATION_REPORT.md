# REAL_IMAGE_CURRENT_RUNTIME_SINGLE_CALL_VERIFICATION

## 结论

本轮按 `PHASE_REAL_IMAGE_CURRENT_RUNTIME_SINGLE_CALL_VERIFICATION` 只发起了 1 次新的真实 SHAPI IMAGE 请求。当前运行时确实加载了修复后的代码，真实 IMAGE 已完成 Provider → execution → candidate → technical validation → promotion review 链路，证明当前响应投影修复有效。

最终状态为：

`REAL_IMAGE_INITIAL_GO_REVIEW_NOT_COMPLETED`

真实 Initial 已成功，但本轮浏览器自动化在等待审核候选时使用了与当前工作区投影不一致的 `reviewEligibility` 字段，未能继续点击“批准并继续”；随后按安全清理流程删除了 disposable Book。因此没有把未发生的 Official v1 宣称为成功，也没有再次调用 Provider。

## 调用预算

| 项目 | 结果 |
| --- | --- |
| 历史真实 SHAPI IMAGE 调用 | 4 |
| 本轮授权新增真实 IMAGE 调用 | 1 |
| 本轮实际新增真实 IMAGE 调用 | 1 |
| 累计真实 IMAGE 调用 | 5 / 6 |
| 本轮 regenerate | 0 |
| 本轮 VIDEO | 0 |
| 浏览器直连 SHAPI | 0 |
| Book 990400 写入 | 0 |

本轮预算已耗尽。不得继续使用第 6 次预算，除非获得新的明确批准。

## 当前运行时证据

- 基线：`7f54114f1965cc21473ede8e7166e70192973f7a`
- 后端进程启动时间：`2026-10-03 07:31 Asia/Shanghai`（证据运行前；完成采集后已停止）
- 后端启动时源码提交：`7f54114f1965cc21473ede8e7166e70192973f7a`
- 后端启动配置：`APP_ENV=staging`、`DEPLOYMENT_ENV=staging`、真实 Provider staging gates、`REAL_PROVIDER_STAGING_MAX_CALLS=1`
- 后端启动前只读 Profile：`local-image-mw4y52` / `shapi-openai-images` / `grok-imagine-image-quality` / `shapi-openai-images.image.v1`
- 当前运行时在唯一一次真实请求前 Provider generation posts 为 0。

## 真实 IMAGE 结果

目标为 1 个 canonical executable IMAGE Shot，PromptIR 已 current，Production Asset 与 binding 已 current，生成模式为 `TEXT_TO_IMAGE`，并通过 UI 显式选择 `local-image-mw4y52`。

真实请求结果：

- GenerationExecution：`SUCCEEDED`
- Provider request id：`shapi-response-28b2497ad7d01f52eb794b4fe4061f0d`
- Provider task id：`shapi-response-28b2497ad7d01f52eb794b4fe4061f0d`
- request/task identity：相等且非空
- Provider response hash：`a8f30ed04c1272db3ace0fe1778f482cdeda26dc9b50ce0667010dfc156f9b93`
- Candidate response hash：同上；两者相等
- logical provider calls：`1`
- transport retry count：`0`
- MediaCandidate：已建立，状态 `MEDIA_CANDIDATE`
- MediaValidationRecord：`TECHNICALLY_VALID`
- MediaPromotionRecord：`REVIEW_REQUIRED`
- 图片：`image/jpeg`、`1024×1024`、`414365` bytes、checksum/storage integrity 通过
- Official Media v1：未创建（`0`），符合“生成完成不得自动 Official”的门禁

上述 execution、candidate、validation、promotion 字段均在 cleanup 前通过只读投影与数据库审计采集；cleanup 后不再保留该 disposable Book 的业务行或媒体文件。

## 浏览器与清理审计

- 普通 V3 UI 旅程完成至真实 IMAGE 提交；没有直接调用 Provider。
- `/images/generations` 真实请求只出现 1 次。
- `generation-attempts`：0
- `generate-video`：0
- unexpected HTTP errors：0
- console errors：0
- duplicate profile warnings：0
- 外部 host：空
- secret leaks：0；authorization header artifacts：0；raw provider body / raw b64：未持久化
- disposable Book：`990453`，通过 UI 删除
- 删除审计：`orphan_rows=0`、`ambiguous_rows=0`
- 生成图片文件、Production Asset 文件与脚本决策文件均已删除；orphan media files：0

## 验证与仓库状态

- Alembic head：`p1q2r3s4t5u6`
- 新 migration：0
- 工作区：报告提交前保持干净；本轮仅增加报告、Truth Audit 与单次调用证据
- 本轮没有修改 response projection 代码

## 产物

- Truth Audit：`docs/ui-v3/REAL_IMAGE_CURRENT_RUNTIME_SINGLE_CALL_VERIFICATION_TRUTH_AUDIT.json`
- Browser evidence：`output/playwright/real-image-current-runtime-single-call/summary.json`
- Browser run detail：`output/playwright/real-image-current-runtime-single-call/run-1.json`

## 处理决定

保留当前运行时第 5 次真实调用证据；丢弃并不再作为当前结论依据的，是上一轮旧 backend process 产生的第 4 次失败结论。当前代码已经证明响应投影链路可以落到候选与技术验证，但本轮没有完成人工审核，因此不得标记为 `REAL_IMAGE_INITIAL_CURRENT_RUNTIME_GO`，也不得宣称完整的真实 Provider vertical slice。

## 下一步

`STOP — no additional real Provider call authorized`

后续若要取得 Official IMAGE v1，需要先修正浏览器审核候选的状态字段映射，再由用户单独批准新的操作预算；不得自动重试或 regenerate。


