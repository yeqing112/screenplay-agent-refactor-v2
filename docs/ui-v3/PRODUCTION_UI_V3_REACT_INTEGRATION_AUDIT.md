# Production UI V3 React Integration Audit

- **Phase**: `PHASE_PRODUCTION_UI_V3_REACT_INTEGRATION_AUDIT`
- **Baseline**: `1bf4b1601308dbba048f0405a7c3237fa1acae5f`
- **Branch**: `codex/visual-authoring-provider-canary-reconcile`
- **Audit scope**: 只读工程契约审计；不修改 `web/src/`，不新增 route，不改变 API/Runtime/DB/状态机。
- **Evidence reviewed**: Final V3 visual language/spec/component blueprint/design tokens/UX copy/shot studio/review system；真实 React、domain、hooks、services；FastAPI route 与核心 authority 实现。

## 1. Executive Summary

当前 React 工作台已经具备 V3 所需的大部分生产事实，但呈现仍是一个以 section 切换为中心的旧编排层。最可靠的正式来源是后端生产投影与各领域 authority/current pointer；旧的 `/api/pipeline/book/{bookId}/outputs` 聚合和浏览器 localStorage 只能作为兼容显示或临时导航状态，不能成为 V3 的正式状态源。

**结论：GO（分阶段）**。首个正式 React 改造 Surface 应从 **Shot Studio** 开始，使用现有 `production-workspace-v2` 的单镜头数据、`ProductionWorkspaceV2Panel` 的准备门禁和现有 storyboard 交互作为适配层。Dashboard/Review Inbox 依赖更高层的统一 resolver 与 reviewable contract，应在 Shot Studio 的状态归一和审核证据模型稳定后推进。不要先重写全局导航，也不要先做跨类型 Review Inbox。

### 已有可保留的核心

- `web/src/domain/productionWorkspace.ts`：V1/V2 schema、normalize、validation、状态人话化和 canonical authority 字段。
- `web/src/services/productionWorkspace.ts`、`productionGeneration.ts`：生产投影、媒体 validate/promote、IMAGE/VIDEO 生成入口。
- `useProductionWorkspace`、`useProductionWorkspaceV2`：真实投影读取、provider-free 约束、刷新边界。
- `ProductWorkspaceDirectorTreatmentPanel`：证据预览、真实调用显式确认、候选编辑、正式确认、历史恢复。
- 现有 storyboard / asset / QA / delivery 纯函数与测试：可拆为 V3 view-model adapter 的来源。

### 必须重构或新增的边界

- `ProductWorkspaceShell` → **REFACTOR** 为 V3 `WorkspaceShell`，保留数据刷新、错误边界和视图模式。
- 现有 section sidebar → **REFACTOR/REPLACE** 为 V3 `GlobalNav` 信息架构；禁止把 prototype HTML 直接复制进 React。
- `ProductionWorkspaceV2Panel`、`ProductWorkspaceStoryboardSection`、`ProductWorkspaceAssetsSection` → **REFACTOR/WRAP** 为 Shot Studio 的 rail/canvas/context。
- Review Inbox/Review Desk/Decision Bar、统一 activity resolver、正式详情抽屉 → **NEW** 适配层；后端需要补统一查询/决策契约才能达到 Final V3 parity。
- 通用 “Undo” → **UNDO_NOT_SUPPORTED**；当前只有各领域 rollback，不存在跨 reviewable 的时间窗口撤销 API。

## 2. Current React Architecture

### 2.1 Runtime tree

```
web/src/main.tsx
  -> App.tsx (localStorage view: projects | canvas)
    -> ProjectsPage.tsx (/api/books)
    -> CanvasPage.tsx (/api/books, lazy ProductWorkspace)
      -> ProductWorkspace.tsx (section/state orchestration root)
        -> ProductWorkspaceShell.tsx (sidebar + sticky header)
          -> ProductWorkspaceSectionContent.tsx (lazy section registry)
            -> dashboard/content/adaptation/scripts/storyboard/canvas/assets/qa/tasks/delivery/models
        -> SmartDirectorDrawer.tsx (global agent drawer)
```

当前没有 React Router。项目与工作区由 `App` 的 React state + `localStorage` 控制；workspace 的 section/shot/episode/step 由 URL query 与 `productWorkspaceNavigationState` 局部恢复。

### 2.2 Orchestration root

`ProductWorkspace.tsx` 同时承担：

- section 与 view mode；
- selected shot、canvas/task/QA handoff；
- `useBookOutputs`、V1/V2 production projection；
- upstream content/adaptation/script data；
- generation/recovery/local task state；
- section bundle wiring；
- pipeline script/storyboard generation polling。

这使它适合先作为 **coexistence adapter**，不适合直接承载新的 V3 review state machine。

### 2.3 Existing surfaces

| Surface | 当前入口 | 现有事实/动作 | V3 判断 |
|---|---|---|---|
| Projects | `ProjectsPage` | project list、delete、model registry | REUSE shell data；删除保持独立 |
| Workspace shell | `ProductWorkspaceShell` | nav、标准/专业切换、refresh、blocked nav、error | REFACTOR |
| Dashboard | `ProductWorkspaceDashboardSection` + `ProductionWorkspaceV2Panel` | summary、production spine、episode progress、next action、blockers、lane actions | REFACTOR；去重 V2 面板 |
| Content | `ProductWorkspaceContentSection` | novel/short input、content task | WRAP |
| Adaptation | `ProductWorkspaceAdaptationSection` | production skill、候选、lock/unlock | REUSE/WRAP |
| Scripts | `ProductWorkspaceScriptsSection` | ScriptIR/decision/release、DirectorTreatment | REFACTOR |
| Storyboard | `ProductWorkspaceStoryboardSection` | shot list、step tabs、keyframe/image/video/recovery | REFACTOR → Shot Studio |
| Canvas | `ProductWorkspaceCanvasBetaSection` | context handoff、shot runtime summary | WRAP/DEFER |
| Assets | `ProductWorkspaceAssetsSection` | filters、asset detail、references、shot bindings、visual authoring/semantic governance | REFACTOR → Asset Library |
| QA | `ProductWorkspaceQaSection` | workbench、issue navigation、recheck/fix | WRAP |
| Tasks | `ProductWorkspaceTasksSection` | task center、creative recovery、reconcile/restart | REFACTOR → Activity/Recovery |
| Delivery | `ProductWorkspaceDeliverySection` | readiness、export records、JSON/PDF export | REFACTOR → Delivery Workspace |
| Models | `ProductWorkspaceModelsSection` | model registry/profile | REUSE; professional details source |
| Director | treatment/runtime panels embedded in scripts/storyboard | treatment → scene blocking → ShotPlan evidence gates | REFACTOR → Director Workspace |

## 3. Current Route / Surface Inventory

### Application routes

- `App`: two in-memory views, no route-level deep link.
- `ProjectsPage`: `GET /api/books`; `DELETE /api/books/{id}`.
- `CanvasPage`: `GET /api/books`; lazy-loads production workspace.

### Workspace sections

`dashboard`, `content`, `adaptation`, `scripts`, `storyboard`, `canvas`, `assets`, `qa`, `tasks`, `delivery`, `models`.

### Deep-link parameters

`section`, `episode`, `shot`, `step`，以及兼容的 `workspace_fixture` / `workspace_v2_fixture` 开发参数。V3 应扩展为 episode/scene/shot/reviewable，但仍由 URL 保存导航上下文，不保存正式状态。

## 4. Current State Management Architecture

| State class | 当前实现 | canonical? | V3 处理 |
|---|---|---:|---|
| Project/book list | page fetch + local React state | 是（读取） | 保留 |
| V1/V2 production snapshot | hooks + service normalize/validate | **是** | 作为唯一生产投影入口 |
| Legacy outputs | `useBookOutputs` + `productWorkspaceProjectDataController` | 否；兼容聚合 | 仅作为 legacy display adapter，逐步退出生产判定 |
| section/selected shot | React state + URL/localStorage | 否 | 保留导航用途 |
| draft text edits | component local state | 否；review candidate | 提交前保持草稿，确认后 refetch authority |
| pending/recovery tasks | `productWorkspaceRecovery.ts` + localStorage + task API | 任务本地索引部分非 canonical | API task status 为事实，localStorage 仅恢复 UX |
| next action | legacy `buildDashboardActions` 或 V1 projection `project.next_actions` | V1 projection 为是 | 统一到 `toNextAction(snapshot)` |
| QA summary | `/qa/workbench` + local derivation | QA endpoint 为是 | 进入 state resolver |
| model selection | explicit profile selection + local state | selection 是输入，不是结果 | 进入 generation intent |
| optimistic official state | 部分组件本地 `approved`/message | 否 | 禁止作为正式状态，mutation 后 refetch |

## 5. Current API / Runtime Contract

### 5.1 Canonical read contracts

- `GET /api/books/{book_id}/production-workspace`：V1 read-only projection；server 明确只读、只读 current authority pointers、`provider_calls=0`。
- `GET /api/books/{book_id}/production-workspace-v2`：V2 dense DTO；same authority source，包含 shot、IMAGE/VIDEO lane、execution、candidate、official、asset authority。
- `web/src/services/productionWorkspace.ts` 在进入 React 前执行 schema validation + normalization。
- `ProductionWorkspaceV2Snapshot` 的 `read_only=true`、`authority_source=current_authority_pointers_only`、`view_contract.standard/professional` 是 V3 的状态契约。

### 5.2 Domain writes already available

- Director runtime：`POST/GET /episodes/{episode_id}/director-plan`、`POST /shots/{shot_id}/director-revise`；deterministic adapter，返回 `llm_called=false`，版本化并保留人工修改。
- Director Treatment：preview、LLM draft（显式确认）、confirm、candidate history；authority/current pointer 在 confirm 后建立。
- Scene Blocking：preview、confirm、readiness；确认后建立 authority/current pointer。
- ShotPlan：preview、creative preview/draft、confirm、readiness；确认后建立 authority/current pointer。
- Storyboard：generate/read/compile/approve/materialize/rollback。
- Keyframe：plan review/compile；image production review。
- Prompt IR：compile/async compile/task polling、prompt versions、rollback。
- Generation：canonical IMAGE/VIDEO submission；生成执行记录、candidate、provider task/request fingerprints。
- Media authority：candidate validate、promote、resolve current official media；promote response 显式返回 `provider_calls=0` 等审计字段。
- Asset authority：authoring requests/proposals/approve/reject、versions、current pointer、references、semantic governance drafts。
- QA：workbench、issue preview-fix、recheck、issue workflow、script rollback。
- Recovery：task status、reconcile、restart、repair retry-plan、repair rollback。
- Delivery：render plan/render/status、export records、PDF export、production readiness/repair plan。

### 5.3 Refresh semantics

当前 `onRefreshAll` 同时刷新 book list、legacy outputs、V1 snapshot、V2 snapshot。它是 re-fetch，不是后端 reconcile；task reconcile/restart 是单独的 domain action。V3 需要明确标注 “同步投影” 与 “恢复任务” 两种动作，不能把 refresh 当作执行或修复。

## 6. Canonical State Sources

| Object / state | canonical source | evidence | non-canonical display |
|---|---|---|---|
| Source Fact / ScriptIR | immutable source/fact snapshot + ScriptIR authority/current version | backend source lineage fields, script rollback | local script/legacy outputs |
| Director Treatment | DirectorTreatmentAuthority + current pointer | confirm builds authority envelope | candidate local state |
| Scene Blocking | SceneBlockingAuthority + pointer | production confirm route | preview response |
| ShotPlan | ShotPlanAuthority + pointer | production confirm route | edited plan local state |
| Shot direction / PromptIR | shot direction/prompt authority + version row | prompt compile/version/rollback | textarea state |
| Visual asset | VisualAssetAuthority/current version pointer | V2 `assets`, authoring/versions endpoints | `useBookOutputs` asset summary |
| Generation | GenerationExecution row | V2 lane `latest_execution` | local pending label |
| Media candidate | MediaCandidateRecord + validation record | candidate list/validate | legacy images array |
| Official media | OfficialMediaVersion + OfficialMediaAuthority + pointer | V2 `official`, media-authority resolve | `adopted` boolean in legacy output |
| Project/episode/shot progress | production workspace projection | V1/V2 endpoint | `buildDashboardActions` fallback |
| Task progress | task endpoints / creative task rows | reconcile/status APIs | localStorage pending list |
| Navigation | URL/localStorage | UX state only | never a production fact |
| Filesystem/artifact | export/download only | delivery records | never canonical |

No React component should infer official state from row counts, `adopted` alone, localStorage, or a stale legacy aggregate.

## 7. Final V3 Component → Existing Code Mapping

| Final V3 component | Existing code | Disposition | Reason |
|---|---|---|---|
| WorkspaceShell | `ProductWorkspaceShell.tsx` | REFACTOR | already owns shell, refresh, loading/error, mode; needs V3 host/drawer/freshness |
| GlobalNav | shell sections + `ProductWorkspace.tsx` section registry | REFACTOR/REPLACE | current menu exposes implementation sections and duplicates task/blocker navigation |
| ProductionDetailsDrawer | professional branches in V2 panel + storyboard advanced panels + task selected panel | WRAP then NEW | evidence fields exist but are fragmented; one drawer contract is missing |
| NextBestAction | `resolveProductionDashboardAction`, V1 `project.next_actions` | REFACTOR | authority action exists; remove legacy fallback in production view |
| EpisodeProgressRail | dashboard episode cards + `project.episodes[].stages` | REFACTOR | data is sufficient; scene-aware/50+ aggregation UI missing |
| ActivityPanel | task center + V2 `latest_execution` + recovery | MERGE/REFACTOR | sources exist, no unified activity resolver |
| BlockerPanel | dashboard current blockers + lane readiness blockers + QA summaries | MERGE/REFACTOR | blocker data exists in multiple DTOs; canonical grouping absent |
| ShotNavigator | storyboard shot list + V2 `shots` | REFACTOR | grouping/filtering exists partly; virtualization and scene contract absent |
| ShotPipeline | V2 IMAGE/VIDEO lanes + storyboard steps | REFACTOR | state data sufficient; one rail should own CTA |
| MediaCanvas | storyboard media panels + V2 official/candidates | WRAP | preview data exists; unified compare/player contract missing |
| KeyframeCard | storyboard keyframe step + automatic keyframe APIs | REFACTOR | review/compile gates exist; START/MIDDLE/END card adapter needed |
| TimelineContinuity | storyboard continuity panels + transition review APIs | WRAP | backend evidence exists; V3 timeline view absent |
| ShotContext | shot output + V2 identity/camera/action/assets | REFACTOR | context is split between legacy output and V2 |
| ReviewQueue | task center + candidate endpoints | NEW | no cross-type reviewable list with stable ordering/version contract |
| ReviewDesk | existing director/storyboard/task detail panels | NEW/WRAP | evidence UI exists but no shared review envelope |
| DecisionBar | per-domain approve/review/promote buttons | NEW | decision semantics vary by endpoint and no shared audit payload |
| DirectorWorkspace | treatment/runtime panels + director APIs | REFACTOR | backend capability strong; surface currently embedded |
| AssetLibrary | assets section + V2 asset authority | REFACTOR | identity/version/reference data exists; navigation is legacy asset-first |
| DeliveryWorkspace | delivery section + export/readiness APIs | REFACTOR | readiness and export are real; official media/release semantics need adapter |
| Model/Provider detail | models section + V2 model/execution | REUSE/WRAP | professional data already exposed |

## 8. Final V3 Implementation Matrix

| Work item | Disposition | Current reuse | New work | Gate |
|---|---|---|---|---|
| Shell host | REFACTOR | ProductWorkspaceShell | global toast/drawer/freshness host | shell a11y + URL parity |
| Canonical resolver | NEW pure adapter | V1/V2 snapshots, QA/task payloads | `toNextAction`, blocker/activity/state mapping | no local official inference |
| Shot Studio | REFACTOR/WRAP | storyboard + V2 panel + generation service | navigator/pipeline/canvas/context composition | single CTA + refetch after mutation |
| Review contract | NEW | domain payload fields | reviewable/evidence/decision adapter | no false “approve” |
| Review Inbox | NEW + backend gap | candidate/task APIs | unified query and stable pagination | all four review types traceable |
| Director workspace | REFACTOR | treatment/runtime panels | scene list + review drawer | authority pointer visible |
| Asset library | REFACTOR | assets section + V2 assets | formal version/binding view | no legacy-only official state |
| Delivery | REFACTOR | delivery pure functions/endpoints | official media gate + export status | release-ready definition agreed |
| Navigation | REFACTOR | URL/local persistence | object-aware deep links | back/forward restores context |
| Legacy coexistence | WRAP | existing sections | feature flag + fallback | parity/regression pass |

## 9. API Capability Matrix

Legend: **YES** = real endpoint and canonical effect exists; **PARTIAL** = pieces exist but V3 contract/aggregation missing; **NO** = no safe backend capability; `MISSING_BACKEND_CAPABILITY` and `UNDO_NOT_SUPPORTED` are explicit findings.

| V3 capability | Status | Existing evidence | V3 implication |
|---|---|---|---|
| Read production project/episode/shot state | YES | V1/V2 production-workspace | use projection only |
| Next best action | YES/PARTIAL | V1 `project.next_actions`, legacy fallback | YES for production; adapter needed |
| Blockers with target | YES | `current_blockers`, stage/episode/shot target params | group in resolver |
| Stale reason/fingerprint | YES | lane prompt stale/reason_codes, authority stale fields | expose professional detail |
| Director plan create/read/revise | YES | director runtime API | no LLM required |
| Director Treatment review/confirm/history | YES | preview/draft/confirm/candidates | shared review envelope missing |
| Scene Blocking review/confirm | YES | preview/confirm/readiness | shared decision envelope missing |
| ShotPlan review/confirm | YES | preview/confirm/readiness | shared decision envelope missing |
| Storyboard approve/compile/materialize/rollback | YES | automatic storyboard API | distinction “compile” vs “approve” must stay visible |
| Keyframe plan review/compile | YES | automatic keyframe API | V3 card adapter needed |
| Image candidate generate | YES | canonical `generate-frame` | explicit paid gate already present |
| Image candidate validate/promote | YES | media authority + keyframe image review | use validate before promote |
| Video candidate generate/reconcile | YES | `generate-video`, video reconcile | queue/activity adapter needed |
| Official media resolve | YES | media-authority resolve/current pointer | canonical official |
| Prompt compile/version/rollback | YES | prompt IR APIs | lineage drawer can reuse |
| Unified Review Inbox | **NO — MISSING_BACKEND_CAPABILITY** | separate treatment, storyboard, keyframe, candidate, QA/task endpoints | add read-only aggregate query before full Inbox |
| Unified review decision | **NO — MISSING_BACKEND_CAPABILITY** | per-domain approve/review/promote payloads | keep domain calls behind adapter |
| Cross-type stable review pagination | **NO — MISSING_BACKEND_CAPABILITY** | no reviewable cursor/order contract | cannot claim 20+ queue parity |
| Generic undo/revoke decision | **NO — UNDO_NOT_SUPPORTED** | storyboard/prompt/repair rollback only | expose history/rollback per domain |
| Review comments/history | PARTIAL | review notes/history in some domains | no common comment/event record |
| Activity stream | PARTIAL | task status + latest execution | no canonical cross-domain activity feed |
| Shot virtualization contract | PARTIAL | V2 returns shot array; no windowed query | client virtualization feasible for moderate list; server pagination missing |
| Asset library query | PARTIAL | V2 assets + legacy outputs | filters/counts are partly local; authority query contract missing |
| Dashboard readiness | YES/PARTIAL | V1/V2 project/episode stages | next action and blocker are real; summary cards partly legacy |
| Delivery readiness | YES | production readiness and export guard | V3 must use official media/readiness, not local adopted flags |
| Model/provider registry | YES | model-registry endpoints | profile selection separate from execution result |
| Provider call suppression in audit | YES | read projections and media promote report zero calls | maintain for read-only audit |

## 10. State Contract Mapping

| V3 state | canonical input | current support | rule |
|---|---|---|---|
| loading | hook load state | YES | local skeleton only |
| empty | empty arrays + not_started | PARTIAL | explain next action; no fake fixture |
| ready | `ready`/generation_readiness.ready | YES | enable domain action |
| running | execution/task status | PARTIAL | normalize queued/running/provider pending |
| review | `REVIEW_REQUIRED`, candidate validation | YES per domain | show evidence/version |
| waiting_upstream | blockers/dependencies | YES | route to target object |
| blocked | blockers/reason_codes/QA | YES | blocker panel separate from review |
| stale | stale flags/reasons | YES | display source fingerprint/time |
| failed | execution failure/task error | PARTIAL | keep lineage and retry/recovery |
| official | current official pointer | YES | never infer from candidate/adopted boolean |

## 11. Review Inbox Feasibility

### Real sources

1. Director Treatment candidate/history endpoints.
2. Scene Blocking and ShotPlan draft/confirm records.
3. Storyboard version status/approve endpoint.
4. Keyframe plan review/compile and image production review.
5. MediaCandidateRecord list + validation/promotion.
6. QA workbench/issues and recovery tasks.

### Gap

There is no backend query that returns a single `reviewable` envelope containing:

`type, object_id, source_version, target_version, evidence, lineage, stale, priority, reviewer_state, decision options, next route`.

Therefore a V3 Review Inbox can start as a **read-only client adapter for Shot Studio only**, but a cross-type inbox is **NO / MISSING_BACKEND_CAPABILITY** until a server aggregate with stable pagination and review decision audit is added. “待审核” must never be synthesized by counting blockers.

## 12. Shot Studio Feasibility

**Feasible as first Surface.**

- Data: V2 already returns identity, scene, duration, camera, action, asset readiness, IMAGE/VIDEO lanes, execution, candidates, official media, blockers and next action.
- APIs: canonical production generation, prompt compile/version, media validate/promote, storyboard/keyframe review/compile, recovery.
- Virtualization: client-side list virtualization is feasible when V2 array is loaded; 40+/100+ contract still needs measured rendering and preferably server pagination/filtering. Mark server-side pagination as **MISSING_BACKEND_CAPABILITY** until provided.
- Single CTA: resolver should choose one action from `shot.next_action` / blockers; hide competing legacy buttons.
- Official state: resolve via media authority; after mutation invalidate/refetch V2.
- Virtualized filtering: episode/scene/state/search can be computed over normalized V2; do not derive state from legacy `shotsByEpisode`.

## 13. Dashboard Data Feasibility

**Mostly feasible.**

- Next Best Action: V1 `project.next_actions[0]` is canonical.
- Episode rail: V1/V2 episode summaries and stage counts are sufficient.
- Blockers: V1 current blockers and target params are sufficient.
- Activity: needs merge of V2 latest execution and task center; no server activity aggregate.
- Summary cards (chapter/word/script counts): still read from legacy book/output aggregates. Keep as informational only until a canonical project summary contract exists.
- Production Spine: data exists; duplicate V2 panel and dashboard spine should merge.

## 14. Director Workspace Feasibility

**Backend strong; React organization incomplete.**

- Treatment preview/LLM draft/confirm/history has evidence fingerprint, candidate editing, explicit external-call gate and authority binding.
- Runtime panel has SceneBlocking → ShotPlan → benchmark chain and human confirmation.
- Director runtime plan API is deterministic/provider-free and supports human shot revision.
- V3 should move these panels into one scene-aware DirectorWorkspace and map each confirm to a reviewable decision. Do not expose LLM call as automatic page load.

## 15. Asset Library Feasibility

**Partially feasible.**

- V2 provides authority/current version, stale status, references, bindings and history.
- Existing assets section supports filters, previews, reference generation, binding edits, visual authoring proposals and semantic governance.
- The section still assembles many summaries from `useBookOutputs`; this creates duplication and can show legacy state beside authority state.
- Formal version/pointer and candidate image promotion are available; a single asset library query and consistent identity search are not. Mark unified asset query as **MISSING_BACKEND_CAPABILITY** if server-side scale is required.

## 16. Delivery Feasibility

**Feasible with explicit gate mapping.**

- Production readiness endpoint and export record/PDF routes exist.
- Delivery section has readiness calculation, export history, repair actions, JSON/PDF export.
- Server export uses deliverable-shot predicate and current formal media checks; this is the source of truth.
- “Ready for delivery” must be read from readiness/export guard, not from local QA count or `adopted` fields.
- Render status and export record history are separate concepts; V3 should label them separately.

## 17. Backend Gap Register

| ID | Gap | Severity | Impact | Required before |
|---|---|---:|---|---|
| BG-01 | Unified `reviewable` read model with stable cursor/order | P0 | Review Inbox cannot be canonical | cross-type Review Inbox |
| BG-02 | Unified decision/audit endpoint or common decision envelope | P0 | DecisionBar cannot guarantee common evidence/changed fields | shared Review Desk |
| BG-03 | Generic undo/revoke window | P1 | “撤销” cannot be implemented truthfully | final Review UX |
| BG-04 | Cross-domain activity stream | P1 | ActivityPanel merges task/execution heuristically | activity parity |
| BG-05 | Server-side shot/asset pagination/filter | P1 | 100+ virtualization relies on full payload | large-project scale |
| BG-06 | Canonical project summary counts | P2 | dashboard cards depend on legacy outputs | dashboard full migration |
| BG-07 | Unified asset identity query/binding read model | P1 | AssetLibrary filters use mixed sources | asset full migration |
| BG-08 | Explicit delivery release/official package status contract | P1 | Delivery can export but “release” semantics remain split | delivery parity |
| BG-09 | Shared comments/decision history record | P1 | review history fragmented | Review Desk parity |

## 18. Duplication Risk Register

| Risk | Current duplication | Mitigation |
|---|---|---|
| D-01 | V1 dashboard + V2 panel both render production spine/lanes | one resolver + one V3 component |
| D-02 | legacy `useBookOutputs` and V2 both describe shots/assets | authority-first adapter; legacy display only |
| D-03 | local “approved/saved” state beside server pointer | refetch after mutation; local state is pending only |
| D-04 | task center and dashboard blocker cards overlap | BlockerPanel owns blockers; ActivityPanel owns executions/tasks |
| D-05 | director treatment/runtime panels embedded in scripts/storyboard | DirectorWorkspace owns scene-level orchestration |
| D-06 | asset section’s reference records and V2 asset authority | V2/current pointer is canonical; asset helper only formats |
| D-07 | delivery readiness pure function and server readiness | server gate wins; client function explains detail only |
| D-08 | URL/localStorage fixture flags | dev-only fixture never enters production state |

## 19. Migration Risk Register

| Risk | Impact | Mitigation / exit criterion |
|---|---|---|
| M-01 | changing shell breaks deep links | preserve section/episode/shot/step and add round-trip tests |
| M-02 | V3 displays candidate as official | require pointer/authority proof in adapter |
| M-03 | review action bypasses domain gate | all decisions call existing endpoint; no generic fake POST |
| M-04 | duplicate generation CTA causes paid calls | single Shot Studio CTA; explicit model/profile gate |
| M-05 | stale data hidden by legacy fallback | production mode fails closed on projection error |
| M-06 | large shot list jank | measure virtualization; add server pagination before 100+ parity |
| M-07 | rollback language overpromises | label domain rollback; no generic undo |
| M-08 | local optimistic updates diverge | invalidate/refetch authority after every mutation |
| M-09 | feature flag splits source rules | flag only switches view; services/domain shared |
| M-10 | delivery appears ready from incomplete data | server readiness/export guard is required |

## 20. Test Coverage Assessment

### Existing coverage to retain

- `productionWorkspace.test.ts`, `productionWorkspaceV2.test.tsx`: schema, provider-call/read-only invariants, lane readiness and professional/standard rendering.
- `ProductWorkspaceShell.test.tsx`: navigation accessibility/blocked state.
- Storyboard tests: shot readiness, reference binding, repair actions, machine prompt export.
- Assets tests: filters, handoff, shot binding, reference generation.
- Delivery tests: readiness, history, export package/document, corrupted summary handling.
- Task/recovery tests: reconcile/restart and task center state.
- Director/Script tests: evidence-first treatment controls and script review states.

### Missing tests before V3 parity

- canonical resolver property tests (one next action, blocker/review separation);
- reviewable envelope mapping for all five review types;
- mutation → refetch → official pointer invariant;
- stale/409 conflict mapping;
- 40+/100+ ShotNavigator virtualization and keyboard focus;
- no generic undo claim when endpoint absent;
- delivery ready only when server readiness and official media agree;
- feature flag coexistence and URL round-trip.

No provider call or production write was executed during this audit. Frontend build and unit-test validation is recorded in the final task report.

## 21. Recommended Incremental Migration Plan

1. **Phase 0 — Contract adapters (current audit output)**  
   Freeze canonical sources, create pure resolver interfaces, add no UI mutation.
2. **Phase 1 — Shot Studio read path**  
   Build V3 navigator/pipeline/context over V2 snapshot; keep existing storyboard actions behind adapters.
3. **Phase 2 — Shot review path**  
   Add KeyframeCard/MediaCanvas/DecisionBar for one shot; call existing review/validate/promote endpoints; refetch V2.
4. **Phase 3 — Director Workspace**  
   Extract treatment/runtime panels; map scene evidence to common review envelope.
5. **Phase 4 — Dashboard**  
   Merge V1/V2 duplicate panels into NextBestAction/EpisodeProgressRail/BlockerPanel/ActivityPanel.
6. **Phase 5 — Asset Library**  
   Authority-first asset list/detail; retain legacy helper for compatibility.
7. **Phase 6 — Delivery Workspace**  
   Server readiness/export guard, official media summary, export history and render status.
8. **Phase 7 — Review Inbox**  
   Only after BG-01/BG-02 are implemented or a formally accepted read-only adapter contract exists.
9. **Phase 8 — Remove legacy presentation**  
   Remove duplicate V2 panel/old menu only after parity, regression and UX acceptance.

### First implementation surface

**Shot Studio** (`storyboard` section) is the recommended starting point because it has the densest complete data contract and the clearest user value: one shot, one pipeline, one evidence-driven next action. It also lets the team validate the Review Desk contract without solving cross-project queue ordering.

## 22. Recommended Commit Sequence

1. `docs: audit production ui v3 react integration` (this report)
2. `feat(ui-v3): add canonical production state adapters`
3. `feat(ui-v3): introduce shot studio read surface`
4. `feat(ui-v3): add shot review desk and decision bar`
5. `feat(ui-v3): extract director workspace`
6. `feat(ui-v3): migrate dashboard and blocker/activity panels`
7. `feat(ui-v3): migrate asset library`
8. `feat(ui-v3): migrate delivery workspace`
9. `feat(api): add reviewable inbox projection` (only after contract approval)
10. `refactor(ui-v3): remove legacy duplicate surfaces`

## 23. Explicit Non-Goals

- 不创建 Final V3 React 页面或新 route。
- 不修改 `web/src/`、API、Runtime、DB、状态机。
- 不自动调用真实 LLM、SHAPI、MiniMax、图片或视频 provider。
- 不自动生成视频、不自动修改剧本、不删除人工审核。
- 不把 local state、fixture、legacy output 当作正式状态。
- 不把 `compile` 误写成 `approve`；compile 是派生/编译动作，approve/confirm 才建立 authority。
- 不承诺不存在的通用 Undo；仅呈现已有 domain rollback。
- 不以报告替代后续实现和 UX acceptance。

## 24. Final Go / No-Go Conditions

### GO for first Shot Studio implementation

- V2 schema validation remains green.
- Shot state resolver proves one primary CTA and separates review/blocker/waiting/stale.
- Every mutation calls existing domain API then refetches V2.
- Candidate and official states are pointer-backed.
- 40+ list performance and keyboard focus are measured.
- No provider calls are made by read-only surfaces.

### NO-GO for full Review Inbox / legacy removal

- BG-01 unified reviewable read model not available.
- BG-02 common decision/evidence contract not available.
- Generic undo is presented despite **UNDO_NOT_SUPPORTED**.
- Review rows cannot expose source version, evidence, lineage, reason and next route.
- Delivery readiness is inferred locally.
- Web source mutations or provider calls appear during audit.

## Audit Conclusion

`PRODUCTION_UI_V3_REACT_INTEGRATION_AUDIT_COMPLETE`

The current codebase is ready for an incremental Shot Studio first migration. Full V3 Review Inbox and legacy presentation removal require the backend gaps above to be resolved or explicitly accepted as scoped adapters.



