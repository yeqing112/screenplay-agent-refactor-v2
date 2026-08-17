import {
  getStoryboardRecoveryKindLabel,
  readShotRuntimeState,
  summarizePendingStoryboardTasks,
} from './productWorkspaceRecovery'
import { inferRecoveryIntentFromTask } from './productWorkspaceTaskCenterState'
import TaskCenterDetailPanels from './productWorkspaceTaskCenterDetailPanels'
import type { BatchTaskAction } from './productWorkspaceBatchActions'
import type { BatchRunRecord } from './productWorkspaceBatchRuns'
import type { TaskCenterEntry, TaskCenterSection, TaskCenterStatus } from './productWorkspaceTasks'
import type { WorkspaceTaskRouteOptions } from './productWorkspaceSectionContracts'

type TaskActionState = {
  mode: 'idle' | 'loading' | 'success' | 'error'
  action:
    | 'qa-autofix'
    | 'qa-recheck'
    | 'recovery-refresh'
    | 'recovery-reconcile'
    | 'recovery-restart'
    | 'recovery-regenerate-latest'
    | BatchTaskAction
    | null
  message: string
}

type TaskCenterPrimaryActionPlan =
  | { action: 'navigate_primary'; label: string; detail: string }
  | { action: 'navigate_canvas'; label: string; detail: string }
  | { action: 'recovery_refresh'; label: string; detail: string }
  | { action: 'recovery_reconcile'; label: string; detail: string }
  | { action: 'recovery_restart'; label: string; detail: string }
  | { action: 'recovery_regenerate_latest'; label: string; detail: string }

interface Props {
  bookId: number
  selectedTask: TaskCenterEntry | null
  navigationSummary?: {
    title: string
    detail: string
  } | null
  operationSummary?: {
    title: string
    detail: string
    primaryLabel?: string
    primaryTarget?: TaskCenterSection | null
    options?: WorkspaceTaskRouteOptions
    secondaryCanvasOptions?: WorkspaceTaskRouteOptions | null
  } | null
  selectedTaskActionState: TaskActionState
  selectedTaskEpisode: number | null
  selectedTaskShotId: string | null
  selectedTaskAssetId: string | null
  latestSelectedBatchRunRecord: BatchRunRecord | null
  selectedBatchRunRecords: BatchRunRecord[]
  batchPromptCompileCount: number
  batchMissingFrameCount: number
  batchMissingVideoCount: number
  batchOpenQaEpisodeCount: number
  onNavigate: (section: TaskCenterSection, options?: WorkspaceTaskRouteOptions) => void
  onOpenPreview: (url: string, title: string) => void
  onRunBatchTaskAction: (action: BatchTaskAction) => void
  onRunRecoveryTaskAction: (action: 'recovery-refresh' | 'recovery-reconcile' | 'recovery-restart' | 'recovery-regenerate-latest') => void
  onRunQaTaskAction: (action: 'qa-autofix' | 'qa-recheck') => void
}

function formatRecoveryAwareGenerationChainLabel(generationChain: string) {
  if (generationChain === 'canvas_recovery_continue_after_frame') return '恢复后继续生成视频'
  if (generationChain === 'canvas_recovery_continue_after_prompt') return '恢复后继续生成首帧/视频'
  if (generationChain === 'canvas_recovery_recompile_then_video') return '恢复后重编再继续生成视频'
  if (generationChain === 'canvas_recovery_recompile_then_frame') return '恢复后重编再生成首帧'
  return formatGenerationChainLabel(generationChain)
}

function formatGenerationChainLabel(generationChain: string) {
  if (generationChain === 'recompile_then_video') return '重编后继续生成视频'
  if (generationChain === 'recompile_then_frame') return '重编后生成首帧'
  if (generationChain === 'task_center_regenerate_latest_video') return '按最新镜头状态重生成视频'
  if (generationChain === 'task_center_regenerate_latest_frame') return '按最新镜头状态重生成首帧'
  return generationChain
}

export function buildTaskCenterPrimaryActionPlan(input: {
  selectedTask: TaskCenterEntry | null
  operationSummary?: {
    primaryLabel?: string
    primaryTarget?: TaskCenterSection | null
    options?: WorkspaceTaskRouteOptions
    secondaryCanvasOptions?: WorkspaceTaskRouteOptions | null
  } | null
  actionState: TaskActionState
  canNavigateToCanvas: boolean
  canRegenerateLatest: boolean
}) {
  const task = input.selectedTask
  if (!task) return null

  if (input.operationSummary?.primaryLabel && input.operationSummary.primaryTarget && input.operationSummary.options) {
    return {
      action: 'navigate_primary',
      label: input.operationSummary.primaryLabel,
      detail: '当前恢复动作已经给出下一步业务入口，建议先沿主链路确认结果是否真正收口。',
    } satisfies TaskCenterPrimaryActionPlan
  }

  if (task.taskId) {
    if (
      input.actionState.mode === 'success' &&
      input.actionState.action &&
      input.actionState.action.startsWith('recovery-') &&
      input.canNavigateToCanvas
    ) {
      return {
        action: 'navigate_canvas',
        label: '在创作画布查看',
        detail: '恢复动作已产生新结果，优先回创作画布检查链路是否已经恢复到可继续创作的状态。',
      } satisfies TaskCenterPrimaryActionPlan
    }

    if (task.status === 'error') {
      if (input.canRegenerateLatest) {
        return {
          action: 'recovery_regenerate_latest',
          label: '按最新状态重生成',
          detail: '当前任务失败，但支持按镜头最新状态重新发起，先用最新上下文接回链路更稳妥。',
        } satisfies TaskCenterPrimaryActionPlan
      }

      return {
        action: 'recovery_restart',
        label: '按原始输入重发',
        detail: '当前任务处于失败态，建议先基于原始输入重新发起一次，再观察服务侧是否恢复正常。',
      } satisfies TaskCenterPrimaryActionPlan
    }

    if (task.status === 'running') {
      return {
        action: 'recovery_reconcile',
        label: '继续回收结果',
        detail: '当前任务仍在执行或等待回收，下一步先继续回收结果。',
      } satisfies TaskCenterPrimaryActionPlan
    }

    if (task.status === 'queued') {
      return {
        action: 'recovery_refresh',
        label: '刷新状态',
        detail: '当前任务刚接回任务中心，建议先刷新一次状态确认服务侧是否已经开始实际执行。',
      } satisfies TaskCenterPrimaryActionPlan
    }

    if (task.status === 'done' && input.canNavigateToCanvas) {
      return {
        action: 'navigate_canvas',
        label: '在创作画布查看',
        detail: '当前任务结果已经回写完成，下一步更适合回创作画布检查产物与后续链路。',
      } satisfies TaskCenterPrimaryActionPlan
    }
  }

  if (input.canNavigateToCanvas) {
    return {
      action: 'navigate_canvas',
      label: '在创作画布查看',
      detail: '当前任务已经带着足够的上下文，回创作画布更容易从全链路视角判断下一步。',
    } satisfies TaskCenterPrimaryActionPlan
  }

  return {
    action: 'navigate_primary',
    label: task.actionLabel,
    detail: '当前任务已经给出明确业务入口，先按这条入口继续推进更直接。',
  } satisfies TaskCenterPrimaryActionPlan
}

export default function TaskCenterSelectedTaskPanel({
  bookId,
  selectedTask,
  navigationSummary,
  operationSummary,
  selectedTaskActionState,
  selectedTaskEpisode,
  selectedTaskShotId,
  selectedTaskAssetId,
  latestSelectedBatchRunRecord,
  selectedBatchRunRecords,
  batchPromptCompileCount,
  batchMissingFrameCount,
  batchMissingVideoCount,
  batchOpenQaEpisodeCount,
  onNavigate,
  onOpenPreview,
  onRunBatchTaskAction,
  onRunRecoveryTaskAction,
  onRunQaTaskAction,
}: Props) {
  const selectedTaskRecoveryIntent: WorkspaceTaskRouteOptions['recoveryIntent'] =
    selectedTaskShotId ? inferRecoveryIntentFromTask(selectedTask) : null
  const canNavigateToCanvas = Boolean(selectedTaskEpisode || selectedTaskShotId || selectedTaskAssetId)
  const canRegenerateLatest = selectedTask?.recoveryKind === 'frame' || selectedTask?.recoveryKind === 'video'
  const primaryActionPlan = buildTaskCenterPrimaryActionPlan({
    selectedTask,
    operationSummary,
    actionState: selectedTaskActionState,
    canNavigateToCanvas,
    canRegenerateLatest,
  })

  const selectedShotRuntimeSummary = (() => {
    if (!selectedTaskEpisode || !selectedTaskShotId) return null
    const { latestExecutionSummary: latestExecution, pendingTasks } = readShotRuntimeState(
      bookId,
      selectedTaskEpisode,
      String(selectedTaskShotId),
    )
    if (!latestExecution && pendingTasks.length === 0) return null
    const pendingSummary = summarizePendingStoryboardTasks(pendingTasks)
    return {
      latestExecutionLabel: latestExecution?.label ?? null,
      latestExecutionAt: latestExecution?.updatedAt ?? null,
      pendingTasks,
      pendingSummary,
    }
  })()

  const promptVersionRelationSummary = buildPromptVersionRelationSummary(selectedTask)

  const runPrimaryAction = () => {
    if (!selectedTask || !primaryActionPlan) return
    switch (primaryActionPlan.action) {
      case 'navigate_primary':
        if (operationSummary?.primaryTarget && operationSummary.options) {
          onNavigate(operationSummary.primaryTarget, operationSummary.options)
        } else {
          onNavigate(selectedTask.actionTarget, buildNavigateOptions(selectedTask, selectedTaskEpisode, selectedTaskShotId, selectedTaskAssetId, selectedTaskRecoveryIntent))
        }
        return
      case 'navigate_canvas':
        onNavigate(
          'canvas',
          buildNavigateOptions(selectedTask, selectedTaskEpisode, selectedTaskShotId, selectedTaskAssetId, selectedTaskRecoveryIntent),
        )
        return
      case 'recovery_refresh':
        onRunRecoveryTaskAction('recovery-refresh')
        return
      case 'recovery_reconcile':
        onRunRecoveryTaskAction('recovery-reconcile')
        return
      case 'recovery_restart':
        onRunRecoveryTaskAction('recovery-restart')
        return
      case 'recovery_regenerate_latest':
        onRunRecoveryTaskAction('recovery-regenerate-latest')
        return
    }
  }

  return (
    <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900 p-5">
      {navigationSummary ? <InfoPanel tone="sky" title="恢复上下文" detail={navigationSummary.detail} label={navigationSummary.title} /> : null}
      {operationSummary ? (
        <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
          <div className="text-sm font-medium text-white">{operationSummary.title}</div>
          <div className="mt-2 text-xs leading-6 text-emerald-100/90">{operationSummary.detail}</div>
          {operationSummary.primaryLabel || operationSummary.secondaryCanvasOptions ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {operationSummary.primaryLabel && operationSummary.primaryTarget && operationSummary.options ? (
                <ActionButton
                  tone="emerald"
                  label={operationSummary.primaryLabel}
                  onClick={() => onNavigate(operationSummary.primaryTarget!, operationSummary.options)}
                />
              ) : null}
              {operationSummary.secondaryCanvasOptions ? (
                <ActionButton
                  tone="slate"
                  label="在创作画布查看"
                  onClick={() => onNavigate('canvas', operationSummary.secondaryCanvasOptions ?? undefined)}
                />
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {selectedTask && primaryActionPlan ? (
        <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <div className="text-sm font-medium text-amber-100">承接后的首个动作</div>
          <div className="mt-2 text-sm text-white">{primaryActionPlan.label}</div>
          <div className="mt-2 text-xs leading-6 text-amber-50/85">{primaryActionPlan.detail}</div>
          <div className="mt-3">
            <ActionButton tone="amber" label="立即继续" onClick={runPrimaryAction} />
          </div>
        </div>
      ) : null}

      {selectedTask ? (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-lg font-semibold text-white">{selectedTask.type}</div>
              <div className="mt-2 text-sm text-slate-400">{selectedTask.target}</div>
            </div>
            <span className={`rounded-full border px-2.5 py-1 text-xs ${statusTone(selectedTask.status)}`}>
              {statusLabel(selectedTask.status)}
            </span>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            <PanelMetricCard title="当前进度" value={selectedTask.progress} detail="让任务状态对创作成员清晰可见" />
            <PanelMetricCard
              title="任务归属"
              value={selectedTask.scope === 'global' ? '批量 / 全局' : selectedTask.episode ? `第 ${selectedTask.episode} 集` : '全局任务'}
              detail={selectedTask.isBatch ? '当前项是统一调度入口' : '按集或全局组织任务'}
            />
            <PanelMetricCard
              title="处理方式"
              value={selectedTask.status === 'skipped' ? '当前跳过' : selectedTask.actionLabel}
              detail="单个任务的问题不应拖住整条生产链路"
            />
          </div>

          {selectedTask.statusReason ? (
            <div className="mt-5 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <div className="text-sm font-medium text-white">当前原因</div>
              <div className="mt-2 text-sm leading-6 text-amber-100/90">{selectedTask.statusReason}</div>
            </div>
          ) : null}

          {selectedTask.promptHealth?.degradedShotCount ? (
            <div className="mt-5 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-medium text-white">提示词恢复建议</div>
                <div className="text-xs text-amber-100/80">
                  跑偏镜头 {selectedTask.promptHealth.degradedShotCount}
                  {selectedTask.promptHealth.recommendedRestoreCount ? ` / 可恢复 ${selectedTask.promptHealth.recommendedRestoreCount}` : ''}
                  {selectedTask.promptHealth.manualRepairCount ? ` / 待人工修复 ${selectedTask.promptHealth.manualRepairCount}` : ''}
                </div>
              </div>
              <div className="mt-3 space-y-2">
                {(selectedTask.promptHealth.degradedShots ?? []).slice(0, 5).map((shot, index) => (
                  <div key={`${shot.episode || 'episode'}-${shot.shotId || index}`} className="rounded-lg border border-amber-500/10 bg-slate-950/40 p-3 text-xs text-slate-200">
                    <div className="font-medium text-white">
                      第 {shot.episode || selectedTask.episode || '-'} 集 / 镜头 {shot.shotId || '未记录'}
                    </div>
                    <div className="mt-1 text-slate-300">
                      建议恢复版本 {shot.recommendedRestoreVersion ?? '未记录'} / 当前版本 {shot.promptVersion ?? '未记录'}
                    </div>
                    {shot.recommendedRestoreReason ? <div className="mt-1 text-slate-400">{shot.recommendedRestoreReason}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {selectedTask.creativeTaskMeta ? (
            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="text-sm font-medium text-white">真实任务链路</div>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3 text-sm text-slate-300">
                {selectedTask.taskId ? <div>任务 ID：{selectedTask.taskId}</div> : null}
                {selectedTask.recoveryKind ? <div>恢复类型：{getStoryboardRecoveryKindLabel(selectedTask.recoveryKind)}</div> : null}
                {selectedTask.creativeTaskMeta.modelProfileId ? <div>模型配置：{selectedTask.creativeTaskMeta.modelProfileId}</div> : null}
                {selectedTask.creativeTaskMeta.provider ? <div>服务商：{selectedTask.creativeTaskMeta.provider}</div> : null}
                {selectedTask.creativeTaskMeta.providerTaskMode ? <div>任务模式：{selectedTask.creativeTaskMeta.providerTaskMode}</div> : null}
                {selectedTask.creativeTaskMeta.generationChain ? (
                  <div>触发链路：{formatRecoveryAwareGenerationChainLabel(selectedTask.creativeTaskMeta.generationChain)}</div>
                ) : null}
                {selectedTask.creativeTaskMeta.taskPromptVersion !== null && selectedTask.creativeTaskMeta.taskPromptVersion !== undefined ? (
                  <div>任务提示词版本：v{selectedTask.creativeTaskMeta.taskPromptVersion}</div>
                ) : null}
                {selectedTask.creativeTaskMeta.currentShotPromptVersion !== null &&
                selectedTask.creativeTaskMeta.currentShotPromptVersion !== undefined ? (
                  <div>镜头当前版本：v{selectedTask.creativeTaskMeta.currentShotPromptVersion}</div>
                ) : null}
                {selectedTask.creativeTaskMeta.promptRecompileTaskId ? (
                  <div>重编任务 ID：{selectedTask.creativeTaskMeta.promptRecompileTaskId}</div>
                ) : null}
                {selectedTask.creativeTaskMeta.promptRecompileVersion !== null &&
                selectedTask.creativeTaskMeta.promptRecompileVersion !== undefined ? (
                  <div>重编版本：v{selectedTask.creativeTaskMeta.promptRecompileVersion}</div>
                ) : null}
                {selectedTask.creativeTaskMeta.promptRecompileReason ? (
                  <div>重编原因：{selectedTask.creativeTaskMeta.promptRecompileReason}</div>
                ) : null}
                {selectedTask.creativeTaskMeta.externalTaskId ? <div>外部任务 ID：{selectedTask.creativeTaskMeta.externalTaskId}</div> : null}
              </div>
              {promptVersionRelationSummary ? (
                <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs leading-5 text-slate-300">
                  {promptVersionRelationSummary}
                </div>
              ) : null}
            </div>
          ) : null}

          {selectedShotRuntimeSummary ? (
            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-medium text-white">当前镜头运行态</div>
                <div className="text-[11px] text-slate-500">
                  第 {selectedTaskEpisode} 集 / 镜头 {selectedTaskShotId}
                </div>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <PanelMetricCard
                  title="最近执行"
                  value={selectedShotRuntimeSummary.latestExecutionLabel || '未记录'}
                  detail={
                    selectedShotRuntimeSummary.latestExecutionAt
                      ? `更新于 ${new Date(selectedShotRuntimeSummary.latestExecutionAt).toLocaleString('zh-CN', { hour12: false })}`
                      : '当前镜头还没有本地执行摘要'
                  }
                />
                <PanelMetricCard
                  title="待回收任务"
                  value={
                    selectedShotRuntimeSummary.pendingSummary.count > 0
                      ? selectedShotRuntimeSummary.pendingSummary.joinedKindLabels
                      : '无'
                  }
                  detail={
                    selectedShotRuntimeSummary.pendingSummary.count > 0
                      ? `共有 ${selectedShotRuntimeSummary.pendingSummary.count} 项待回收任务`
                      : '当前镜头没有待回收任务'
                  }
                />
                <PanelMetricCard
                  title="运行态建议"
                  value={
                    selectedShotRuntimeSummary.pendingTasks.length > 0
                      ? '先回收任务'
                      : selectedShotRuntimeSummary.latestExecutionLabel
                        ? '可继续复核结果'
                        : '可继续发起执行'
                  }
                  detail={
                    selectedShotRuntimeSummary.pendingTasks.length > 0
                      ? '建议先把待回收任务收口，再决定是否重发或进入画布继续处理。'
                      : selectedShotRuntimeSummary.latestExecutionLabel
                        ? '当前镜头已有最近执行记录，可直接回画布或分镜工作台继续检查输出。'
                        : '当前镜头还没有运行态记录，可先回画布发起一次最小动作。'
                  }
                />
              </div>
              {selectedShotRuntimeSummary.pendingSummary.latestUpdatedAt ? (
                <div className="mt-3 text-xs text-slate-400">
                  待回收更新于 {new Date(selectedShotRuntimeSummary.pendingSummary.latestUpdatedAt).toLocaleString('zh-CN', { hour12: false })}
                </div>
              ) : null}
              {selectedShotRuntimeSummary.pendingSummary.latestTaskId &&
              selectedShotRuntimeSummary.pendingSummary.latestSourceLabel ? (
                <div className="mt-2 text-xs text-slate-400">
                  最近待回收来源：{selectedShotRuntimeSummary.pendingSummary.latestSourceLabel} · 任务 ID：{selectedShotRuntimeSummary.pendingSummary.latestTaskId}
                </div>
              ) : null}
              {selectedShotRuntimeSummary.pendingTasks.length > 0 ? (
                <div className="mt-4 space-y-2">
                  {selectedShotRuntimeSummary.pendingTasks.slice(0, 4).map((task) => (
                    <div key={`${task.taskId}-${task.updatedAt}`} className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs text-slate-300">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span>{getStoryboardRecoveryKindLabel(task.kind)} · 任务 ID：{task.taskId}</span>
                        <span className="text-slate-500">
                          {new Date(task.updatedAt).toLocaleString('zh-CN', { hour12: false })}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {selectedTask.creativeTaskMeta?.firstFrameUrl || selectedTask.creativeTaskMeta?.referenceImages?.length ? (
            <div className="mt-5 grid gap-4 xl:grid-cols-2">
              <PreviewCard
                title="首帧预览"
                countLabel={selectedTask.creativeTaskMeta?.firstFrameAssetId || undefined}
                imageUrl={selectedTask.creativeTaskMeta?.firstFrameUrl || undefined}
                imageTitle="首帧预览"
                onOpenPreview={onOpenPreview}
              />
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-xs font-medium text-slate-300">静态参考图预览</div>
                  <div className="text-[11px] text-slate-500">
                    {selectedTask.creativeTaskMeta?.referenceImages?.length ?? 0} / {selectedTask.creativeTaskMeta?.referenceAssetIds?.length ?? 0}
                  </div>
                </div>
                {selectedTask.creativeTaskMeta?.referenceImages?.length ? (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {selectedTask.creativeTaskMeta.referenceImages.slice(0, 4).map((image, index) => (
                      <button
                        key={`${image.referenceAssetId || image.imageUrl || 'reference'}-${index}`}
                        type="button"
                        onClick={() => onOpenPreview(image.imageUrl ?? '', image.title || `参考图 ${index + 1}`)}
                        className="overflow-hidden rounded-lg border border-slate-800 bg-slate-950 text-left transition hover:border-slate-600"
                      >
                        {image.imageUrl ? <img src={image.imageUrl} alt={image.title || `参考图 ${index + 1}`} className="aspect-square w-full object-cover" /> : null}
                        <div className="px-3 py-2">
                          <div className="truncate text-xs text-slate-200">{image.title || `参考图 ${index + 1}`}</div>
                          {image.referenceAssetId ? <div className="mt-1 truncate text-[11px] text-slate-500">{image.referenceAssetId}</div> : null}
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <EmptyHint text="当前任务没有记录可预览的静态参考图" />
                )}
              </div>
            </div>
          ) : null}

          <TaskCenterDetailPanels
            selectedTask={selectedTask}
            selectedTaskActionState={selectedTaskActionState}
            latestSelectedBatchRunRecord={latestSelectedBatchRunRecord}
            selectedBatchRunRecords={selectedBatchRunRecords}
            batchPromptCompileCount={batchPromptCompileCount}
            batchMissingFrameCount={batchMissingFrameCount}
            batchMissingVideoCount={batchMissingVideoCount}
            batchOpenQaEpisodeCount={batchOpenQaEpisodeCount}
            onRunBatchTaskAction={onRunBatchTaskAction}
            onRunRecoveryTaskAction={onRunRecoveryTaskAction}
            onRunQaTaskAction={onRunQaTaskAction}
          />

          <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
            <div className="text-sm font-medium text-white">任务说明</div>
            <div className="mt-3 text-sm leading-6 text-slate-300">{selectedTask.detail}</div>
            <div className="mt-3 text-xs text-slate-500">{buildTaskActionHint(selectedTask)}</div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <ActionButton
              tone="sky"
              label={selectedTask.actionLabel}
              onClick={() =>
                onNavigate(
                  selectedTask.actionTarget,
                  buildNavigateOptions(selectedTask, selectedTaskEpisode, selectedTaskShotId, selectedTaskAssetId, selectedTaskRecoveryIntent),
                )
              }
            />
            {canNavigateToCanvas ? (
              <ActionButton
                tone="slate"
                label="在创作画布查看"
                onClick={() =>
                  onNavigate(
                    'canvas',
                    buildNavigateOptions(selectedTask, selectedTaskEpisode, selectedTaskShotId, selectedTaskAssetId, selectedTaskRecoveryIntent),
                  )
                }
              />
            ) : null}
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-500">
          请先在任务中心选择一个任务。
        </div>
      )}
    </div>
  )
}

function buildNavigateOptions(
  selectedTask: TaskCenterEntry,
  selectedTaskEpisode: number | null,
  selectedTaskShotId: string | null,
  selectedTaskAssetId: string | null,
  selectedTaskRecoveryIntent: WorkspaceTaskRouteOptions['recoveryIntent'],
): WorkspaceTaskRouteOptions {
  return {
    episode: selectedTaskEpisode,
    shotId: selectedTaskShotId,
    assetId: selectedTaskAssetId,
    assetLabel: selectedTask.creativeTaskMeta?.assetSubject || selectedTask.target,
    taskId: selectedTask.taskId ?? null,
    recoveryKind: selectedTask.recoveryKind ?? null,
    recoveryIntent: selectedTaskRecoveryIntent,
  }
}

function buildPromptVersionRelationSummary(task: TaskCenterEntry | null) {
  const meta = task?.creativeTaskMeta
  if (!meta) return null
  const taskPromptVersion = meta.taskPromptVersion
  const recompileVersion = meta.promptRecompileVersion
  const generationChain = meta.generationChain
  if (taskPromptVersion === null || taskPromptVersion === undefined) return null
  if (
    generationChain === 'task_center_regenerate_latest_video' ||
    generationChain === 'task_center_regenerate_latest_frame'
  ) {
    return `本次任务直接使用镜头当前状态发起，实际提交给模型的是当前镜头版本 v${taskPromptVersion}。`
  }
  if (recompileVersion === null || recompileVersion === undefined) {
    return `本次任务实际提交给模型的是 v${taskPromptVersion}。`
  }
  if (taskPromptVersion === recompileVersion) {
    return `本次任务直接沿用了重编产出的 v${taskPromptVersion}。`
  }
  if (taskPromptVersion > recompileVersion) {
    return `本次任务由重编版本 v${recompileVersion} 触发，但真正提交给模型的是后续演进到的 v${taskPromptVersion}。`
  }
  return `本次任务记录的重编版本 v${recompileVersion} 高于任务提交版本 v${taskPromptVersion}，建议回到分镜工作台核对版本链路。`
}

function buildTaskActionHint(task: TaskCenterEntry) {
  if (task.retryable) return '当前任务支持继续恢复或重发，建议先在任务中心确认状态，再决定是否回到业务界面。'
  if (task.status === 'done') return `当前任务已完成，建议进入 ${task.actionLabel} 查看结果并确认是否继续下游。`
  if (task.status === 'blocked') return `当前任务处于阻塞状态，建议先进入 ${task.actionLabel} 查明原因，再决定是否继续推进。`
  if (task.status === 'queued') return `当前任务仍在排队中，建议稍后进入 ${task.actionLabel} 查看最新状态。`
  if (task.status === 'running') return `当前任务正在执行中，建议继续在 ${task.actionLabel} 跟踪结果回收。`
  if (task.status === 'skipped') return `当前任务已被跳过，可进入 ${task.actionLabel} 查看是否需要重新纳入流程。`
  return `当前任务建议先进入 ${task.actionLabel} 查看上下文，再决定下一步。`
}

function statusTone(status: TaskCenterStatus) {
  switch (status) {
    case 'done':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
    case 'running':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-200'
    case 'error':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
    case 'blocked':
      return 'border-slate-600 bg-slate-800 text-slate-300'
    case 'skipped':
      return 'border-violet-500/30 bg-violet-500/10 text-violet-200'
    default:
      return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  }
}

function statusLabel(status: TaskCenterStatus) {
  switch (status) {
    case 'done':
      return '已完成'
    case 'running':
      return '进行中'
    case 'error':
      return '失败'
    case 'blocked':
      return '阻塞'
    case 'skipped':
      return '已跳过'
    default:
      return '待处理'
  }
}

function PanelMetricCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{detail}</div>
    </div>
  )
}

function ActionButton({
  label,
  onClick,
  tone,
}: {
  label: string
  onClick: () => void
  tone: 'amber' | 'emerald' | 'sky' | 'slate'
}) {
  const toneClass =
    tone === 'amber'
      ? 'border-amber-400/60 text-amber-50 hover:border-amber-300 hover:text-white'
      : tone === 'emerald'
        ? 'border-emerald-500/50 text-emerald-100 hover:border-emerald-400 hover:text-white'
        : tone === 'sky'
          ? 'border-sky-500/50 text-sky-200 hover:border-sky-400 hover:text-white'
          : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'

  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${toneClass}`}
    >
      {label}
    </button>
  )
}

function InfoPanel({ tone, title, label, detail }: { tone: 'sky'; title: string; label: string; detail: string }) {
  return (
    <div className="mb-4 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3">
      <div className="text-sm font-medium text-sky-100">{title}</div>
      <div className="mt-2 text-sm text-white">{label}</div>
      <div className="mt-2 text-xs leading-6 text-sky-100/85">{detail}</div>
    </div>
  )
}

function PreviewCard({
  title,
  countLabel,
  imageUrl,
  imageTitle,
  onOpenPreview,
}: {
  title: string
  countLabel?: string
  imageUrl?: string
  imageTitle: string
  onOpenPreview: (url: string, title: string) => void
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-medium text-slate-300">{title}</div>
        {countLabel ? <div className="text-[11px] text-slate-500">{countLabel}</div> : null}
      </div>
      {imageUrl ? (
        <button
          type="button"
          onClick={() => onOpenPreview(imageUrl, imageTitle)}
          className="mt-3 block w-full overflow-hidden rounded-lg border border-slate-800 bg-slate-950 transition hover:border-slate-600"
        >
          <img src={imageUrl} alt={imageTitle} className="aspect-video w-full object-cover" />
        </button>
      ) : (
        <EmptyHint text="当前任务没有记录可预览的图片" />
      )}
    </div>
  )
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="mt-3 rounded-lg border border-dashed border-slate-700 px-3 py-8 text-center text-xs text-slate-500">
      {text}
    </div>
  )
}
