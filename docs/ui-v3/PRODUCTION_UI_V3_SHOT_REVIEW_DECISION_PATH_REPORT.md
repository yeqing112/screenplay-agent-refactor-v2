# Production UI V3 Shot Review Decision Path Report

**阶段：** `PHASE_PRODUCTION_UI_V3_SHOT_REVIEW_DECISION_PATH`
**完成标记：** `PRODUCTION_UI_V3_SHOT_REVIEW_DECISION_PATH_COMPLETE`
**验证日期：** 2026-09-30
**基线：** `f49cc3718170993fbef405a4a10d34c555e456cb`
**分支：** `codex/visual-authoring-provider-canary-reconcile`

## Scope

本轮把 Shot Studio V3 的单镜头 IMAGE / VIDEO Media Candidate Review 接入为受控人工审批闭环：

```text
Review Desk
  ↓
Decision Bar
  ↓
existing media validation contract
  ↓
existing media promotion contract
  ↓
await V2 canonical refresh
  ↓
productionUiV3 normalization
  ↓
OfficialMediaPointer confirmation
```

范围只覆盖当前选中 Shot 的当前 IMAGE 或 VIDEO candidate。没有实现 Review Inbox、跨镜头队列、跨领域 reviewable、生成、重试、通用修改、通用驳回或撤销。

## Real Media Review Contract

重新审阅的真实实现：

- `web/src/services/productionWorkspace.ts`
- `api/media_authority_api.py`
- `api/asset_promotion_api.py`
- `core/media_authority.py`
- `tests/test_asset_promotion_runtime.py`

已有端点：

```text
POST /api/media-authority/candidates/{candidate_id}/validate
POST /api/media-authority/promote
POST /api/assets/candidates/{candidate_id}/validate
POST /api/assets/candidates/{candidate_id}/promote
GET  /api/media-authority/books/{book_id}/episodes/{episode}/shots/{shot}/roles/{media_role}
```

本轮没有新增后端路由、数据库表或 review schema。Shot Studio 使用现有 asset promotion endpoint 记录显式 `APPROVE`，避免把确认-only legacy wrapper 当成新的通用审核 API。

## Files Added / Changed

新增：

- `web/src/services/productWorkspaceShotReview.ts`
- `web/src/services/productWorkspaceShotReview.test.ts`
- `docs/ui-v3/PRODUCTION_UI_V3_SHOT_REVIEW_DECISION_PATH_REPORT.md`
- `docs/ui-v3/shot-review-read/shot-review-image-1440.png`
- `docs/ui-v3/shot-review-read/shot-review-video-1440.png`
- `docs/ui-v3/shot-review-read/shot-review-promoting.png`
- `docs/ui-v3/shot-review-read/shot-review-confirmed.png`

修改：

- `web/src/components/ProductWorkspaceShotStudioV3.tsx`
- `web/src/components/ProductWorkspaceShotStudioV3.test.tsx`
- `web/src/components/ProductWorkspace.tsx`
- `web/src/components/ProductWorkspaceSectionContent.tsx`
- `web/src/components/productWorkspaceSectionBundlesController.ts`
- `web/src/components/productWorkspaceSectionContracts.ts`
- `web/src/hooks/useProductionWorkspaceV2.ts`
- `web/src/fixtures/productionWorkspaceV2.ts`
- `web/src/services/productionWorkspace.ts`
- `web/src/domain/productionWorkspaceV2.test.tsx`

## Validation Semantics

真实 `validate_media_candidate()` 会：

1. 校验 Candidate 与 GenerationExecution lineage。
2. 校验 Provider response projection、storage identity、checksum、mime、尺寸和媒体类型。
3. 校验 PromptIR / Asset / Reference / Generation Policy 当前性。
4. 创建或复用 `MediaValidationRecord`，记录状态 `TECHNICALLY_VALID`。
5. 建立 `MediaPromotionRecord(review_status=REVIEW_REQUIRED)`。
6. 将 candidate projection 保留为候选，不能直接视为 OfficialMedia。

因此 adapter 中的 `TECHNICALLY_VALID` 和 `REVIEW_REQUIRED` 都表示可进入人工审核路径；它们不等于正式版本。缺失 `validation_id` 时控制器才调用 validate；validate 没有返回验证 ID 时 fail closed。

## Promotion Semantics

人工批准调用已有：

```text
POST /api/assets/candidates/{candidate_id}/promote
{
  validation_id,
  reviewer: "shot-studio-human",
  decision: "APPROVE",
  review_notes,
  confirmation: true
}
```

Backend 仍负责检查：

- validation status 必须是 `TECHNICALLY_VALID` 或 `REVIEW_REQUIRED`
- validation integrity、candidate fingerprint 和 execution lineage
- technical validation fingerprint
- current PromptIR / asset / reference / generation policy snapshot
- VIDEO 的 source lineage
- explicit approval decision

成功后 backend 建立或复用：

- `OfficialMediaVersion`
- `OfficialMediaAuthority`
- `OfficialMediaPointer`

重复 promotion 由后端的 candidate + validation identity 复用既有 OfficialMedia 记录，不在 UI 侧重复提交。

## Mutation Architecture

新增：

- `web/src/services/productWorkspaceShotReview.ts`
- `createShotStudioMediaReviewController()`
- `ShotReviewCandidateIdentity`
- `ShotReviewMutationState`

状态明确区分：

```text
idle
confirming
validating
promoting
refreshing
confirmed
failed
```

控制器负责：

- 捕获 `shotId / lane / candidateId / validationId`
- 提交前 freshness check
- 缺失 validation ID 时的 validate
- 显式 APPROVE promotion
- promotion 错误归一化
- canonical V2 refresh
- 有上限的 projection lag retry
- canonical confirmation
- mutation lock 和卸载/取消信号边界

React View 只负责 Review Desk、Decision Bar 和状态呈现，没有把完整 mutation 流程写进 JSX。

## Canonical Confirmation Flow

实现的关键不变量：

```text
candidate
  ↓
Decision Bar
  ↓
freshness check
  ↓
validate only when validation_id is missing
  ↓
explicit APPROVE promotion
  ↓
await refreshProductionWorkspaceV2()
  ↓
toShotStudioViewModels()
  ↓
official.isCanonicalOfficial === true
  ↓
official.version.candidate_id === captured candidateId
  ↓
UI displays canonical confirmation
```

promotion POST 的成功响应不会直接设置 local official state。只有新的 V2 snapshot 同时证明 current pointer、authority、version 和 candidate identity 后，UI 才显示“已建立正式版本”。

## Projection Lag Handling

promotion 成功后，控制器最多执行 3 次 V2 canonical refresh，默认间隔 120ms。每次 refresh 后重新读取当前 Shot ViewModel。

如果 pointer 尚未出现：

```text
确认请求已完成，但正式状态尚未同步。
请重新同步生产状态。
```

控制器不会无限 polling、不会重复 POST、不会把 POST success 当作 official。

## Conflict Handling

对 409、`MEDIA_PROMOTION_STALE`、`MEDIA_PROMOTION_CONFLICT`：

1. 不自动重试 promotion POST。
2. 先执行一次 canonical refresh。
3. 如果 refresh 后确认了 captured candidate 的 current pointer，显示“正式状态已更新”。
4. 否则保持 candidate，显示冲突并要求重新同步。

Promotion 失败不会删除 candidate、清空 Review Desk、跳到下一 Shot 或伪造批准成功。

## Double Submit Protection

控制器进入 `confirming` 后立即锁定当前 mutation。重复点击、Enter 重复触发或并发调用都会被拒绝，后端 promotion 调用保持 exactly once。

Selection identity 固定为：

```text
shotId
lane
candidateId
validationId
```

用户切换 Shot 时，旧 mutation 的确认仍只针对 captured candidate；不会用当前 selected Shot 猜测旧结果，也不会污染新的 Shot UI。

## IMAGE Review Flow

DEV review fixture：

```text
IMAGE candidate = TECHNICALLY_VALID + validation_id
VIDEO = IMAGE_TO_VIDEO waiting for OFFICIAL_IMAGE_REQUIRED
```

批准并 canonical refresh 后：

```text
IMAGE official.isCanonicalOfficial = true
VIDEO state = ready
Next Best Action = 生成视频
```

“生成视频”仍是只读生产动作，`requiresProviderCall=true)，本轮不会自动调用 Provider。

## VIDEO Review Flow

DEV review fixture：

```text
IMAGE official
VIDEO candidate = TECHNICALLY_VALID + validation_id
```

批准并 canonical refresh 后：

```text
IMAGE official
VIDEO official
Shot state = official
Next Best Action = 查看正式版本
```

不会自动进入 Delivery，也不会触发后续生成。

## Decision Bar

Review Desk 显示：

- Candidate media evidence
- Candidate / 非正式标记
- Shot、Scene、Lane
- Validation state
- Review reason
- Version / model
- Current Official 对比区域（如存在）
- Professional mode 下的 candidate ID

Primary：

```text
批准并继续
```

含义是通过现有 Media Authority promotion 建立 canonical official。Secondary `要求修改` 保持 disabled，并说明“统一修改意见契约尚未接入”。

Mutation 中按钮文案依次表达：

```text
正在确认…
正在建立验证记录…
正在建立正式版本…
正在同步正式状态…
```

Progress 使用 `role=status` / `aria-live`，错误使用 `role=alert`。

## Disabled Unsupported Decisions

本轮没有实现：

- Generate Image
- Generate Video
- Retry / Regenerate
- Compile Prompt
- Storyboard Compile
- Director / Scene Blocking / ShotPlan confirm
- Generic Request Changes
- Generic Reject
- Generic Undo
- Review Inbox
- Cross-shot queue
- Dashboard / GlobalNav migration
- Legacy Storyboard removal

UI 中没有出现“撤销”。

## Network Audit

Browser QA 使用 DEV fixture 和 Playwright route mock：

```text
POST /api/assets/candidates/fixture-media-candidate-image/promote  [mocked 200]
POST /api/assets/candidates/fixture-media-candidate-video/promote  [mocked 200]
```

由于 DEV candidate 已有 validation ID，批准路径没有额外 validate POST。控制器单测覆盖缺失 validation ID 时的 validate → validation_id → promote 两步路径。

本轮主动审核请求中没有：

```text
generate-image
generate-video
SHAPI
MiniMax
LLM
storyboard generation
prompt compile
```

页面既有的 agent reconcile 请求与本轮 Review mutation 分开记录，不归因于 Shot Studio Review Desk。

## Tests

新增定向 controller tests 覆盖：

- IMAGE / VIDEO approval
- existing validation ID
- missing validation ID
- missing returned validation ID fail closed
- promotion once
- double submit lock
- POST success without pointer
- promotion error preserves candidate
- 409 conflict re-resolution
- stale candidate rejection
- canonical contradiction rejection
- IMAGE_TO_VIDEO next action
- VIDEO → Shot official
- REVIEW_REQUIRED / TECHNICALLY_VALID semantics

新增 Review Desk / service tests 覆盖：

- IMAGE Review Desk
- VIDEO Review Desk
- candidate never appears official before promotion
- Standard / Professional ID visibility
- disabled unsupported decisions
- existing explicit human promotion endpoint payload

结果：

```text
pytest -q tests/test_asset_promotion_runtime.py: 5 passed
定向 mutation + Review tests: 23 passed
全量 Web tests: 56 files / 356 tests passed
npm --prefix web run build: PASS
git diff --check: PASS
```

## Browser QA

使用 DEV-only `workspace_v2_fixture=review`，未连接真实 candidate 或真实 production mutation。

已验证：

- IMAGE Review Desk
- VIDEO Review Desk
- Decision Bar primary / disabled secondary
- promotion pending screenshot
- canonical confirmation screenshot
- IMAGE approval 后 VIDEO next action = 生成视频
- VIDEO approval 后 Shot = 正式版本
- Standard / Professional mode
- 1280×900：`innerWidth=1280`, `scrollWidth=1280`
- 1440×900：`innerWidth=1440`, `scrollWidth=1440`
- 1920×1080：`innerWidth=1920`, `scrollWidth=1920`
- 三个宽度下 Review Desk 和批准按钮均存在且可访问
- 浏览器 console errors = 0

## Production Safety

本轮实现了真实 mutation path，但 QA 没有写入真实生产数据：

```text
Production mutation paths implemented:
- existing candidate validation wrapper
- existing explicit candidate APPROVE promotion wrapper
- canonical V2 refresh / confirmation

Real media promotions during QA: 0
Real candidate validation writes during QA: 0
Real production writes during QA: 0
Provider submissions: 0
Real LLM calls: 0
Real SHAPI calls: 0
Real MiniMax calls: 0
Real image generation calls: 0
Real video generation calls: 0
Backend route / schema / DB mutations: 0
```

DEV fixture只返回 evidence placeholder，不伪造图片、视频或缩略图。

## Deferred Capabilities

后续阶段再处理：

- Review Inbox
- cross-shot queue
- generic Request Changes / Reject contract
- generic Undo
- Director / Keyframe review
- real authenticated reviewer identity
- server pagination / virtualization
- default surface migration
- actual provider generation controls

## Completion Status

```text
PRODUCTION_UI_V3_SHOT_REVIEW_DECISION_PATH_COMPLETE
```

## Visual Evidence

- [IMAGE review · 1440px](shot-review-read/shot-review-image-1440.png)
- [VIDEO review · 1440px](shot-review-read/shot-review-video-1440.png)
- [Promotion pending](shot-review-read/shot-review-promoting.png)
- [Canonical confirmation](shot-review-read/shot-review-confirmed.png)
